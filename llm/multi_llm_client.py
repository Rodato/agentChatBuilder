"""Multi-provider LLM client with task-based routing."""

import os
from enum import Enum
from typing import Optional, Dict, Any
import httpx
from loguru import logger


class LLMProvider(Enum):
    """Available LLM providers and models via OpenRouter."""

    # Google
    GEMINI_25_FLASH = "google/gemini-2.5-flash"
    GEMINI_25_FLASH_LITE = "google/gemini-2.5-flash-lite"
    GEMINI_31_PRO = "google/gemini-3.1-pro-preview"
    GEMINI_31_FLASH_LITE = "google/gemini-3.1-flash-lite-preview"
    GEMINI_3_PRO = "google/gemini-3-pro-preview"

    # OpenAI
    GPT4O_MINI = "openai/gpt-4o-mini"
    GPT41_MINI = "openai/gpt-4.1-mini"
    GPT54 = "openai/gpt-5.4"
    GPT4O = "openai/gpt-4o"

    # Anthropic
    CLAUDE_SONNET_46 = "anthropic/claude-sonnet-4.6"
    CLAUDE_OPUS_46 = "anthropic/claude-opus-4.6"
    CLAUDE_HAIKU_45 = "anthropic/claude-haiku-4.5"
    CLAUDE_37_THINKING = "anthropic/claude-3.7-sonnet:thinking"

    # Mistral
    MISTRAL_SMALL = "mistralai/mistral-small-2603"
    MISTRAL_SMALL_CREATIVE = "mistralai/mistral-small-creative"
    MISTRAL_SMALL_32B = "mistralai/mistral-small-3.2-24b-instruct"

    # MiniMax
    MINIMAX_M27 = "minimax/minimax-m2.7"

    # DeepSeek
    DEEPSEEK_R1_7B = "deepseek/deepseek-r1-distill-qwen-7b"
    DEEPSEEK_R1_14B = "deepseek/deepseek-r1-distill-qwen-14b"
    DEEPSEEK_R1_0528 = "deepseek/deepseek-r1-0528"
    DEEPSEEK_R1_32B = "deepseek/deepseek-r1-distill-qwen-32b"


# Map model ID string → LLMProvider (for agent config lookup)
MODEL_REGISTRY: Dict[str, LLMProvider] = {p.value: p for p in LLMProvider}

# Task to model mapping
TASK_MODEL_MAPPING = {
    "detection": LLMProvider.GEMINI_25_FLASH_LITE,   # Fast, cheap
    "intent": LLMProvider.GEMINI_25_FLASH_LITE,       # Fast, cheap
    "rag": LLMProvider.GEMINI_25_FLASH,               # Balance
    "workshop": LLMProvider.CLAUDE_SONNET_46,         # Deep analysis
    "brainstorm": LLMProvider.MISTRAL_SMALL_CREATIVE, # Creative
    "sensitive": LLMProvider.CLAUDE_SONNET_46,        # Careful
    "fallback": LLMProvider.GEMINI_25_FLASH_LITE,     # Fast
}


class MultiLLMClient:
    """
    Client for multiple LLM providers with task-based routing.

    Optimizes cost/quality by selecting the best model for each task type.
    """

    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, openrouter_api_key: Optional[str] = None):
        self.openrouter_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.openrouter_key:
            logger.warning("No OpenRouter API key provided")

    def complete(
        self,
        prompt: str,
        provider: Optional[LLMProvider] = None,
        model_id: Optional[str] = None,
        task: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Complete a prompt using the specified provider, model ID, or task routing.

        Args:
            prompt: User prompt
            provider: Specific LLMProvider enum value
            model_id: Raw OpenRouter model ID string (e.g. "google/gemini-2.5-flash")
            task: Task type for automatic model selection
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            system_prompt: Optional system prompt

        Returns:
            Generated text response
        """
        if model_id:
            resolved_model = model_id
        elif provider:
            resolved_model = provider.value
        elif task:
            resolved_model = TASK_MODEL_MAPPING.get(task, LLMProvider.GEMINI_25_FLASH_LITE).value
        else:
            resolved_model = LLMProvider.GEMINI_25_FLASH_LITE.value

        logger.debug(f"Using model: {resolved_model}")
        return self._call_openrouter(prompt, resolved_model, temperature, max_tokens, system_prompt)

    def _call_openrouter(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Call OpenRouter API."""
        if not self.openrouter_key:
            raise ValueError("OpenRouter API key not configured")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://agentchatbuilder.com",
            "X-Title": "Agent Chat Builder",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    self.OPENROUTER_BASE_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]

        except httpx.HTTPError as e:
            logger.error(f"OpenRouter API error: {e}")
            raise

    def get_provider_for_task(self, task: str) -> LLMProvider:
        """Get the recommended provider for a task type."""
        return TASK_MODEL_MAPPING.get(task, LLMProvider.GEMINI_25_FLASH_LITE)

    def list_providers(self) -> Dict[str, str]:
        """List all available providers."""
        return {p.name: p.value for p in LLMProvider}
