"""Sensitive agent for handling delicate topics carefully."""

from typing import Optional
from loguru import logger

from .base_agent import BaseAgent, AgentState
from llm.multi_llm_client import MultiLLMClient


DEFAULT_CONFIG = {
    "model": "anthropic/claude-sonnet-4.6",
    "temperature": 0.3,
    "system_prompt": "You are a compassionate and careful assistant. Handle sensitive topics with empathy and respect. Provide supportive responses and suggest professional help when appropriate.",
}


class SensitiveAgent(BaseAgent):
    """Handles sensitive and delicate topic queries."""

    def __init__(self, llm_client: Optional[MultiLLMClient] = None, agent_config: dict = None):
        super().__init__("SensitiveAgent", llm_client)
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
            logger.error(f"SensitiveAgent error: {e}")
            state.response = "Entiendo que esto es un tema delicado. Por favor contacta a un profesional si necesitas ayuda especializada."

        state.metadata["agent_used"] = "sensitive"
        state.metadata["human_handoff"] = True
        return state
