"""API routes for agent configuration management (persisted in Supabase)."""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

from db import get_supabase
from core.agent_defaults import DEFAULT_AGENTS

router = APIRouter()


class AgentConfig(BaseModel):
    agent_id: str
    name: str
    objective: str = ""
    system_prompt: str = ""
    model: str = "google/gemini-2.5-flash-lite"
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    tools: Dict[str, bool] = Field(default_factory=dict)
    enabled: bool = True
    is_custom: bool = False
    position: int = 0


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    objective: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0)
    tools: Optional[Dict[str, bool]] = None
    enabled: Optional[bool] = None
    position: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


def seed_default_agents(bot_id: str) -> None:
    """Insert the built-in agent rows for a newly-created bot."""
    rows = [{"bot_id": bot_id, **a} for a in DEFAULT_AGENTS]
    try:
        get_supabase().table("bot_agents").upsert(rows, on_conflict="bot_id,agent_id").execute()
    except Exception as e:
        logger.exception(f"Failed to seed agents for bot {bot_id}: {e}")


def _ensure_seeded(bot_id: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """If the bot has no agents yet (legacy bots), seed defaults and re-fetch."""
    if rows:
        return rows
    seed_default_agents(bot_id)
    result = (
        get_supabase()
        .table("bot_agents")
        .select("*")
        .eq("bot_id", bot_id)
        .order("position")
        .execute()
    )
    return result.data or []


@router.get("/{bot_id}/agents")
async def list_agents(bot_id: str) -> List[Dict[str, Any]]:
    try:
        result = (
            get_supabase()
            .table("bot_agents")
            .select("*")
            .eq("bot_id", bot_id)
            .order("position")
            .execute()
        )
        return _ensure_seeded(bot_id, result.data or [])
    except Exception as e:
        logger.exception(f"Error listing agents for bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudieron cargar los agentes.")


@router.put("/{bot_id}/agents/{agent_id}")
async def update_agent(bot_id: str, agent_id: str, patch: AgentUpdate):
    try:
        data = {k: v for k, v in patch.model_dump().items() if v is not None}
        if not data:
            raise HTTPException(status_code=400, detail="Sin campos para actualizar.")
        result = (
            get_supabase()
            .table("bot_agents")
            .update(data)
            .eq("bot_id", bot_id)
            .eq("agent_id", agent_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Agente no encontrado.")
        # Invalidate the cached orchestrator so the next /chat reflects the change.
        try:
            from api.main import invalidate_orchestrator
            invalidate_orchestrator(bot_id)
        except Exception:
            pass
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating agent {agent_id} for bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo actualizar el agente.")


@router.post("/{bot_id}/agents", status_code=201)
async def create_custom_agent(bot_id: str, agent: AgentConfig):
    """Create a custom agent row (is_custom=True). Custom agents aren't routed by the orchestrator yet."""
    try:
        row = {"bot_id": bot_id, **agent.model_dump(), "is_custom": True}
        result = get_supabase().table("bot_agents").insert(row).execute()
        return result.data[0]
    except Exception as e:
        logger.exception(f"Error creating custom agent for bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo crear el agente.")


@router.delete("/{bot_id}/agents/{agent_id}", status_code=204)
async def delete_agent(bot_id: str, agent_id: str):
    try:
        get_supabase().table("bot_agents").delete().eq("bot_id", bot_id).eq("agent_id", agent_id).eq("is_custom", True).execute()
    except Exception as e:
        logger.exception(f"Error deleting agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo eliminar el agente.")
