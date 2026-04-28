"""API routes for agent configuration management (persisted in Supabase)."""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from loguru import logger

from db import get_supabase
from core.agent_defaults import DEFAULT_AGENTS, VALID_INTENTS

router = APIRouter()


def _validate_intents(values: Optional[List[str]]) -> List[str]:
    if not values:
        return []
    cleaned: List[str] = []
    seen: set = set()
    for v in values:
        if not isinstance(v, str):
            continue
        v = v.strip().upper()
        if v not in VALID_INTENTS:
            raise ValueError(f"Intent inválido: {v}. Permitidos: {sorted(VALID_INTENTS)}")
        if v in seen:
            continue
        seen.add(v)
        cleaned.append(v)
    return cleaned


VALID_KINDS = {"agent", "graph"}


def _validate_kind(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    v = value.strip().lower()
    if v not in VALID_KINDS:
        raise ValueError(f"kind inválido: {value}. Permitidos: {sorted(VALID_KINDS)}")
    return v


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
    intents: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    kind: Optional[str] = "agent"
    graph_definition: Optional[Dict[str, Any]] = None

    @field_validator("intents")
    @classmethod
    def _check_intents(cls, v):
        return _validate_intents(v)

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v):
        return _validate_kind(v)


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
    intents: Optional[List[str]] = None
    kind: Optional[str] = None
    graph_definition: Optional[Dict[str, Any]] = None

    @field_validator("intents")
    @classmethod
    def _check_intents(cls, v):
        if v is None:
            return v
        return _validate_intents(v)

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v):
        return _validate_kind(v)


def seed_default_agents(bot_id: str) -> None:
    """Insert the built-in agent rows for a newly-created bot."""
    rows = [{"bot_id": bot_id, **a} for a in DEFAULT_AGENTS]
    try:
        get_supabase().table("bot_agents").upsert(rows, on_conflict="bot_id,agent_id").execute()
    except Exception as e:
        logger.exception(f"Failed to seed agents for bot {bot_id}: {e}")


def _ensure_seeded(bot_id: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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


def _invalidate(bot_id: str) -> None:
    try:
        from api.main import invalidate_orchestrator
        invalidate_orchestrator(bot_id)
    except Exception:
        pass


def _workflows_referencing_agent(bot_id: str, agent_id: str) -> List[Dict[str, str]]:
    """Return [{workflow_id, workflow_name}] for workflows whose definition has
    a node of type='agent' with data.agent_id == agent_id."""
    try:
        result = (
            get_supabase()
            .table("workflows")
            .select("id, name, definition")
            .eq("bot_id", bot_id)
            .execute()
        )
    except Exception as e:
        logger.warning(f"Could not check workflow references for {agent_id}: {e}")
        return []

    blockers: List[Dict[str, str]] = []
    for wf in result.data or []:
        definition = wf.get("definition") or {}
        nodes = definition.get("nodes") or []
        for node in nodes:
            if node.get("type") != "agent":
                continue
            data = node.get("data") or {}
            if data.get("agent_id") == agent_id:
                blockers.append({"workflow_id": wf["id"], "workflow_name": wf.get("name", "")})
                break
    return blockers


# ── Routes ───────────────────────────────────────────────────────────────────

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

        # `intents`, `kind`, `graph_definition` solo aplican a custom agents.
        if any(k in data for k in ("intents", "kind", "graph_definition")):
            current = (
                get_supabase()
                .table("bot_agents")
                .select("is_custom")
                .eq("bot_id", bot_id)
                .eq("agent_id", agent_id)
                .single()
                .execute()
                .data
            ) or {}
            if not current.get("is_custom"):
                data.pop("intents", None)
                data.pop("kind", None)
                data.pop("graph_definition", None)

        result = (
            get_supabase()
            .table("bot_agents")
            .update(data)
            .eq("bot_id", bot_id)
            .eq("agent_id", agent_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Especialista no encontrado.")
        _invalidate(bot_id)
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating agent {agent_id} for bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo actualizar el especialista.")


@router.post("/{bot_id}/agents", status_code=201)
async def create_custom_agent(bot_id: str, agent: AgentConfig):
    """Create a custom specialist (is_custom=True). Reachable via Workflows
    or — when registered for one or more intents — via the agentic router."""
    try:
        payload = agent.model_dump()
        payload["is_custom"] = True
        if payload.get("intents") is None:
            payload["intents"] = []
        row = {"bot_id": bot_id, **payload}
        result = get_supabase().table("bot_agents").insert(row).execute()
    except Exception as e:
        logger.exception(f"Error creating custom agent for bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo crear el especialista.")
    _invalidate(bot_id)
    return result.data[0]


@router.delete("/{bot_id}/agents/{agent_id}", status_code=204)
async def delete_agent(bot_id: str, agent_id: str):
    # Only custom agents can be deleted (builtins are seeded for every bot).
    try:
        current = (
            get_supabase()
            .table("bot_agents")
            .select("is_custom")
            .eq("bot_id", bot_id)
            .eq("agent_id", agent_id)
            .single()
            .execute()
            .data
        )
    except Exception:
        current = None

    if not current:
        raise HTTPException(status_code=404, detail="Especialista no encontrado.")
    if not current.get("is_custom"):
        raise HTTPException(status_code=400, detail="Solo se pueden eliminar especialistas custom.")

    blockers = _workflows_referencing_agent(bot_id, agent_id)
    if blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Este especialista está usado por uno o más workflows. Edita esos workflows antes de borrarlo.",
                "blocked_by": blockers,
            },
        )

    try:
        get_supabase().table("bot_agents").delete().eq("bot_id", bot_id).eq("agent_id", agent_id).eq("is_custom", True).execute()
    except Exception as e:
        logger.exception(f"Error deleting agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo eliminar el especialista.")
    _invalidate(bot_id)
