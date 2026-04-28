"""Bot map: top-level topology of a bot (agents + workflows + edges)."""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from loguru import logger

from db import get_supabase
from core.agent_defaults import DEFAULT_AGENTS, AGENT_ID_TO_INTENT


router = APIRouter()


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
        agents.append({
            "id": agent_id,
            "name": row.get("name"),
            "enabled": bool(row.get("enabled", True)),
            "is_custom": True,
            "intent": None,
            "tools": row.get("tools") or {},
            "trigger_flows": metadata.get("trigger_flows") or [],
        })

    # Workflows: extract handoffs from each definition.
    workflows: List[Dict[str, Any]] = []
    for wf in workflow_rows:
        definition = wf.get("definition") or {}
        nodes = definition.get("nodes") or []
        handoffs: List[Dict[str, Any]] = []
        for n in nodes:
            if n.get("type") != "handoff":
                continue
            data = n.get("data") or {}
            target = data.get("target") or "agentic"
            handoffs.append({
                "target": target,
                "target_workflow_id": data.get("target_workflow_id"),
                "label": data.get("label"),
            })
        workflows.append({
            "id": wf["id"],
            "name": wf["name"],
            "trigger_type": wf["trigger_type"],
            "trigger_value": wf.get("trigger_value"),
            "enabled": bool(wf.get("enabled", True)),
            "version": wf.get("version", 1),
            "handoffs": handoffs,
        })

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

    # Agentic hub → enabled built-in agents (intent routing).
    for agent in agents:
        if not agent["enabled"] or agent["is_custom"]:
            continue
        edges.append({
            "id": f"edge-agentic-agent-{agent['id']}",
            "source": "agentic",
            "target": f"agent:{agent['id']}",
            "kind": "intent_route",
            "label": agent.get("intent") or "",
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
