"""Small disk cache for public data downloads.

Every fetch records where the bytes came from and when, so downstream tool results
can cite the retrieval time and say whether the data is live or from cache.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import httpx

from app.config import settings

USER_AGENT = "airport-investment-agent/0.1 (+public data research tool)"


FAILURE_BACKOFF_SECONDS = 60.0
_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_last_failure: Dict[str, float] = {}


class SourceUnavailable(RuntimeError):
    """Raised when a source can be fetched neither live nor from cache."""


def _lock_for(name: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(name, threading.Lock())


def _atomic_write(path: Path, content: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(content)
    os.replace(tmp, path)


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

    One fetch per source at a time (per-name lock), atomic cache writes, and a short back-off after
    a failed download so concurrent callers (panel polling, chat tools) do not pile onto a source
    that is down. Falls back to a stale cached copy if the network call fails.
    """
    path, meta_path = _paths(cache_name)
    with _lock_for(cache_name):
        meta = _read_meta(meta_path)
        if path.exists() and meta.get("retrieved_at"):
            age = time.time() - path.stat().st_mtime
            recently_failed = time.time() - _last_failure.get(cache_name, 0.0) < FAILURE_BACKOFF_SECONDS
            if age < ttl_seconds or settings.offline or recently_failed:
                return Fetched(path.read_bytes(), str(meta.get("url", url)), str(meta["retrieved_at"]), True, stale=age >= ttl_seconds)
        if settings.offline:
            raise SourceUnavailable(f"OFFLINE=1 and no cached copy of {cache_name}")
        if time.time() - _last_failure.get(cache_name, 0.0) < FAILURE_BACKOFF_SECONDS:
            raise SourceUnavailable(f"{cache_name} failed recently; backing off before retrying")

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
            _last_failure[cache_name] = time.time()
            if path.exists():
                return Fetched(path.read_bytes(), str(meta.get("url", url)), str(meta.get("retrieved_at", "unknown")), True, stale=True)
            raise SourceUnavailable(f"Could not fetch {url}: {exc}") from exc

        _last_failure.pop(cache_name, None)
        retrieved_at = _now_iso()
        _atomic_write(path, content)
        _atomic_write(meta_path, json.dumps({"url": final_url, "retrieved_at": retrieved_at, "size": len(content)}).encode())
        return Fetched(content, final_url, retrieved_at, False)


def cached_file(cache_name: str) -> Optional[Path]:
    path, _ = _paths(cache_name)
    return path if path.exists() else None
