"""Runtime configuration loaded from environment variables and an optional .env file.

Secrets (such as ANTHROPIC_API_KEY) are never stored in code; they come from the
environment or a local, git-ignored .env file.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Plain settings object (no pydantic, so importing it is cheap and 3.9-safe)."""

    def __init__(self) -> None:
        self.root: Path = ROOT
        cache = os.getenv("CACHE_DIR", ".cache")
        self.cache_dir: Path = (ROOT / cache) if not os.path.isabs(cache) else Path(cache)
        self.snapshot_dir: Path = ROOT / "data" / "snapshots"
        self.reference_dir: Path = ROOT / "app" / "reference"
        self.web_dir: Path = ROOT / "app" / "web"

        self.llm_provider: str = os.getenv("LLM_PROVIDER", "auto").strip().lower()
        self.llm_model: str = os.getenv("LLM_MODEL", "claude-fable-5-1").strip()
        self.anthropic_api_key: str = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        self.claude_cli: str = os.getenv("CLAUDE_CLI", "claude").strip()
        self.llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT", "180"))

        self.host: str = os.getenv("HOST", "127.0.0.1")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.offline: bool = _bool("OFFLINE", False)
        self.http_timeout: float = float(os.getenv("HTTP_TIMEOUT", "90"))

    def resolve_llm_provider(self) -> str:
        """Pick the concrete provider for LLM_PROVIDER=auto."""
        if self.llm_provider != "auto":
            return self.llm_provider
        if self.anthropic_api_key:
            return "anthropic"
        if shutil.which(self.claude_cli):
            return "claude_cli"
        return "rules"


settings = Settings()
