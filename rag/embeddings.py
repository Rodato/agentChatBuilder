"""Embedding generation — supports OpenAI directly (fast, recommended) or OpenRouter.

Provider selection via env var EMBEDDING_PROVIDER:
- "openai" (default if OPENAI_API_KEY is set): direct OpenAI API with
  text-embedding-3-small. ~10x faster than ada-002 via OpenRouter.
- "openrouter": legacy fallback using openai/text-embedding-ada-002 via
  OpenRouter (slow ~90s, kept for backwards compatibility).

To force a provider, set EMBEDDING_PROVIDER=openai or =openrouter.
The embedding dimension is consistent at 1536, so swapping providers
is safe for new uploads (existing chunks stay in their original space —
mixing dimensions in the same bot will degrade retrieval; reupload to
reindex).
"""

import os
from typing import List, Optional

import httpx
from loguru import logger


_OPENAI_URL = "https://api.openai.com/v1/embeddings"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"


def _select_provider() -> str:
    explicit = (os.getenv("EMBEDDING_PROVIDER") or "").strip().lower()
    if explicit in ("openai", "openrouter"):
        return explicit
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "openrouter"


class EmbeddingClient:
    DIMENSIONS = 1536  # text-embedding-3-small and ada-002 both default to 1536.

    def __init__(self, api_key: Optional[str] = None, provider: Optional[str] = None):
        self.provider = (provider or _select_provider()).lower()
        if self.provider == "openai":
            self.url = _OPENAI_URL
            self.model = "text-embedding-3-small"
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        else:
            self.url = _OPENROUTER_URL
            self.model = "openai/text-embedding-ada-002"
            self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")

        if not self.api_key:
            logger.warning(f"No API key configured for embedding provider '{self.provider}'")
        else:
            logger.info(f"EmbeddingClient: provider={self.provider} model={self.model}")

    def embed(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str], batch_size: int = 96) -> List[List[float]]:
        if not self.api_key:
            raise ValueError(f"API key not configured for embedding provider '{self.provider}'")

        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {"model": self.model, "input": batch}
            # OpenAI direct is fast (~1s per batch); keep the long timeout for
            # the OpenRouter fallback which can take ~90s.
            with httpx.Client(
                timeout=httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=5.0)
            ) as client:
                response = client.post(self.url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                sorted_data = sorted(data["data"], key=lambda x: x["index"])
                all_embeddings.extend(item["embedding"] for item in sorted_data)

        return all_embeddings
