"""API routes for agent configuration management."""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# In-memory store: {bot_id: {agent_id: config}}
_agent_configs: Dict[str, Dict[str, Any]] = {}


class AgentConfig(BaseModel):
    model: str = "mistral-7b"
    temperature: float = 0.7
    system_prompt: str = ""
    tools: Dict[str, bool] = {}
    enabled: bool = True


@router.get("/{bot_id}/agents")
async def list_agents(bot_id: str):
    """List all agent configs for a bot."""
    return _agent_configs.get(bot_id, {})


@router.put("/{bot_id}/agents/{agent_id}")
async def update_agent(bot_id: str, agent_id: str, config: AgentConfig):
    """Update agent config for a bot."""
    if bot_id not in _agent_configs:
        _agent_configs[bot_id] = {}
    _agent_configs[bot_id][agent_id] = config.model_dump()
    return {"status": "ok", "agent_id": agent_id, "config": _agent_configs[bot_id][agent_id]}
