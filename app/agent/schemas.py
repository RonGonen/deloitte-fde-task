"""Request/response models for the chat API (validated at the system boundary)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
MAX_MESSAGE_CHARS = 2000


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    session_id: Optional[str] = None
    provider: Optional[str] = Field(default=None, description="Override: rules | claude_cli | anthropic")

    @field_validator("message")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.replace("\x00", "").strip()
        if not value:
            raise ValueError("message must not be blank")
        return value

    @field_validator("session_id")
    @classmethod
    def _uuid(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        if not UUID_RE.match(value):
            raise ValueError("session_id must be a UUID")
        return value.lower()

    @field_validator("provider")
    @classmethod
    def _provider(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        if value not in {"rules", "claude_cli", "anthropic"}:
            raise ValueError("provider must be one of rules, claude_cli, anthropic")
        return value


class ChatResponse(BaseModel):
    session_id: str
    text: str
    mode: str
    provider: str
    model: Optional[str] = None
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)
    latency_ms: int = 0
    warnings: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    provider: str
    model: str
    sources: Dict[str, Any]
    universe_size: int
