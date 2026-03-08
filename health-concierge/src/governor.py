"""Message governor.

Controls message frequency, timing, and volume to avoid
notification fatigue. Enforces daily/weekly message budgets.

Rules (evaluated in order by can_send):
1. Daily cap (default 4)
2. Nudge cap (2/day)
3. Backoff (unanswered >= 2 reduces cap to 1/day)
4. Quiet mode (1 message/day)
5. Paused mode (block all except one re_engagement)
6. Time restrictions (7 AM - 11 PM user-local)
7. Spacing (2h minimum between outbound messages)

Mode transitions (checked before rules):
- active -> quiet: no user message for 36h
- quiet -> paused: no user message for 7 days
"""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src import db

logger = logging.getLogger(__name__)

# Configurable defaults
DEFAULT_DAILY_CAP = 4
DEFAULT_NUDGE_CAP = 2
BACKOFF_THRESHOLD = 2
SPACING_HOURS = 2
QUIET_HOURS_START = 23  # 11 PM
QUIET_HOURS_END = 7  # 7 AM
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


def _get_user_timezone(user_id: str) -> ZoneInfo:
    """Get the user's timezone from DB, defaulting to Asia/Jerusalem."""
    user = db.get_user(user_id)
    tz_name = "Asia/Jerusalem"
    if user and user.get("timezone"):
        tz_name = user["timezone"]
    return ZoneInfo(tz_name)


def _check_mode_transitions(user_id: str, state: dict) -> dict:
    """Check and apply mode transitions based on silence duration.

    Returns the (possibly updated) state dict.
    """
    now = _now_utc()
    last_user_msg = _parse_iso(state.get("last_user_message"))
    mode = state.get("mode", "active")

    if last_user_msg is None:
        return state

    silence = now - last_user_msg

    if mode == "active" and silence > timedelta(hours=ACTIVE_TO_QUIET_HOURS):
        logger.info("User %s: active -> quiet (silent for %s)", user_id, silence)
        db.update_engagement_state(user_id, mode="quiet")
        state["mode"] = "quiet"
        mode = "quiet"

    if mode == "quiet" and silence > timedelta(days=QUIET_TO_PAUSED_DAYS):
        logger.info("User %s: quiet -> paused (silent for %s)", user_id, silence)
        db.update_engagement_state(user_id, mode="paused")
        state["mode"] = "paused"

    return state


def _count_today_nudges(user_id: str, user_tz: ZoneInfo) -> int:
    """Count outbound nudge messages sent today in the user's timezone."""
    now_local = _now_utc().astimezone(user_tz)
    start_of_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_local.astimezone(timezone.utc).isoformat()

    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages "
            "WHERE user_id = ? AND direction = 'outbound' "
            "AND trigger_type = 'nudge' AND created_at >= ?",
            (user_id, start_of_day_utc),
        ).fetchone()
    return row["cnt"] if row else 0


def can_send(user_id: str, message_type: str) -> bool:
    """Check whether an outbound message is allowed.

    Args:
        user_id: The user to check.
        message_type: One of "check_in", "nudge", "re_engagement".

    Returns:
        True if the message may be sent, False if blocked.
    """
    state = db.get_engagement_state(user_id)
    user_tz = _get_user_timezone(user_id)
    now = _now_utc()

    # Apply mode transitions first
    state = _check_mode_transitions(user_id, state)

    mode = state.get("mode", "active")
    daily_count = state.get("daily_outbound_count", 0)
    unanswered = state.get("unanswered_count", 0)

    # Rule 1: Daily cap
    if daily_count >= DEFAULT_DAILY_CAP:
        logger.debug("User %s: blocked by daily cap (%d)", user_id, daily_count)
        return False

    # Rule 2: Nudge cap
    if message_type == "nudge":
        nudge_count = _count_today_nudges(user_id, user_tz)
        if nudge_count >= DEFAULT_NUDGE_CAP:
            logger.debug("User %s: blocked by nudge cap (%d)", user_id, nudge_count)
            return False

    # Rule 3: Backoff -- if unanswered >= 2, cap reduces to 1/day
    if unanswered >= BACKOFF_THRESHOLD and daily_count >= 1:
        logger.debug("User %s: blocked by backoff (unanswered=%d)", user_id, unanswered)
        return False

    # Rule 4: Quiet mode -- only 1 message/day
    if mode == "quiet" and daily_count >= 1:
        logger.debug("User %s: blocked by quiet mode cap", user_id)
        return False

    # Rule 5: Paused mode -- block all except one re_engagement
    if mode == "paused":
        if message_type != "re_engagement":
            logger.debug("User %s: blocked by paused mode (type=%s)", user_id, message_type)
            return False
        # Allow one re_engagement, but not if we already sent one today
        if daily_count >= 1:
            logger.debug("User %s: blocked by paused mode (already sent re_engagement)", user_id)
            return False

    # Rule 6: Time restrictions (7 AM - 11 PM user-local)
    now_local = now.astimezone(user_tz)
    if now_local.hour < QUIET_HOURS_END or now_local.hour >= QUIET_HOURS_START:
        logger.debug("User %s: blocked by time restriction (hour=%d)", user_id, now_local.hour)
        return False

    # Rule 7: Spacing -- at least 2 hours since last outbound
    last_outbound = _parse_iso(state.get("last_outbound_message"))
    if last_outbound is not None:
        elapsed = now - last_outbound
        if elapsed < timedelta(hours=SPACING_HOURS):
            logger.debug("User %s: blocked by spacing (%s since last)", user_id, elapsed)
            return False

    return True


def record_send(user_id: str) -> None:
    """Record that an outbound message was sent.

    Increments daily_outbound_count, updates last_outbound_message,
    and increments unanswered_count.
    """
    state = db.get_engagement_state(user_id)
    now_iso = _now_utc().isoformat()

    db.update_engagement_state(
        user_id,
        daily_outbound_count=state.get("daily_outbound_count", 0) + 1,
        last_outbound_message=now_iso,
        unanswered_count=state.get("unanswered_count", 0) + 1,
    )


def record_user_message(user_id: str) -> None:
    """Record that the user sent a message.

    Resets unanswered_count, updates last_user_message,
    and transitions mode back to active if needed.
    """
    now_iso = _now_utc().isoformat()
    db.update_engagement_state(
        user_id,
        last_user_message=now_iso,
        unanswered_count=0,
        mode="active",
    )


def reset_daily_counts() -> None:
    """Reset daily_outbound_count to 0 for all users.

    Intended to be called by a daily cron job at midnight.
    """
    now_iso = _now_utc().isoformat()
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE engagement_state SET daily_outbound_count = 0, "
            "daily_outbound_reset_at = ?",
            (now_iso,),
        )
    logger.info("Daily counts reset for all users")
