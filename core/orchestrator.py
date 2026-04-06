"""Main orchestrator for agent pipeline using LangGraph StateGraph."""

import time
import os
from typing import Dict, Any, Optional
from loguru import logger

from langgraph.graph import StateGraph, END

from .state import GraphState, AgentState
from agents.greeting_agent import GreetingAgent
from agents.rag_agent import RAGAgent
from agents.plan_agent import PlanAgent
from agents.ideate_agent import IdeateAgent
from agents.sensitive_agent import SensitiveAgent
from agents.fallback_agent import FallbackAgent
from llm.multi_llm_client import MultiLLMClient, LLMProvider


DEFAULT_AGENT_CONFIGS = {
    "GREETING": {
        "model": "mistral-7b",
        "temperature": 0.7,
        "system_prompt": "You are a friendly and welcoming assistant. Greet the user warmly and ask how you can help them.",
    },
    "FACTUAL": {
        "model": "mistral-7b",
        "temperature": 0.3,
        "system_prompt": "You are a knowledgeable assistant. Answer questions accurately based on the provided context.",
    },
    "PLAN": {
        "model": "gpt-4o-mini",
        "temperature": 0.5,
        "system_prompt": "You are a strategic planning assistant. Help users create detailed, actionable plans.",
    },
    "IDEATE": {
        "model": "gemini-flash",
        "temperature": 0.9,
        "system_prompt": "You are a creative brainstorming partner. Generate diverse, innovative ideas.",
    },
    "SENSITIVE": {
        "model": "gpt-4o-mini",
        "temperature": 0.3,
        "system_prompt": "You are a compassionate and careful assistant. Handle sensitive topics with empathy.",
    },
    "AMBIGUOUS": {
        "model": "mistral-7b",
        "temperature": 0.5,
        "system_prompt": "You are a helpful assistant. When a query is unclear, ask clarifying questions.",
    },
}


def _graph_state_to_agent_state(state: GraphState) -> AgentState:
    return AgentState(
        user_input=state["user_input"],
        language=state.get("language", "es"),
        language_config=state.get("language_config", {}),
        mode=state.get("intent", ""),
        context="",
        response="",
        sources=[],
        metadata={},
        debug_info={},
    )


def make_agent_node(agent, agent_key: str):
    """Create a LangGraph node function from an agent instance."""
    def node(state: GraphState) -> GraphState:
        s = _graph_state_to_agent_state(state)
        s = agent.process(s)
        state["response"] = s.response
        state["sources"] = s.sources
        state["agent_used"] = s.metadata.get("agent_used", agent_key.lower())
        return state
    node.__name__ = f"{agent_key.lower()}_node"
    return node


def route_by_intent(state: GraphState) -> str:
    """Conditional routing function based on detected intent."""
    intent_to_node = {
        "GREETING": "greeting_agent",
        "FACTUAL": "rag_agent",
        "PLAN": "plan_agent",
        "IDEATE": "ideate_agent",
        "SENSITIVE": "sensitive_agent",
        "AMBIGUOUS": "fallback_agent",
    }
    return intent_to_node.get(state.get("intent", "AMBIGUOUS"), "fallback_agent")


class Orchestrator:
    """
    Main orchestrator that routes queries through the agent pipeline.

    Pipeline: language_detection → intent_routing → [conditional] → specialized_agent → END
    """

    def __init__(self, agent_configs: Optional[Dict[str, Any]] = None):
        self.agent_configs = agent_configs or DEFAULT_AGENT_CONFIGS
        self.llm = MultiLLMClient()

        # Initialize vector store only if MongoDB URI is configured
        self.vector_store = None
        if os.getenv("MONGODB_URI"):
            try:
                from rag.vector_store import VectorStore
                self.vector_store = VectorStore()
            except Exception as e:
                logger.warning(f"Could not initialize vector store: {e}")

        self.graph = self._build_graph()

    def _build_graph(self):
        """Build and compile the LangGraph StateGraph."""
        # Instantiate agents with their configs
        greeting = GreetingAgent(self.llm, self.agent_configs.get("GREETING"))
        rag = RAGAgent(self.llm, self.agent_configs.get("FACTUAL"), self.vector_store)
        plan = PlanAgent(self.llm, self.agent_configs.get("PLAN"), self.vector_store)
        ideate = IdeateAgent(self.llm, self.agent_configs.get("IDEATE"))
        sensitive = SensitiveAgent(self.llm, self.agent_configs.get("SENSITIVE"))
        fallback = FallbackAgent(self.llm, self.agent_configs.get("AMBIGUOUS"))

        graph = StateGraph(GraphState)

        # Detection and routing nodes
        graph.add_node("language_detection", self._language_detection_node)
        graph.add_node("intent_routing", self._intent_routing_node)

        # Specialized agent nodes
        graph.add_node("greeting_agent", make_agent_node(greeting, "GREETING"))
        graph.add_node("rag_agent", make_agent_node(rag, "FACTUAL"))
        graph.add_node("plan_agent", make_agent_node(plan, "PLAN"))
        graph.add_node("ideate_agent", make_agent_node(ideate, "IDEATE"))
        graph.add_node("sensitive_agent", make_agent_node(sensitive, "SENSITIVE"))
        graph.add_node("fallback_agent", make_agent_node(fallback, "AMBIGUOUS"))

        # Edges
        graph.set_entry_point("language_detection")
        graph.add_edge("language_detection", "intent_routing")
        graph.add_conditional_edges(
            "intent_routing",
            route_by_intent,
            {
                "greeting_agent": "greeting_agent",
                "rag_agent": "rag_agent",
                "plan_agent": "plan_agent",
                "ideate_agent": "ideate_agent",
                "sensitive_agent": "sensitive_agent",
                "fallback_agent": "fallback_agent",
            },
        )
        for node in ["greeting_agent", "rag_agent", "plan_agent", "ideate_agent", "sensitive_agent", "fallback_agent"]:
            graph.add_edge(node, END)

        return graph.compile()

    def _language_detection_node(self, state: GraphState) -> GraphState:
        """Detect language from user input."""
        text = state["user_input"].lower()
        # Simple heuristic; replace with LanguageAgent LLM call when available
        if any(w in text for w in ["ola", "olá", "obrigado", "como vai"]):
            state["language"] = "pt"
        elif any(w in text for w in ["hello", "hi ", "thanks", "how are"]):
            state["language"] = "en"
        else:
            state["language"] = "es"
        state["debug_info"]["language_detection"] = state["language"]
        return state

    def _intent_routing_node(self, state: GraphState) -> GraphState:
        """Classify intent from user input using keyword heuristics."""
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

    def process_query(
        self,
        user_input: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a user query through the full LangGraph pipeline."""
        start_time = time.time()

        initial_state: GraphState = {
            "user_input": user_input,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "language": "es",
            "language_config": {},
            "detected_filters": {},
            "intent": "AMBIGUOUS",
            "intent_confidence": 0.0,
            "agent_configs": self.agent_configs,
            "response": "",
            "sources": [],
            "agent_used": "",
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

    def _get_error_message(self, language: str) -> str:
        messages = {
            "es": "Lo siento, ocurrió un error. Por favor intenta de nuevo.",
            "en": "Sorry, an error occurred. Please try again.",
            "pt": "Desculpe, ocorreu um erro. Por favor, tente novamente.",
        }
        return messages.get(language, messages["es"])
