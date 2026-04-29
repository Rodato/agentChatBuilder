"""Bot map: top-level topology of a bot (agents + workflows + edges)."""

from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

from db import get_supabase
from core.agent_defaults import DEFAULT_AGENTS, AGENT_ID_TO_INTENT, VALID_INTENTS


router = APIRouter()


VALID_KINDS = {"entry", "intent_route", "intent", "manual_trigger"}


class MapEdgeIn(BaseModel):
    source: str
    target: str
    kind: str
    label: Optional[str] = None


class MapUpdateIn(BaseModel):
    edges: List[MapEdgeIn] = Field(default_factory=list)


@router.get("/{bot_id}/map")
async def get_bot_map(bot_id: str) -> Dict[str, Any]:
    """Return everything the frontend needs to render the bot's topology.

    Shape:
      {
        "bot_id": str,
        "agents":   [{ id, name, enabled, is_custom, intent, tools, trigger_flows[] }],
        "workflows":[{ id, name, trigger_type, trigger_value, enabled, version,
                       handoffs: [{ target: "agentic"|"workflow", target_workflow_id?, label? }] }],
        "edges":    [{ id, source, target, kind, label? }],
        "entry":    { kind: "on_start"|"agentic", workflow_id?: str }
      }

    Edge kinds:
      - "entry"            from synthetic "start" node into entry point
      - "intent"           from "agentic" hub into a workflow (on_intent)
      - "manual_trigger"   from an agent into a workflow (function-calling-lite)
      - "handoff"          from a workflow into another workflow
      - "handoff_agentic"  from a workflow back to the agentic hub
    """
    sb = get_supabase()

    # Verify the bot exists.
    try:
        bot = sb.table("bots").select("id, name").eq("id", bot_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Bot no encontrado.")

    # Fetch agents + workflows in parallel-ish (Supabase python client is sync; sequential is fine).
    try:
        agent_rows = (
            sb.table("bot_agents")
            .select("agent_id, name, enabled, is_custom, tools, metadata, position")
            .eq("bot_id", bot_id)
            .order("position")
            .execute()
            .data
        ) or []
    except Exception as e:
        logger.warning(f"map: failed to load bot_agents for {bot_id}: {e}")
        agent_rows = []

    try:
        workflow_rows = (
            sb.table("workflows")
            .select("id, name, trigger_type, trigger_value, enabled, version, definition")
            .eq("bot_id", bot_id)
            .order("created_at")
            .execute()
            .data
        ) or []
    except Exception as e:
        logger.warning(f"map: failed to load workflows for {bot_id}: {e}")
        workflow_rows = []

    # Hydrate agents: if no row exists for a built-in, use defaults.
    by_agent_id = {row["agent_id"]: row for row in agent_rows}
    defaults_by_id = {a["agent_id"]: a for a in DEFAULT_AGENTS}

    agents: List[Dict[str, Any]] = []
    for agent_id in defaults_by_id:
        row = by_agent_id.get(agent_id) or defaults_by_id[agent_id]
        metadata = row.get("metadata") or {}
        agents.append({
            "id": agent_id,
            "name": row.get("name"),
            "enabled": bool(row.get("enabled", True)),
            "is_custom": False,
            "intent": AGENT_ID_TO_INTENT.get(agent_id),
            "tools": row.get("tools") or {},
            "trigger_flows": metadata.get("trigger_flows") or [],
        })
    # Custom agents (not in defaults) still get listed.
    for agent_id, row in by_agent_id.items():
        if agent_id in defaults_by_id:
            continue
        metadata = row.get("metadata") or {}
        intents = list(row.get("intents") or [])
        agents.append({
            "id": agent_id,
            "name": row.get("name"),
            "enabled": bool(row.get("enabled", True)),
            "is_custom": True,
            "intent": intents[0] if intents else None,
            "intents": intents,
            "tools": row.get("tools") or {},
            "trigger_flows": metadata.get("trigger_flows") or [],
        })

    # Workflows: extract handoffs and agent-node references from each definition.
    workflows: List[Dict[str, Any]] = []
    workflow_agent_refs: List[Dict[str, Any]] = []  # workflow → worker dependencies
    for wf in workflow_rows:
        definition = wf.get("definition") or {}
        nodes = definition.get("nodes") or []
        handoffs: List[Dict[str, Any]] = []
        agent_refs: List[str] = []
        for n in nodes:
            t = n.get("type")
            data = n.get("data") or {}
            if t == "handoff":
                target = data.get("target") or "agentic"
                handoffs.append({
                    "target": target,
                    "target_workflow_id": data.get("target_workflow_id"),
                    "label": data.get("label"),
                })
            elif t == "agent":
                agent_id = data.get("agent_id")
                if agent_id and agent_id not in agent_refs:
                    agent_refs.append(agent_id)
        workflows.append({
            "id": wf["id"],
            "name": wf["name"],
            "trigger_type": wf["trigger_type"],
            "trigger_value": wf.get("trigger_value"),
            "enabled": bool(wf.get("enabled", True)),
            "version": wf.get("version", 1),
            "handoffs": handoffs,
            "agent_refs": agent_refs,
        })
        for agent_id in agent_refs:
            workflow_agent_refs.append({"workflow_id": wf["id"], "agent_id": agent_id})

    workflows_by_id = {w["id"]: w for w in workflows}
    edges: List[Dict[str, Any]] = []

    # Entry edge: start → on_start workflow (if any & enabled) or agentic hub.
    on_start = next(
        (w for w in workflows if w["trigger_type"] == "on_start" and w["enabled"]),
        None,
    )
    if on_start:
        edges.append({
            "id": f"edge-start-onstart",
            "source": "start",
            "target": f"workflow:{on_start['id']}",
            "kind": "entry",
            "label": "Inicio",
        })
        # And the on_start eventually flows to agentic via its handoffs (handled below).
        entry = {"kind": "on_start", "workflow_id": on_start["id"]}
    else:
        edges.append({
            "id": "edge-start-agentic",
            "source": "start",
            "target": "agentic",
            "kind": "entry",
            "label": "Inicio",
        })
        entry = {"kind": "agentic"}

    # Agentic hub → enabled agents (intent routing).
    # Builtins always get one edge labelled with their fixed intent. Customs
    # get one edge per registered intent; if they list none, no intent edge
    # (they're only invocable from a Workflow node).
    for agent in agents:
        if not agent["enabled"]:
            continue
        if not agent["is_custom"]:
            edges.append({
                "id": f"edge-agentic-agent-{agent['id']}",
                "source": "agentic",
                "target": f"agent:{agent['id']}",
                "kind": "intent_route",
                "label": agent.get("intent") or "",
            })
        else:
            for intent in agent.get("intents", []):
                edges.append({
                    "id": f"edge-agentic-agent-{agent['id']}-{intent}",
                    "source": "agentic",
                    "target": f"agent:{agent['id']}",
                    "kind": "intent_route",
                    "label": intent,
                })

    # on_intent workflows: edge from agentic → workflow, labelled with the intent.
    for wf in workflows:
        if wf["trigger_type"] != "on_intent" or not wf["enabled"]:
            continue
        edges.append({
            "id": f"edge-intent-{wf['id']}",
            "source": "agentic",
            "target": f"workflow:{wf['id']}",
            "kind": "intent",
            "label": wf.get("trigger_value") or "intent",
        })

    # Manual workflows: edge from each agent that lists it in metadata.trigger_flows.
    manual_wf_by_id = {w["id"]: w for w in workflows if w["trigger_type"] == "manual" and w["enabled"]}
    manual_wf_by_name = {w["name"]: w for w in manual_wf_by_id.values()}
    for agent in agents:
        if not agent["enabled"]:
            continue
        if not (agent["tools"].get("trigger_flow")):
            continue
        allowed = agent["trigger_flows"] or []
        # When allowed is empty, the agent sees ALL manual workflows (matches agent_defaults logic).
        targets = list(manual_wf_by_id.values()) if not allowed else [
            manual_wf_by_id[ref] if ref in manual_wf_by_id else manual_wf_by_name.get(ref)
            for ref in allowed
        ]
        for wf in targets:
            if not wf:
                continue
            edges.append({
                "id": f"edge-manual-{agent['id']}-{wf['id']}",
                "source": f"agent:{agent['id']}",
                "target": f"workflow:{wf['id']}",
                "kind": "manual_trigger",
                "label": "trigger_flow",
            })

    # Workflow → Worker: derived from agent nodes inside each workflow definition.
    agent_ids_set = {a["id"] for a in agents}
    for ref in workflow_agent_refs:
        if ref["agent_id"] not in agent_ids_set:
            continue  # references a deleted worker
        edges.append({
            "id": f"edge-wfagent-{ref['workflow_id']}-{ref['agent_id']}",
            "source": f"workflow:{ref['workflow_id']}",
            "target": f"agent:{ref['agent_id']}",
            "kind": "workflow_agent",
            "label": "usa",
        })

    # Handoffs from each workflow.
    for wf in workflows:
        for ho in wf["handoffs"]:
            if ho["target"] == "agentic":
                edges.append({
                    "id": f"edge-handoff-{wf['id']}-agentic",
                    "source": f"workflow:{wf['id']}",
                    "target": "agentic",
                    "kind": "handoff_agentic",
                    "label": ho.get("label") or "handoff",
                })
            elif ho["target"] == "workflow" and ho.get("target_workflow_id"):
                target_id = ho["target_workflow_id"]
                if target_id in workflows_by_id:
                    edges.append({
                        "id": f"edge-handoff-{wf['id']}-{target_id}",
                        "source": f"workflow:{wf['id']}",
                        "target": f"workflow:{target_id}",
                        "kind": "handoff",
                        "label": ho.get("label") or "handoff",
                    })

    return {
        "bot_id": bot_id,
        "bot_name": bot.get("name") if bot else None,
        "agents": agents,
        "workflows": workflows,
        "edges": edges,
        "entry": entry,
    }


# ── PUT /map: apply a desired topology by diffing against current state ────

def _parse_node_ref(ref: str) -> Tuple[str, Optional[str]]:
    """'agent:cobranza' → ('agent', 'cobranza'); 'agentic' → ('agentic', None)."""
    if ":" in ref:
        kind, _id = ref.split(":", 1)
        return kind, _id
    return ref, None


@router.put("/{bot_id}/map")
async def update_bot_map(bot_id: str, body: MapUpdateIn) -> Dict[str, Any]:
    """Apply a desired topology to the bot's workers and workflows.

    The map describes the *routing* relationships; the actual entities
    (workers and workflows) are created in their own tabs. This endpoint:
      1. Validates each edge.
      2. Computes the desired state per worker/workflow.
      3. Persists the diff with UPDATEs (no inserts/deletes of entities).
      4. Invalidates the orchestrator cache.
    """
    sb = get_supabase()

    # ── Load current state ────────────────────────────────────────────────
    try:
        agent_rows = (
            sb.table("bot_agents")
            .select("agent_id, name, enabled, is_custom, tools, metadata, position, intents")
            .eq("bot_id", bot_id)
            .execute()
            .data
        ) or []
    except Exception as e:
        logger.exception(f"map PUT: load agents failed for {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo cargar el estado actual del mapa.")

    try:
        workflow_rows = (
            sb.table("workflows")
            .select("id, name, trigger_type, trigger_value, enabled, version")
            .eq("bot_id", bot_id)
            .execute()
            .data
        ) or []
    except Exception as e:
        logger.exception(f"map PUT: load workflows failed for {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo cargar el estado actual del mapa.")

    agents_by_id = {row["agent_id"]: row for row in agent_rows}
    workflows_by_id = {row["id"]: row for row in workflow_rows}

    # ── Compute desired state per entity ──────────────────────────────────
    # Workers: intents set, trigger_flow tool flag, allow-list of workflow ids.
    desired_worker_intents: Dict[str, Set[str]] = {a: set() for a in agents_by_id}
    desired_trigger_flows: Dict[str, Set[str]] = {a: set() for a in agents_by_id}

    # Workflows: trigger_type and trigger_value from incoming edges.
    desired_wf_trigger: Dict[str, Tuple[str, Optional[str]]] = {}

    seen_on_start: Optional[str] = None

    for edge in body.edges:
        if edge.kind not in VALID_KINDS:
            raise HTTPException(status_code=400, detail=f"Tipo de arista no soportado: {edge.kind}")

        src_kind, src_id = _parse_node_ref(edge.source)
        tgt_kind, tgt_id = _parse_node_ref(edge.target)

        if edge.kind == "entry":
            # start → workflow:{id}: this workflow becomes on_start.
            if src_kind != "start" or tgt_kind != "workflow":
                raise HTTPException(status_code=400, detail="Arista 'entry' debe ir de start a un workflow.")
            if not tgt_id or tgt_id not in workflows_by_id:
                raise HTTPException(status_code=400, detail=f"Workflow {tgt_id} no existe.")
            if seen_on_start and seen_on_start != tgt_id:
                raise HTTPException(status_code=400, detail="Solo un workflow puede ser on_start.")
            seen_on_start = tgt_id
            desired_wf_trigger[tgt_id] = ("on_start", None)

        elif edge.kind == "intent_route":
            # agentic → agent:{id} with label = INTENT.
            if src_kind != "agentic" or tgt_kind != "agent":
                raise HTTPException(status_code=400, detail="intent_route debe ir de agentic a un worker.")
            if not tgt_id or tgt_id not in agents_by_id:
                raise HTTPException(status_code=400, detail=f"Worker {tgt_id} no existe.")
            intent = (edge.label or "").upper()
            if intent not in VALID_INTENTS:
                raise HTTPException(status_code=400, detail=f"Intent inválido: {edge.label}")
            # Builtins have a fixed intent; we reject overriding them via this route.
            row = agents_by_id[tgt_id]
            if not row.get("is_custom"):
                # For builtins, intent_route is implicit (no-op) — skip.
                continue
            desired_worker_intents[tgt_id].add(intent)

        elif edge.kind == "intent":
            # agentic → workflow:{id} with label = INTENT.
            if src_kind != "agentic" or tgt_kind != "workflow":
                raise HTTPException(status_code=400, detail="intent debe ir de agentic a un workflow.")
            if not tgt_id or tgt_id not in workflows_by_id:
                raise HTTPException(status_code=400, detail=f"Workflow {tgt_id} no existe.")
            intent = (edge.label or "").upper()
            if intent not in VALID_INTENTS:
                raise HTTPException(status_code=400, detail=f"Intent inválido para workflow on_intent: {edge.label}")
            if tgt_id in desired_wf_trigger and desired_wf_trigger[tgt_id][0] == "on_start":
                raise HTTPException(status_code=400, detail=f"Workflow {tgt_id} ya marcado como on_start.")
            desired_wf_trigger[tgt_id] = ("on_intent", intent)

        elif edge.kind == "manual_trigger":
            # agent:{id} → workflow:{id}: worker can trigger this workflow.
            if src_kind != "agent" or tgt_kind != "workflow":
                raise HTTPException(status_code=400, detail="manual_trigger debe ir de un worker a un workflow.")
            if not src_id or src_id not in agents_by_id:
                raise HTTPException(status_code=400, detail=f"Worker {src_id} no existe.")
            if not tgt_id or tgt_id not in workflows_by_id:
                raise HTTPException(status_code=400, detail=f"Workflow {tgt_id} no existe.")
            desired_trigger_flows[src_id].add(tgt_id)
            # Workflows that are manual_trigger targets default to manual trigger if not otherwise set.
            desired_wf_trigger.setdefault(tgt_id, ("manual", None))

    # Workflows not mentioned in any edge → default to manual (no auto-trigger).
    for wf_id in workflows_by_id:
        desired_wf_trigger.setdefault(wf_id, ("manual", None))

    # ── Apply diffs ───────────────────────────────────────────────────────
    errors: List[str] = []

    # Workers: update intents, tools.trigger_flow, metadata.trigger_flows.
    for agent_id, row in agents_by_id.items():
        if not row.get("is_custom"):
            # Builtins: only manual_trigger allow-list applies (intents are fixed).
            current_tools = dict(row.get("tools") or {})
            current_metadata = dict(row.get("metadata") or {})
            current_flows = list(current_metadata.get("trigger_flows") or [])
            new_flows = sorted(desired_trigger_flows.get(agent_id, set()))
            new_trigger_flow = bool(new_flows)
            if (current_tools.get("trigger_flow") or False) == new_trigger_flow and sorted(current_flows) == new_flows:
                continue
            current_tools["trigger_flow"] = new_trigger_flow
            current_metadata["trigger_flows"] = new_flows
            try:
                sb.table("bot_agents").update({"tools": current_tools, "metadata": current_metadata}) \
                    .eq("bot_id", bot_id).eq("agent_id", agent_id).execute()
            except Exception as e:
                errors.append(f"agent {agent_id}: {e}")
            continue

        # Custom agents: also update intents.
        current_intents = sorted(row.get("intents") or [])
        new_intents = sorted(desired_worker_intents.get(agent_id, set()))
        current_tools = dict(row.get("tools") or {})
        current_metadata = dict(row.get("metadata") or {})
        current_flows = list(current_metadata.get("trigger_flows") or [])
        new_flows = sorted(desired_trigger_flows.get(agent_id, set()))
        new_trigger_flow = bool(new_flows)

        update: Dict[str, Any] = {}
        if current_intents != new_intents:
            update["intents"] = new_intents
        if (current_tools.get("trigger_flow") or False) != new_trigger_flow:
            current_tools["trigger_flow"] = new_trigger_flow
            update["tools"] = current_tools
        if sorted(current_flows) != new_flows:
            current_metadata["trigger_flows"] = new_flows
            update["metadata"] = current_metadata
        if not update:
            continue
        try:
            sb.table("bot_agents").update(update) \
                .eq("bot_id", bot_id).eq("agent_id", agent_id).execute()
        except Exception as e:
            errors.append(f"agent {agent_id}: {e}")

    # Workflows: update trigger_type, trigger_value.
    for wf_id, row in workflows_by_id.items():
        new_type, new_value = desired_wf_trigger.get(wf_id, ("manual", None))
        current_type = row.get("trigger_type", "manual")
        current_value = row.get("trigger_value")
        if current_type == new_type and (current_value or None) == (new_value or None):
            continue
        try:
            sb.table("workflows").update({
                "trigger_type": new_type,
                "trigger_value": new_value,
                "version": (row.get("version") or 1) + 1,
                "updated_at": "now()",
            }).eq("id", wf_id).eq("bot_id", bot_id).execute()
        except Exception as e:
            errors.append(f"workflow {wf_id}: {e}")

    # ── Invalidate orchestrator cache ────────────────────────────────────
    try:
        from api.main import invalidate_orchestrator
        invalidate_orchestrator(bot_id)
    except Exception:
        pass

    if errors:
        logger.warning(f"map PUT for {bot_id} had partial errors: {errors}")
        raise HTTPException(status_code=500, detail={"message": "Algunos cambios no se aplicaron.", "errors": errors})

    return await get_bot_map(bot_id)
