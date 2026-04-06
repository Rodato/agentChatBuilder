"""Embedding generation using OpenAI."""

import os
from typing import List, Optional
import httpx
from loguru import logger


class EmbeddingClient:
    """
    Client for generating text embeddings using OpenAI ada-002.

    Embeddings are 1536-dimensional vectors used for semantic search.
    """

    OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
    MODEL = "text-embedding-ada-002"
    DIMENSIONS = 1536

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("No OpenAI API key for embeddings")

    def embed(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats (1536 dimensions)
        """
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.MODEL,
            "input": text,
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    self.OPENAI_EMBEDDINGS_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data["data"][0]["embedding"]

        except httpx.HTTPError as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    def embed_batch(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call

        Returns:
            List of embeddings
        """
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")

        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.debug(f"Embedding batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1}")

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.MODEL,
                "input": batch,
            }

            try:
                with httpx.Client(timeout=60.0) as client:
                    response = client.post(
                        self.OPENAI_EMBEDDINGS_URL,
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()

                    # Sort by index to maintain order
                    sorted_data = sorted(data["data"], key=lambda x: x["index"])
                    batch_embeddings = [item["embedding"] for item in sorted_data]
                    all_embeddings.extend(batch_embeddings)

            except httpx.HTTPError as e:
                logger.error(f"Batch embedding failed: {e}")
                raise

        return all_embeddings
