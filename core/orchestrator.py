"""Main orchestrator for agent pipeline using LangGraph StateGraph."""

import time
import os
from typing import Dict, Any, Optional
from loguru import logger

from langgraph.graph import StateGraph, END

from .state import GraphState, AgentState
from .agent_defaults import (
    AGENT_ID_TO_INTENT,
    INTENT_TO_AGENT_ID,
    BUILTIN_AGENT_IDS,
    build_agent_configs,
    resolve_agent_for_intent,
)
from agents.greeting_agent import GreetingAgent
from agents.rag_agent import RAGAgent
from agents.plan_agent import PlanAgent
from agents.ideate_agent import IdeateAgent
from agents.sensitive_agent import SensitiveAgent
from agents.fallback_agent import FallbackAgent
from agents.generic_agent import GenericAgent
from agents.graph_worker import GraphWorker
from llm.multi_llm_client import MultiLLMClient


# Used as last-resort fallback when no bot-specific configs are loaded.
DEFAULT_AGENT_CONFIGS_BY_AGENT_ID = build_agent_configs([])


def _graph_state_to_agent_state(state: GraphState) -> AgentState:
    return AgentState(
        user_input=state["user_input"],
        language=state.get("language", "es"),
        language_config=state.get("language_config", {}),
        mode=state.get("intent", ""),
        context=state.get("context") or "",
        response="",
        sources=[],
        metadata={},
        debug_info={},
        bot_id=state.get("bot_id") or state.get("conversation_id"),
    )


_BUILTIN_CLASSES = {
    "greeting": GreetingAgent,
    "factual": RAGAgent,
    "plan": PlanAgent,
    "ideate": IdeateAgent,
    "sensitive": SensitiveAgent,
    "fallback": FallbackAgent,
}


class Orchestrator:
    """
    Main orchestrator that routes queries through the agent pipeline.

    Pipeline: language_detection → intent_routing → dispatch → END

    The intent → agent mapping is resolved at runtime (per query) so that
    custom agents registered for an intent take precedence over builtins
    without recompiling the graph.
    """

    def __init__(
        self,
        agent_configs: Optional[Dict[str, Any]] = None,
        configs_by_agent_id: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        # `configs_by_agent_id` is the new shape (Dict[agent_id, config]).
        # `agent_configs` is the legacy shape (Dict[INTENT, config]) — accepted
        # for backwards compatibility with anything still passing it.
        if configs_by_agent_id is not None:
            self.configs_by_agent_id = configs_by_agent_id
        elif agent_configs is not None and any(k in AGENT_ID_TO_INTENT.values() for k in agent_configs):
            # Legacy: convert {INTENT: cfg} into {agent_id: cfg} for the builtins only.
            self.configs_by_agent_id = {}
            for agent_id, intent in AGENT_ID_TO_INTENT.items():
                cfg = agent_configs.get(intent) or {}
                self.configs_by_agent_id[agent_id] = {
                    "agent_id": agent_id,
                    "model": cfg.get("model"),
                    "temperature": cfg.get("temperature"),
                    "system_prompt": cfg.get("system_prompt"),
                    "tools": {},
                    "is_custom": False,
                    "intents": [],
                    "enabled": True,
                    "position": 0,
                    "metadata": {},
                    "name": agent_id,
                }
        else:
            self.configs_by_agent_id = DEFAULT_AGENT_CONFIGS_BY_AGENT_ID

        self.llm = MultiLLMClient()

        # Initialize vector store only if MongoDB URI is configured.
        self.vector_store = None
        if os.getenv("MONGODB_URI"):
            try:
                from rag.vector_store import VectorStore
                self.vector_store = VectorStore()
            except Exception as e:
                logger.warning(f"Could not initialize vector store: {e}")

        self.agents: Dict[str, Any] = {}
        self.graph = self._build_graph()

    # ── Agent factory ───────────────────────────────────────────────────────

    def _instantiate_agent(self, agent_id: str, config: Dict[str, Any]):
        cls = _BUILTIN_CLASSES.get(agent_id)
        if cls is not None:
            return cls(self.llm, config, self.vector_store)
        # Custom workers: kind="graph" → GraphWorker; otherwise GenericAgent.
        if (config or {}).get("kind") == "graph":
            gw = GraphWorker(
                name=config.get("name") or agent_id,
                llm_client=self.llm,
                agent_config=config,
                vector_store=self.vector_store,
            )
            # Allow worker_ref nodes to delegate to sibling workers.
            gw.orchestrator_ref = self
            return gw
        return GenericAgent(
            name=config.get("name") or agent_id,
            llm_client=self.llm,
            agent_config=config,
            vector_store=self.vector_store,
        )

    # ── Graph ───────────────────────────────────────────────────────────────

    def _build_graph(self):
        """Build and compile the LangGraph StateGraph."""
        # Instantiate all agents we know about (builtins always; customs from config).
        for agent_id in BUILTIN_AGENT_IDS:
            cfg = self.configs_by_agent_id.get(agent_id) or {}
            self.agents[agent_id] = self._instantiate_agent(agent_id, cfg)
        for agent_id, cfg in self.configs_by_agent_id.items():
            if agent_id in self.agents:
                continue
            self.agents[agent_id] = self._instantiate_agent(agent_id, cfg)

        graph = StateGraph(GraphState)
        graph.add_node("language_detection", self._language_detection_node)
        graph.add_node("intent_routing", self._intent_routing_node)
        graph.add_node("dispatch", self._dispatch_node)

        graph.set_entry_point("language_detection")
        graph.add_edge("language_detection", "intent_routing")
        graph.add_edge("intent_routing", "dispatch")
        graph.add_edge("dispatch", END)

        return graph.compile()

    # ── Nodes ───────────────────────────────────────────────────────────────

    def _language_detection_node(self, state: GraphState) -> GraphState:
        import re
        text = state["user_input"].lower()

        def has_word(word, t):
            return bool(re.search(rf"\b{re.escape(word)}\b", t))

        if any(has_word(w, text) for w in ["olá", "obrigado", "como vai", "bom dia", "boa tarde", "tudo bem"]):
            state["language"] = "pt"
        elif any(has_word(w, text) for w in ["hello", "hi", "thanks", "how are", "good morning"]):
            state["language"] = "en"
        else:
            state["language"] = "es"
        state["debug_info"]["language_detection"] = state["language"]
        return state

    def _intent_routing_node(self, state: GraphState) -> GraphState:
        text = state["user_input"].lower()

        greeting_words = ["hola", "hello", "hi", "buenos", "buenas", "hey", "saludos", "bom dia", "boa tarde"]
        plan_words = ["plan", "cómo puedo", "how can i", "pasos", "steps", "implementar", "implement", "estrategia"]
        ideate_words = ["ideas", "brainstorm", "creatividad", "innova", "propón", "suggest", "ocurrencia"]
        sensitive_words = ["depresión", "ansiedad", "suicid", "crisis", "ayuda urgente", "depression", "anxiety"]

        if any(w in text for w in greeting_words):
            state["intent"] = "GREETING"
            state["intent_confidence"] = 0.9
        elif any(w in text for w in sensitive_words):
            state["intent"] = "SENSITIVE"
            state["intent_confidence"] = 0.9
        elif any(w in text for w in plan_words):
            state["intent"] = "PLAN"
            state["intent_confidence"] = 0.8
        elif any(w in text for w in ideate_words):
            state["intent"] = "IDEATE"
            state["intent_confidence"] = 0.8
        elif "?" in text or len(text) > 20:
            state["intent"] = "FACTUAL"
            state["intent_confidence"] = 0.7
        else:
            state["intent"] = "AMBIGUOUS"
            state["intent_confidence"] = 0.5

        state["debug_info"]["intent"] = state["intent"]
        state["debug_info"]["intent_confidence"] = state["intent_confidence"]
        return state

    def _dispatch_node(self, state: GraphState) -> GraphState:
        """Resolve intent → agent_id (custom-or-builtin) and run that agent."""
        intent = state.get("intent", "AMBIGUOUS")
        agent_id = resolve_agent_for_intent(intent, self.configs_by_agent_id)
        agent = self.agents.get(agent_id) or self.agents.get("fallback")
        if agent is None:
            state["response"] = self._get_error_message(state.get("language", "es"))
            state["agent_used"] = "error_handler"
            return state

        s = _graph_state_to_agent_state(state)
        s = agent.process(s)
        state["response"] = s.response
        state["sources"] = s.sources
        # Agent_used: prefer the resolved agent_id (so customs show up in UI meta).
        state["agent_used"] = s.metadata.get("agent_used") or agent_id
        return state

    # ── Public API ──────────────────────────────────────────────────────────

    def process_query(
        self,
        user_input: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()

        initial_state: GraphState = {
            "user_input": user_input,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "bot_id": bot_id,
            "language": "es",
            "language_config": {},
            "detected_filters": {},
            "intent": "AMBIGUOUS",
            "intent_confidence": 0.0,
            "agent_configs": self.configs_by_agent_id,
            "response": "",
            "sources": [],
            "agent_used": "",
            "context": context,
            "debug_info": {},
            "processing_time_ms": 0,
        }

        try:
            result = self.graph.invoke(initial_state)
        except Exception as e:
            logger.error(f"Orchestrator error: {e}")
            result = initial_state
            result["response"] = self._get_error_message(initial_state["language"])
            result["agent_used"] = "error_handler"
            result["debug_info"]["error"] = str(e)

        result["processing_time_ms"] = int((time.time() - start_time) * 1000)

        return {
            "response": result["response"],
            "sources": result["sources"],
            "agent_used": result["agent_used"],
            "language": result["language"],
            "intent": result["intent"],
            "intent_confidence": result["intent_confidence"],
            "processing_time_ms": result["processing_time_ms"],
            "debug_info": result["debug_info"],
        }

    def get_agent(self, agent_id: str):
        """Return an agent instance by id (builtins or customs)."""
        return self.agents.get(agent_id)

    def _get_error_message(self, language: str) -> str:
        messages = {
            "es": "Lo siento, ocurrió un error. Por favor intenta de nuevo.",
            "en": "Sorry, an error occurred. Please try again.",
            "pt": "Desculpe, ocorreu um erro. Por favor, tente novamente.",
        }
        return messages.get(language, messages["es"])
