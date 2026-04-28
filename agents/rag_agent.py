"""RAG agent for answering factual questions from documents."""

from typing import Any, Optional
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
    """Handles factual queries using RAG (Retrieval-Augmented Generation).

    Unlike other specialists, RAG is the *primary* operation: when retrieval
    returns nothing, this agent answers with a polite "no encontré info"
    message instead of letting the LLM hallucinate. To guarantee retrieval
    happens, this agent always searches (regardless of `tools.rag_search`)."""

    def __init__(
        self,
        llm_client: Optional[MultiLLMClient] = None,
        agent_config: Optional[dict] = None,
        vector_store: Optional[Any] = None,
    ):
        super().__init__(
            name="RAGAgent",
            llm_client=llm_client,
            agent_config=agent_config or DEFAULT_CONFIG,
            vector_store=vector_store,
        )
        if self.llm is None:
            self.llm = MultiLLMClient()

    def process(self, state: AgentState) -> AgentState:
        self.log_processing(state)

        rag_context = ""
        sources = []
        if self.vector_store:
            try:
                results = self.vector_store.search(
                    state.user_input, top_k=5, bot_id=state.bot_id
                )
                if results:
                    rag_context = self._format_rag_context(results)
                    sources = results
            except Exception as e:
                logger.warning(f"RAG search failed: {e}")

        if not rag_context and not state.context:
            state.response = NO_RESULTS.get(state.language, NO_RESULTS["es"])
            state.metadata["agent_used"] = "rag"
            return state

        # Combine upstream context (e.g. captured workflow vars) with RAG snippets.
        context_parts = []
        if state.context:
            context_parts.append(state.context)
        if rag_context:
            context_parts.append(rag_context)
        context = "\n\n".join(context_parts)

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
