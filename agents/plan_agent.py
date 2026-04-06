"""Plan agent for handling planning and workshop intents."""

from typing import Optional, Any
from loguru import logger

from .base_agent import BaseAgent, AgentState
from llm.multi_llm_client import MultiLLMClient


DEFAULT_CONFIG = {
    "model": "anthropic/claude-sonnet-4.6",
    "temperature": 0.5,
    "system_prompt": "You are a strategic planning assistant. Help users create detailed, actionable plans. Be structured and thorough.",
}


class PlanAgent(BaseAgent):
    """Handles planning and implementation queries."""

    def __init__(
        self,
        llm_client: Optional[MultiLLMClient] = None,
        agent_config: dict = None,
        vector_store: Optional[Any] = None,
    ):
        super().__init__("PlanAgent", llm_client)
        self.config = agent_config or DEFAULT_CONFIG
        self.vector_store = vector_store
        if self.llm is None:
            self.llm = MultiLLMClient()

    def process(self, state: AgentState) -> AgentState:
        self.log_processing(state)

        # Enrich with RAG context if available
        prompt = state.user_input
        if self.vector_store:
            try:
                results = self.vector_store.search(state.user_input, top_k=5)
                if results:
                    context = "\n\n".join(r.get("content", "") for r in results)
                    prompt = f"Context:\n{context}\n\nRequest: {state.user_input}"
                    state.sources = results
            except Exception as e:
                logger.warning(f"PlanAgent RAG search failed: {e}")

        try:
            state.response = self.llm.complete(
                prompt=prompt,
                model_id=self.config["model"],
                temperature=self.config["temperature"],
                system_prompt=self.config["system_prompt"],
            )
        except Exception as e:
            logger.error(f"PlanAgent error: {e}")
            state.response = "Lo siento, no pude generar un plan en este momento."

        state.metadata["agent_used"] = "plan"
        return state
