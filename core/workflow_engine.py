"""Stack-aware workflow execution engine.

Each user turn is executed against the **top frame** of `conversations.workflow_stack`.
A frame is: `{workflow_id, node_id, pending_capture?}`. The engine itself does not
decide when to push/pop frames — that is the responsibility of `core.chat_engine.ChatEngine`,
which interprets the engine's `handoff` output.

Node types supported:
- `message`   — emits fixed text and advances in the same turn (non-blocking)
- `capture`   — stores user input into a named variable with optional type validation
- `agent`     — invokes a specialized agent and emits its response
- `handoff`   — signals a transition back to agentic mode or to another workflow
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from db import get_supabase
from core.state import AgentState


MAX_ITERATIONS_PER_TURN = 20

_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")

VALID_DATA_TYPES = {"text", "number", "email", "date", "boolean", "phone"}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"[+\d()\s\-]{6,}")
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%y")
_BOOLEAN_TRUE = {"si", "sí", "yes", "true", "1", "on", "ok", "claro", "dale"}
_BOOLEAN_FALSE = {"no", "false", "0", "off", "nope"}


def validate_capture_value(value: str, data_type: str) -> Tuple[bool, Any, Optional[str]]:
    """Returns (ok, normalized_value, error_message).

    For ok=True, `normalized_value` is the value to persist (typed when possible).
    For ok=False, `error_message` is a user-facing string explaining the issue.
    """
    raw = (value or "").strip()
    dt = (data_type or "text").lower()
    if not raw:
        return False, None, "El valor no puede estar vacío."
    if dt == "text":
        return True, raw, None
    if dt == "number":
        try:
            if "." in raw or "," in raw:
                return True, float(raw.replace(",", ".")), None
            return True, int(raw), None
        except ValueError:
            return False, None, "Necesito un número válido."
    if dt == "email":
        return (True, raw.lower(), None) if _EMAIL_RE.match(raw) else (False, None, "Necesito un correo electrónico válido (ej: nombre@ejemplo.com).")
    if dt == "phone":
        return (True, raw, None) if _PHONE_RE.search(raw) else (False, None, "Necesito un número de teléfono válido.")
    if dt == "boolean":
        low = raw.lower()
        if low in _BOOLEAN_TRUE:
            return True, True, None
        if low in _BOOLEAN_FALSE:
            return True, False, None
        return False, None, "Responde sí o no."
    if dt == "date":
        for fmt in _DATE_FORMATS:
            try:
                d = datetime.strptime(raw, fmt).date()
                return True, d.isoformat(), None
            except ValueError:
                continue
        return False, None, "Necesito una fecha válida (ej: 2026-04-28 o 28/04/2026)."
    # Unknown type — accept as text.
    return True, raw, None


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
            pc = frame["pending_capture"]
            var_name = pc["var_name"]
            data_type = pc.get("data_type") or "text"
            ok, normalized, err = validate_capture_value(user_input, data_type)
            if ok:
                captured_vars[var_name] = (
                    sanitize_value(normalized) if isinstance(normalized, str) else normalized
                )
                frame["pending_capture"] = None
                frame["node_id"] = self._next_node_id(workflow, frame["node_id"])
            else:
                # Validation failed — keep pending_capture, re-prompt.
                node = self._node(workflow, frame["node_id"])
                retry_prompt = render_template(
                    (node.get("data") or {}).get("prompt", "") if node else "",
                    captured_vars,
                )
                response = f"{err} {retry_prompt}".strip() if retry_prompt else err
                return {
                    "response": response or "El valor no es válido. Inténtalo de nuevo.",
                    "sources": [],
                    "agent_used": "capture",
                    "language": "es",
                    "frame": frame,
                    "handoff": None,
                    "captured_vars": captured_vars,
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                }

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

            if ntype == "message":
                text = render_template(data.get("text") or data.get("prompt") or "", captured_vars)
                if text:
                    response = (response + "\n\n" + text) if response else text
                if agent_used is None:
                    agent_used = "message"
                frame["node_id"] = self._next_node_id(workflow, node["id"])
                continue  # advance to next node in the same turn

            if ntype == "capture":
                var_name = data.get("var_name")
                if not var_name:
                    frame["node_id"] = self._next_node_id(workflow, node["id"])
                    continue
                if data.get("skip_if_present") and var_name in captured_vars:
                    frame["node_id"] = self._next_node_id(workflow, node["id"])
                    continue
                frame["pending_capture"] = {
                    "var_name": var_name,
                    "data_type": data.get("data_type") or "text",
                }
                rendered = render_template(data.get("prompt", ""), captured_vars)
                response = (response + "\n\n" + rendered) if response and rendered else (response or rendered)
                agent_used = "capture"
                break

            if ntype == "agent":
                agent_id = data.get("agent_id")
                agent = self.orch.get_agent(agent_id) if agent_id else None
                if agent is None:
                    logger.warning(f"Unknown agent_id '{agent_id}' — skipping node.")
                    frame["node_id"] = self._next_node_id(workflow, node["id"])
                    continue
                agent_response, agent_sources, agent_language = self._invoke_agent(
                    agent=agent,
                    node_data=data,
                    captured_vars=captured_vars,
                    bot_id=bot_id,
                    user_input=user_input or "",
                )
                response = (response + "\n\n" + agent_response) if response and agent_response else (response or agent_response)
                sources = agent_sources or sources
                language = agent_language or language
                agent_used = agent_id
                frame["node_id"] = self._next_node_id(workflow, node["id"])
                break

            if ntype == "handoff":
                farewell = render_template(data.get("farewell"), captured_vars)
                if farewell:
                    response = (response + "\n\n" + farewell) if response else farewell
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
