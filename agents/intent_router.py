"""Intent router agent - Classifies user intent into categories."""

import json
from typing import Any, Dict, Tuple, Optional
from loguru import logger

from .base_agent import BaseAgent, AgentState


# Intent categories
INTENTS = {
    "GREETING": "Simple greetings, hellos, hi, good morning, etc.",
    "FACTUAL": "Questions seeking specific information, facts, data",
    "PLAN": "Requests to adapt, implement, plan, schedule, organize",
    "IDEATE": "Requests for new ideas, creativity, brainstorming",
    "SENSITIVE": "Topics involving trauma, conflict, identity, religion",
    "AMBIGUOUS": "Unclear intent, too vague, needs clarification",
}


INTENT_DETECTION_PROMPT = """You are an intent classifier. Classify the user message into ONE of these categories:

GREETING - Simple greetings, hellos, hi, good morning, etc.
FACTUAL - Questions seeking specific information, facts, data, "what is", "how many", "tell me about"
PLAN - Requests to adapt, implement, plan, schedule, organize activities
IDEATE - Requests for new ideas, creativity, brainstorming, innovation
SENSITIVE - Topics involving trauma, religion, family conflict, identity crisis, abuse
AMBIGUOUS - Unclear intent, too vague, needs clarification

User message: "{user_input}"
Language detected: {language}

Respond ONLY with a JSON object (no markdown, no extra text):
{{"intent": "CATEGORY", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}
"""


class IntentRouter(BaseAgent):
    """
    Classifies user intent to route to the appropriate specialized agent.

    Intents:
    - GREETING: Welcome messages
    - FACTUAL: RAG Agent
    - PLAN: Workshop Agent
    - IDEATE: Brainstorming Agent
    - SENSITIVE: Safe Edge Agent
    - AMBIGUOUS: Fallback Agent
    """

    def __init__(self, llm_client: Optional[Any] = None):
        super().__init__("IntentRouter", llm_client)

    def process(self, state: AgentState) -> AgentState:
        """Classify intent and update state."""
        self.log_processing(state)

        if not self.llm:
            logger.warning("No LLM client - using fallback intent detection")
            intent, confidence, reasoning = self._fallback_detection(state)
        else:
            intent, confidence, reasoning = self._llm_detection(state)

        state.mode = intent
        state.metadata["intent_confidence"] = confidence
        state.metadata["intent_reasoning"] = reasoning

        self.add_debug_info(state, {
            "intent": intent,
            "confidence": confidence,
            "reasoning": reasoning,
        })

        logger.info(f"[{self.name}] Intent: {intent} (confidence: {confidence:.2f})")
        return state

    def _llm_detection(self, state: AgentState) -> Tuple[str, float, str]:
        """Detect intent using LLM."""
        try:
            prompt = INTENT_DETECTION_PROMPT.format(
                user_input=state.user_input,
                language=state.language,
            )

            response = self.llm.complete(
                prompt=prompt,
                temperature=0.1,
                max_tokens=200,
            )

            # Parse JSON response
            result = json.loads(response.strip())
            intent = result.get("intent", "AMBIGUOUS").upper()
            confidence = float(result.get("confidence", 0.5))
            reasoning = result.get("reasoning", "")

            # Validate intent
            if intent not in INTENTS:
                intent = "AMBIGUOUS"
                confidence = 0.3

            return intent, confidence, reasoning

        except Exception as e:
            logger.error(f"LLM intent detection failed: {e}")
            return self._fallback_detection(state)

    def _fallback_detection(self, state: AgentState) -> Tuple[str, float, str]:
        """Fallback keyword-based intent detection."""
        text = state.user_input.lower()

        # Greeting patterns
        greeting_patterns = ["hola", "hello", "hi", "buenos días", "good morning", "olá"]
        if any(p in text for p in greeting_patterns) and len(text.split()) <= 5:
            return "GREETING", 0.8, "Greeting keyword detected"

        # Sensitive patterns
        sensitive_patterns = ["trauma", "abuse", "crisis", "conflict", "religion", "identity"]
        if any(p in text for p in sensitive_patterns):
            return "SENSITIVE", 0.7, "Sensitive topic keyword detected"

        # Plan patterns
        plan_patterns = ["how to", "cómo", "implement", "adapt", "plan", "organiz"]
        if any(p in text for p in plan_patterns):
            return "PLAN", 0.6, "Planning keyword detected"

        # Ideate patterns
        ideate_patterns = ["idea", "creative", "brainstorm", "innovate", "new way"]
        if any(p in text for p in ideate_patterns):
            return "IDEATE", 0.6, "Ideation keyword detected"

        # Question patterns suggest factual
        question_patterns = ["what", "qué", "who", "quién", "when", "cuándo", "where", "dónde", "?"]
        if any(p in text for p in question_patterns):
            return "FACTUAL", 0.5, "Question pattern detected"

        return "AMBIGUOUS", 0.3, "No clear pattern detected"

    def classify(self, user_input: str, language: str = "es") -> Dict[str, Any]:
        """
        Convenience method to classify intent without full state.

        Returns:
            Dict with intent, confidence, and reasoning
        """
        state = AgentState(user_input=user_input, language=language)
        state = self.process(state)

        return {
            "intent": state.mode,
            "confidence": state.metadata.get("intent_confidence", 0.5),
            "reasoning": state.metadata.get("intent_reasoning", ""),
        }
