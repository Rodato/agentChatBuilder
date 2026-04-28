"""GraphWorker: runner para Workers tipo grafo (orchestrator + sub-agentes).

Un Worker tipo grafo se define con un `graph_definition` similar a un
workflow, pero los nodos son sub-agentes coordinados por un orchestrator
LLM en lugar de captures/handoffs.

Tipos de nodo:
- `orchestrator`: único nodo de entrada. Su LLM decide a qué subagente
  delegar respondiendo con JSON {"route": "<id>"}. Recibe el user_input
  + system_prompt + lista de rutas posibles.
- `subagent`: sub-agente con prompt, modelo, tools (rag_search heredado).
  Recibe el user_input + outputs de upstream subagents si los hay.
- `synthesizer`: combina outputs de varios subagentes en una respuesta
  final. Recibe el user_input + concat de outputs upstream.

El runner ejecuta hasta nodo terminal (sin sucesores) y devuelve su output.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_agent import BaseAgent, AgentState
from llm.multi_llm_client import MultiLLMClient


MAX_GRAPH_DEPTH = 8

VALID_NODE_TYPES = {"orchestrator", "subagent", "synthesizer"}


def _extract_route(text: str) -> Optional[str]:
    """Try to parse {"route": "<id>"} from the orchestrator's response.

    Accepts JSON anywhere in the string (the LLM may wrap it in markdown).
    """
    if not text:
        return None
    # Look for the first {...} block.
    match = re.search(r"\{[^{}]*\}", text, flags=re.DOTALL)
    candidate = match.group(0) if match else text
    try:
        data = json.loads(candidate)
    except Exception:
        return None
    route = data.get("route") if isinstance(data, dict) else None
    return str(route) if route else None


class GraphWorker(BaseAgent):
    """Worker whose body is a graph of sub-agents."""

    def __init__(
        self,
        name: str,
        llm_client: Optional[MultiLLMClient] = None,
        agent_config: Optional[Dict[str, Any]] = None,
        vector_store: Optional[Any] = None,
    ):
        super().__init__(
            name=name,
            llm_client=llm_client,
            agent_config=agent_config,
            vector_store=vector_store,
        )
        if self.llm is None:
            self.llm = MultiLLMClient()

        graph = (self.config or {}).get("graph_definition") or {}
        self.nodes: Dict[str, Dict[str, Any]] = {n["id"]: n for n in (graph.get("nodes") or []) if n.get("id")}
        self.edges: List[Dict[str, str]] = list(graph.get("edges") or [])
        self.entry_node_id: Optional[str] = graph.get("entry_node_id") or self._infer_entry()

    def _infer_entry(self) -> Optional[str]:
        # Prefer the orchestrator node, else any node without inbound edges.
        for nid, n in self.nodes.items():
            if (n.get("type") or n.get("data", {}).get("type")) == "orchestrator":
                return nid
        targets = {e.get("target") for e in self.edges}
        for nid in self.nodes:
            if nid not in targets:
                return nid
        return next(iter(self.nodes), None)

    # ── Graph traversal helpers ─────────────────────────────────────────────

    def _node_data(self, node_id: str) -> Dict[str, Any]:
        n = self.nodes.get(node_id) or {}
        return n.get("data") or n  # accept both shapes

    def _node_type(self, node_id: str) -> str:
        n = self.nodes.get(node_id) or {}
        return n.get("type") or self._node_data(node_id).get("type") or "subagent"

    def _successors(self, node_id: str) -> List[Dict[str, str]]:
        return [e for e in self.edges if e.get("source") == node_id]

    def _upstream_outputs(
        self,
        node_id: str,
        outputs: Dict[str, str],
        explicit_inputs: Optional[List[str]] = None,
    ) -> List[tuple[str, str]]:
        """Return [(node_id, output)] of nodes feeding into `node_id`."""
        if explicit_inputs:
            return [(nid, outputs[nid]) for nid in explicit_inputs if nid in outputs]
        # Default: all edges with target == node_id whose source has an output.
        return [
            (e["source"], outputs[e["source"]])
            for e in self.edges
            if e.get("target") == node_id and e.get("source") in outputs
        ]

    # ── Sub-node executors ──────────────────────────────────────────────────

    def _run_orchestrator(self, node_id: str, state: AgentState) -> Optional[str]:
        data = self._node_data(node_id)
        # Routes available = ids of subagents/synthesizers downstream of this node.
        routes = [e["target"] for e in self._successors(node_id)]
        if not routes:
            return None
        routes_block = "\n".join(
            f"  - {r}: {self._node_data(r).get('label') or self._node_data(r).get('system_prompt', '')[:80]}"
            for r in routes
        )
        system_prompt = (
            (data.get("system_prompt") or "Eres un orquestador. Decide a qué sub-agente delegar.")
            + "\n\n"
            "Responde EXCLUSIVAMENTE con un JSON válido del tipo {\"route\": \"<id-del-sub-agente>\"} "
            "elegido de la siguiente lista, sin texto adicional.\n\n"
            f"Sub-agentes disponibles:\n{routes_block}\n"
        )
        try:
            response = self.llm.complete(
                prompt=state.user_input,
                model_id=data.get("model") or "google/gemini-2.5-flash-lite",
                temperature=float(data.get("temperature", 0.2)),
                system_prompt=system_prompt,
            )
        except Exception as e:
            logger.warning(f"[{self.name}] orchestrator LLM error: {e}")
            return None
        route = _extract_route(response or "")
        if route and route in self.nodes:
            return route
        # Fallback: first downstream node.
        return routes[0] if routes else None

    def _run_subagent(self, node_id: str, state: AgentState, outputs: Dict[str, str]) -> str:
        data = self._node_data(node_id)
        upstream = self._upstream_outputs(node_id, outputs)

        # RAG search if this node enables it (or inherits from worker config).
        ctx_blocks: List[str] = []
        if state.context:
            ctx_blocks.append(state.context)
        for src_id, out in upstream:
            ctx_blocks.append(f"[{self._node_data(src_id).get('label') or src_id}]\n{out}")

        node_tools = data.get("tools") or {}
        if node_tools.get("rag_search") and self.vector_store:
            try:
                results = self.vector_store.search(
                    state.user_input, top_k=5, bot_id=state.bot_id
                )
                if results:
                    ctx_blocks.append(self._format_rag_context(results))
            except Exception as e:
                logger.warning(f"[{self.name}/{node_id}] RAG failed: {e}")

        prompt = state.user_input
        if ctx_blocks:
            prompt = "Context:\n" + "\n\n---\n\n".join(ctx_blocks) + f"\n\nQuestion: {state.user_input}"

        try:
            return self.llm.complete(
                prompt=prompt,
                model_id=data.get("model") or "google/gemini-2.5-flash-lite",
                temperature=float(data.get("temperature", 0.5)),
                system_prompt=data.get("system_prompt") or "",
            ) or ""
        except Exception as e:
            logger.error(f"[{self.name}/{node_id}] subagent LLM error: {e}")
            return ""

    def _run_synthesizer(self, node_id: str, state: AgentState, outputs: Dict[str, str]) -> str:
        data = self._node_data(node_id)
        explicit_inputs = data.get("inputs") if isinstance(data.get("inputs"), list) else None
        upstream = self._upstream_outputs(node_id, outputs, explicit_inputs)

        ctx = "\n\n---\n\n".join(
            f"[{self._node_data(src_id).get('label') or src_id}]\n{out}"
            for src_id, out in upstream
        )
        prompt = (
            f"Outputs de sub-agentes a sintetizar:\n{ctx}\n\n"
            f"Pregunta original: {state.user_input}"
        )
        try:
            return self.llm.complete(
                prompt=prompt,
                model_id=data.get("model") or "google/gemini-2.5-flash",
                temperature=float(data.get("temperature", 0.4)),
                system_prompt=data.get("system_prompt")
                    or "Eres un sintetizador. Combina los outputs de los sub-agentes en una respuesta clara y completa para el usuario.",
            ) or ""
        except Exception as e:
            logger.error(f"[{self.name}/{node_id}] synthesizer LLM error: {e}")
            return ""

    # ── Main entry ──────────────────────────────────────────────────────────

    def process(self, state: AgentState) -> AgentState:
        self.log_processing(state)

        if not self.nodes or not self.entry_node_id:
            state.response = "Este worker no tiene un grafo válido configurado."
            state.metadata["agent_used"] = self.name.lower()
            return state

        outputs: Dict[str, str] = {}
        visited: List[str] = []
        current: Optional[str] = self.entry_node_id

        while current and len(visited) < MAX_GRAPH_DEPTH:
            visited.append(current)
            kind = self._node_type(current)

            if kind == "orchestrator":
                next_id = self._run_orchestrator(current, state)
                if not next_id:
                    state.response = "El orquestador no pudo decidir un sub-agente."
                    break
                current = next_id
                continue

            if kind == "subagent":
                outputs[current] = self._run_subagent(current, state, outputs)
            elif kind == "synthesizer":
                outputs[current] = self._run_synthesizer(current, state, outputs)
            else:
                logger.warning(f"[{self.name}] unknown node type {kind} at {current}")
                outputs[current] = ""

            successors = self._successors(current)
            if not successors:
                # Terminal — its output is the response.
                state.response = outputs.get(current, "") or "(sin respuesta)"
                break
            # Follow first successor by default.
            current = successors[0].get("target")

        if not state.response:
            state.response = outputs.get(visited[-1] if visited else "", "") or "(sin respuesta)"

        state.metadata["agent_used"] = self.name.lower()
        state.metadata["graph_visited"] = visited
        return state
