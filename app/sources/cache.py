"""Small disk cache for public data downloads.

Every fetch records where the bytes came from and when, so downstream tool results
can cite the retrieval time and say whether the data is live or from cache.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import httpx

from app.config import settings

USER_AGENT = "airport-investment-agent/0.1 (+public data research tool)"


class SourceUnavailable(RuntimeError):
    """Raised when a source can be fetched neither live nor from cache."""


@dataclass
class Fetched:
    content: bytes
    url: str
    retrieved_at: str
    from_cache: bool
    stale: bool = False

    @property
    def meta(self) -> Dict[str, object]:
        return {
            "url": self.url,
            "retrieved_at": self.retrieved_at,
            "from_cache": self.from_cache,
            "stale": self.stale,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _paths(name: str) -> "tuple[Path, Path]":
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    return settings.cache_dir / name, settings.cache_dir / (name + ".meta.json")


def _read_meta(meta_path: Path) -> Dict[str, object]:
    try:
        return json.loads(meta_path.read_text())
    except (OSError, ValueError):
        return {}


def fetch_bytes(
    url: str,
    cache_name: str,
    ttl_seconds: float,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    prime_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Fetched:
    """Return bytes for ``url``, using the disk cache when fresh.

    Falls back to a stale cached copy if the network call fails. ``prime_url`` is an
    optional page to GET first (some ASP sites require a session cookie/referer).
    """
    path, meta_path = _paths(cache_name)
    meta = _read_meta(meta_path)
    if path.exists() and meta.get("retrieved_at"):
        age = time.time() - path.stat().st_mtime
        if age < ttl_seconds or settings.offline:
            return Fetched(path.read_bytes(), str(meta.get("url", url)), str(meta["retrieved_at"]), True, stale=age >= ttl_seconds)
    if settings.offline:
        raise SourceUnavailable(f"OFFLINE=1 and no cached copy of {cache_name}")

    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    try:
        with httpx.Client(headers=request_headers, timeout=timeout or settings.http_timeout, follow_redirects=True) as client:
            if prime_url:
                client.get(prime_url)
            response = client.get(url, params=params)
            response.raise_for_status()
            content = response.content
            final_url = str(response.url)
    except (httpx.HTTPError, OSError) as exc:
        if path.exists():
            return Fetched(path.read_bytes(), str(meta.get("url", url)), str(meta.get("retrieved_at", "unknown")), True, stale=True)
        raise SourceUnavailable(f"Could not fetch {url}: {exc}") from exc

    retrieved_at = _now_iso()
    path.write_bytes(content)
    meta_path.write_text(json.dumps({"url": final_url, "retrieved_at": retrieved_at, "size": len(content)}))
    return Fetched(content, final_url, retrieved_at, False)


def cached_file(cache_name: str) -> Optional[Path]:
    path, _ = _paths(cache_name)
    return path if path.exists() else None
