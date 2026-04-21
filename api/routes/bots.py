"""CRUD routes for bots."""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from db import get_supabase
from api.routes.agents import seed_default_agents

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class BotCreate(BaseModel):
    name: str
    description: Optional[str] = None
    personality: Optional[str] = None
    welcome_message: Optional[str] = "Hola! ¿En qué puedo ayudarte?"


class BotUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    personality: Optional[str] = None
    welcome_message: Optional[str] = None
    is_active: Optional[bool] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
async def list_bots():
    try:
        result = get_supabase().table("bots").select("*").order("created_at", desc=True).execute()
        return result.data
    except Exception as e:
        logger.exception(f"Error listing bots: {e}")
        raise HTTPException(status_code=500, detail="No se pudieron cargar los bots.")


@router.post("", status_code=201)
async def create_bot(bot: BotCreate):
    try:
        result = get_supabase().table("bots").insert(bot.model_dump()).execute()
        created = result.data[0]
    except Exception as e:
        logger.exception(f"Error creating bot: {e}")
        raise HTTPException(status_code=500, detail="No se pudo crear el bot.")

    # Seed default agents for the new bot (non-fatal if it fails).
    seed_default_agents(created["id"])
    return created


@router.get("/{bot_id}")
async def get_bot(bot_id: str):
    try:
        result = get_supabase().table("bots").select("*").eq("id", bot_id).single().execute()
        return result.data
    except Exception as e:
        logger.exception(f"Error fetching bot {bot_id}: {e}")
        raise HTTPException(status_code=404, detail="Bot no encontrado")


@router.put("/{bot_id}")
async def update_bot(bot_id: str, bot: BotUpdate):
    try:
        data = {k: v for k, v in bot.model_dump().items() if v is not None}
        data["updated_at"] = "now()"
        result = get_supabase().table("bots").update(data).eq("id", bot_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Bot no encontrado")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo actualizar el bot.")


@router.delete("/{bot_id}", status_code=204)
async def delete_bot(bot_id: str):
    try:
        get_supabase().table("bots").delete().eq("id", bot_id).execute()
    except Exception as e:
        logger.exception(f"Error deleting bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo eliminar el bot.")
