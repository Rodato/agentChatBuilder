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
        rag_context = ""
        sources = []
        if self.vector_store:
            try:
                results = self.vector_store.search(
                    state.user_input, top_k=5, bot_id=state.bot_id
                )
                if results:
                    # Prepend each chunk with its source label and (when present) the
                    # doc-level summary, so the LLM has high-signal framing per snippet.
                    seen_summaries: set[str] = set()
                    blocks: list[str] = []
                    for r in results:
                        header_parts = []
                        if r.get("doc_name"):
                            header_parts.append(r["doc_name"])
                        if r.get("page") is not None:
                            header_parts.append(f"p.{r['page']}")
                        header = f"[{' · '.join(header_parts)}]" if header_parts else ""
                        block = ""
                        summary = r.get("doc_summary")
                        if summary and summary not in seen_summaries:
                            block += f"Resumen del documento: {summary}\n"
                            seen_summaries.add(summary)
                        block += f"{header}\n{r.get('content', '')}".strip()
                        blocks.append(block)
                    rag_context = "\n\n---\n\n".join(blocks)
                    sources = results
            except Exception as e:
                logger.warning(f"RAG search failed: {e}")

        if not rag_context and not state.context:
            state.response = NO_RESULTS.get(state.language, NO_RESULTS["es"])
            state.metadata["agent_used"] = "rag"
            return state

        # Preserve any upstream context (e.g. captured workflow vars) and append RAG snippets.
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
