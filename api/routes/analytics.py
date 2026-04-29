"""Analytics endpoints — aggregate metrics from chat_messages per bot."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from db import get_supabase


router = APIRouter()


@router.get("/{bot_id}/analytics")
async def get_bot_analytics(
    bot_id: str,
    days: int = Query(7, ge=1, le=90),
) -> Dict[str, Any]:
    """Aggregate analytics for the bot over the last N days.

    Returns:
      - totals: overall message/conversation/turn counters.
      - daily: bucket of message counts per day (last N days).
      - by_agent: distribution of assistant messages by agent_used.
      - by_intent: distribution by detected intent.
      - by_mode: agentic vs workflow mix.
      - avg_processing_ms: mean response latency for assistant messages.
    """
    sb = get_supabase()

    # Verify bot exists.
    try:
        sb.table("bots").select("id").eq("id", bot_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Agente no encontrado.")

    since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        result = (
            sb.table("chat_messages")
            .select("role, agent_used, intent, mode, processing_time_ms, created_at, conversation_id")
            .eq("bot_id", bot_id)
            .gte("created_at", since.isoformat())
            .order("created_at")
            .limit(10000)
            .execute()
        )
        rows: List[Dict[str, Any]] = result.data or []
    except Exception as e:
        logger.warning(f"analytics: query failed for {bot_id}: {e}")
        rows = []

    # Build daily bucket (one entry per day for the last N days, even if 0).
    today = datetime.now(timezone.utc).date()
    daily_user: Dict[str, int] = {}
    daily_assistant: Dict[str, int] = {}
    for i in range(days):
        day = (today - timedelta(days=days - 1 - i)).isoformat()
        daily_user[day] = 0
        daily_assistant[day] = 0

    by_agent: Counter = Counter()
    by_intent: Counter = Counter()
    by_mode: Counter = Counter()
    conversations: set = set()
    total_user = 0
    total_assistant = 0
    proc_times: List[int] = []

    for row in rows:
        role = row.get("role")
        created = row.get("created_at")
        # Supabase returns ISO strings — slice to get the date.
        day_key = (created or "")[:10]
        if role == "user":
            total_user += 1
            daily_user[day_key] = daily_user.get(day_key, 0) + 1
        elif role == "assistant":
            total_assistant += 1
            daily_assistant[day_key] = daily_assistant.get(day_key, 0) + 1
            agent = row.get("agent_used") or "unknown"
            by_agent[agent] += 1
            intent = row.get("intent")
            if intent:
                by_intent[intent] += 1
            mode = row.get("mode")
            if mode:
                by_mode[mode] += 1
            if isinstance(row.get("processing_time_ms"), (int, float)):
                proc_times.append(int(row["processing_time_ms"]))
        if row.get("conversation_id"):
            conversations.add(row["conversation_id"])

    avg_processing_ms = int(sum(proc_times) / len(proc_times)) if proc_times else 0

    daily = [
        {"date": day, "user": daily_user[day], "assistant": daily_assistant[day]}
        for day in sorted(daily_user.keys())
    ]

    return {
        "bot_id": bot_id,
        "since": since.isoformat(),
        "days": days,
        "totals": {
            "messages": total_user + total_assistant,
            "user_messages": total_user,
            "assistant_messages": total_assistant,
            "conversations": len(conversations),
        },
        "daily": daily,
        "by_agent": [{"agent": k, "count": v} for k, v in by_agent.most_common(20)],
        "by_intent": [{"intent": k, "count": v} for k, v in by_intent.most_common()],
        "by_mode": [{"mode": k, "count": v} for k, v in by_mode.most_common()],
        "avg_processing_ms": avg_processing_ms,
    }
