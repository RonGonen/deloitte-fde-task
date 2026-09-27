"""FastAPI application: chat API plus the static web UI. Binds to loopback by default."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, HTTPException
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


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    orch = get_orchestrator()
    return orch.chat(request.message, request.session_id, request.provider)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(settings.web_dir / "index.html")


app.mount("/static", StaticFiles(directory=str(settings.web_dir)), name="static")
