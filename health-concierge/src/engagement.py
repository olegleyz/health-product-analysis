"""Engagement state machine.

Manages user engagement modes (active / quiet / paused) and
handles mode transitions and re-engagement messaging.

Mode transitions:
- active -> quiet:  no user message for 36 hours
- quiet  -> paused: no user message for 7 days
- any    -> active: user sends a message
"""

import logging
from datetime import datetime, timedelta, timezone

from src import db
from src.llm import call_llm

logger = logging.getLogger(__name__)

ACTIVE_TO_QUIET_HOURS = 36
QUIET_TO_PAUSED_DAYS = 7


def _now_utc() -> datetime:
    """Return current UTC datetime. Separated for easy mocking."""
    return datetime.now(timezone.utc)


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp string to a timezone-aware datetime."""
    if not ts:
        return None
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def update_on_user_message(user_id: str) -> None:
    """Called when user sends any message.

    Sets mode to 'active', updates last_user_message to now,
    and resets unanswered_count to 0.
    """
    state = db.get_engagement_state(user_id)
    old_mode = state.get("mode", "active")
    now_iso = _now_utc().isoformat()

    db.update_engagement_state(
        user_id,
        mode="active",
        last_user_message=now_iso,
        unanswered_count=0,
    )

    if old_mode != "active":
        logger.info("User %s: %s -> active (user message received)", user_id, old_mode)


def update_on_outbound(user_id: str) -> None:
    """Called when system sends a message.

    Updates last_outbound_message to now, increments daily_outbound_count,
    and increments unanswered_count.
    """
    state = db.get_engagement_state(user_id)
    now_iso = _now_utc().isoformat()

    db.update_engagement_state(
        user_id,
        last_outbound_message=now_iso,
        daily_outbound_count=state.get("daily_outbound_count", 0) + 1,
        unanswered_count=state.get("unanswered_count", 0) + 1,
    )


def check_mode_transition(user_id: str) -> str:
    """Evaluate if mode should change based on silence duration.

    Returns the current mode after any transition.
    """
    state = db.get_engagement_state(user_id)
    mode = state.get("mode", "active")
    last_user_msg = _parse_iso(state.get("last_user_message"))
    now = _now_utc()

    if last_user_msg is None:
        return mode

    silence = now - last_user_msg

    if mode == "active" and silence > timedelta(hours=ACTIVE_TO_QUIET_HOURS):
        logger.info("User %s: active -> quiet (silent for %s)", user_id, silence)
        db.update_engagement_state(user_id, mode="quiet")
        mode = "quiet"

    if mode == "quiet" and silence > timedelta(days=QUIET_TO_PAUSED_DAYS):
        logger.info("User %s: quiet -> paused (silent for %s)", user_id, silence)
        db.update_engagement_state(user_id, mode="paused")
        mode = "paused"

    return mode


def get_re_engagement_message(user_id: str) -> str | None:
    """Generate a re-engagement message for paused users.

    Returns None if user is not paused or if a re-engagement
    message has already been sent recently.
    """
    state = db.get_engagement_state(user_id)
    mode = state.get("mode", "active")

    if mode != "paused":
        return None

    # Check if we've already sent a re-engagement message
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM messages WHERE user_id = ? "
            "AND direction = 'outbound' AND trigger_type = 're_engagement' "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()

    if row is not None:
        return None

    # Generate a gentle re-engagement message via LLM
    user = db.get_user(user_id)
    name = user.get("name", "there") if user else "there"

    system_prompt = (
        "You are a friendly health concierge. Generate a short, warm, "
        "low-pressure re-engagement message for a user who hasn't been active "
        "for a while. Keep it to 1-2 sentences. No pressure to respond. "
        "Be genuine and caring."
    )
    user_message = (
        f"Generate a gentle re-engagement message for {name}. "
        "Something like 'Hey, just checking in. No pressure to respond — "
        "I'm here whenever you're ready.' but in your own words."
    )

    message = call_llm(system_prompt, user_message, max_tokens=150)
    return message
