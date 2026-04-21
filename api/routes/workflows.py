"""API routes for managing multiple workflows per bot with triggers."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

from db import get_supabase

router = APIRouter()

VALID_TRIGGER_TYPES = {"on_start", "on_intent", "manual"}
VALID_INTENTS = {"GREETING", "FACTUAL", "PLAN", "IDEATE", "SENSITIVE", "AMBIGUOUS"}


# ── Schemas ──────────────────────────────────────────────────────────────────

class WorkflowDefinition(BaseModel):
    version: int = 1
    entry_node_id: Optional[str] = None
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)


class WorkflowCreate(BaseModel):
    name: str
    trigger_type: str = "manual"
    trigger_value: Optional[str] = None
    definition: Optional[WorkflowDefinition] = None
    enabled: bool = True


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_value: Optional[str] = None
    definition: Optional[WorkflowDefinition] = None
    enabled: Optional[bool] = None


class WorkflowToggle(BaseModel):
    enabled: bool


# ── Helpers ──────────────────────────────────────────────────────────────────

def _validate_definition(definition: WorkflowDefinition) -> Dict[str, Any]:
    node_ids = {n.get("id") for n in definition.nodes if n.get("id")}
    if definition.nodes and not definition.entry_node_id:
        definition.entry_node_id = definition.nodes[0].get("id")
    if definition.entry_node_id and definition.entry_node_id not in node_ids and definition.nodes:
        raise HTTPException(status_code=400, detail="entry_node_id no corresponde a ningún nodo.")
    for e in definition.edges:
        if e.get("source") not in node_ids or e.get("target") not in node_ids:
            raise HTTPException(status_code=400, detail=f"Edge {e.get('id')} referencia nodos inválidos.")
    return definition.model_dump()


def _validate_trigger(trigger_type: str, trigger_value: Optional[str]) -> None:
    if trigger_type not in VALID_TRIGGER_TYPES:
        raise HTTPException(status_code=400, detail=f"trigger_type inválido: {trigger_type}")
    if trigger_type == "on_intent" and trigger_value not in VALID_INTENTS:
        raise HTTPException(status_code=400, detail=f"trigger_value debe ser uno de: {sorted(VALID_INTENTS)}")


def _abort_active_conversations(bot_id: str) -> None:
    try:
        get_supabase().table("conversations").update({"status": "aborted"}).eq("bot_id", bot_id).eq("status", "active").execute()
    except Exception as e:
        logger.warning(f"Could not abort active conversations for bot {bot_id}: {e}")


def _invalidate_orchestrator_cache(bot_id: str) -> None:
    try:
        from api.main import invalidate_orchestrator
        invalidate_orchestrator(bot_id)
    except Exception:
        pass


def _check_onstart_conflict(bot_id: str, trigger_type: str, enabled: bool, exclude_id: Optional[str] = None) -> None:
    """Raise if there is another enabled on_start workflow for the same bot."""
    if trigger_type != "on_start" or not enabled:
        return
    q = (
        get_supabase()
        .table("workflows")
        .select("id")
        .eq("bot_id", bot_id)
        .eq("trigger_type", "on_start")
        .eq("enabled", True)
    )
    result = q.execute()
    conflicting = [row for row in (result.data or []) if row["id"] != exclude_id]
    if conflicting:
        raise HTTPException(
            status_code=400,
            detail="Ya hay otro workflow on_start activo para este bot. Desactívalo primero.",
        )


# ── Routes — plural (nueva API) ─────────────────────────────────────────────

@router.get("/{bot_id}/workflows")
async def list_workflows(bot_id: str):
    try:
        result = (
            get_supabase()
            .table("workflows")
            .select("id, name, trigger_type, trigger_value, enabled, version, created_at, updated_at")
            .eq("bot_id", bot_id)
            .order("created_at")
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.exception(f"Error listing workflows for bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudieron cargar los workflows.")


@router.post("/{bot_id}/workflows", status_code=201)
async def create_workflow(bot_id: str, body: WorkflowCreate):
    _validate_trigger(body.trigger_type, body.trigger_value)
    _check_onstart_conflict(bot_id, body.trigger_type, body.enabled)
    definition = _validate_definition(body.definition or WorkflowDefinition())
    try:
        row = {
            "bot_id": bot_id,
            "name": body.name,
            "trigger_type": body.trigger_type,
            "trigger_value": body.trigger_value,
            "enabled": body.enabled,
            "definition": definition,
            "entry_node_id": definition.get("entry_node_id"),
            "version": 1,
        }
        result = get_supabase().table("workflows").insert(row).execute()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating workflow for {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo crear el workflow.")
    _invalidate_orchestrator_cache(bot_id)
    return result.data[0]


@router.get("/{bot_id}/workflows/{workflow_id}")
async def get_workflow(bot_id: str, workflow_id: str):
    try:
        result = (
            get_supabase()
            .table("workflows")
            .select("*")
            .eq("bot_id", bot_id)
            .eq("id", workflow_id)
            .single()
            .execute()
        )
        return result.data
    except Exception as e:
        logger.exception(f"Error fetching workflow {workflow_id}: {e}")
        raise HTTPException(status_code=404, detail="Workflow no encontrado.")


@router.put("/{bot_id}/workflows/{workflow_id}")
async def update_workflow(bot_id: str, workflow_id: str, body: WorkflowUpdate):
    payload: Dict[str, Any] = {}
    if body.name is not None:
        payload["name"] = body.name
    if body.trigger_type is not None:
        _validate_trigger(body.trigger_type, body.trigger_value)
        payload["trigger_type"] = body.trigger_type
        payload["trigger_value"] = body.trigger_value
    if body.enabled is not None:
        payload["enabled"] = body.enabled
    if body.definition is not None:
        definition = _validate_definition(body.definition)
        payload["definition"] = definition
        payload["entry_node_id"] = definition.get("entry_node_id")

    if not payload:
        raise HTTPException(status_code=400, detail="Sin campos para actualizar.")

    # Check on_start conflict (if enabling or changing to on_start).
    current = (
        get_supabase()
        .table("workflows")
        .select("trigger_type, enabled, version")
        .eq("id", workflow_id)
        .single()
        .execute()
        .data
    ) or {}
    next_trigger = payload.get("trigger_type", current.get("trigger_type"))
    next_enabled = payload.get("enabled", current.get("enabled"))
    _check_onstart_conflict(bot_id, next_trigger, next_enabled, exclude_id=workflow_id)

    payload["version"] = (current.get("version") or 1) + 1
    payload["updated_at"] = "now()"

    try:
        result = (
            get_supabase()
            .table("workflows")
            .update(payload)
            .eq("id", workflow_id)
            .eq("bot_id", bot_id)
            .execute()
        )
    except Exception as e:
        logger.exception(f"Error updating workflow {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo actualizar el workflow.")

    _abort_active_conversations(bot_id)
    _invalidate_orchestrator_cache(bot_id)
    return result.data[0] if result.data else {}


@router.delete("/{bot_id}/workflows/{workflow_id}", status_code=204)
async def delete_workflow(bot_id: str, workflow_id: str):
    try:
        get_supabase().table("workflows").delete().eq("id", workflow_id).eq("bot_id", bot_id).execute()
    except Exception as e:
        logger.exception(f"Error deleting workflow {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo eliminar el workflow.")
    _invalidate_orchestrator_cache(bot_id)


@router.post("/{bot_id}/workflows/{workflow_id}/toggle")
async def toggle_workflow(bot_id: str, workflow_id: str, body: WorkflowToggle):
    try:
        current = (
            get_supabase()
            .table("workflows")
            .select("trigger_type")
            .eq("id", workflow_id)
            .single()
            .execute()
            .data
        ) or {}
        _check_onstart_conflict(bot_id, current.get("trigger_type"), body.enabled, exclude_id=workflow_id)
        get_supabase().table("workflows").update({"enabled": body.enabled}).eq("id", workflow_id).eq("bot_id", bot_id).execute()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error toggling workflow {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo cambiar el estado del workflow.")
    _invalidate_orchestrator_cache(bot_id)
    return {"status": "ok", "enabled": body.enabled}


# ── Routes — legacy (singular) ──────────────────────────────────────────────
# Kept for backwards-compat with the old UI. Points at the bot's on_start workflow.

@router.get("/{bot_id}/workflow")
async def get_legacy_workflow(bot_id: str):
    try:
        result = (
            get_supabase()
            .table("workflows")
            .select("*")
            .eq("bot_id", bot_id)
            .eq("trigger_type", "on_start")
            .limit(1)
            .execute()
        )
        row = (result.data or [None])[0]
    except Exception as e:
        logger.exception(f"Legacy get_workflow for {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo cargar el workflow.")
    # workflow_mode: does the bot have any enabled workflow (on_start or other)?
    try:
        count = (
            get_supabase()
            .table("workflows")
            .select("id", count="exact")
            .eq("bot_id", bot_id)
            .eq("enabled", True)
            .execute()
        ).count
        workflow_mode = "workflow" if count and count > 0 else "free"
    except Exception:
        workflow_mode = "free"
    return {"workflow_mode": workflow_mode, "workflow": row}
