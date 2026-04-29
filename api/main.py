"""Main FastAPI application."""

import asyncio
import time
import uuid
from typing import Optional, Dict, Any, Tuple, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from loguru import logger

from core.config import settings
from core.orchestrator import Orchestrator
from core.agent_defaults import build_agent_configs
from core.chat_engine import ChatEngine
from db import get_supabase


# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Agent Chat Builder",
    description="Platform for building chatbots with specialized agents",
    version="0.1.0",
)

_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Orchestrator + ChatEngine cache by bot_id ────────────────────────────────

_ORCH_TTL_SECONDS = 30
_orch_cache: Dict[str, Tuple[float, Orchestrator, ChatEngine]] = {}


def _load_bot_agent_rows(bot_id: str) -> List[Dict[str, Any]]:
    try:
        result = (
            get_supabase()
            .table("bot_agents")
            .select("*")
            .eq("bot_id", bot_id)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.warning(f"Failed to load bot_agents for {bot_id}: {e}")
        return []


def _load_manual_workflows(bot_id: str) -> List[Dict[str, Any]]:
    try:
        result = (
            get_supabase()
            .table("workflows")
            .select("id, name")
            .eq("bot_id", bot_id)
            .eq("trigger_type", "manual")
            .eq("enabled", True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.warning(f"Failed to load manual workflows for {bot_id}: {e}")
        return []


def get_engines_for_bot(bot_id: str) -> Tuple[Orchestrator, ChatEngine]:
    """Return cached (Orchestrator, ChatEngine) pair for the bot."""
    now = time.time()
    cached = _orch_cache.get(bot_id)
    if cached and now - cached[0] < _ORCH_TTL_SECONDS:
        return cached[1], cached[2]

    agent_rows = _load_bot_agent_rows(bot_id)
    manual_workflows = _load_manual_workflows(bot_id)
    configs = build_agent_configs(agent_rows, manual_workflows=manual_workflows)
    orch = Orchestrator(configs_by_agent_id=configs)
    chat = ChatEngine(orch)
    _orch_cache[bot_id] = (now, orch, chat)
    return orch, chat


def invalidate_orchestrator(bot_id: str) -> None:
    _orch_cache.pop(bot_id, None)


# ── Schemas ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    bot_id: str
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None


class ChatStartRequest(BaseModel):
    bot_id: str
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"name": "Agent Chat Builder", "version": "0.1.0", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy", "environment": settings.app_env}


def _log_chat_message(
    *,
    conversation_id: str,
    bot_id: str,
    role: str,
    content: str,
    agent_used: Optional[str] = None,
    intent: Optional[str] = None,
    mode: Optional[str] = None,
    processing_time_ms: Optional[int] = None,
) -> None:
    """Best-effort insert into chat_messages for analytics."""
    if not content:
        return
    try:
        get_supabase().table("chat_messages").insert({
            "conversation_id": conversation_id,
            "bot_id": bot_id,
            "role": role,
            "content": content,
            "agent_used": agent_used,
            "intent": intent,
            "mode": mode,
            "processing_time_ms": processing_time_ms,
        }).execute()
    except Exception as e:
        logger.warning(f"chat_messages insert failed for {conversation_id}: {e}")


@app.post("/chat")
async def chat(req: ChatRequest):
    conversation_id = req.conversation_id or str(uuid.uuid4())
    _, engine = get_engines_for_bot(req.bot_id)
    result = await asyncio.to_thread(
        engine.step,
        bot_id=req.bot_id,
        conversation_id=conversation_id,
        user_id=req.user_id,
        user_input=req.message,
    )
    # Ensure conversation_id is always included.
    result.setdefault("conversation_id", conversation_id)
    # Best-effort analytics log (user message + assistant response).
    _log_chat_message(
        conversation_id=conversation_id,
        bot_id=req.bot_id,
        role="user",
        content=req.message,
    )
    _log_chat_message(
        conversation_id=conversation_id,
        bot_id=req.bot_id,
        role="assistant",
        content=result.get("response", ""),
        agent_used=result.get("agent_used"),
        intent=result.get("intent"),
        mode=result.get("mode"),
        processing_time_ms=result.get("processing_time_ms"),
    )
    return result


@app.post("/chat/start")
async def chat_start(req: ChatStartRequest):
    conversation_id = req.conversation_id or str(uuid.uuid4())
    _, engine = get_engines_for_bot(req.bot_id)
    result = await asyncio.to_thread(
        engine.start,
        bot_id=req.bot_id,
        conversation_id=conversation_id,
        user_id=req.user_id,
    )
    result.setdefault("conversation_id", conversation_id)
    _log_chat_message(
        conversation_id=conversation_id,
        bot_id=req.bot_id,
        role="assistant",
        content=result.get("response", ""),
        agent_used=result.get("agent_used"),
        intent=result.get("intent"),
        mode=result.get("mode"),
        processing_time_ms=result.get("processing_time_ms"),
    )
    return result


# ── Routers ──────────────────────────────────────────────────────────────────

from api.routes.bots import router as bots_router
from api.routes.agents import router as agents_router
from api.routes.documents import router as documents_router
from api.routes.workflows import router as workflows_router
from api.routes.bot_map import router as bot_map_router
from api.routes.analytics import router as analytics_router

app.include_router(bots_router, prefix="/api/bots", tags=["bots"])
app.include_router(agents_router, prefix="/api/bots", tags=["agents"])
app.include_router(documents_router, prefix="/api/bots", tags=["documents"])
app.include_router(workflows_router, prefix="/api/bots", tags=["workflows"])
app.include_router(bot_map_router, prefix="/api/bots", tags=["bot-map"])
app.include_router(analytics_router, prefix="/api/bots", tags=["analytics"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=settings.app_debug,
    )
