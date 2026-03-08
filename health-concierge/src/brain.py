"""Concierge Brain — reactive path.

Handles incoming user messages: loads context, calls LLM, extracts
health data, and updates engagement state.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from src.db import (
    get_daily_summaries,
    get_device_data,
    get_engagement_state,
    get_recent_messages,
    get_user,
    save_message,
    update_engagement_state,
)
from src.llm import call_llm, call_llm_json
from src.prompts.persona import SYSTEM_PROMPT, format_context_block

logger = logging.getLogger(__name__)

# Keyword sets for cheap pre-filter before LLM extraction
_WORKOUT_KEYWORDS = {
    "run", "ran", "gym", "workout", "exercise", "lift", "swim",
    "bike", "walk", "yoga", "training", "cardio",
}
_MEAL_KEYWORDS = {
    "ate", "eat", "breakfast", "lunch", "dinner", "snack", "meal",
    "food", "cooked",
}
_SLEEP_KEYWORDS = {
    "sleep", "slept", "nap", "bed", "wake", "woke", "tired", "rest",
}
_MOOD_KEYWORDS = {
    "feel", "feeling", "stressed", "happy", "sad", "anxious", "great",
    "terrible", "exhausted",
}
_ALL_KEYWORDS = _WORKOUT_KEYWORDS | _MEAL_KEYWORDS | _SLEEP_KEYWORDS | _MOOD_KEYWORDS

_EXTRACTION_PROMPT = """\
Extract health data from this user message. Return JSON only, no explanation:
{"workout_mentioned": bool, "workout_type": str|null, "workout_duration": str|null,
 "meal_mentioned": bool, "meal_type": str|null, "meal_description": str|null,
 "sleep_mentioned": bool, "sleep_time": str|null, "mood": str|null}
"""


def handle_message(user_id: str, text: str) -> str:
    """Process an incoming user message and return the concierge response.

    Steps:
    0. Check onboarding status — route to onboarding if incomplete
    1. Load user profile, recent messages, device data, daily summaries
    2. Format context and call LLM for a response
    3. Extract health data from the message (cost-optimized)
    4. Save messages and update engagement state
    """
    # 0. Check onboarding status
    from src.onboarding import get_onboarding_step, handle_onboarding_message

    step = get_onboarding_step(user_id)
    if step is not None:
        return handle_onboarding_message(user_id, text)

    # 1. Load context data
    user_profile = get_user(user_id)
    recent_messages = get_recent_messages(user_id, limit=20)
    since_48h = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    device_data = get_device_data(user_id, since=since_48h)
    daily_summaries = get_daily_summaries(user_id, days=7)

    # 2. Format context for LLM
    device_summary = _format_device_data_summary(device_data)

    # Convert messages to the format expected by format_context_block
    formatted_messages = [
        {"role": msg.get("direction", "unknown"), "content": msg.get("content", "")}
        for msg in recent_messages
    ]

    context_block = format_context_block(
        user_profile=user_profile,
        recent_messages=formatted_messages,
        device_data_summary=device_summary,
        daily_summaries=daily_summaries,
    )

    # 3. Call LLM — include current date/time so it knows "today" vs "tomorrow"
    now = datetime.now(timezone.utc)
    date_line = (
        f"\n\nCurrent date/time: {now.strftime('%A, %B %d, %Y %I:%M %p')} UTC.\n"
        "Use this to distinguish between past, present, and future events. "
        "If the user discussed plans for tomorrow, do NOT check in on those "
        "plans until that day actually arrives."
    )
    system = SYSTEM_PROMPT + date_line
    if context_block:
        system += "\n\n" + context_block
    response = call_llm(system, text)

    # 4. Extract data from user message (cost-optimized)
    extracted = extract_data(text)

    # 5. Save inbound message with extracted data
    save_message(user_id, "inbound", text, extracted_data=extracted)

    # 6. Save outbound response
    save_message(user_id, "outbound", response, trigger_type="reactive")

    # 7. Update engagement state
    now_iso = datetime.now(timezone.utc).isoformat()
    update_engagement_state(
        user_id,
        last_user_message=now_iso,
        unanswered_count=0,
    )

    return response


def extract_data(user_message: str) -> dict | None:
    """Extract health data from a user message.

    Uses a keyword heuristic first to avoid unnecessary LLM calls.
    Returns a dict of extracted fields or None if no health data found.
    """
    # Cheap keyword check
    words = set(re.findall(r"[a-z]+", user_message.lower()))
    if not words & _ALL_KEYWORDS:
        return None

    # Keywords matched — call LLM for structured extraction
    try:
        result = call_llm_json(_EXTRACTION_PROMPT, user_message)
        return result
    except (ValueError, Exception) as exc:
        logger.warning("Data extraction failed: %s", exc)
        return None


def _format_device_data_summary(device_data: list[dict]) -> str:
    """Format device data records into a human-readable summary string.

    Returns empty string if no data.
    """
    if not device_data:
        return ""

    lines = ["Recent device data (last 48h):"]
    for rec in device_data:
        source = rec.get("source", "Unknown")
        data_type = rec.get("data_type", "")
        recorded_at = rec.get("recorded_at", "")
        data = rec.get("data", {})

        # Format the date portion
        date_str = recorded_at[:10] if recorded_at else "unknown"

        # Build a summary line from the data dict
        details = _format_data_details(source, data_type, data)
        lines.append(f"- {source} {data_type} ({date_str}): {details}")

    return "\n".join(lines)


def _format_data_details(source: str, data_type: str, data: dict) -> str:
    """Format the details of a single device data record."""
    parts: list[str] = []

    # Try common fields
    if "duration" in data:
        parts.append(data["duration"])
    if "distance" in data:
        parts.append(data["distance"])
    if "avg_hr" in data:
        parts.append(f"avg HR {data['avg_hr']}")
    if "efficiency" in data:
        parts.append(f"efficiency {data['efficiency']}%")
    if "readiness_score" in data:
        parts.append(f"readiness score {data['readiness_score']}")
    if "weight" in data:
        parts.append(f"{data['weight']} kg")
    if "body_fat" in data:
        parts.append(f"body fat {data['body_fat']}%")
    if "activity_type" in data:
        parts.append(data["activity_type"])
    if "sleep_duration" in data:
        parts.append(data["sleep_duration"])
    if "score" in data:
        parts.append(f"score {data['score']}")

    if parts:
        return ", ".join(parts)

    # Fallback: just dump key=value pairs
    fallback = [f"{k}={v}" for k, v in data.items()]
    return ", ".join(fallback) if fallback else "no details"
