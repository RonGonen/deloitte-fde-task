"""LLM adapter that drives the locally installed Claude Code CLI in headless mode.

This lets the app use the Claude account the machine is already logged into (no API key
file). Each round is one ``claude -p`` invocation with structured JSON output. The CLI's
own tools are disabled (``--tools ""``); our deterministic tools are described in the
prompt and executed by the orchestrator. Subprocess arguments are passed as a list (no
shell), and the nested-session guard variables are stripped from the environment.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import settings

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "arguments_json": {"type": "string", "description": "JSON object of arguments"}},
                "required": ["name", "arguments_json"],
                "additionalProperties": False,
            },
        },
        "final_answer": {"type": ["string", "null"], "description": "Markdown answer for the analyst, or null if tool calls are needed first"},
    },
    "required": ["tool_calls", "final_answer"],
    "additionalProperties": False,
}


class LLMError(RuntimeError):
    pass


@dataclass
class AssistantTurn:
    text: Optional[str]
    tool_calls: List[Dict[str, Any]]
    usage: Dict[str, Any] = field(default_factory=dict)


def _tool_block(tools: List[Dict[str, Any]]) -> str:
    lines = ["Available tools (call by name with a JSON object of arguments):"]
    for t in tools:
        lines.append(f"- {t['name']}: {t['description']}\n  arguments schema: {json.dumps(t['input_schema'], separators=(',', ':'))}")
    return "\n".join(lines)


def build_prompt(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], session_context: Optional[str] = None) -> str:
    """Render the conversation (including prior tool calls/results) as one text prompt."""
    parts = [_tool_block(tools)]
    if session_context:
        parts.append("Conversation state:\n" + session_context)
    parts.append("Transcript:")
    for m in messages:
        role = m["role"]
        content = m["content"]
        if isinstance(content, str):
            parts.append(f"[{role}] {content}")
            continue
        for block in content:
            kind = block.get("type")
            if kind == "text":
                parts.append(f"[{role}] {block['text']}")
            elif kind == "tool_use":
                parts.append(f"[assistant -> tool call] {block['name']} {json.dumps(block['input'], separators=(',', ':'))}")
            elif kind == "tool_result":
                parts.append(f"[tool result for {block.get('name', block.get('tool_use_id'))}] {block['content']}")
    parts.append(
        "Decide the next step. If you still need data, return tool_calls (one or more, independent calls together) and final_answer=null. "
        "If you have everything needed, return tool_calls=[] and the complete markdown final_answer following the system prompt's format."
    )
    return "\n\n".join(parts)


class ClaudeCliClient:
    def __init__(self, cli: Optional[str] = None, model: Optional[str] = None, timeout: Optional[float] = None) -> None:
        self.cli = cli or settings.claude_cli
        self.model = model or settings.llm_model
        self.timeout = timeout or settings.llm_timeout_seconds

    @staticmethod
    def available(cli: Optional[str] = None) -> bool:
        return shutil.which(cli or settings.claude_cli) is not None

    def complete(self, system: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], session_context: Optional[str] = None) -> AssistantTurn:
        prompt = build_prompt(messages, tools, session_context)
        cmd = [
            self.cli, "-p", prompt,
            "--output-format", "json",
            "--json-schema", json.dumps(OUTPUT_SCHEMA),
            "--system-prompt", system,
            "--model", self.model,
            "--tools", "",
            "--no-session-persistence",
        ]
        env = {k: v for k, v in os.environ.items() if k not in {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"}}
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, env=env, cwd=str(settings.root))
        except subprocess.TimeoutExpired as exc:
            raise LLMError(f"claude CLI timed out after {self.timeout:.0f}s") from exc
        except OSError as exc:
            raise LLMError(f"could not run claude CLI: {exc}") from exc
        if proc.returncode != 0:
            raise LLMError(f"claude CLI exited {proc.returncode}: {(proc.stderr or proc.stdout)[:400]}")
        try:
            payload = json.loads(proc.stdout)
        except ValueError as exc:
            raise LLMError(f"claude CLI returned non-JSON output: {proc.stdout[:200]}") from exc
        if payload.get("is_error"):
            raise LLMError(f"claude CLI error: {str(payload.get('result'))[:400]}")
        structured = payload.get("structured_output")
        if structured is None:
            try:
                structured = json.loads(payload.get("result") or "")
            except ValueError as exc:
                raise LLMError("claude CLI response did not contain structured output") from exc
        calls = []
        for call in structured.get("tool_calls") or []:
            try:
                arguments = json.loads(call.get("arguments_json") or "{}")
            except ValueError:
                arguments = {}
            calls.append({"name": call.get("name"), "arguments": arguments if isinstance(arguments, dict) else {}})
        usage = {"cost_usd": payload.get("total_cost_usd"), "duration_ms": payload.get("duration_ms"),
                 "model_usage": list((payload.get("modelUsage") or {}).keys())}
        return AssistantTurn(structured.get("final_answer"), calls, usage)
