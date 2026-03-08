"""Proactive message generation.

Generates outbound messages (morning check-ins, evening check-ins,
weekly reflections, nudges, etc.) using device data, daily summaries,
and the LLM.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src import db
from src.governor import can_send
from src.llm import call_llm
from src.meals import get_meal_repertoire
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
    meal_repertoire: list[dict] | None = None,
) -> str:
    """Build the user-message prompt for the morning check-in LLM call."""
    context = format_context_block(
        user_profile=user_profile,
        device_data_summary=device_summary,
        daily_summaries=daily_summaries,
        meal_repertoire=meal_repertoire,
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

    # Step 5b: Load meal repertoire for nutrition context
    meal_repertoire = get_meal_repertoire(user_id)

    morning_prompt = _build_morning_prompt(
        user_profile, device_summary, daily_summaries, sleep_quality,
        meal_repertoire=meal_repertoire or None,
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
    meal_repertoire: list[dict] | None = None,
) -> str:
    """Build the user-message prompt for the evening check-in LLM call."""
    context = format_context_block(
        user_profile=user_profile,
        recent_messages=[
            {"role": m["direction"], "content": m["content"]}
            for m in reversed(recent_messages)
        ],
        device_data_summary=activities_summary or None,
        meal_repertoire=meal_repertoire,
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

    # Step 5: Load meal repertoire for nutrition context
    meal_repertoire = get_meal_repertoire(user_id)

    # Step 6: Build prompt and call LLM
    evening_prompt = _build_evening_prompt(
        user_profile, activities, activities_summary, recent_msgs,
        meal_repertoire=meal_repertoire or None,
    )

    message = call_llm(SYSTEM_PROMPT, evening_prompt, max_tokens=256)
    logger.info("Generated evening check-in for user %s", user_id)
    return message


# --- Weekly reflection ---


def _week_ago_iso() -> str:
    """Return the date 7 days ago as ISO date string (YYYY-MM-DD) in UTC."""
    return (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")


def _summarize_sleep_trend(daily_summaries: list[dict]) -> str | None:
    """Extract a sleep trend description from daily summaries.

    Looks at structured data for sleep_score or sleep_hours across days.
    Returns a short description or None if insufficient data.
    """
    scores: list[float] = []
    for s in daily_summaries:
        structured = s.get("structured", {})
        if isinstance(structured, dict):
            score = structured.get("sleep_score") or structured.get("sleep_hours")
            if score is not None:
                scores.append(float(score))

    if len(scores) < 2:
        return None

    # Summaries are newest-first; first_half = older, second_half = newer
    first_half = scores[len(scores) // 2 :]
    second_half = scores[: len(scores) // 2]

    if first_half and second_half:
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        if avg_second > avg_first + 2:
            return "improving"
        elif avg_second < avg_first - 2:
            return "declining"
    return "stable"


def _get_weight_change(
    device_data: list[dict],
) -> tuple[float | None, float | None]:
    """Return (earliest_weight, latest_weight) from weight device data.

    Returns (None, None) if no weight data found.
    """
    weights: list[tuple[str, float]] = []
    for rec in device_data:
        data = rec.get("data", {})
        w = data.get("weight_kg") or data.get("weight")
        if w is not None:
            weights.append((rec.get("recorded_at", ""), float(w)))

    if not weights:
        return None, None

    weights.sort(key=lambda x: x[0])
    return weights[0][1], weights[-1][1]


def _build_weekly_reflection_prompt(
    user_profile: dict | None,
    daily_summaries: list[dict],
    workout_count: int,
    sleep_trend: str | None,
    weight_earliest: float | None,
    weight_latest: float | None,
) -> str:
    """Build the prompt for the weekly reflection LLM call."""
    context = format_context_block(
        user_profile=user_profile,
        daily_summaries=daily_summaries,
    )

    # Build a data block for the LLM
    data_lines: list[str] = []
    data_lines.append(f"Workouts this week: {workout_count}")

    if sleep_trend:
        data_lines.append(f"Sleep trend: {sleep_trend}")
    else:
        data_lines.append("Sleep trend: insufficient data")

    if weight_earliest is not None and weight_latest is not None:
        change = weight_latest - weight_earliest
        sign = "+" if change > 0 else ""
        data_lines.append(
            f"Weight: {weight_earliest:.1f} kg -> {weight_latest:.1f} kg "
            f"({sign}{change:.1f} kg)"
        )
    else:
        data_lines.append("Weight: no data this week")

    data_block = "\n".join(data_lines)

    instructions = [
        "Generate a weekly reflection message for Sunday evening.",
        "This replaces the normal evening check-in.",
        "Summarize the week briefly using the data provided below.",
        f"Here is this week's data:\n{data_block}",
        "Include the workout count in your message.",
        "Mention the sleep trend if data is available.",
        "Mention weight change if data is available.",
        "Highlight one positive pattern you see in the daily summaries "
        "(e.g. 'You trained consistently' or 'Your sleep improved').",
        "End with one reflective question about next week "
        "(e.g. 'What do you want to focus on next week?').",
        "Keep it concise: 3-5 sentences maximum.",
        "Follow all persona and safety rules.",
    ]

    prompt = ""
    if context:
        prompt += context + "\n\n"
    prompt += "## Instructions\n" + "\n".join(f"- {i}" for i in instructions)

    return prompt


def generate_weekly_reflection(user_id: str) -> str | None:
    """Generate a weekly reflection message for Sunday evening.

    Summarizes the past 7 days: workouts, sleep trends, nutrition,
    weight change. Highlights one positive pattern and asks a
    reflective question.

    Returns None if the governor blocks the message.
    """
    # Step 1: Check governor
    if not can_send(user_id, "check_in"):
        logger.info("Weekly reflection blocked by governor for user %s", user_id)
        return None

    # Step 2: Load user profile
    user_profile = db.get_user(user_id)

    # Step 3: Load 7 days of daily summaries
    daily_summaries = db.get_daily_summaries(user_id, days=7)

    # Step 4: Load device data for the past week
    week_ago = _week_ago_iso()
    activity_data: list[dict] = []
    for source in ("garmin", "strava"):
        records = db.get_device_data(
            user_id, source=source, data_type="activity", since=week_ago
        )
        activity_data.extend(records)

    weight_data = db.get_device_data(
        user_id, data_type="weight", since=week_ago
    )

    # Step 5: Compute metrics
    workout_count = len(activity_data)
    sleep_trend = _summarize_sleep_trend(daily_summaries)
    weight_earliest, weight_latest = _get_weight_change(weight_data)

    # Step 6: Build prompt and call LLM
    reflection_prompt = _build_weekly_reflection_prompt(
        user_profile,
        daily_summaries,
        workout_count,
        sleep_trend,
        weight_earliest,
        weight_latest,
    )

    message = call_llm(SYSTEM_PROMPT, reflection_prompt, max_tokens=512)
    logger.info("Generated weekly reflection for user %s", user_id)
    return message
