"""Base agent class for all specialized agents."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger

from core.state import AgentState  # re-exported for legacy imports


class BaseAgent(ABC):
    """
    Abstract base class for all specialized agents.

    All agents must implement:
    - process(state) -> state: Main processing logic

    Capability helpers (opt-in via config.tools):
    - maybe_retrieve(state): if tools.rag_search and a vector store is wired,
      returns a (context_block, sources) tuple filtered by state.bot_id.
    """

    def __init__(
        self,
        name: str,
        llm_client: Optional[Any] = None,
        agent_config: Optional[Dict[str, Any]] = None,
        vector_store: Optional[Any] = None,
    ):
        self.name = name
        self.llm = llm_client
        self.config: Dict[str, Any] = agent_config or {}
        self.vector_store = vector_store

    @abstractmethod
    def process(self, state: AgentState) -> AgentState:
        """Process the state and return it with `response` populated."""
        pass

    # ── Capability helpers ──────────────────────────────────────────────────

    def _rag_enabled(self) -> bool:
        tools = (self.config or {}).get("tools") or {}
        return bool(tools.get("rag_search"))

    def maybe_retrieve(
        self,
        state: AgentState,
        top_k: int = 5,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """If `tools.rag_search` is on and a vector store is available, run a
        retrieval scoped to `state.bot_id` and return a framed context block plus
        the raw sources. Otherwise return ('', [])."""
        if not self._rag_enabled() or not self.vector_store:
            return "", []
        try:
            results = self.vector_store.search(
                state.user_input, top_k=top_k, bot_id=state.bot_id
            )
        except Exception as e:
            logger.warning(f"[{self.name}] RAG search failed: {e}")
            return "", []
        if not results:
            return "", []
        return self._format_rag_context(results), results

    @staticmethod
    def _format_rag_context(results: List[Dict[str, Any]]) -> str:
        """Render retrieved chunks with per-chunk header and dedup'd doc summary."""
        seen_summaries: set = set()
        blocks: List[str] = []
        for r in results:
            header_parts: List[str] = []
            if r.get("doc_name"):
                header_parts.append(str(r["doc_name"]))
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
        return "\n\n---\n\n".join(blocks)

    # ── Misc ────────────────────────────────────────────────────────────────

    def should_process(self, state: AgentState) -> bool:
        return bool(state.user_input)

    def log_processing(self, state: AgentState):
        preview = state.user_input[:50] + "..." if len(state.user_input) > 50 else state.user_input
        logger.info(f"[{self.name}] Processing: {preview}")

    def add_debug_info(self, state: AgentState, info: Dict[str, Any]) -> AgentState:
        state.debug_info[self.name] = info
        return state

    def get_system_prompt(self, state: AgentState) -> str:
        return f"You are a helpful assistant responding in {state.language}."

    def format_response(self, response: str, state: AgentState) -> str:
        return response.strip()
