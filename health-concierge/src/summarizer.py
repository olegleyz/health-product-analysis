"""Daily summary generation.

Generates end-of-day summaries combining conversation history and device data.
Produces both a natural language summary and structured JSON.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from src import db
from src.llm import call_llm, call_llm_json

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM_PROMPT = """\
You are a personal health concierge summarizing a user's day.
Write a natural language summary of 3-5 sentences describing what the user did,
how they felt, and any notable events. Be concise and warm.
If there is very little data, write a brief 1-2 sentence summary acknowledging the quiet day."""

_STRUCTURED_SYSTEM_PROMPT = """\
You are a personal health data extractor. Given a user's day of conversations and device data,
extract structured information as JSON. Return ONLY valid JSON with this schema:
{
  "workouts": [{"type": "string", "duration": "string", "source": "string"}],
  "meals": [{"type": "string", "description": "string", "quality": "string"}],
  "sleep": {"duration": "string", "quality": "string", "bedtime": "string", "source": "string"},
  "mood": "string or null",
  "weight": "number or null",
  "readiness": "number or null",
  "notable": "string or null"
}
Omit fields that have no data (use null for scalars, empty arrays for lists).
Return ONLY the JSON object, no markdown fences or extra text."""


def _get_messages_for_date(user_id: str, date: str) -> list[dict]:
    """Fetch all messages for a user on a specific date."""
    start = f"{date}T00:00:00"
    end = f"{date}T23:59:59"
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE user_id = ? AND created_at >= ? AND created_at <= ? "
            "ORDER BY created_at ASC",
            (user_id, start, end),
        ).fetchall()
    result = [dict(r) for r in rows]
    for msg in result:
        if msg.get("extracted_data"):
            msg["extracted_data"] = json.loads(msg["extracted_data"])
    return result


def _get_device_data_for_date(user_id: str, date: str) -> list[dict]:
    """Fetch all device data for a user on a specific date.

    Filters to only records with recorded_at on the given date to avoid
    including data from subsequent days.
    """
    start = f"{date}T00:00:00"
    end = f"{date}T23:59:59"
    records = db.get_device_data(user_id, since=start)
    return [r for r in records if r.get("recorded_at", "") <= end]


def _build_day_context(messages: list[dict], device_data: list[dict]) -> str:
    """Build a text representation of the day's data for the LLM."""
    parts = []

    if messages:
        parts.append("## Conversations")
        for msg in messages:
            direction = "User" if msg["direction"] == "inbound" else "Concierge"
            parts.append(f"[{msg.get('created_at', '')}] {direction}: {msg['content']}")

    if device_data:
        parts.append("\n## Device Data")
        for rec in device_data:
            parts.append(
                f"[{rec.get('recorded_at', '')}] {rec['source']}/{rec['data_type']}: "
                f"{json.dumps(rec['data'])}"
            )

    if not parts:
        return "No conversations or device data recorded for this day."

    return "\n".join(parts)


def _summary_exists(user_id: str, date: str) -> bool:
    """Check if a summary already exists for this user and date."""
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM daily_summaries WHERE user_id = ? AND date = ?",
            (user_id, date),
        ).fetchone()
    return row is not None


def generate_daily_summary(user_id: str, date: str) -> dict:
    """Generate a daily summary for a user on a given date.

    Loads all messages and device data for the date, calls the LLM to produce
    a natural language summary and structured JSON extraction.

    Returns:
        {"summary": str, "structured": dict}
    """
    messages = _get_messages_for_date(user_id, date)
    device_data = _get_device_data_for_date(user_id, date)
    context = _build_day_context(messages, device_data)

    user_message = f"Date: {date}\n\n{context}"

    # Get natural language summary
    summary_text = call_llm(_SUMMARY_SYSTEM_PROMPT, user_message, max_tokens=512)

    # Get structured data
    structured = call_llm_json(_STRUCTURED_SYSTEM_PROMPT, user_message, max_tokens=1024)

    logger.info(
        "Generated daily summary for user=%s date=%s messages=%d device_records=%d",
        user_id, date, len(messages), len(device_data),
    )

    return {"summary": summary_text, "structured": structured}
