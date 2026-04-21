"""State definitions for the agent orchestrator."""

from typing import TypedDict, Optional, List, Dict, Any
from dataclasses import dataclass, field


class GraphState(TypedDict):
    """State passed through the LangGraph pipeline."""

    # Input
    user_input: str
    user_id: Optional[str]
    conversation_id: Optional[str]
    bot_id: Optional[str]

    # Detection results
    language: str  # es, en, pt
    language_config: Dict[str, Any]
    detected_filters: Dict[str, Any]  # program, category, audience

    # Routing
    intent: str  # GREETING, FACTUAL, PLAN, IDEATE, SENSITIVE, AMBIGUOUS
    intent_confidence: float  # 0.0 - 1.0

    # Agent output
    response: str
    sources: List[Dict[str, Any]]
    agent_used: str

    # Agent configurations
    agent_configs: Dict[str, Any]  # {"GREETING": {...}, "FACTUAL": {...}, ...}

    # Context injected by ChatEngine (captured_vars from conversation)
    context: Optional[str]

    # Debug
    debug_info: Dict[str, Any]
    processing_time_ms: int


@dataclass
class AgentState:
    """State for individual agent processing."""

    user_input: str
    language: str = "es"
    language_config: Dict[str, Any] = field(default_factory=dict)
    mode: str = ""  # intent
    context: str = ""
    response: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    debug_info: Dict[str, Any] = field(default_factory=dict)
    bot_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "user_input": self.user_input,
            "language": self.language,
            "language_config": self.language_config,
            "mode": self.mode,
            "context": self.context,
            "response": self.response,
            "sources": self.sources,
            "metadata": self.metadata,
            "debug_info": self.debug_info,
        }
