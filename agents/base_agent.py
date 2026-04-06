"""Base agent class for all specialized agents."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class AgentState:
    """State passed to and from agents."""

    user_input: str
    language: str = "es"
    language_config: Dict[str, Any] = field(default_factory=dict)
    mode: str = ""  # intent type
    context: str = ""
    response: str = ""
    sources: list = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    debug_info: Dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """
    Abstract base class for all specialized agents.

    All agents must implement:
    - process(state) -> state: Main processing logic
    """

    def __init__(self, name: str, llm_client: Optional[Any] = None):
        self.name = name
        self.llm = llm_client

    @abstractmethod
    def process(self, state: AgentState) -> AgentState:
        """
        Process the state and return modified state with response.

        Args:
            state: Current agent state

        Returns:
            Modified state with response populated
        """
        pass

    def should_process(self, state: AgentState) -> bool:
        """
        Validate if this agent should process the state.

        Override in subclasses for specific validation.
        """
        return bool(state.user_input)

    def log_processing(self, state: AgentState):
        """Log the start of processing."""
        preview = state.user_input[:50] + "..." if len(state.user_input) > 50 else state.user_input
        logger.info(f"[{self.name}] Processing: {preview}")

    def add_debug_info(self, state: AgentState, info: Dict[str, Any]) -> AgentState:
        """Add debug information to state."""
        state.debug_info[self.name] = info
        return state

    def get_system_prompt(self, state: AgentState) -> str:
        """
        Get the system prompt for this agent.

        Override in subclasses for specific prompts.
        """
        return f"You are a helpful assistant responding in {state.language}."

    def format_response(self, response: str, state: AgentState) -> str:
        """
        Format the response for the channel.

        Override for channel-specific formatting (WhatsApp, Telegram, etc.)
        """
        return response.strip()
