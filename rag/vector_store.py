"""Vector store abstraction for MongoDB Atlas."""

import os
from typing import List, Dict, Any, Optional
from loguru import logger

try:
    from pymongo import MongoClient
    from pymongo.collection import Collection
except ImportError:
    MongoClient = None
    Collection = None

from .embeddings import EmbeddingClient


class VectorStore:
    """
    Vector store using MongoDB Atlas with vector search.

    Supports:
    - Semantic search with embeddings
    - Pre-filters (program, category, audience)
    - Hybrid search (filters + similarity)
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        db_name: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_client: Optional[EmbeddingClient] = None,
    ):
        self.uri = uri or os.getenv("MONGODB_URI")
        self.db_name = db_name or os.getenv("MONGODB_DB_NAME", "agent_chat_builder")
        self.collection_name = collection_name or os.getenv("MONGODB_COLLECTION_NAME", "documents")

        self.client = None
        self.collection = None
        self.embedding_client = embedding_client or EmbeddingClient()

        self._connect()

    def _connect(self):
        """Connect to MongoDB."""
        if not self.uri:
            logger.warning("No MongoDB URI - vector store not connected")
            return

        if MongoClient is None:
            logger.error("pymongo not installed")
            return

        try:
            self.client = MongoClient(self.uri)
            self.collection = self.client[self.db_name][self.collection_name]
            logger.info(f"Connected to MongoDB: {self.db_name}.{self.collection_name}")
        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents.

        Args:
            query: Search query text
            top_k: Number of results to return
            filters: Optional filters (program, category, audience)
            min_score: Minimum similarity score

        Returns:
            List of documents with similarity scores
        """
        if not self.collection:
            logger.error("Vector store not connected")
            return []

        # Generate query embedding
        try:
            query_embedding = self.embedding_client.embed(query)
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}")
            return []

        # Build aggregation pipeline
        pipeline = self._build_search_pipeline(
            query_embedding=query_embedding,
            top_k=top_k,
            filters=filters,
            min_score=min_score,
        )

        try:
            results = list(self.collection.aggregate(pipeline))
            logger.info(f"Found {len(results)} results for query")
            return results
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _build_search_pipeline(
        self,
        query_embedding: List[float],
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Build MongoDB aggregation pipeline for vector search."""

        # Build filter for vector search
        vector_filter = {}
        if filters:
            if filters.get("program"):
                vector_filter["program_name"] = {"$eq": filters["program"]}
            if filters.get("categories"):
                vector_filter["document_category"] = {"$in": filters["categories"]}
            if filters.get("audiences"):
                vector_filter["target_audiences"] = {"$in": filters["audiences"]}

        # Vector search stage
        search_stage = {
            "$vectorSearch": {
                "index": "vector_index",  # Ensure this index exists
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": top_k * 10,
                "limit": top_k,
            }
        }

        if vector_filter:
            search_stage["$vectorSearch"]["filter"] = vector_filter

        # Project stage
        project_stage = {
            "$project": {
                "_id": 0,
                "document_name": 1,
                "section_header": 1,
                "content": 1,
                "program_name": 1,
                "document_category": 1,
                "target_audiences": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        }

        pipeline = [search_stage, project_stage]

        # Add score filter if specified
        if min_score > 0:
            pipeline.append({"$match": {"score": {"$gte": min_score}}})

        return pipeline

    def add_document(
        self,
        content: str,
        metadata: Dict[str, Any],
        embedding: Optional[List[float]] = None,
    ) -> str:
        """
        Add a document to the vector store.

        Args:
            content: Document text content
            metadata: Document metadata
            embedding: Optional pre-computed embedding

        Returns:
            Document ID
        """
        if not self.collection:
            raise RuntimeError("Vector store not connected")

        # Generate embedding if not provided
        if embedding is None:
            embedding = self.embedding_client.embed(content)

        document = {
            "content": content,
            "embedding": embedding,
            **metadata,
        }

        result = self.collection.insert_one(document)
        logger.info(f"Added document: {result.inserted_id}")
        return str(result.inserted_id)

    def count(self) -> int:
        """Get total document count."""
        if not self.collection:
            return 0
        return self.collection.count_documents({})

    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")
