"""LLM adapter for the Anthropic API (official SDK) with native tool use.

Used when ANTHROPIC_API_KEY is configured (loaded from the environment / .env, never from
code). Thinking is left at the model's default (adaptive on current models) and tool choice
is always ``auto``, which is what Claude Fable 5.1 requires.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import anthropic

from app.agent.llm_claude_cli import AssistantTurn, LLMError
from app.config import settings

MAX_TOKENS = 4096


def _to_api_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    api: List[Dict[str, Any]] = []
    for m in messages:
        if m["role"] == "assistant" and m.get("_raw") is not None:
            api.append({"role": "assistant", "content": m["_raw"]})
            continue
        content = m["content"]
        if isinstance(content, list):
            blocks = []
            for b in content:
                if b.get("type") == "tool_result":
                    block = {"type": "tool_result", "tool_use_id": b["tool_use_id"], "content": b["content"]}
                    if b.get("is_error"):
                        block["is_error"] = True
                    blocks.append(block)
                elif b.get("type") == "tool_use":
                    blocks.append({"type": "tool_use", "id": b["id"], "name": b["name"], "input": b["input"]})
                elif b.get("type") == "text":
                    blocks.append({"type": "text", "text": b["text"]})
            api.append({"role": m["role"], "content": blocks})
        else:
            api.append({"role": m["role"], "content": content})
    return api


class AnthropicClient:
    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None, timeout: Optional[float] = None) -> None:
        key = api_key or settings.anthropic_api_key or None
        self.client = anthropic.Anthropic(api_key=key, timeout=timeout or settings.llm_timeout_seconds, max_retries=2)
        self.model = model or settings.llm_model

    def complete(self, system: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], session_context: Optional[str] = None) -> AssistantTurn:
        system_text = system if not session_context else system + "\n\nConversation state:\n" + session_context
        try:
            response = self.client.messages.create(
                model=self.model, max_tokens=MAX_TOKENS, system=system_text, tools=tools, messages=_to_api_messages(messages),
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic API key was rejected") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Anthropic API rate limit reached") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Anthropic API connection error: {exc}") from exc
        if response.stop_reason == "refusal":
            raise LLMError("The model declined to answer this request")
        text = "".join(b.text for b in response.content if b.type == "text").strip() or None
        calls = [{"id": b.id, "name": b.name, "arguments": dict(b.input)} for b in response.content if b.type == "tool_use"]
        usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens, "stop_reason": response.stop_reason}
        turn = AssistantTurn(text if not calls else text, calls, usage)
        turn.raw_content = response.content  # type: ignore[attr-defined]  # preserved for replay (keeps thinking blocks intact)
        return turn
