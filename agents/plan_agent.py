"""Plan agent for handling planning and workshop intents."""

from typing import Any, Optional
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
        agent_config: Optional[dict] = None,
        vector_store: Optional[Any] = None,
    ):
        super().__init__(
            name="PlanAgent",
            llm_client=llm_client,
            agent_config=agent_config or DEFAULT_CONFIG,
            vector_store=vector_store,
        )
        if self.llm is None:
            self.llm = MultiLLMClient()

    def process(self, state: AgentState) -> AgentState:
        self.log_processing(state)

        rag_context, sources = self.maybe_retrieve(state)
        prompt = (
            f"Context:\n{rag_context}\n\nRequest: {state.user_input}"
            if rag_context
            else state.user_input
        )
        if sources:
            state.sources = sources

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
