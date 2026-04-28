"""Ideate agent for creative brainstorming."""

from typing import Any, Optional
from loguru import logger

from .base_agent import BaseAgent, AgentState
from llm.multi_llm_client import MultiLLMClient


DEFAULT_CONFIG = {
    "model": "mistralai/mistral-small-creative",
    "temperature": 0.9,
    "system_prompt": "You are a creative brainstorming partner. Generate diverse, innovative, and inspiring ideas. Think outside the box and encourage creative thinking.",
}


class IdeateAgent(BaseAgent):
    """Handles creative ideation and brainstorming requests."""

    def __init__(
        self,
        llm_client: Optional[MultiLLMClient] = None,
        agent_config: Optional[dict] = None,
        vector_store: Optional[Any] = None,
    ):
        super().__init__(
            name="IdeateAgent",
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

        try:
            state.response = self.llm.complete(
                prompt=prompt,
                model_id=self.config["model"],
                temperature=self.config["temperature"],
                system_prompt=self.config["system_prompt"],
            )
            if sources:
                state.sources = sources
        except Exception as e:
            logger.error(f"IdeateAgent error: {e}")
            state.response = "No pude generar ideas en este momento. Por favor intenta de nuevo."

        state.metadata["agent_used"] = "ideate"
        return state
