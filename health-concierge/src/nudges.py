"""Proactive nudges triggered by device data events or time-based rules.

Nudge types:
1. Post-workout: encouragement + recovery after new activity detected
2. Bedtime: reminder 30 min before stated bedtime goal
3. Drift — no workout: gentle alert after N days without activity
4. Drift — sleep: bedtime shifted >30 min later over 5 days vs prior week
5. Drift — weight: weight trend up >1kg over 2 weeks
"""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src import db
from src.governor import can_send, record_send
from src.llm import call_llm
from src.prompts.persona import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Defaults
WORKOUT_DRIFT_DAYS = 4
SLEEP_DRIFT_SHIFT_MINUTES = 30
SLEEP_DRIFT_RECENT_DAYS = 5
SLEEP_DRIFT_BASELINE_DAYS = 7
WEIGHT_DRIFT_KG = 1.0
WEIGHT_DRIFT_WEEKS = 2
POST_WORKOUT_WINDOW_HOURS = 1


def _now_utc() -> datetime:
    """Return current UTC datetime. Separated for easy mocking."""
    return datetime.now(timezone.utc)


def _today_iso() -> str:
    """Return today's date as ISO string."""
    return _now_utc().strftime("%Y-%m-%d")


def _get_user_timezone(user_id: str) -> ZoneInfo:
    """Get user timezone, defaulting to Asia/Jerusalem."""
    user = db.get_user(user_id)
    tz_name = "Asia/Jerusalem"
    if user and user.get("timezone"):
        tz_name = user["timezone"]
    return ZoneInfo(tz_name)


def _count_drift_nudges_today(user_id: str) -> int:
    """Count drift nudge messages sent today (user-local time)."""
    user_tz = _get_user_timezone(user_id)
    now_local = _now_utc().astimezone(user_tz)
    start_of_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_local.astimezone(timezone.utc).isoformat()

    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages "
            "WHERE user_id = ? AND direction = 'outbound' "
            "AND trigger_type IN ('nudge_drift_workout', 'nudge_drift_sleep', 'nudge_drift_weight') "
            "AND created_at >= ?",
            (user_id, start_of_day_utc),
        ).fetchone()
    return row["cnt"] if row else 0


def _generate_nudge_message(nudge_type: str, context: str) -> str:
    """Use LLM to generate a nudge message."""
    prompt = (
        f"## Nudge type\n{nudge_type}\n\n"
        f"## Context\n{context}\n\n"
        "## Instructions\n"
        "- Generate a brief nudge message (1-2 sentences).\n"
        "- Use the Gentle Drift Alert or Pre-Behavior Primer archetype.\n"
        "- Be warm, non-judgmental, and brief.\n"
        "- Do not guilt-trip or use streak language.\n"
        "- One question maximum.\n"
        "- Follow all persona and safety rules.\n"
    )
    return call_llm(SYSTEM_PROMPT, prompt, max_tokens=128)


def check_post_workout(user_id: str) -> str | None:
    """Check for new activity in the last hour and send encouragement.

    Returns nudge message or None.
    """
    since = (_now_utc() - timedelta(hours=POST_WORKOUT_WINDOW_HOURS)).isoformat()

    activities: list[dict] = []
    for source in ("garmin", "strava"):
        records = db.get_device_data(
            user_id, source=source, data_type="activity", since=since
        )
        activities.extend(records)

    if not activities:
        return None

    # Check if we already sent a post-workout nudge recently (last 2 hours)
    check_since = (_now_utc() - timedelta(hours=2)).isoformat()
    with db.get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM messages "
            "WHERE user_id = ? AND direction = 'outbound' "
            "AND trigger_type = 'nudge_post_workout' "
            "AND created_at >= ?",
            (user_id, check_since),
        ).fetchone()

    if existing:
        logger.debug("Post-workout nudge already sent for user %s", user_id)
        return None

    # Build context from the activity
    act = activities[0]
    data = act.get("data", {})
    name = data.get("name", data.get("type", "Activity"))
    duration = data.get("duration_minutes", "unknown")
    source = act.get("source", "unknown")

    context = (
        f"The user just completed: {name} ({duration} min) via {source}. "
        "Send encouragement and brief recovery advice."
    )

    return _generate_nudge_message("Post-workout encouragement", context)


def check_bedtime(user_id: str) -> str | None:
    """Check if it's 30 min before the user's bedtime goal.

    Returns nudge message or None.
    """
    user = db.get_user(user_id)
    if not user:
        return None

    # Get bedtime goal from user preferences or goals
    goals = user.get("goals") or {}
    bedtime_str = goals.get("bedtime")
    if not bedtime_str:
        return None

    # Parse bedtime (expected format: "HH:MM" or "23:00")
    try:
        bedtime_hour, bedtime_minute = map(int, bedtime_str.split(":"))
    except (ValueError, AttributeError):
        logger.warning("Invalid bedtime format for user %s: %s", user_id, bedtime_str)
        return None

    user_tz = _get_user_timezone(user_id)
    now_local = _now_utc().astimezone(user_tz)

    # Target is 30 min before bedtime
    target_time = now_local.replace(
        hour=bedtime_hour, minute=bedtime_minute, second=0, microsecond=0
    ) - timedelta(minutes=30)

    # Check if we're within a 15-minute window of the target
    diff = abs((now_local - target_time).total_seconds())
    if diff > 15 * 60:  # more than 15 min away
        return None

    # Check if already sent today
    start_of_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_local.astimezone(timezone.utc).isoformat()

    with db.get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM messages "
            "WHERE user_id = ? AND direction = 'outbound' "
            "AND trigger_type = 'nudge_bedtime' "
            "AND created_at >= ?",
            (user_id, start_of_day_utc),
        ).fetchone()

    if existing:
        return None

    context = f"It's about 30 minutes before the user's bedtime goal ({bedtime_str}). Suggest winding down."
    return _generate_nudge_message("Bedtime reminder", context)


def check_drift_workout(user_id: str) -> str | None:
    """Check if no workout in the last N days (default 4).

    Returns nudge message or None.
    """
    since = (_now_utc() - timedelta(days=WORKOUT_DRIFT_DAYS)).isoformat()

    activities: list[dict] = []
    for source in ("garmin", "strava"):
        records = db.get_device_data(
            user_id, source=source, data_type="activity", since=since
        )
        activities.extend(records)

    if activities:
        return None  # Recent activity exists, no drift

    context = (
        f"No workout detected in the last {WORKOUT_DRIFT_DAYS} days. "
        "Send a gentle check-in — not judgmental, just curious if everything is okay."
    )
    return _generate_nudge_message("Gentle drift alert — no recent workout", context)


def check_drift_sleep(user_id: str) -> str | None:
    """Check if average bedtime shifted >30 min later over the past 5 days vs prior week.

    Returns nudge message or None.
    """
    now = _now_utc()

    # Recent period: last 5 days
    recent_since = (now - timedelta(days=SLEEP_DRIFT_RECENT_DAYS)).isoformat()
    recent_records = db.get_device_data(
        user_id, data_type="sleep", since=recent_since
    )

    # Baseline period: 5-12 days ago
    baseline_end = (now - timedelta(days=SLEEP_DRIFT_RECENT_DAYS)).isoformat()
    baseline_start = (
        now - timedelta(days=SLEEP_DRIFT_RECENT_DAYS + SLEEP_DRIFT_BASELINE_DAYS)
    ).isoformat()
    baseline_records = db.get_device_data(
        user_id, data_type="sleep", since=baseline_start
    )
    # Filter baseline to only records before recent period
    baseline_records = [
        r for r in baseline_records
        if r.get("recorded_at", "") < baseline_end
    ]

    if len(recent_records) < 3 or len(baseline_records) < 3:
        return None  # Not enough data

    def _avg_bedtime_minutes(records: list[dict]) -> float | None:
        """Extract average bedtime as minutes-from-midnight from sleep data."""
        bedtimes: list[float] = []
        for rec in records:
            data = rec.get("data", {})
            bt = data.get("bedtime")
            if bt:
                try:
                    parts = bt.split(":")
                    minutes = int(parts[0]) * 60 + int(parts[1])
                    # Handle after-midnight bedtimes (e.g., 01:00 = 25*60)
                    if minutes < 12 * 60:
                        minutes += 24 * 60
                    bedtimes.append(minutes)
                except (ValueError, IndexError):
                    continue
        if not bedtimes:
            return None
        return sum(bedtimes) / len(bedtimes)

    recent_avg = _avg_bedtime_minutes(recent_records)
    baseline_avg = _avg_bedtime_minutes(baseline_records)

    if recent_avg is None or baseline_avg is None:
        return None

    shift = recent_avg - baseline_avg
    if shift <= SLEEP_DRIFT_SHIFT_MINUTES:
        return None

    context = (
        f"The user's average bedtime has shifted about {int(shift)} minutes later "
        "over the past 5 days compared to the prior week. "
        "Gently mention the shift without being preachy."
    )
    return _generate_nudge_message("Gentle drift alert — bedtime shifting later", context)


def check_drift_weight(user_id: str) -> str | None:
    """Check if weight trend is up >1kg over 2 weeks.

    Returns nudge message or None.
    """
    now = _now_utc()
    since = (now - timedelta(weeks=WEIGHT_DRIFT_WEEKS)).isoformat()

    weight_records = db.get_device_data(
        user_id, data_type="weight", since=since
    )

    if len(weight_records) < 2:
        return None

    # Records are newest first (from db query ORDER BY recorded_at DESC)
    newest = weight_records[0]
    oldest = weight_records[-1]

    newest_weight = newest.get("data", {}).get("weight_kg")
    oldest_weight = oldest.get("data", {}).get("weight_kg")

    if newest_weight is None or oldest_weight is None:
        return None

    diff = newest_weight - oldest_weight
    if diff <= WEIGHT_DRIFT_KG:
        return None

    context = (
        f"Weight has trended up by about {diff:.1f} kg over the past "
        f"{WEIGHT_DRIFT_WEEKS} weeks (from {oldest_weight} to {newest_weight} kg). "
        "Mention it gently, without judgment. Focus on awareness, not alarm."
    )
    return _generate_nudge_message("Gentle drift alert — weight trend", context)


def check_and_send_nudges(user_id: str) -> list[str]:
    """Evaluate all nudge conditions and send if triggered and governor allows.

    Returns list of nudge messages that were sent.
    """
    sent: list[str] = []

    # Post-workout nudge (not a drift nudge, so no drift-per-day limit)
    if can_send(user_id, "nudge"):
        msg = check_post_workout(user_id)
        if msg:
            db.save_message(user_id, "outbound", msg, trigger_type="nudge_post_workout")
            record_send(user_id)
            sent.append(msg)
            logger.info("Post-workout nudge sent to user %s", user_id)

    # Bedtime nudge (not a drift nudge)
    if can_send(user_id, "nudge"):
        msg = check_bedtime(user_id)
        if msg:
            db.save_message(user_id, "outbound", msg, trigger_type="nudge_bedtime")
            record_send(user_id)
            sent.append(msg)
            logger.info("Bedtime nudge sent to user %s", user_id)

    # Drift nudges — max 1 per day
    drift_checks = [
        ("nudge_drift_workout", check_drift_workout),
        ("nudge_drift_sleep", check_drift_sleep),
        ("nudge_drift_weight", check_drift_weight),
    ]

    for trigger_type, check_fn in drift_checks:
        if _count_drift_nudges_today(user_id) >= 1:
            logger.debug("Drift nudge limit reached for user %s today", user_id)
            break

        if not can_send(user_id, "nudge"):
            logger.debug("Governor blocked nudge for user %s", user_id)
            break

        msg = check_fn(user_id)
        if msg:
            db.save_message(user_id, "outbound", msg, trigger_type=trigger_type)
            record_send(user_id)
            sent.append(msg)
            logger.info("%s sent to user %s", trigger_type, user_id)

    return sent
