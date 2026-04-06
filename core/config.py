"""Application configuration."""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_env: str = "development"
    app_debug: bool = True
    app_port: int = 8000

    # OpenRouter (Multi-LLM Gateway)
    openrouter_api_key: Optional[str] = None

    # OpenAI (Embeddings)
    openai_api_key: Optional[str] = None

    # MongoDB
    mongodb_uri: Optional[str] = None
    mongodb_db_name: str = "agent_chat_builder"
    mongodb_collection_name: str = "documents"

    # Supabase
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None

    # Twilio
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_whatsapp_number: Optional[str] = None

    # Telegram
    telegram_bot_token: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
