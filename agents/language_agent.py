"""Language detection agent."""

import json
from typing import Any, Optional, Tuple
from loguru import logger

from .base_agent import BaseAgent, AgentState


LANGUAGE_DETECTION_PROMPT = """Detect the language of this text.
Respond ONLY with the ISO 639-1 code (es, en, pt, fr, de, etc.):

Text: "{text}"

Language code:"""


LANGUAGE_CONFIGS = {
    "es": {
        "name": "Español",
        "greeting": "¡Hola!",
        "error_message": "Lo siento, ocurrió un error. Por favor intenta de nuevo.",
        "clarification": "¿Podrías darme más detalles?",
        "no_results": "No encontré información relevante sobre eso.",
    },
    "en": {
        "name": "English",
        "greeting": "Hello!",
        "error_message": "Sorry, an error occurred. Please try again.",
        "clarification": "Could you give me more details?",
        "no_results": "I couldn't find relevant information about that.",
    },
    "pt": {
        "name": "Português",
        "greeting": "Olá!",
        "error_message": "Desculpe, ocorreu um erro. Por favor, tente novamente.",
        "clarification": "Poderia me dar mais detalhes?",
        "no_results": "Não encontrei informações relevantes sobre isso.",
    },
}


class LanguageAgent(BaseAgent):
    """
    Detects the language of user input and loads appropriate configuration.

    Supported languages: es (Spanish), en (English), pt (Portuguese)
    Default: Spanish
    """

    def __init__(self, llm_client: Optional[Any] = None, default_language: str = "es"):
        super().__init__("LanguageAgent", llm_client)
        self.default_language = default_language

    def process(self, state: AgentState) -> AgentState:
        """Detect language and load configuration."""
        self.log_processing(state)

        if not self.llm:
            logger.warning("No LLM client - using fallback language detection")
            language, confidence = self._fallback_detection(state.user_input)
        else:
            language, confidence = self._llm_detection(state.user_input)

        # Load language config
        state.language = language
        state.language_config = LANGUAGE_CONFIGS.get(
            language, LANGUAGE_CONFIGS[self.default_language]
        )

        self.add_debug_info(state, {
            "detected_language": language,
            "confidence": confidence,
            "config_loaded": True,
        })

        logger.info(f"[{self.name}] Detected: {language} (confidence: {confidence:.2f})")
        return state

    def _llm_detection(self, text: str) -> Tuple[str, float]:
        """Detect language using LLM."""
        try:
            prompt = LANGUAGE_DETECTION_PROMPT.format(text=text[:500])

            response = self.llm.complete(
                prompt=prompt,
                temperature=0.0,
                max_tokens=10,
            )

            language = response.strip().lower()[:2]

            # Validate language code
            if language in LANGUAGE_CONFIGS:
                return language, 0.9

            # Check for common variations
            language_mapping = {
                "sp": "es", "spanish": "es", "español": "es",
                "english": "en", "inglés": "en",
                "portuguese": "pt", "português": "pt", "br": "pt",
            }
            if language in language_mapping:
                return language_mapping[language], 0.8

            return self.default_language, 0.5

        except Exception as e:
            logger.error(f"LLM language detection failed: {e}")
            return self._fallback_detection(text)

    def _fallback_detection(self, text: str) -> Tuple[str, float]:
        """Fallback keyword-based language detection."""
        text_lower = text.lower()

        # Spanish indicators
        spanish_words = ["hola", "qué", "cómo", "gracias", "por favor", "está", "buenos"]
        spanish_count = sum(1 for w in spanish_words if w in text_lower)

        # English indicators
        english_words = ["hello", "what", "how", "thanks", "please", "the", "good"]
        english_count = sum(1 for w in english_words if w in text_lower)

        # Portuguese indicators
        portuguese_words = ["olá", "obrigado", "por favor", "como", "você", "bom"]
        portuguese_count = sum(1 for w in portuguese_words if w in text_lower)

        counts = {
            "es": spanish_count,
            "en": english_count,
            "pt": portuguese_count,
        }

        max_lang = max(counts, key=counts.get)
        max_count = counts[max_lang]

        if max_count > 0:
            return max_lang, min(0.3 + (max_count * 0.15), 0.8)

        return self.default_language, 0.3

    def detect(self, text: str) -> dict:
        """
        Convenience method to detect language without full state.

        Returns:
            Dict with language code and config
        """
        state = AgentState(user_input=text)
        state = self.process(state)

        return {
            "language": state.language,
            "config": state.language_config,
        }
