"""Vector store using MongoDB with cosine similarity search."""

import os
import re
from typing import List, Dict, Any, Optional, Set
from loguru import logger

import numpy as np

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

from .embeddings import EmbeddingClient


_TOKEN_RE = re.compile(r"[\wáéíóúñü]+", re.IGNORECASE)


def _tokenize(text: str) -> Set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 2}


class VectorStore:
    COLLECTION = "doc_chunks"
    KEYWORD_BOOST = 0.05  # added to cosine score for each matched keyword (capped)
    MAX_KEYWORD_BOOST = 0.15

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
                    "doc_summary": 1,
                    "doc_keywords": 1,
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

        query_tokens = _tokenize(query)

        # Cosine similarity + keyword overlap boost
        scores = []
        for chunk in chunks:
            emb = chunk.get("embedding")
            if not emb:
                continue
            vec = np.array(emb)
            cosine = float(np.dot(query_vec, vec) / (np.linalg.norm(query_vec) * np.linalg.norm(vec) + 1e-10))
            kw_list = chunk.get("doc_keywords") or []
            matches = sum(1 for kw in kw_list if kw and kw.lower() in query_tokens)
            boost = min(self.KEYWORD_BOOST * matches, self.MAX_KEYWORD_BOOST)
            scores.append((cosine + boost, cosine, matches, chunk))

        # Sort by boosted score, return top_k above threshold (compared on cosine)
        scores.sort(key=lambda x: x[0], reverse=True)
        results = [
            {
                "content": c["content"],
                "score": s_boosted,
                "cosine": s_cos,
                "keyword_matches": kw_matches,
                "doc_id": c.get("doc_id"),
                "doc_name": c.get("doc_name"),
                "doc_summary": c.get("doc_summary"),
                "page": c.get("page"),
            }
            for s_boosted, s_cos, kw_matches, c in scores[:top_k]
            if s_cos >= min_score or kw_matches > 0
        ]

        logger.info(
            f"VectorStore: {len(results)} results (query='{query[:40]}', bot_id={bot_id}, kw_tokens={len(query_tokens)})"
        )
        return results

    def close(self):
        if self.client:
            self.client.close()
