"""Vector store using MongoDB with cosine similarity search."""

import os
from typing import List, Dict, Any, Optional
from loguru import logger

import numpy as np

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

from .embeddings import EmbeddingClient


class VectorStore:
    COLLECTION = "doc_chunks"

    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        self.uri = uri or os.getenv("MONGODB_URI")
        self.db_name = db_name or os.getenv("MONGODB_DB_NAME", "agent_chat_builder")
        self.embedding_client = EmbeddingClient()
        self.client = None
        self.collection = None
        self._connect()

    def _connect(self):
        if not self.uri or MongoClient is None:
            logger.warning("MongoDB not configured — vector store disabled")
            return
        try:
            self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self.collection = self.client[self.db_name][self.COLLECTION]
            logger.info(f"VectorStore connected: {self.db_name}.{self.COLLECTION}")
        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")

    def search(
        self,
        query: str,
        top_k: int = 5,
        bot_id: Optional[str] = None,
        min_score: float = 0.3,
    ) -> List[Dict[str, Any]]:
        if self.collection is None:
            logger.error("VectorStore not connected")
            return []

        # Generate query embedding
        try:
            query_vec = np.array(self.embedding_client.embed(query))
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            return []

        # Fetch candidate chunks (filter by bot_id if provided)
        mongo_filter = {}
        if bot_id:
            mongo_filter["bot_id"] = bot_id

        try:
            cursor = self.collection.find(
                mongo_filter,
                {
                    "_id": 0,
                    "embedding": 1,
                    "content": 1,
                    "doc_id": 1,
                    "chunk_index": 1,
                    "doc_name": 1,
                    "page": 1,
                },
            )
            chunks = list(cursor)
        except Exception as e:
            logger.error(f"MongoDB fetch failed: {e}")
            return []

        if not chunks:
            logger.info("No chunks found in vector store")
            return []

        # Cosine similarity
        scores = []
        for chunk in chunks:
            emb = chunk.get("embedding")
            if not emb:
                continue
            vec = np.array(emb)
            score = float(np.dot(query_vec, vec) / (np.linalg.norm(query_vec) * np.linalg.norm(vec) + 1e-10))
            scores.append((score, chunk))

        # Sort by score, return top_k above threshold
        scores.sort(key=lambda x: x[0], reverse=True)
        results = [
            {
                "content": c["content"],
                "score": s,
                "doc_id": c.get("doc_id"),
                "doc_name": c.get("doc_name"),
                "page": c.get("page"),
            }
            for s, c in scores[:top_k]
            if s >= min_score
        ]

        logger.info(f"VectorStore: {len(results)} results (query='{query[:40]}', bot_id={bot_id})")
        return results

    def close(self):
        if self.client:
            self.client.close()
