"""WhatsApp webhook handler with async processing."""

import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, Request, Response
from loguru import logger

try:
    from twilio.rest import Client as TwilioClient
except ImportError:
    TwilioClient = None

from core.orchestrator import Orchestrator
from memory.memory_manager import MemoryManager

router = APIRouter()

# Thread pool for CPU-bound tasks
executor = ThreadPoolExecutor(max_workers=10)

# Initialize components
orchestrator = Orchestrator()
memory_manager = MemoryManager()

# Twilio client
twilio_client: Optional[TwilioClient] = None


def get_twilio_client() -> Optional[TwilioClient]:
    """Get or create Twilio client."""
    global twilio_client

    if twilio_client is None and TwilioClient is not None:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")

        if account_sid and auth_token:
            twilio_client = TwilioClient(account_sid, auth_token)
            logger.info("Twilio client initialized")
        else:
            logger.warning("Twilio credentials not configured")

    return twilio_client


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    """
    Handle incoming WhatsApp messages from Twilio.

    Architecture: Async non-blocking
    1. Respond immediately with 200 OK (empty)
    2. Process message in background
    3. Send response actively via Twilio API

    This avoids Twilio's 15-second webhook timeout.
    """
    try:
        # Parse form data
        form_data = await request.form()
        message_body = form_data.get("Body", "")
        from_number = form_data.get("From", "")
        message_sid = form_data.get("MessageSid", "")

        logger.info(f"Received message from {from_number}: {message_body[:50]}...")

        # Launch background processing (don't wait)
        asyncio.create_task(
            process_and_respond(
                message=message_body,
                from_number=from_number,
                message_sid=message_sid,
            )
        )

        # Respond immediately to Twilio (200 OK, empty body)
        return Response(content="", media_type="text/xml")

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return Response(content="", media_type="text/xml")


async def process_and_respond(
    message: str,
    from_number: str,
    message_sid: str,
):
    """
    Process message in background and send response via Twilio API.

    Runs in ThreadPoolExecutor for CPU-bound LLM calls.
    """
    try:
        # Get event loop
        loop = asyncio.get_event_loop()

        # Process with orchestrator (CPU-bound, run in thread)
        result = await loop.run_in_executor(
            executor,
            process_message,
            message,
            from_number,
        )

        # Send response via Twilio
        await send_whatsapp_message(
            to_number=from_number,
            message=result["response"],
        )

        logger.info(f"Response sent to {from_number} (agent: {result['agent_used']})")

    except Exception as e:
        logger.error(f"Background processing error: {e}")

        # Send error message
        await send_whatsapp_message(
            to_number=from_number,
            message="Lo siento, ocurrió un error. Por favor intenta de nuevo.",
        )


def process_message(message: str, phone_number: str) -> dict:
    """
    Process message through the agent pipeline.

    This runs in a thread pool executor.
    """
    # Get or create user
    user = memory_manager.get_or_create_user(phone_number)
    user_id = user.get("id")

    # Get or create conversation
    conversation = memory_manager.get_or_create_conversation(user_id) if user_id else {}
    conversation_id = conversation.get("id")

    # Build context from memory
    context = ""
    if user_id and conversation_id:
        context = memory_manager.build_context(user_id, conversation_id)

    # Process through orchestrator
    result = orchestrator.process_query(
        user_input=message,
        user_id=user_id,
        conversation_id=conversation_id,
        context=context,
    )

    # Store message
    if user_id and conversation_id:
        memory_manager.store_message(
            conversation_id=conversation_id,
            user_id=user_id,
            user_message=message,
            bot_response=result["response"],
            agent_type=result["agent_used"],
            language=result["language"],
            intent=result["intent"],
            response_time_ms=result["processing_time_ms"],
            sources=result.get("sources"),
        )

        # Create memory for important interactions
        if result["agent_used"] in ["safe_edge", "workshop", "brainstorming"]:
            memory_manager.create_memory(
                conversation_id=conversation_id,
                user_id=user_id,
                content=f"User asked: {message[:100]}. Topic: {result['intent']}",
                agent_type=result["agent_used"],
            )

    return result


async def send_whatsapp_message(to_number: str, message: str):
    """Send WhatsApp message via Twilio API."""
    client = get_twilio_client()

    if not client:
        logger.error("Twilio client not available")
        return

    from_number = os.getenv("TWILIO_WHATSAPP_NUMBER")
    if not from_number:
        logger.error("TWILIO_WHATSAPP_NUMBER not configured")
        return

    try:
        # Format message for WhatsApp (remove markdown that doesn't render)
        formatted_message = format_for_whatsapp(message)

        # Send via Twilio
        client.messages.create(
            body=formatted_message,
            from_=from_number,
            to=to_number,
        )

    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {e}")


def format_for_whatsapp(text: str, max_length: int = 1600) -> str:
    """
    Format text for WhatsApp.

    - Remove unsupported markdown
    - Truncate if too long
    - Clean up formatting
    """
    # Remove markdown headers
    import re
    text = re.sub(r"#{1,6}\s*", "", text)

    # Remove bold/italic markers (WhatsApp uses different syntax)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)  # **bold** -> *bold*
    text = re.sub(r"__(.+?)__", r"_\1_", text)  # __italic__ -> _italic_

    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)

    # Clean up multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length - 3] + "..."

    return text.strip()


@router.get("/health")
async def health():
    """Health check for WhatsApp channel."""
    client = get_twilio_client()

    return {
        "channel": "whatsapp",
        "status": "healthy",
        "twilio_connected": client is not None,
    }
