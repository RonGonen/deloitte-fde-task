"""FastAPI application: chat API plus the static web UI. Binds to loopback by default."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.agent import tools as T
from app.agent.orchestrator import Orchestrator
from app.agent.schemas import ChatRequest, ChatResponse, HealthResponse
from app.agent.session import SessionStore
from app.config import settings
from app.engine import Engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

_state: Dict[str, Any] = {"engine": None, "orchestrator": None, "error": None}
_lock = threading.Lock()


def get_orchestrator() -> Orchestrator:
    with _lock:
        if _state["orchestrator"] is None:
            try:
                engine = Engine.load()
                engine.metrics_table()
            except Exception as exc:  # noqa: BLE001
                _state["error"] = str(exc)
                log.exception("engine failed to load")
                raise HTTPException(status_code=503, detail=f"Data engine failed to load: {exc}")
            _state["engine"] = engine
            _state["orchestrator"] = Orchestrator(engine, SessionStore())
            log.info("engine ready: %s universe airports", len(engine.metrics_table()))
        return _state["orchestrator"]


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        get_orchestrator()
    except HTTPException:
        log.error("engine not ready at startup; will retry on first request")
    yield


app = FastAPI(title="Airport Investment Intelligence Agent", version="0.1.0", docs_url="/api/docs", redoc_url=None, lifespan=_lifespan)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    orch = get_orchestrator()
    return HealthResponse(status="ready", provider=orch.provider_for(None), model=settings.llm_model,
                          sources=orch.engine.source_status, universe_size=int(len(orch.engine.metrics_table())))


@app.get("/api/methodology")
def methodology() -> Dict[str, Any]:
    orch = get_orchestrator()
    return {topic: T.dispatch(orch.engine, "explain_methodology", {"topic": topic})["data"] for topic in T.TOPICS}


@app.get("/api/tools")
def tools_spec() -> Dict[str, Any]:
    return {"tools": T.TOOL_SPECS}


STATE_CODE_RE = re.compile(r"^[A-Za-z]{2}$")


@app.get("/api/regions")
def regions() -> Dict[str, Any]:
    """Region names and state codes available for the ranking panel."""
    orch = get_orchestrator()
    reg = orch.engine.registry.regions
    return {"regions": sorted(reg["regions"].keys()), "states": reg["states"]}


@app.get("/api/rank")
def rank(
    region: Optional[str] = Query(default=None, max_length=40, description="Named region, e.g. 'new england'"),
    states: Optional[str] = Query(default=None, max_length=200, description="Comma-separated two-letter state codes"),
    min_enplanements: int = Query(default=100_000, ge=0, le=100_000_000),
    limit: int = Query(default=10, ge=1, le=25),
) -> Dict[str, Any]:
    """Same deterministic Expansion Opportunity ranking the chat uses (rank_airports tool), for the side panel."""
    orch = get_orchestrator()
    args: Dict[str, Any] = {"min_enplanements": min_enplanements, "limit": limit}
    if region:
        if region.lower().strip() not in orch.engine.registry.regions["regions"]:
            raise HTTPException(status_code=422, detail="unknown region")
        args["region"] = region.lower().strip()
    if states:
        codes: List[str] = [c.strip().upper() for c in states.split(",") if c.strip()]
        if not codes or any(not STATE_CODE_RE.match(c) for c in codes) or len(codes) > 20:
            raise HTTPException(status_code=422, detail="states must be up to 20 comma-separated two-letter codes")
        args["states"] = codes
    result = T.dispatch(orch.engine, "rank_airports", args, None)
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    return {"data": result["data"], "sources": result["sources"], "caveats": result["caveats"], "confidence": result["confidence"]}


@app.get("/api/live")
def live() -> Dict[str, Any]:
    """Nationwide live FAA NAS status (ground delays, ground stops, closures), never used in scores."""
    orch = get_orchestrator()
    result = T.dispatch(orch.engine, "live_airport_status", {}, None)
    return {"data": result["data"], "sources": result["sources"], "caveats": result["caveats"]}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    orch = get_orchestrator()
    return orch.chat(request.message, request.session_id, request.provider)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(settings.web_dir / "index.html")


app.mount("/static", StaticFiles(directory=str(settings.web_dir)), name="static")
