"""Default agent configurations + helpers used by the orchestrator."""

from typing import Dict, Any, List, Optional

BUILTIN_AGENT_IDS = ["greeting", "factual", "plan", "ideate", "sensitive", "fallback"]

# Builtin agent_id ↔ intent (the orchestrator uses this for default routing).
AGENT_ID_TO_INTENT = {
    "greeting": "GREETING",
    "factual": "FACTUAL",
    "plan": "PLAN",
    "ideate": "IDEATE",
    "sensitive": "SENSITIVE",
    "fallback": "AMBIGUOUS",
}

INTENT_TO_AGENT_ID = {v: k for k, v in AGENT_ID_TO_INTENT.items()}

VALID_INTENTS = set(AGENT_ID_TO_INTENT.values())


DEFAULT_AGENTS: List[Dict[str, Any]] = [
    {
        "agent_id": "greeting",
        "name": "Saludo",
        "objective": "Manejar saludos y mensajes de bienvenida",
        "system_prompt": "Eres un asistente amable. Saluda al usuario calurosamente y pregunta cómo puedes ayudarle.",
        "model": "google/gemini-2.5-flash-lite",
        "temperature": 0.7,
        "tools": {"rag_search": False, "user_memory": False, "trigger_flow": False, "human_handoff": False, "external_api": False},
        "enabled": True,
        "is_custom": False,
        "position": 0,
    },
    {
        "agent_id": "factual",
        "name": "Informativo (RAG)",
        "objective": "Responder preguntas desde tus documentos",
        "system_prompt": "Eres un asistente bien informado. Responde preguntas con precisión basándote en el contexto proporcionado.",
        "model": "google/gemini-2.5-flash",
        "temperature": 0.3,
        "tools": {"rag_search": True, "user_memory": False, "trigger_flow": False, "human_handoff": False, "external_api": False},
        "enabled": True,
        "is_custom": False,
        "position": 1,
    },
    {
        "agent_id": "plan",
        "name": "Planificación",
        "objective": "Ayudar a los usuarios a planificar y organizar",
        "system_prompt": "Eres un asistente de planificación estratégica. Ayuda a crear planes detallados y accionables.",
        "model": "openai/gpt-4o-mini",
        "temperature": 0.5,
        "tools": {"rag_search": True, "user_memory": False, "trigger_flow": False, "human_handoff": False, "external_api": False},
        "enabled": False,
        "is_custom": False,
        "position": 2,
    },
    {
        "agent_id": "ideate",
        "name": "Lluvia de Ideas",
        "objective": "Generar ideas creativas",
        "system_prompt": "Eres un compañero creativo de brainstorming. Genera ideas diversas e innovadoras.",
        "model": "google/gemini-2.5-flash",
        "temperature": 0.9,
        "tools": {"rag_search": False, "user_memory": False, "trigger_flow": False, "human_handoff": False, "external_api": False},
        "enabled": False,
        "is_custom": False,
        "position": 3,
    },
    {
        "agent_id": "sensitive",
        "name": "Temas Sensibles",
        "objective": "Manejar temas delicados con cuidado",
        "system_prompt": "Eres un asistente compasivo y cuidadoso. Maneja temas sensibles con empatía y respeto.",
        "model": "openai/gpt-4o-mini",
        "temperature": 0.3,
        "tools": {"rag_search": False, "user_memory": False, "trigger_flow": False, "human_handoff": True, "external_api": False},
        "enabled": True,
        "is_custom": False,
        "position": 4,
    },
    {
        "agent_id": "fallback",
        "name": "Fallback",
        "objective": "Manejar consultas poco claras o ambiguas",
        "system_prompt": "Eres un asistente útil. Cuando una consulta no está clara, haz preguntas de aclaración.",
        "model": "google/gemini-2.5-flash-lite",
        "temperature": 0.5,
        "tools": {"rag_search": False, "user_memory": False, "trigger_flow": False, "human_handoff": False, "external_api": False},
        "enabled": True,
        "is_custom": False,
        "position": 5,
    },
]


def _inject_trigger_flow_block(
    system_prompt: str,
    tools: Dict[str, Any],
    metadata: Dict[str, Any],
    manual_workflows: List[Dict[str, Any]],
) -> str:
    """When tools.trigger_flow is on and there are manual workflows the agent
    is allowed to invoke, prepend a function-calling-lite instruction block."""
    if not tools.get("trigger_flow") or not manual_workflows:
        return system_prompt
    allowed = set(metadata.get("trigger_flows") or [])
    visible = [
        w for w in manual_workflows
        if not allowed or w.get("id") in allowed or w.get("name") in allowed
    ]
    if not visible:
        return system_prompt
    bullet_list = "\n".join(
        f'  - "{w.get("id")}" ({w.get("name")}): {w.get("description") or "sin descripción"}'
        for w in visible
    )
    return (
        "Tienes acceso a flujos especializados. Si detectas que el usuario "
        "quiere iniciar alguno, responde EXCLUSIVAMENTE con un JSON válido del tipo "
        '{"trigger_flow": "<id-del-flujo>", "reason": "<motivo breve>"} '
        "sin texto adicional antes ni después. Si no aplica, responde normalmente en prosa.\n\n"
        f"Flujos disponibles:\n{bullet_list}\n\n"
        "---\n\n"
    ) + system_prompt


def build_agent_configs(
    agent_rows: List[Dict[str, Any]],
    manual_workflows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Build the per-agent config dict consumed by the Orchestrator.

    Returns Dict[agent_id, config] for ALL agents the bot has — builtins
    (with defaults filled in for missing ones) and customs.

    Each config carries:
      - model, temperature, system_prompt   (required by every agent)
      - tools         (capability gates: rag_search, trigger_flow, etc.)
      - is_custom     (bool)
      - intents       (list[str], only customs use it for routing)
      - enabled       (bool)
      - position      (int)
      - name          (display)
      - metadata      (free-form, e.g. trigger_flows allow-list)
    """
    by_agent_id = {row["agent_id"]: row for row in agent_rows or []}
    defaults_by_id = {a["agent_id"]: a for a in DEFAULT_AGENTS}
    manual_workflows = manual_workflows or []

    configs: Dict[str, Dict[str, Any]] = {}

    # Always emit configs for the 6 builtins, falling back to defaults.
    for agent_id in BUILTIN_AGENT_IDS:
        row = by_agent_id.get(agent_id) or defaults_by_id[agent_id]
        configs[agent_id] = _row_to_config(row, manual_workflows, force_builtin=True)

    # Plus any customs the bot has defined.
    for agent_id, row in by_agent_id.items():
        if agent_id in configs:
            continue
        if not row.get("is_custom"):
            continue
        configs[agent_id] = _row_to_config(row, manual_workflows, force_builtin=False)

    return configs


def _row_to_config(
    row: Dict[str, Any],
    manual_workflows: List[Dict[str, Any]],
    force_builtin: bool,
) -> Dict[str, Any]:
    tools = row.get("tools") or {}
    metadata = row.get("metadata") or {}
    system_prompt = _inject_trigger_flow_block(
        row.get("system_prompt", ""),
        tools,
        metadata,
        manual_workflows,
    )
    return {
        "agent_id": row.get("agent_id"),
        "name": row.get("name") or row.get("agent_id"),
        "model": row.get("model", "google/gemini-2.5-flash-lite"),
        "temperature": float(row.get("temperature", 0.7)),
        "system_prompt": system_prompt,
        "tools": tools,
        "is_custom": False if force_builtin else bool(row.get("is_custom")),
        "intents": list(row.get("intents") or []) if not force_builtin else [],
        "enabled": bool(row.get("enabled", True)),
        "position": int(row.get("position", 0)),
        "metadata": metadata,
        "kind": (row.get("kind") or "agent") if not force_builtin else "agent",
        "graph_definition": row.get("graph_definition") if not force_builtin else None,
    }


def resolve_agent_for_intent(
    intent: str,
    configs: Dict[str, Dict[str, Any]],
) -> str:
    """Given a detected intent, return the agent_id that should handle it.

    Preference order:
      1. An enabled custom agent that lists `intent` in its `intents`
         (lowest `position` wins if multiple).
      2. The builtin mapped by INTENT_TO_AGENT_ID.
      3. "fallback" as last resort.
    """
    candidates = [
        cfg for cfg in configs.values()
        if cfg.get("is_custom") and cfg.get("enabled") and intent in (cfg.get("intents") or [])
    ]
    if candidates:
        candidates.sort(key=lambda c: c.get("position", 0))
        return candidates[0]["agent_id"]
    builtin = INTENT_TO_AGENT_ID.get(intent, "fallback")
    return builtin if builtin in configs else "fallback"


# ── Backwards compatibility shim ────────────────────────────────────────────
# Older callers (and any tests) may still import build_orchestrator_configs
# expecting Dict[INTENT, config]. Provide a thin wrapper that adapts.

def build_orchestrator_configs(
    agent_rows: List[Dict[str, Any]],
    manual_workflows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Legacy shape: Dict[INTENT, {model, temperature, system_prompt}] for the 6 builtins."""
    full = build_agent_configs(agent_rows, manual_workflows=manual_workflows)
    out: Dict[str, Dict[str, Any]] = {}
    for agent_id, intent in AGENT_ID_TO_INTENT.items():
        cfg = full.get(agent_id) or {}
        out[intent] = {
            "model": cfg.get("model"),
            "temperature": cfg.get("temperature"),
            "system_prompt": cfg.get("system_prompt"),
        }
    return out
