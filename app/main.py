"""FastAPI application: chat API plus the static web UI.

Security model for this single-analyst tool:
- Bind to loopback (the documented default). Requests from any non-loopback client are refused
  unless APP_TOKEN is configured, so the API cannot be exposed unauthenticated by accident.
- When APP_TOKEN is set (shell environment only, never a file), every /api/* request must carry
  ``Authorization: Bearer <token>``; the comparison is constant-time.
- Security headers and a strict same-origin Content-Security-Policy on every response; no CORS.
- All query and body inputs are validated; tool errors map to 4xx with fixed messages and
  internal exception text stays in the server log.
"""
from __future__ import annotations

import hmac
import ipaddress
import logging
import re
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.agent import tools as T
from app.agent.orchestrator import Orchestrator, to_json
from app.agent.schemas import ChatRequest, ChatResponse, HealthResponse
from app.agent.session import SessionStore
from app.config import settings
from app.engine import Engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

ENGINE_RETRY_SECONDS = 30
STATE_CODE_RE = re.compile(r"^[A-Za-z]{2}$")
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
DOCS_PATHS = ("/api/docs", "/api/openapi.json")

_state: Dict[str, Any] = {"orchestrator": None, "failed_at": 0.0}
_lock = threading.Lock()


def get_orchestrator() -> Orchestrator:
    orch = _state["orchestrator"]
    if orch is not None:  # fast path, no lock once loaded
        return orch
    with _lock:
        if _state["orchestrator"] is not None:
            return _state["orchestrator"]
        if time.time() - _state["failed_at"] < ENGINE_RETRY_SECONDS:
            raise HTTPException(status_code=503, detail="Data engine is not ready; retry shortly.")
        try:
            engine = Engine.load()
            engine.metrics_table()
        except Exception:  # noqa: BLE001 - details go to the log, not the client
            _state["failed_at"] = time.time()
            log.exception("data engine failed to load")
            raise HTTPException(status_code=503, detail="Data engine failed to load; see the server log.")
        _state["orchestrator"] = Orchestrator(engine, SessionStore())
        log.info("engine ready: %s universe airports", len(engine.metrics_table()))
        return _state["orchestrator"]


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    if settings.app_token:
        log.info("API token authentication enabled")
    else:
        log.info("no APP_TOKEN set: API accepts loopback clients only")
    try:
        get_orchestrator()
    except HTTPException:
        log.error("engine not ready at startup; will retry on request")
    yield


app = FastAPI(title="Airport Investment Intelligence Agent", version="0.1.0", docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json", lifespan=_lifespan)


def _client_is_local(request: Request) -> bool:
    """True for loopback clients and for transports without an IP (unix sockets, test clients)."""
    host = request.client.host if request.client else None
    if not host:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return True


def _token_ok(request: Request) -> bool:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[7:].strip(), settings.app_token)


@app.middleware("http")
async def security_middleware(request: Request, call_next) -> Response:
    path = request.url.path
    if path.startswith("/api/"):
        if settings.app_token:
            if not _token_ok(request):
                return JSONResponse({"detail": "authentication required"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
        elif not _client_is_local(request):
            log.warning("refused non-loopback client %s: APP_TOKEN is not configured", request.client.host if request.client else "?")
            return JSONResponse({"detail": "remote access requires APP_TOKEN"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), payment=()"
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if not path.startswith(DOCS_PATHS):  # the OpenAPI UI loads its own assets
        response.headers["Content-Security-Policy"] = CSP
    return response


def _sanitized(payload: Dict[str, Any]) -> Any:
    """Same NaN/numpy-safe serialization the chat path uses, so panel and chat never diverge."""
    import json
    return json.loads(to_json(payload))


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    orch = get_orchestrator()
    return HealthResponse(status="ready", provider=orch.provider_for(None), model=settings.llm_model,
                          sources=_sanitized(orch.engine.source_status), universe_size=int(len(orch.engine.metrics_table())))


@app.get("/api/methodology")
def methodology() -> Any:
    orch = get_orchestrator()
    return _sanitized({topic: T.dispatch(orch.engine, "explain_methodology", {"topic": topic})["data"] for topic in T.TOPICS})


@app.get("/api/tools")
def tools_spec() -> Dict[str, Any]:
    return {"tools": T.TOOL_SPECS}


@app.get("/api/regions")
def regions() -> Dict[str, Any]:
    """Region names (aliases with identical state sets collapsed) and state codes for the panel."""
    orch = get_orchestrator()
    reg = orch.engine.registry.regions
    seen: Dict[frozenset, str] = {}
    for name, states in reg["regions"].items():
        seen.setdefault(frozenset(states), name)
    return {"regions": sorted(seen.values()), "states": reg["states"]}


@app.get("/api/rank")
def rank(
    region: Optional[str] = Query(default=None, max_length=40, description="Named region, e.g. 'new england'"),
    states: Optional[str] = Query(default=None, max_length=200, description="Comma-separated two-letter state codes"),
    min_enplanements: int = Query(default=100_000, ge=0, le=100_000_000),
    limit: int = Query(default=10, ge=1, le=25),
) -> Any:
    """Same deterministic Expansion Opportunity ranking the chat uses (rank_airports tool), for the side panel."""
    orch = get_orchestrator()
    args: Dict[str, Any] = {"min_enplanements": min_enplanements, "limit": limit}
    if region:
        args["region"] = region.strip().lower()
    if states:
        known = orch.engine.registry.regions["states"]
        codes: List[str] = [c.strip().upper() for c in states.split(",") if c.strip()]
        if not codes or len(codes) > 20 or any(not STATE_CODE_RE.match(c) or c not in known for c in codes):
            raise HTTPException(status_code=422, detail="states must be up to 20 comma-separated known two-letter state codes")
        args["states"] = codes
    result = T.dispatch(orch.engine, "rank_airports", args, None)
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    return _sanitized({"data": result["data"], "sources": result["sources"], "caveats": result["caveats"], "confidence": result["confidence"]})


@app.get("/api/live")
def live() -> Any:
    """Nationwide live FAA NAS status (ground delays, ground stops, closures), never used in scores."""
    orch = get_orchestrator()
    result = T.dispatch(orch.engine, "live_airport_status", {}, None)
    data = dict(result["data"])
    if data.get("error"):
        log.warning("live FAA status unavailable: %s", data["error"])
        data["error"] = "FAA live status feed is unavailable right now"
    return _sanitized({"data": data, "sources": result["sources"], "caveats": result["caveats"]})


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    orch = get_orchestrator()
    return orch.chat(request.message, request.session_id, request.provider)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(settings.web_dir / "index.html")


app.mount("/static", StaticFiles(directory=str(settings.web_dir)), name="static")
