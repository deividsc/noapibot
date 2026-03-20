"""
FastAPI HTTP server — Cloud Run entry point for noapibot GCP adaptation.
Replaces the Telegram interface with plain HTTP endpoints.

Endpoints:
  POST /task     {"task": "...", "context": "..."}  → run orchestration
  GET  /health   → {"status": "ok"}
  GET  /agents   → list of available agent personas
"""
import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

from noapibot.config import validate_secrets, AGENTS_DIR, DEFAULT_MODEL
from noapibot.core import run_with_context
from noapibot.memory import load_memory_async, save_memory_async
import noapibot.state as state

# ── Optional WebSocket dashboard (disabled if no DASHBOARD_API_KEY) ───────────
_WS_ENABLED = bool(os.environ.get("DASHBOARD_API_KEY", ""))


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_secrets()
    if _WS_ENABLED:
        import websockets
        from noapibot.websocket import ws_handler, metrics_broadcaster
        ws_server = await websockets.serve(ws_handler, "0.0.0.0", 8765)
        asyncio.create_task(metrics_broadcaster())
    yield
    if _WS_ENABLED:
        ws_server.close()


app = FastAPI(title="noapibot-gcp", lifespan=lifespan)


# ── Auth ───────────────────────────────────────────────────────────────────────
_API_KEY = os.environ.get("NOAPIBOT_API_KEY", "")


def _check_auth(authorization: str | None):
    """Require Bearer token if NOAPIBOT_API_KEY is set (used locally/testing)."""
    if not _API_KEY:
        return  # Cloud Run handles auth via IAM Identity Tokens
    if not authorization or authorization != f"Bearer {_API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Models ─────────────────────────────────────────────────────────────────────

class TaskRequest(BaseModel):
    task: str
    context: str = ""
    session_id: str = "default"


class TaskResponse(BaseModel):
    session_id: str
    response: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "noapibot-gcp", "model": state.current_model}


@app.get("/agents")
def list_agents(authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    agents = []
    if AGENTS_DIR.exists():
        for f in sorted(AGENTS_DIR.glob("*.md")):
            agents.append({"name": f.stem, "file": f.name})
    return {"agents": agents}


@app.post("/task", response_model=TaskResponse)
async def run_task(req: TaskRequest, authorization: str | None = Header(default=None)):
    _check_auth(authorization)

    user_msg = req.task
    if req.context:
        user_msg = f"{req.task}\n\nContexto adicional: {req.context}"

    from datetime import datetime
    mem = await load_memory_async(req.session_id)
    response = await run_with_context(
        state.current_model,
        user_msg,
        session_id=req.session_id,
    )
    mem.append({"role": "user", "text": user_msg, "ts": datetime.now().isoformat()})
    mem.append({"role": "assistant", "text": response, "ts": datetime.now().isoformat()})
    await save_memory_async(mem, req.session_id)

    return TaskResponse(session_id=req.session_id, response=response)
