"""Ideate agent for creative brainstorming."""

from typing import Optional
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

    def __init__(self, llm_client: Optional[MultiLLMClient] = None, agent_config: dict = None):
        super().__init__("IdeateAgent", llm_client)
        self.config = agent_config or DEFAULT_CONFIG
        if self.llm is None:
            self.llm = MultiLLMClient()

    def process(self, state: AgentState) -> AgentState:
        self.log_processing(state)

        try:
            state.response = self.llm.complete(
                prompt=state.user_input,
                model_id=self.config["model"],
                temperature=self.config["temperature"],
                system_prompt=self.config["system_prompt"],
            )
        except Exception as e:
            logger.error(f"IdeateAgent error: {e}")
            state.response = "No pude generar ideas en este momento. Por favor intenta de nuevo."

        state.metadata["agent_used"] = "ideate"
        return state
