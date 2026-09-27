"""In-memory conversation sessions (single-user local tool; nothing is persisted)."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SESSION_TTL_SECONDS = 60 * 60
MAX_TURNS_KEPT = 12


@dataclass
class Session:
    id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: List[Dict[str, str]] = field(default_factory=list)   # {"role": "user"|"assistant", "content": str}
    last_result: Optional[Dict[str, Any]] = None                    # {"tool", "arguments", "airports", "states"}
    active_airports: List[str] = field(default_factory=list)
    active_states: List[str] = field(default_factory=list)

    def add_turn(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > MAX_TURNS_KEPT * 2:
            self.messages = self.messages[-MAX_TURNS_KEPT * 2 :]
        self.updated_at = time.time()

    def remember(self, tool: str, arguments: Dict[str, Any], airports: List[str], states: Optional[List[str]] = None) -> None:
        self.last_result = {"tool": tool, "arguments": dict(arguments), "airports": list(airports), "states": list(states or [])}
        if airports:
            self.active_airports = list(airports)
        if states:
            self.active_states = list(states)
        self.updated_at = time.time()


class SessionStore:
    def __init__(self, ttl_seconds: float = SESSION_TTL_SECONDS) -> None:
        self._sessions: Dict[str, Session] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def get_or_create(self, session_id: Optional[str]) -> Session:
        with self._lock:
            self._purge()
            if session_id and session_id in self._sessions:
                return self._sessions[session_id]
            sid = session_id or str(uuid.uuid4())
            session = Session(id=sid)
            self._sessions[sid] = session
            return session

    def _purge(self) -> None:
        cutoff = time.time() - self._ttl
        for sid in [s for s, sess in self._sessions.items() if sess.updated_at < cutoff]:
            del self._sessions[sid]

    def __len__(self) -> int:
        return len(self._sessions)
