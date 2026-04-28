"""CRUD routes for bots."""

import os
import shutil
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from db import get_supabase
from api.routes.agents import seed_default_agents

router = APIRouter()


UPLOAD_DIR = "uploads"


def _purge_bot_resources(bot_id: str) -> None:
    """Delete bot-specific resources outside of Postgres (Mongo chunks + uploaded files)."""
    # Mongo doc_chunks (vectors)
    try:
        from pymongo import MongoClient
        from core.config import settings

        mongo = MongoClient(settings.mongodb_uri)
        result = mongo[settings.mongodb_db_name]["doc_chunks"].delete_many({"bot_id": bot_id})
        mongo.close()
        logger.info(f"[delete_bot] purged {result.deleted_count} chunks for {bot_id}")
    except Exception as e:
        logger.warning(f"[delete_bot] could not purge Mongo chunks for {bot_id}: {e}")

    # Filesystem uploads
    bot_dir = os.path.join(UPLOAD_DIR, bot_id)
    if os.path.isdir(bot_dir):
        try:
            shutil.rmtree(bot_dir, ignore_errors=True)
            logger.info(f"[delete_bot] removed uploads dir {bot_dir}")
        except Exception as e:
            logger.warning(f"[delete_bot] could not remove {bot_dir}: {e}")


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
    # Purge Mongo + filesystem first (best-effort, non-fatal). The SQL cascade
    # is the source of truth, so we always proceed with the Postgres delete.
    _purge_bot_resources(bot_id)
    # Invalidate any cached orchestrator/chat engine for this bot.
    try:
        from api.main import invalidate_orchestrator
        invalidate_orchestrator(bot_id)
    except Exception:
        pass
    try:
        get_supabase().table("bots").delete().eq("id", bot_id).execute()
    except Exception as e:
        logger.exception(f"Error deleting bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo eliminar el agente.")
