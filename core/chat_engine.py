"""Top-level coordinator: decides per-turn whether the WorkflowEngine or
the Orchestrator (agentic) drives the conversation.

State of a conversation is the tuple `(workflow_stack, captured_vars)`.
- Non-empty stack → top frame runs through WorkflowEngine.
- Empty stack    → Orchestrator handles the turn (intent routing + agent).

Transitions:
- Agentic → Workflow: (a) intent router matches a workflow with `trigger_type='on_intent'`,
  or (b) an agent's response is a JSON `{"trigger_flow": <id>}`.
- Workflow → Agentic: engine returned `handoff.target='agentic'` → pop frame.
- Workflow → Workflow (handoff): engine returned `handoff.target='workflow'` → pop + push new frame.
- on_start: when a conversation is created and no stack exists yet, push the bot's
  `on_start` workflow if any.

This module also handles the persistence of `conversations` (workflow_stack, captured_vars,
mode, status).
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

from db import get_supabase
from core.state import AgentState
from core.workflow_engine import WorkflowEngine, render_template


MAX_STACK_DEPTH = 5


class ChatEngine:
    def __init__(self, orchestrator):
        self.orch = orchestrator
        self.wf = WorkflowEngine(orchestrator)

    # ── Public API ──────────────────────────────────────────────────────────

    def start(self, *, bot_id: str, conversation_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Kickoff: returns the first bot message without consuming user input."""
        start_time = time.time()
        conv = self._load_or_create_conversation(conversation_id=conversation_id, bot_id=bot_id, user_id=user_id)

        # If the conversation already has state, don't re-initialize; just return a no-op greeting.
        if conv.get("workflow_stack") or conv.get("status") in ("completed", "aborted"):
            pass

        # Try to push on_start if nothing is running.
        if not conv.get("workflow_stack"):
            on_start_id = self._find_workflow(bot_id=bot_id, trigger_type="on_start")
            if on_start_id:
                self._push_frame(conv, on_start_id)
                return self._run_current_frame(bot_id=bot_id, conv=conv, user_input=None, started_at=start_time)

        # No onboarding workflow → try the greeting worker, else generic fallback.
        welcome, agent_used = self._compute_welcome(bot_id)
        self._persist(conv)
        return {
            "response": welcome,
            "agent_used": agent_used,
            "intent": None,
            "language": "es",
            "sources": [],
            "conversation_id": conv["id"],
            "mode": conv.get("mode", "agentic"),
            "status": conv.get("status", "active"),
            "processing_time_ms": int((time.time() - start_time) * 1000),
        }

    def step(self, *, bot_id: str, conversation_id: str, user_input: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        start_time = time.time()
        conv = self._load_or_create_conversation(conversation_id=conversation_id, bot_id=bot_id, user_id=user_id)

        # If running a workflow, execute its top frame.
        if conv.get("workflow_stack"):
            return self._run_current_frame(bot_id=bot_id, conv=conv, user_input=user_input, started_at=start_time)

        # Agentic mode. Run the orchestrator first.
        orch_result = self.orch.process_query(
            user_input=user_input,
            user_id=user_id,
            conversation_id=conversation_id,
            bot_id=bot_id,
            context=self._vars_to_context(conv),
        )

        # Intent-triggered workflow?
        intent = orch_result.get("intent")
        on_intent_id = self._find_workflow(bot_id=bot_id, trigger_type="on_intent", trigger_value=intent) if intent else None
        if on_intent_id:
            if not self._push_frame(conv, on_intent_id):
                return self._stack_overflow_response(conv, start_time)
            wf_result = self._run_current_frame(bot_id=bot_id, conv=conv, user_input=None, started_at=start_time)
            # Preserve intent for telemetry
            wf_result["intent"] = intent
            return wf_result

        # Agent-emitted trigger_flow?
        trigger = _parse_trigger_flow(orch_result.get("response") or "")
        if trigger:
            target_id = self._resolve_manual_workflow(bot_id=bot_id, identifier=trigger["workflow_id"])
            if target_id:
                if not self._push_frame(conv, target_id):
                    return self._stack_overflow_response(conv, start_time)
                wf_result = self._run_current_frame(bot_id=bot_id, conv=conv, user_input=None, started_at=start_time)
                wf_result["intent"] = intent
                wf_result["agent_used"] = f"{orch_result.get('agent_used')}→{wf_result.get('agent_used')}"
                return wf_result
            # Unknown workflow_id → fall through with a safe message.
            orch_result["response"] = "No pude iniciar ese flujo. ¿Puedes reformular?"

        self._persist(conv)
        return {
            "response": orch_result.get("response", ""),
            "agent_used": orch_result.get("agent_used", ""),
            "intent": intent,
            "language": orch_result.get("language", "es"),
            "sources": orch_result.get("sources", []),
            "conversation_id": conv["id"],
            "mode": "agentic",
            "status": conv.get("status", "active"),
            "processing_time_ms": int((time.time() - start_time) * 1000),
        }

    # ── Frame execution ─────────────────────────────────────────────────────

    def _run_current_frame(self, *, bot_id: str, conv: Dict[str, Any], user_input: Optional[str], started_at: float) -> Dict[str, Any]:
        """Run the top frame; apply stack transitions; recurse if a handoff leaves us in another frame or agentic."""
        frame = conv["workflow_stack"][-1]
        vars_before = dict(conv.get("captured_vars") or {})

        if user_input is None:
            result = self.wf.start(bot_id=bot_id, frame=frame, captured_vars=vars_before)
        else:
            result = self.wf.step(bot_id=bot_id, frame=frame, captured_vars=vars_before, user_input=user_input)

        conv["captured_vars"] = result.get("captured_vars") or vars_before

        # Update the top frame in-place with the returned state (or remove it).
        updated_frame = result.get("frame")
        if updated_frame:
            conv["workflow_stack"][-1] = updated_frame
        else:
            conv["workflow_stack"].pop()

        handoff = result.get("handoff")
        response = result.get("response") or ""
        agent_used = result.get("agent_used")
        language = result.get("language", "es")
        sources = result.get("sources", [])

        # Apply transitions. If the frame produced a response, we end the turn here.
        # If the handoff leaves us in a continuation (next frame / agentic kickoff) AND
        # the frame did NOT produce user-visible text, we run the next frame to produce one.
        if handoff and handoff.get("target") == "workflow" and handoff.get("target_workflow_id"):
            if not self._push_frame(conv, handoff["target_workflow_id"]):
                return self._stack_overflow_response(conv, started_at)
            # Only chain into the new frame if we don't yet have text.
            if not response:
                return self._run_current_frame(bot_id=bot_id, conv=conv, user_input=None, started_at=started_at)

        # If a workflow completed silently (no response) and we're back to agentic, fall through to orchestrator with the pending user input.
        if not response and not conv.get("workflow_stack") and user_input:
            # Recompute as agentic turn with the same user_input.
            return self.step(bot_id=bot_id, conversation_id=conv["id"], user_input=user_input, user_id=conv.get("user_id"))

        self._persist(conv)
        return {
            "response": response,
            "agent_used": agent_used,
            "intent": "WORKFLOW",
            "language": language,
            "sources": sources,
            "conversation_id": conv["id"],
            "mode": "workflow" if conv.get("workflow_stack") else "agentic",
            "status": conv.get("status", "active"),
            "processing_time_ms": int((time.time() - started_at) * 1000),
        }

    def _push_frame(self, conv: Dict[str, Any], workflow_id: str) -> bool:
        stack = conv.get("workflow_stack") or []
        if len(stack) >= MAX_STACK_DEPTH:
            return False
        stack.append({"workflow_id": workflow_id, "node_id": None, "pending_capture": None})
        conv["workflow_stack"] = stack
        conv["mode"] = "workflow"
        return True

    def _stack_overflow_response(self, conv: Dict[str, Any], started_at: float) -> Dict[str, Any]:
        logger.error("Workflow stack overflow — aborting.")
        conv["workflow_stack"] = []
        conv["mode"] = "agentic"
        conv["status"] = "aborted"
        self._persist(conv)
        return {
            "response": "Se detectó un ciclo de workflows. Reinicia la conversación para continuar.",
            "agent_used": "error",
            "intent": None,
            "language": "es",
            "sources": [],
            "conversation_id": conv["id"],
            "mode": "agentic",
            "status": "aborted",
            "processing_time_ms": int((time.time() - started_at) * 1000),
        }

    # ── DB helpers ─────────────────────────────────────────────────────────

    def _load_or_create_conversation(
        self, *, conversation_id: str, bot_id: str, user_id: Optional[str]
    ) -> Dict[str, Any]:
        sb = get_supabase()
        try:
            result = sb.table("conversations").select("*").eq("id", conversation_id).limit(1).execute()
            if result.data:
                conv = result.data[0]
                conv.setdefault("captured_vars", {})
                conv.setdefault("workflow_stack", [])
                return conv
        except Exception as e:
            logger.warning(f"Conversation lookup failed ({conversation_id}): {e}")

        row = {
            "id": conversation_id,
            "bot_id": bot_id,
            "user_id": user_id,
            "workflow_stack": [],
            "captured_vars": {},
            "mode": "agentic",
            "status": "active",
        }
        try:
            created = sb.table("conversations").insert(row).execute()
            return created.data[0]
        except Exception as e:
            logger.exception(f"Failed to create conversation {conversation_id}: {e}")
            return row

    def _persist(self, conv: Dict[str, Any]) -> None:
        try:
            update_row = {
                "workflow_stack": conv.get("workflow_stack") or [],
                "captured_vars": conv.get("captured_vars") or {},
                "mode": "workflow" if conv.get("workflow_stack") else "agentic",
                "status": conv.get("status", "active"),
                "last_activity_at": "now()",
            }
            get_supabase().table("conversations").update(update_row).eq("id", conv["id"]).execute()
        except Exception as e:
            logger.warning(f"Failed to persist conversation {conv.get('id')}: {e}")

    # Precedence for the kickoff message of a brand-new conversation:
    #   1. (caller) workflow on_start enabled → executed before reaching this method
    #   2. greeting worker enabled → invoke it here with a synthetic prompt
    #   3. generic localized hardcoded fallback
    _GENERIC_WELCOME = {
        "es": "¡Hola! ¿En qué puedo ayudarte?",
        "en": "Hi! How can I help you?",
        "pt": "Olá! Como posso ajudar?",
    }

    def _compute_welcome(self, bot_id: str) -> tuple[str, str]:
        """Returns (response_text, agent_used)."""
        greeting_agent = self.orch.get_agent("greeting") if self.orch else None
        greeting_enabled = bool(
            self.orch
            and (self.orch.configs_by_agent_id.get("greeting") or {}).get("enabled")
        )
        if greeting_agent and greeting_enabled:
            try:
                state = AgentState(
                    user_input="",
                    language="es",
                    mode="WELCOME",
                    bot_id=bot_id,
                )
                state = greeting_agent.process(state)
                if (state.response or "").strip():
                    return state.response.strip(), state.metadata.get("agent_used", "greeting")
            except Exception as e:
                logger.warning(f"[chat_engine] greeting worker failed for kickoff {bot_id}: {e}")
        return self._GENERIC_WELCOME["es"], "welcome"

    # ── Workflow lookups ───────────────────────────────────────────────────

    def _find_workflow(self, *, bot_id: str, trigger_type: str, trigger_value: Optional[str] = None) -> Optional[str]:
        try:
            q = (
                get_supabase()
                .table("workflows")
                .select("id")
                .eq("bot_id", bot_id)
                .eq("trigger_type", trigger_type)
                .eq("enabled", True)
            )
            if trigger_value is not None:
                q = q.eq("trigger_value", trigger_value)
            result = q.limit(1).execute()
            if result.data:
                return result.data[0]["id"]
        except Exception as e:
            logger.warning(f"_find_workflow failed: {e}")
        return None

    def _resolve_manual_workflow(self, *, bot_id: str, identifier: str) -> Optional[str]:
        """Resolve a workflow referenced by the LLM — can be an id or a name."""
        if not identifier:
            return None
        try:
            # Try exact id match first.
            result = (
                get_supabase()
                .table("workflows")
                .select("id")
                .eq("bot_id", bot_id)
                .eq("id", identifier)
                .eq("trigger_type", "manual")
                .eq("enabled", True)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]["id"]
            # Fall back to name match.
            result = (
                get_supabase()
                .table("workflows")
                .select("id")
                .eq("bot_id", bot_id)
                .eq("name", identifier)
                .eq("trigger_type", "manual")
                .eq("enabled", True)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]["id"]
        except Exception as e:
            logger.warning(f"_resolve_manual_workflow failed: {e}")
        return None

    def _vars_to_context(self, conv: Dict[str, Any]) -> Optional[str]:
        vars = conv.get("captured_vars") or {}
        if not vars:
            return None
        return "\n".join(f"{k}: {v}" for k, v in vars.items())


# ── Helpers ─────────────────────────────────────────────────────────────────

import json  # placed here because only _parse_trigger_flow needs it


def _parse_trigger_flow(text: str) -> Optional[Dict[str, Any]]:
    """Return {'workflow_id': ..., 'reason': ...} if text is JSON trigger, else None."""
    if not text:
        return None
    s = text.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return None
    try:
        data = json.loads(s)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    key = "trigger_flow"
    if key not in data:
        return None
    return {"workflow_id": str(data[key]), "reason": str(data.get("reason", ""))}
