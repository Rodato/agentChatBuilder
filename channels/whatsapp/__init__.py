"""WhatsApp channel using Twilio."""

from .webhook import router as whatsapp_router

__all__ = ["whatsapp_router"]
