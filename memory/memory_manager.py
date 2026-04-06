"""Memory manager for conversation context and persistence."""

import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from loguru import logger

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None


# Importance scores by agent type
IMPORTANCE_SCORES = {
    "safe_edge": 0.9,
    "workshop": 0.8,
    "brainstorming": 0.7,
    "plan": 0.7,
    "rag": 0.5,
    "fallback": 0.3,
    "greeting": 0.1,
}


class MemoryManager:
    """
    Manages conversation memory and user context.

    Features:
    - User profile management
    - Conversation history
    - Memory with importance scoring
    - Context building for LLM prompts
    - Automatic cleanup of old memories
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ):
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")

        self.client: Optional[Client] = None
        self._connect()

    def _connect(self):
        """Connect to Supabase."""
        if not self.supabase_url or not self.supabase_key:
            logger.warning("No Supabase credentials - memory not connected")
            return

        if create_client is None:
            logger.error("supabase-py not installed")
            return

        try:
            self.client = create_client(self.supabase_url, self.supabase_key)
            logger.info("Connected to Supabase")
        except Exception as e:
            logger.error(f"Supabase connection failed: {e}")

    # ==================== User Management ====================

    def get_or_create_user(self, phone_number: str) -> Dict[str, Any]:
        """Get existing user or create new one."""
        if not self.client:
            return {"id": None, "phone_number": phone_number}

        try:
            # Try to get existing user
            result = self.client.table("users").select("*").eq("phone_number", phone_number).execute()

            if result.data:
                # Update last interaction
                user = result.data[0]
                self.client.table("users").update({
                    "last_interaction_at": datetime.utcnow().isoformat(),
                    "total_messages": user.get("total_messages", 0) + 1,
                }).eq("id", user["id"]).execute()
                return user

            # Create new user
            new_user = {
                "phone_number": phone_number,
                "preferred_language": "es",
                "first_interaction_at": datetime.utcnow().isoformat(),
                "last_interaction_at": datetime.utcnow().isoformat(),
                "total_messages": 1,
            }
            result = self.client.table("users").insert(new_user).execute()
            return result.data[0] if result.data else new_user

        except Exception as e:
            logger.error(f"User management error: {e}")
            return {"id": None, "phone_number": phone_number}

    # ==================== Conversation Management ====================

    def get_or_create_conversation(self, user_id: str) -> Dict[str, Any]:
        """Get active conversation or create new one."""
        if not self.client or not user_id:
            return {"id": None, "user_id": user_id}

        try:
            # Get active conversation
            result = self.client.table("conversations").select("*").eq("user_id", user_id).eq("is_active", True).execute()

            if result.data:
                conv = result.data[0]
                # Update message count
                self.client.table("conversations").update({
                    "message_count": conv.get("message_count", 0) + 1,
                }).eq("id", conv["id"]).execute()
                return conv

            # Create new conversation
            new_conv = {
                "user_id": user_id,
                "session_started_at": datetime.utcnow().isoformat(),
                "message_count": 1,
                "is_active": True,
            }
            result = self.client.table("conversations").insert(new_conv).execute()
            return result.data[0] if result.data else new_conv

        except Exception as e:
            logger.error(f"Conversation management error: {e}")
            return {"id": None, "user_id": user_id}

    # ==================== Message Storage ====================

    def store_message(
        self,
        conversation_id: str,
        user_id: str,
        user_message: str,
        bot_response: str,
        agent_type: str,
        language: str,
        intent: str,
        response_time_ms: int,
        sources: Optional[List[Dict]] = None,
    ) -> Optional[str]:
        """Store a message exchange."""
        if not self.client or not conversation_id:
            return None

        try:
            message = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "user_message": user_message,
                "bot_response": bot_response,
                "agent_type": agent_type,
                "detected_language": language,
                "detected_intent": intent,
                "response_time_ms": response_time_ms,
                "sources_used": sources or [],
                "created_at": datetime.utcnow().isoformat(),
            }
            result = self.client.table("messages").insert(message).execute()
            return result.data[0]["id"] if result.data else None

        except Exception as e:
            logger.error(f"Message storage error: {e}")
            return None

    # ==================== Memory Management ====================

    def create_memory(
        self,
        conversation_id: str,
        user_id: str,
        content: str,
        agent_type: str,
        memory_type: str = "context",
    ) -> Optional[str]:
        """Create a memory entry with importance scoring."""
        if not self.client or not conversation_id:
            return None

        importance = IMPORTANCE_SCORES.get(agent_type, 0.5)

        try:
            memory = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "memory_type": memory_type,
                "memory_content": content,
                "importance_score": importance,
                "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
                "is_active": True,
                "created_at": datetime.utcnow().isoformat(),
            }
            result = self.client.table("conversation_memory").insert(memory).execute()
            return result.data[0]["id"] if result.data else None

        except Exception as e:
            logger.error(f"Memory creation error: {e}")
            return None

    def get_memories(
        self,
        user_id: str,
        limit: int = 5,
        min_importance: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Get top memories by importance for a user."""
        if not self.client or not user_id:
            return []

        try:
            result = self.client.table("conversation_memory").select("*").eq("user_id", user_id).eq("is_active", True).gte("importance_score", min_importance).order("importance_score", desc=True).limit(limit).execute()

            return result.data or []

        except Exception as e:
            logger.error(f"Memory retrieval error: {e}")
            return []

    # ==================== Context Building ====================

    def build_context(
        self,
        user_id: str,
        conversation_id: str,
        last_messages: int = 3,
        top_memories: int = 5,
    ) -> str:
        """
        Build context string for LLM prompt.

        Combines recent messages with important memories.
        """
        context_parts = []

        # Get recent messages
        if self.client and conversation_id:
            try:
                result = self.client.table("messages").select("user_message, bot_response").eq("conversation_id", conversation_id).order("created_at", desc=True).limit(last_messages).execute()

                if result.data:
                    context_parts.append("Recent conversation:")
                    for msg in reversed(result.data):
                        context_parts.append(f"User: {msg['user_message']}")
                        context_parts.append(f"Assistant: {msg['bot_response'][:200]}...")
            except Exception as e:
                logger.error(f"Context building error: {e}")

        # Get important memories
        memories = self.get_memories(user_id, limit=top_memories)
        if memories:
            context_parts.append("\nRelevant context:")
            for mem in memories:
                context_parts.append(f"- {mem['memory_content'][:150]}")

        return "\n".join(context_parts) if context_parts else ""

    # ==================== Cleanup ====================

    def cleanup_old_memories(self, days: int = 30) -> int:
        """Delete memories older than specified days."""
        if not self.client:
            return 0

        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            result = self.client.table("conversation_memory").delete().lt("created_at", cutoff).execute()
            count = len(result.data) if result.data else 0
            logger.info(f"Cleaned up {count} old memories")
            return count

        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            return 0
