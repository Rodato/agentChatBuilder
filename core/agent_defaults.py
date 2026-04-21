"""Default agent configurations used to seed a new bot."""

from typing import Dict, Any, List, Optional

BUILTIN_AGENT_IDS = ["greeting", "factual", "plan", "ideate", "sensitive", "fallback"]

# agent_id → intent_key (how the orchestrator identifies them)
AGENT_ID_TO_INTENT = {
    "greeting": "GREETING",
    "factual": "FACTUAL",
    "plan": "PLAN",
    "ideate": "IDEATE",
    "sensitive": "SENSITIVE",
    "fallback": "AMBIGUOUS",
}

INTENT_TO_AGENT_ID = {v: k for k, v in AGENT_ID_TO_INTENT.items()}


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


def build_orchestrator_configs(
    agent_rows: List[Dict[str, Any]],
    manual_workflows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Convert bot_agents rows into the {INTENT: config} dict the Orchestrator expects.

    Falls back to DEFAULT_AGENTS for any missing built-in agent.
    Custom agents (is_custom=True) are ignored by the orchestrator in MVP.

    If `manual_workflows` is provided and an agent has `tools.trigger_flow=true`,
    a function-calling-lite block is prepended to its system_prompt listing the
    available workflows and the JSON format expected to trigger one.
    """
    by_agent_id = {row["agent_id"]: row for row in agent_rows or []}
    configs: Dict[str, Dict[str, Any]] = {}
    defaults_by_id = {a["agent_id"]: a for a in DEFAULT_AGENTS}
    manual_workflows = manual_workflows or []

    for agent_id, intent in AGENT_ID_TO_INTENT.items():
        row = by_agent_id.get(agent_id) or defaults_by_id[agent_id]
        system_prompt = row.get("system_prompt", "")

        tools = row.get("tools") or {}
        metadata = row.get("metadata") or {}
        if tools.get("trigger_flow") and manual_workflows:
            allowed = set(metadata.get("trigger_flows") or [])
            visible = [
                w for w in manual_workflows
                if not allowed or w.get("id") in allowed or w.get("name") in allowed
            ]
            if visible:
                bullet_list = "\n".join(
                    f'  - "{w.get("id")}" ({w.get("name")}): {w.get("description") or "sin descripción"}'
                    for w in visible
                )
                system_prompt = (
                    "Tienes acceso a flujos especializados. Si detectas que el usuario "
                    "quiere iniciar alguno, responde EXCLUSIVAMENTE con un JSON válido del tipo "
                    '{"trigger_flow": "<id-del-flujo>", "reason": "<motivo breve>"} '
                    "sin texto adicional antes ni después. Si no aplica, responde normalmente en prosa.\n\n"
                    f"Flujos disponibles:\n{bullet_list}\n\n"
                    "---\n\n"
                ) + system_prompt

        configs[intent] = {
            "model": row["model"],
            "temperature": float(row["temperature"]),
            "system_prompt": system_prompt,
        }
    return configs
