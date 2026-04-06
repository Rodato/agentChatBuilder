"""Greeting agent for handling welcome and greeting intents."""

from typing import Optional
from loguru import logger

from .base_agent import BaseAgent, AgentState
from llm.multi_llm_client import MultiLLMClient


DEFAULT_CONFIG = {
    "model": "google/gemini-2.5-flash-lite",
    "temperature": 0.7,
    "system_prompt": "You are a friendly and welcoming assistant. Greet the user warmly and ask how you can help them.",
}


class GreetingAgent(BaseAgent):
    """Handles greeting and welcome intents."""

    def __init__(self, llm_client: Optional[MultiLLMClient] = None, agent_config: dict = None):
        super().__init__("GreetingAgent", llm_client)
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
            logger.error(f"GreetingAgent error: {e}")
            fallbacks = {"es": "¡Hola! ¿En qué puedo ayudarte?", "en": "Hello! How can I help you?", "pt": "Olá! Como posso ajudar?"}
            state.response = fallbacks.get(state.language, fallbacks["es"])

        state.metadata["agent_used"] = "greeting"
        return state
