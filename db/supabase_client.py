"""Supabase client singleton."""

from functools import lru_cache
from supabase import create_client, Client
from core.config import settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Return a cached Supabase client instance."""
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(settings.supabase_url, settings.supabase_key)
