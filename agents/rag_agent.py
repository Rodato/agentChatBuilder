"""RAG agent for answering factual questions from documents."""

from typing import Optional, Any
from loguru import logger

from .base_agent import BaseAgent, AgentState
from llm.multi_llm_client import MultiLLMClient


DEFAULT_CONFIG = {
    "model": "google/gemini-2.5-flash",
    "temperature": 0.3,
    "system_prompt": "You are a knowledgeable assistant. Answer questions accurately based on the provided context. If the context doesn't contain the answer, say so clearly.",
}

NO_RESULTS = {
    "es": "No encontré información relevante en los documentos disponibles.",
    "en": "I couldn't find relevant information in the available documents.",
    "pt": "Não encontrei informações relevantes nos documentos disponíveis.",
}


class RAGAgent(BaseAgent):
    """Handles factual queries using RAG (Retrieval-Augmented Generation)."""

    def __init__(
        self,
        llm_client: Optional[MultiLLMClient] = None,
        agent_config: dict = None,
        vector_store: Optional[Any] = None,
    ):
        super().__init__("RAGAgent", llm_client)
        self.config = agent_config or DEFAULT_CONFIG
        self.vector_store = vector_store
        if self.llm is None:
            self.llm = MultiLLMClient()

    def process(self, state: AgentState) -> AgentState:
        self.log_processing(state)

        # Try RAG search if vector store available
        context = ""
        sources = []
        if self.vector_store:
            try:
                results = self.vector_store.search(state.user_input, top_k=5)
                if results:
                    context = "\n\n".join(r.get("content", "") for r in results)
                    sources = results
            except Exception as e:
                logger.warning(f"RAG search failed: {e}")

        if not context:
            state.response = NO_RESULTS.get(state.language, NO_RESULTS["es"])
            state.metadata["agent_used"] = "rag"
            return state

        prompt = f"Context:\n{context}\n\nQuestion: {state.user_input}"

        try:
            state.response = self.llm.complete(
                prompt=prompt,
                model_id=self.config["model"],
                temperature=self.config["temperature"],
                system_prompt=self.config["system_prompt"],
            )
            state.sources = sources
        except Exception as e:
            logger.error(f"RAGAgent LLM error: {e}")
            state.response = NO_RESULTS.get(state.language, NO_RESULTS["es"])

        state.metadata["agent_used"] = "rag"
        return state
