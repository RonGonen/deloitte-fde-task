"""Turn orchestration: session memory -> LLM tool loop (or rules router) -> grounded answer."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set

from app.agent import rules_router
from app.agent import tools as T
from app.agent.llm_claude_cli import AssistantTurn, ClaudeCliClient, LLMError
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.schemas import ChatResponse
from app.agent.session import Session, SessionStore
from app.config import settings
from app.engine import Engine

log = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 4
NUMBER_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?:\s?([MKBmkb])(?![\w]))?(?![\w])")
SUFFIX_MULTIPLIER = {"k": 1_000.0, "m": 1_000_000.0, "b": 1_000_000_000.0}


def _json_default(value: Any) -> Any:
    try:
        import numpy as np  # noqa: WPS433
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return None if np.isnan(value) else float(value)
        if isinstance(value, (np.bool_,)):
            return bool(value)
    except ImportError:  # pragma: no cover
        pass
    return str(value)


def to_json(value: Any) -> str:
    return json.dumps(value, default=_json_default, ensure_ascii=False)


def _numbers_in(value: Any, out: Set[float]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if value == value:  # not NaN
            out.add(float(value))
        return
    if isinstance(value, dict):
        for v in value.values():
            _numbers_in(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _numbers_in(v, out)
    elif isinstance(value, str):
        for m in NUMBER_RE.finditer(value):
            try:
                out.add(float(m.group(0).replace(",", "")))
            except ValueError:
                pass


def _grounded(candidate: float, decimals: int, pool: Set[float], relative: bool) -> bool:
    """Match within the candidate's own rounding precision; large/abbreviated numbers also get 0.5% slack."""
    tolerance_abs = 0.5 * 10 ** (-decimals)
    for v in pool:
        for scaled in (v, v * 100.0, v / 100.0, (v - 1.0) * 100.0):
            tolerance = max(tolerance_abs, 0.005 * abs(scaled)) if relative else tolerance_abs
            if abs(scaled - candidate) <= tolerance:
                return True
    return False


def ground_check(text: str, tool_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Report which numbers in the answer cannot be traced to any tool result.

    Tolerant on purpose: a text number is grounded if some tool value (or its x100 / /100
    percent-fraction twin) matches it within its own rounding precision or 0.5%. Numbers in
    source metadata and caveats (years, periods) count as grounded. Suffixes like 36.5M are
    expanded. Small integers (<= 10) are ignored because they are usually list numbering.
    """
    pool: Set[float] = set()
    for r in tool_results:
        _numbers_in(r.get("data"), pool)
        _numbers_in(r.get("arguments"), pool)
        _numbers_in(r.get("sources"), pool)
        _numbers_in(r.get("caveats"), pool)
    candidates: List[Any] = []
    for m in NUMBER_RE.finditer(text):
        raw = m.group(0).strip()
        try:
            value = float((m.group(1) + (m.group(2) or "")).replace(",", ""))
        except ValueError:
            continue
        suffix = (m.group(3) or "").lower()
        if suffix:
            value *= SUFFIX_MULTIPLIER[suffix]
        elif value <= 10:
            continue
        decimals = 0 if suffix else (len(m.group(2)) - 1 if m.group(2) else 0)
        candidates.append((raw, value, decimals, bool(suffix) or value >= 1000))
    ungrounded = [raw for raw, value, decimals, relative in candidates if not _grounded(value, decimals, pool, relative)]
    return {"checked": len(candidates), "ungrounded": sorted(set(ungrounded))}


class Orchestrator:
    def __init__(self, engine: Engine, sessions: Optional[SessionStore] = None, llm_factory=None) -> None:
        self.engine = engine
        self.sessions = sessions or SessionStore()
        self._llm_factory = llm_factory  # for tests: callable(provider) -> client with .complete()

    # ----------------------------------------------------------------- helpers
    def provider_for(self, override: Optional[str]) -> str:
        provider = override or settings.resolve_llm_provider()
        if provider == "anthropic" and not settings.anthropic_api_key and not self._llm_factory:
            return "rules"
        if provider == "claude_cli" and not ClaudeCliClient.available() and not self._llm_factory:
            return "rules"
        return provider

    def _client(self, provider: str):
        if self._llm_factory:
            return self._llm_factory(provider)
        if provider == "anthropic":
            from app.agent.llm_anthropic import AnthropicClient
            return AnthropicClient()
        return ClaudeCliClient()

    @staticmethod
    def _session_context(session: Session) -> Optional[str]:
        if not session.last_result:
            return None
        last = session.last_result
        return (f"Previous tool: {last['tool']} with arguments {to_json(last['arguments'])}; airports in that result (in order): "
                f"{', '.join(last['airports']) or 'none'}; states: {', '.join(last.get('states') or []) or 'none'}. Ordinal references ('the second one') point into that list.")

    # -------------------------------------------------------------------- chat
    def chat(self, message: str, session_id: Optional[str] = None, provider_override: Optional[str] = None) -> ChatResponse:
        started = time.time()
        session = self.sessions.get_or_create(session_id)
        provider = self.provider_for(provider_override)
        warnings: List[str] = []
        if provider == "rules":
            payload = self._rules(session, message)
            mode = "rules"
            model = None
        else:
            try:
                payload = self._llm(session, message, provider)
                mode = "llm"
                model = settings.llm_model
            except LLMError as exc:
                log.warning("LLM path failed (%s); falling back to rules", exc)
                warnings.append(f"LLM unavailable ({exc}); answered with the rules-based interpreter.")
                payload = self._rules(session, message)
                mode = "rules"
                model = None
        session.add_turn("user", message)
        session.add_turn("assistant", payload["text"])
        tool_results = payload["tool_results"]
        sources = _dedupe_sources(tool_results)
        caveats = _dedupe([c for r in tool_results for c in r.get("caveats", [])])
        grounding = ground_check(payload["text"], tool_results) if tool_results else {"checked": 0, "ungrounded": []}
        if mode == "llm" and grounding["ungrounded"]:
            warnings.append("Numbers not traceable to a data source: " + ", ".join(grounding["ungrounded"][:8]))
        return ChatResponse(session_id=session.id, text=payload["text"], mode=mode, provider=provider, model=model,
                            tool_results=json.loads(to_json(tool_results)), sources=sources, caveats=caveats,
                            latency_ms=int((time.time() - started) * 1000), warnings=warnings + payload.get("warnings", []))

    def _rules(self, session: Session, message: str) -> Dict[str, Any]:
        return rules_router.answer(self.engine, session, message)

    def _llm(self, session: Session, message: str, provider: str) -> Dict[str, Any]:
        client = self._client(provider)
        messages: List[Dict[str, Any]] = [dict(m) for m in session.messages] + [{"role": "user", "content": message}]
        context = self._session_context(session)
        all_results: List[Dict[str, Any]] = []
        warnings: List[str] = []
        for round_no in range(MAX_TOOL_ROUNDS):
            turn: AssistantTurn = client.complete(SYSTEM_PROMPT, messages, T.TOOL_SPECS, context)
            if not turn.tool_calls:
                text = (turn.text or "").strip()
                if not text:
                    raise LLMError("empty answer from the model")
                return {"text": text, "tool_results": all_results, "warnings": warnings}
            assistant_blocks: List[Dict[str, Any]] = []
            if turn.text:
                assistant_blocks.append({"type": "text", "text": turn.text})
            result_blocks: List[Dict[str, Any]] = []
            for i, call in enumerate(turn.tool_calls):
                call_id = call.get("id") or f"call_{round_no}_{i}"
                name, arguments = call.get("name"), call.get("arguments") or {}
                assistant_blocks.append({"type": "tool_use", "id": call_id, "name": name, "input": arguments})
                result = T.dispatch(self.engine, name, arguments, session) if name in T.HANDLERS else \
                    {"tool": name, "arguments": arguments, "error": f"unknown tool {name}", "data": {}, "sources": [], "caveats": [], "confidence": {"level": "low"}, "method": ""}
                all_results.append(result)
                block = {"type": "tool_result", "tool_use_id": call_id, "name": name, "content": to_json(_compact_for_model(result))}
                if result.get("error"):
                    block["is_error"] = True
                result_blocks.append(block)
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": assistant_blocks}
            raw = getattr(turn, "raw_content", None)
            if raw is not None:
                assistant_msg["_raw"] = raw
            messages.append(assistant_msg)
            messages.append({"role": "user", "content": result_blocks})
        # Out of rounds: ask the rules narrator to summarize whatever was gathered.
        warnings.append("The model used all tool rounds without a final answer; showing the deterministic summary of the last result.")
        if all_results:
            last = all_results[-1]
            narrated = rules_router.answer(self.engine, session, message)["text"] if not last.get("error") else f"Tool error: {last['error']}"
            return {"text": narrated, "tool_results": all_results, "warnings": warnings}
        raise LLMError("no answer and no tool results after the maximum number of rounds")


def _compact_for_model(result: Dict[str, Any]) -> Dict[str, Any]:
    """Trim bulky fields before sending a tool result to the model (UI still gets the full payload)."""
    slim = dict(result)
    data = slim.get("data")
    if isinstance(data, dict):
        data = dict(data)
        if "taf_history" in data and isinstance(data["taf_history"], list):
            data["taf_history"] = [h for h in data["taf_history"] if h["year"] >= 2019]
        slim["data"] = data
    slim.pop("method", None)
    return slim


def _dedupe(items: List[str]) -> List[str]:
    seen: Set[str] = set()
    out = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _dedupe_sources(tool_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    out = []
    for r in tool_results:
        for s in r.get("sources", []):
            key = str(s.get("name"))
            if key not in seen:
                seen.add(key)
                out.append(s)
    return out
