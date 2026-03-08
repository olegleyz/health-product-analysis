"""Proactive message generation.

Generates outbound messages (morning check-ins, evening check-ins, nudges, etc.)
using device data, daily summaries, and the LLM.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from src import db
from src.governor import can_send
from src.llm import call_llm
from src.prompts.persona import SYSTEM_PROMPT, format_context_block

logger = logging.getLogger(__name__)


def _yesterday_iso() -> str:
    """Return yesterday's date as ISO date string (YYYY-MM-DD) in UTC."""
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def _format_sleep_data(sleep_records: list[dict]) -> str | None:
    """Format sleep device data into a human-readable summary for the prompt."""
    if not sleep_records:
        return None

    lines: list[str] = []
    for rec in sleep_records:
        data = rec.get("data", {})
        source = rec.get("source", "unknown")
        parts: list[str] = []

        if "duration_hours" in data:
            parts.append(f"Duration: {data['duration_hours']}h")
        if "score" in data:
            parts.append(f"Score: {data['score']}")
        if "quality" in data:
            parts.append(f"Quality: {data['quality']}")
        if "deep_sleep_hours" in data:
            parts.append(f"Deep sleep: {data['deep_sleep_hours']}h")
        if "rem_sleep_hours" in data:
            parts.append(f"REM sleep: {data['rem_sleep_hours']}h")
        if "readiness_score" in data:
            parts.append(f"Readiness: {data['readiness_score']}")

        if parts:
            lines.append(f"Sleep ({source}): {', '.join(parts)}")

    return "\n".join(lines) if lines else None


def _format_device_summary(
    sleep_records: list[dict],
    readiness_records: list[dict],
    weight_records: list[dict],
) -> str | None:
    """Combine all device data into a single summary string."""
    parts: list[str] = []

    sleep_text = _format_sleep_data(sleep_records)
    if sleep_text:
        parts.append(sleep_text)

    for rec in readiness_records:
        data = rec.get("data", {})
        source = rec.get("source", "unknown")
        score = data.get("score") or data.get("readiness_score")
        if score is not None:
            parts.append(f"Readiness ({source}): {score}")

    for rec in weight_records:
        data = rec.get("data", {})
        weight = data.get("weight_kg") or data.get("weight")
        if weight is not None:
            parts.append(f"Weight: {weight} kg")

    return "\n".join(parts) if parts else None


def _get_sleep_quality(sleep_records: list[dict]) -> str | None:
    """Determine sleep quality from records. Returns 'poor', 'fair', or 'good'."""
    if not sleep_records:
        return None

    for rec in sleep_records:
        data = rec.get("data", {})
        score = data.get("score")
        if score is not None:
            if score < 60:
                return "poor"
            elif score < 75:
                return "fair"
            else:
                return "good"

    return None


def _build_morning_prompt(
    user_profile: dict | None,
    device_summary: str | None,
    daily_summaries: list[dict],
    sleep_quality: str | None,
) -> str:
    """Build the user-message prompt for the morning check-in LLM call."""
    context = format_context_block(
        user_profile=user_profile,
        device_data_summary=device_summary,
        daily_summaries=daily_summaries,
    )

    instructions: list[str] = [
        "Generate a morning check-in message for this user.",
        "Keep it brief: 2-3 sentences maximum.",
        "Ask about today's plans — specifically what time they're planning to train, if relevant.",
        "One question maximum.",
    ]

    if device_summary:
        instructions.append(
            "Reference the actual sleep/device data naturally (don't recite numbers robotically)."
        )
    else:
        instructions.append(
            "No sleep data is available — ask how they slept instead of referencing data."
        )

    if sleep_quality == "poor":
        instructions.append(
            "The user slept poorly. Use an empathetic, gentle tone. "
            "Acknowledge the rough night. Don't push hard on training."
        )
    elif sleep_quality == "good":
        instructions.append(
            "The user slept well. Use an energized, upbeat tone."
        )

    prompt = ""
    if context:
        prompt += context + "\n\n"
    prompt += "## Instructions\n" + "\n".join(f"- {i}" for i in instructions)

    return prompt


def generate_morning_checkin(user_id: str) -> str | None:
    """Generate a morning check-in message. Returns None if governor blocks."""
    # Step 1: Check governor
    if not can_send(user_id, "check_in"):
        logger.info("Morning check-in blocked by governor for user %s", user_id)
        return None

    # Step 2: Load user profile
    user_profile = db.get_user(user_id)

    # Step 3: Load last night's device data
    yesterday = _yesterday_iso()
    sleep_records = db.get_device_data(
        user_id, source="oura", data_type="sleep", since=yesterday
    )
    readiness_records = db.get_device_data(
        user_id, data_type="readiness", since=yesterday
    )
    weight_records = db.get_device_data(
        user_id, source="renpho", data_type="weight", since=yesterday
    )

    # Step 4: Load recent daily summaries
    daily_summaries = db.get_daily_summaries(user_id, days=3)

    # Step 5: Format prompt
    device_summary = _format_device_summary(
        sleep_records, readiness_records, weight_records
    )
    sleep_quality = _get_sleep_quality(sleep_records)

    morning_prompt = _build_morning_prompt(
        user_profile, device_summary, daily_summaries, sleep_quality
    )

    # Step 6: Call LLM
    message = call_llm(SYSTEM_PROMPT, morning_prompt, max_tokens=256)

    logger.info("Generated morning check-in for user %s", user_id)
    return message


# --- Evening check-in ---


def _today_iso() -> str:
    """Return today's date as ISO date string (YYYY-MM-DD) in UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_todays_activities(user_id: str) -> list[dict]:
    """Fetch today's activity records from device data (garmin/strava)."""
    today = _today_iso()
    activities: list[dict] = []
    for source in ("garmin", "strava"):
        records = db.get_device_data(
            user_id, source=source, data_type="activity", since=today
        )
        activities.extend(records)
    return activities


def _format_activities_summary(activities: list[dict]) -> str:
    """Format a list of activity records into a readable summary."""
    if not activities:
        return ""
    lines: list[str] = []
    for act in activities:
        data = act.get("data", {})
        name = data.get("name", data.get("type", "Activity"))
        duration = data.get("duration_minutes", "?")
        source = act.get("source", "unknown")
        lines.append(f"- {name} ({duration} min) via {source}")
    return "\n".join(lines)


def _morning_checkin_sent_today(user_id: str) -> bool:
    """Check if a morning check-in was sent today."""
    today = _today_iso()
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM messages "
            "WHERE user_id = ? AND direction = 'outbound' "
            "AND trigger_type = 'morning_check_in' "
            "AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, today),
        ).fetchone()
    return row is not None


def _user_replied_since_morning_checkin(user_id: str) -> bool:
    """Check if the user sent any message after today's morning check-in."""
    today = _today_iso()
    with db.get_connection() as conn:
        morning_row = conn.execute(
            "SELECT created_at FROM messages "
            "WHERE user_id = ? AND direction = 'outbound' "
            "AND trigger_type = 'morning_check_in' "
            "AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, today),
        ).fetchone()
        if morning_row is None:
            return True  # No morning check-in sent, no issue

        morning_ts = morning_row["created_at"]

        reply_row = conn.execute(
            "SELECT id FROM messages "
            "WHERE user_id = ? AND direction = 'inbound' "
            "AND created_at > ? "
            "LIMIT 1",
            (user_id, morning_ts),
        ).fetchone()
    return reply_row is not None


def _build_evening_prompt(
    user_profile: dict | None,
    activities: list[dict],
    activities_summary: str,
    recent_messages: list[dict],
) -> str:
    """Build the user-message prompt for the evening check-in LLM call."""
    context = format_context_block(
        user_profile=user_profile,
        recent_messages=[
            {"role": m["direction"], "content": m["content"]}
            for m in reversed(recent_messages)
        ],
        device_data_summary=activities_summary or None,
    )

    if activities:
        activity_instruction = (
            "The user trained today. Acknowledge the workout briefly and "
            "ask how it felt. Here are today's activities:\n"
            f"{activities_summary}"
        )
    else:
        activity_instruction = (
            "No workout was detected today. This could be a rest day — "
            "that's perfectly fine. Do not be judgmental or imply they should "
            "have worked out."
        )

    instructions = [
        "Generate an evening check-in message for this user.",
        "It's the end of their day — they are winding down.",
        "Keep it short: 1-2 sentences maximum.",
        "Ask one open-ended question about how their day went.",
        "Be warm but not over-the-top.",
        "Follow all persona and safety rules.",
        activity_instruction,
    ]

    prompt = ""
    if context:
        prompt += context + "\n\n"
    prompt += "## Instructions\n" + "\n".join(f"- {i}" for i in instructions)

    return prompt


def generate_evening_checkin(user_id: str) -> str | None:
    """Generate an evening check-in message.

    Returns None if governor blocks, morning check-in was unanswered,
    or there's another reason to skip.
    """
    # Step 1: Check governor
    if not can_send(user_id, "check_in"):
        logger.info("Evening check-in blocked by governor for user %s", user_id)
        return None

    # Step 2: Skip if morning check-in was sent today but user hasn't replied
    if _morning_checkin_sent_today(user_id) and not _user_replied_since_morning_checkin(user_id):
        logger.info(
            "Skipping evening check-in for user %s: morning check-in unanswered",
            user_id,
        )
        return None

    # Step 3: Load today's activities
    activities = _get_todays_activities(user_id)
    activities_summary = _format_activities_summary(activities)

    # Step 4: Load user profile and recent messages
    user_profile = db.get_user(user_id)
    recent_msgs = db.get_recent_messages(user_id, limit=10)

    # Step 5: Build prompt and call LLM
    evening_prompt = _build_evening_prompt(
        user_profile, activities, activities_summary, recent_msgs
    )

    message = call_llm(SYSTEM_PROMPT, evening_prompt, max_tokens=256)
    logger.info("Generated evening check-in for user %s", user_id)
    return message
