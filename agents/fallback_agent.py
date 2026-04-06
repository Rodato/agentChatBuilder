"""Fallback agent for ambiguous or unclear queries."""

from typing import Optional
from loguru import logger

from .base_agent import BaseAgent, AgentState
from llm.multi_llm_client import MultiLLMClient


DEFAULT_CONFIG = {
    "model": "google/gemini-2.5-flash-lite",
    "temperature": 0.5,
    "system_prompt": "You are a helpful assistant. When a query is unclear, ask clarifying questions to better understand what the user needs. Be friendly and guide the conversation.",
}


class FallbackAgent(BaseAgent):
    """Handles ambiguous or unclear queries by asking for clarification."""

    def __init__(self, llm_client: Optional[MultiLLMClient] = None, agent_config: dict = None):
        super().__init__("FallbackAgent", llm_client)
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
            logger.error(f"FallbackAgent error: {e}")
            fallbacks = {
                "es": "No estoy seguro de entender. ¿Podrías darme más detalles?",
                "en": "I'm not sure I understand. Could you give me more details?",
                "pt": "Não tenho certeza se entendi. Poderia me dar mais detalhes?",
            }
            state.response = fallbacks.get(state.language, fallbacks["es"])

        state.metadata["agent_used"] = "fallback"
        return state
