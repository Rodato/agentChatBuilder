"""Generic agent body used for custom specialists.

Builtins (greeting, factual, plan, ideate, sensitive, fallback) keep their
specific classes for behaviors that aren't expressible from config alone
(e.g. RAGAgent's "no encontré info" message). Custom agents created from the
UI use this class — they're parameterizable from config + tools.rag_search.
"""

from typing import Any, Optional
from loguru import logger

from .base_agent import BaseAgent, AgentState
from llm.multi_llm_client import MultiLLMClient


class GenericAgent(BaseAgent):
    """A specialist whose behavior is fully defined by its persisted config."""

    def __init__(
        self,
        name: str,
        llm_client: Optional[MultiLLMClient] = None,
        agent_config: Optional[dict] = None,
        vector_store: Optional[Any] = None,
    ):
        super().__init__(name=name, llm_client=llm_client, agent_config=agent_config, vector_store=vector_store)
        if self.llm is None:
            self.llm = MultiLLMClient()

    def process(self, state: AgentState) -> AgentState:
        self.log_processing(state)

        rag_context, sources = self.maybe_retrieve(state)

        # Build prompt: user-supplied context (e.g. captured workflow vars) +
        # retrieved RAG context + the actual user input.
        context_parts = []
        if state.context:
            context_parts.append(state.context)
        if rag_context:
            context_parts.append(rag_context)

        if context_parts:
            prompt = "Context:\n" + "\n\n".join(context_parts) + f"\n\nQuestion: {state.user_input}"
        else:
            prompt = state.user_input

        try:
            state.response = self.llm.complete(
                prompt=prompt,
                model_id=self.config.get("model", "google/gemini-2.5-flash-lite"),
                temperature=float(self.config.get("temperature", 0.7)),
                system_prompt=self.config.get("system_prompt", ""),
            )
            if sources:
                state.sources = sources
        except Exception as e:
            logger.error(f"[{self.name}] LLM error: {e}")
            state.response = "Lo siento, ocurrió un error al procesar tu solicitud."

        # agent_used is set by the orchestrator (it knows the agent_id).
        state.metadata.setdefault("agent_used", self.name.lower())
        return state
