"""Stack-aware workflow execution engine.

Each user turn is executed against the **top frame** of `conversations.workflow_stack`.
A frame is: `{workflow_id, node_id, pending_capture?}`. The engine itself does not
decide when to push/pop frames — that is the responsibility of `core.chat_engine.ChatEngine`,
which interprets the engine's `handoff` output.

Node types supported:
- `capture`   — stores user input into a named variable, then advances
- `agent`     — invokes a specialized agent and emits its response
- `handoff`   — signals a transition back to agentic mode or to another workflow
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from db import get_supabase
from core.state import AgentState


MAX_ITERATIONS_PER_TURN = 20

_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_template(template: Optional[str], vars: Dict[str, Any]) -> str:
    if not template:
        return ""
    return _VAR_RE.sub(lambda m: str(vars.get(m.group(1), "")), template)


def sanitize_value(value: Any) -> str:
    """Light protection against prompt-injection via captured vars."""
    if not isinstance(value, str):
        value = str(value)
    value = value.replace("```", "'''")
    return value[:500]


class WorkflowEngine:
    def __init__(self, orchestrator):
        self.orch = orchestrator

    # ── Public API ──────────────────────────────────────────────────────────

    def start(
        self,
        *,
        bot_id: str,
        frame: Dict[str, Any],
        captured_vars: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run a fresh frame without consuming user input."""
        return self._run(
            bot_id=bot_id,
            frame=frame,
            captured_vars=captured_vars,
            user_input=None,
        )

    def step(
        self,
        *,
        bot_id: str,
        frame: Dict[str, Any],
        captured_vars: Dict[str, Any],
        user_input: str,
    ) -> Dict[str, Any]:
        return self._run(
            bot_id=bot_id,
            frame=frame,
            captured_vars=captured_vars,
            user_input=user_input,
        )

    # ── Core runtime ────────────────────────────────────────────────────────

    def _run(
        self,
        *,
        bot_id: str,
        frame: Dict[str, Any],
        captured_vars: Dict[str, Any],
        user_input: Optional[str],
    ) -> Dict[str, Any]:
        """Execute the current frame until a blocking state or terminal.

        Returns a dict with:
          - response, sources, agent_used, language
          - frame: the (possibly updated) frame, or None if the workflow finished
          - handoff: {"target": "agentic"|"workflow", "target_workflow_id"?, "farewell"?} or None
          - captured_vars: (possibly updated) vars
        """
        start_time = time.time()
        workflow = self._load_workflow(frame["workflow_id"])
        if not workflow:
            return {
                "response": "(Workflow no encontrado)",
                "sources": [],
                "agent_used": None,
                "language": "es",
                "frame": None,
                "handoff": {"target": "agentic"},
                "captured_vars": captured_vars,
                "processing_time_ms": int((time.time() - start_time) * 1000),
            }

        # Ensure node_id is set to the entry when starting.
        if not frame.get("node_id"):
            frame["node_id"] = workflow.get("entry_node_id")

        # Consume pending_capture with incoming user input.
        if user_input is not None and frame.get("pending_capture"):
            var_name = frame["pending_capture"]["var_name"]
            captured_vars[var_name] = sanitize_value(user_input)
            frame["pending_capture"] = None
            frame["node_id"] = self._next_node_id(workflow, frame["node_id"])

        response = ""
        sources: List[Dict[str, Any]] = []
        agent_used: Optional[str] = None
        language = "es"
        handoff: Optional[Dict[str, Any]] = None

        iterations = 0
        while frame.get("node_id"):
            iterations += 1
            if iterations > MAX_ITERATIONS_PER_TURN:
                logger.error("Workflow exceeded iteration limit — possible cycle.")
                response = "Error: el workflow tiene un ciclo o excede el límite de pasos."
                handoff = {"target": "agentic"}
                frame["node_id"] = None
                break

            node = self._node(workflow, frame["node_id"])
            if node is None:
                logger.warning(f"Node {frame['node_id']} not found — handoff to agentic.")
                handoff = {"target": "agentic"}
                frame["node_id"] = None
                break

            ntype = node.get("type")
            data = node.get("data") or {}

            if ntype == "capture":
                var_name = data.get("var_name")
                if not var_name:
                    frame["node_id"] = self._next_node_id(workflow, node["id"])
                    continue
                if data.get("skip_if_present") and var_name in captured_vars:
                    frame["node_id"] = self._next_node_id(workflow, node["id"])
                    continue
                frame["pending_capture"] = {"var_name": var_name}
                response = render_template(data.get("prompt", ""), captured_vars)
                agent_used = "capture"
                break

            if ntype == "agent":
                agent_id = data.get("agent_id")
                agent = self.orch.get_agent(agent_id) if agent_id else None
                if agent is None:
                    logger.warning(f"Unknown agent_id '{agent_id}' — skipping node.")
                    frame["node_id"] = self._next_node_id(workflow, node["id"])
                    continue
                response, sources, language = self._invoke_agent(
                    agent=agent,
                    node_data=data,
                    captured_vars=captured_vars,
                    bot_id=bot_id,
                    user_input=user_input or "",
                )
                agent_used = agent_id
                frame["node_id"] = self._next_node_id(workflow, node["id"])
                break

            if ntype == "handoff":
                farewell = render_template(data.get("farewell"), captured_vars)
                response = farewell
                target = data.get("target") or "agentic"
                handoff = {"target": target}
                if target == "workflow":
                    handoff["target_workflow_id"] = data.get("target_workflow_id")
                frame["node_id"] = None
                agent_used = "handoff"
                break

            # Unknown node type — skip forward.
            logger.warning(f"Unknown node type '{ntype}' at {node.get('id')}")
            frame["node_id"] = self._next_node_id(workflow, node["id"])

        # If we ran off the graph without an explicit handoff, treat it as an agentic handoff.
        if not frame.get("node_id") and handoff is None:
            handoff = {"target": "agentic"}

        return {
            "response": response,
            "sources": sources,
            "agent_used": agent_used,
            "language": language,
            "frame": frame if frame.get("node_id") or frame.get("pending_capture") else None,
            "handoff": handoff,
            "captured_vars": captured_vars,
            "processing_time_ms": int((time.time() - start_time) * 1000),
        }

    def _invoke_agent(
        self,
        *,
        agent,
        node_data: Dict[str, Any],
        captured_vars: Dict[str, Any],
        bot_id: str,
        user_input: str,
    ):
        ctx_block = "\n".join(f"{k}: {v}" for k, v in captured_vars.items())

        override = node_data.get("system_prompt_override")
        original_sp = agent.config.get("system_prompt") if getattr(agent, "config", None) else None
        if override:
            rendered = render_template(override, captured_vars)
            if getattr(agent, "config", None) is not None:
                agent.config["system_prompt"] = rendered

        state = AgentState(
            user_input=user_input or render_template(node_data.get("prompt", ""), captured_vars),
            language="es",
            mode="WORKFLOW",
            context=ctx_block,
            bot_id=bot_id,
        )
        try:
            state = agent.process(state)
        finally:
            if override and getattr(agent, "config", None) is not None and original_sp is not None:
                agent.config["system_prompt"] = original_sp

        return state.response, state.sources, state.language

    # ── DB access ───────────────────────────────────────────────────────────

    def _load_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        try:
            result = (
                get_supabase()
                .table("workflows")
                .select("id, version, definition")
                .eq("id", workflow_id)
                .limit(1)
                .execute()
            )
        except Exception as e:
            logger.exception(f"Failed to load workflow {workflow_id}: {e}")
            return None
        if not result.data:
            return None
        row = result.data[0]
        definition = row.get("definition") or {}
        return {
            "id": row["id"],
            "version": row["version"],
            "entry_node_id": definition.get("entry_node_id"),
            "nodes": definition.get("nodes") or [],
            "edges": definition.get("edges") or [],
        }

    # ── Graph helpers ───────────────────────────────────────────────────────

    def _node(self, workflow: Dict[str, Any], node_id: str) -> Optional[Dict[str, Any]]:
        for n in workflow["nodes"]:
            if n.get("id") == node_id:
                return n
        return None

    def _next_node_id(self, workflow: Dict[str, Any], current_id: str) -> Optional[str]:
        for e in workflow["edges"]:
            if e.get("source") == current_id:
                return e.get("target")
        return None
