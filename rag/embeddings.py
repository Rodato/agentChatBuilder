"""Embedding generation using OpenRouter."""

import os
from typing import List, Optional
import httpx
from loguru import logger


class EmbeddingClient:
    OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"
    MODEL = "openai/text-embedding-ada-002"
    DIMENSIONS = 1536

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            logger.warning("No OPENROUTER_API_KEY configured for embeddings")

    def embed(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str], batch_size: int = 96) -> List[List[float]]:
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not configured")

        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {"model": self.MODEL, "input": batch}
            with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=5.0)) as client:
                response = client.post(
                    self.OPENROUTER_URL, headers=headers, json=payload
                )
                response.raise_for_status()
                data = response.json()
                sorted_data = sorted(data["data"], key=lambda x: x["index"])
                all_embeddings.extend(item["embedding"] for item in sorted_data)

        return all_embeddings
