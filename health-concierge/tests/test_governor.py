"""Tests for the frequency governor module."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src import db
from src.governor import (
    can_send,
    record_send,
    record_user_message,
    reset_daily_counts,
)


@pytest.fixture(autouse=True)
def setup_db(tmp_db_path, test_settings, monkeypatch):
    """Initialize a fresh DB and patch settings for every test."""
    monkeypatch.setattr("src.db.settings", test_settings)
    monkeypatch.setattr("config.settings", test_settings)
    db.init_db(str(tmp_db_path))
    # Create a test user
    db.upsert_user("u1", name="Test", timezone="Asia/Jerusalem")
    yield


def _set_state(user_id: str, **fields) -> None:
    """Helper: set engagement state fields."""
    db.update_engagement_state(user_id, **fields)


def _utc(year=2026, month=3, day=7, hour=10, minute=0) -> datetime:
    """Helper: build a UTC datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _mock_now(dt: datetime):
    """Return a patcher that mocks _now_utc to return dt."""
    return patch("src.governor._now_utc", return_value=dt)


# --- Basic allow / daily cap ---

def test_allows_first_message_of_day():
    """Fresh state, daily count 0 -> True."""
    # 10 AM UTC = 12 PM Israel (within allowed hours)
    with _mock_now(_utc(hour=10)):
        assert can_send("u1", "check_in") is True


def test_blocks_after_daily_cap():
    """Daily outbound count at 4 -> False."""
    _set_state("u1", daily_outbound_count=4)
    with _mock_now(_utc(hour=10)):
        assert can_send("u1", "check_in") is False


# --- Nudge cap ---

def test_blocks_nudge_after_nudge_cap():
    """Two nudges already sent today -> nudge blocked."""
    now = _utc(hour=10)
    # Insert two outbound nudge messages for today
    with db.get_connection() as conn:
        for i in range(2):
            conn.execute(
                "INSERT INTO messages (user_id, direction, content, trigger_type, created_at) "
                "VALUES (?, 'outbound', ?, 'nudge', ?)",
                ("u1", f"nudge {i}", now.isoformat()),
            )
    with _mock_now(now):
        assert can_send("u1", "nudge") is False


def test_allows_checkin_even_after_nudge_cap():
    """Nudge cap hit but check_in still works."""
    now = _utc(hour=10)
    with db.get_connection() as conn:
        for i in range(2):
            conn.execute(
                "INSERT INTO messages (user_id, direction, content, trigger_type, created_at) "
                "VALUES (?, 'outbound', ?, 'nudge', ?)",
                ("u1", f"nudge {i}", now.isoformat()),
            )
    with _mock_now(now):
        assert can_send("u1", "check_in") is True


# --- Backoff ---

def test_reduces_cap_on_unanswered():
    """Unanswered count 2, daily count 1 -> False (cap reduced to 1)."""
    _set_state("u1", unanswered_count=2, daily_outbound_count=1)
    with _mock_now(_utc(hour=10)):
        assert can_send("u1", "check_in") is False


# --- Quiet mode ---

def test_blocks_in_quiet_mode_after_one():
    """Mode quiet, daily count 1 -> False."""
    _set_state("u1", mode="quiet", daily_outbound_count=1)
    with _mock_now(_utc(hour=10)):
        assert can_send("u1", "check_in") is False


# --- Paused mode ---

def test_blocks_all_in_paused_mode():
    """Mode paused -> blocks check_in and nudge, allows first re_engagement."""
    _set_state("u1", mode="paused", daily_outbound_count=0)
    with _mock_now(_utc(hour=10)):
        assert can_send("u1", "check_in") is False
        assert can_send("u1", "nudge") is False
        assert can_send("u1", "re_engagement") is True


def test_blocks_second_re_engagement_in_paused_mode():
    """Paused mode: only one re_engagement per day."""
    _set_state("u1", mode="paused", daily_outbound_count=1)
    with _mock_now(_utc(hour=10)):
        assert can_send("u1", "re_engagement") is False


# --- Time restrictions ---

def test_blocks_before_7am():
    """6 AM user-local time -> False."""
    # Asia/Jerusalem is UTC+2 (winter) or UTC+3 (summer).
    # March 7 2026 is winter (IST = UTC+2). So 4 AM UTC = 6 AM local.
    with _mock_now(_utc(hour=4)):
        assert can_send("u1", "check_in") is False


def test_blocks_after_11pm():
    """11:30 PM user-local time -> False."""
    # 21:30 UTC = 23:30 IST (UTC+2)
    with _mock_now(_utc(hour=21, minute=30)):
        assert can_send("u1", "check_in") is False


# --- Spacing ---

def test_blocks_within_2h_of_last_message():
    """Last outbound 1 hour ago -> False."""
    now = _utc(hour=10)
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    _set_state("u1", last_outbound_message=one_hour_ago)
    with _mock_now(now):
        assert can_send("u1", "check_in") is False


def test_allows_after_2h_spacing():
    """Last outbound 3 hours ago -> True."""
    now = _utc(hour=12)
    three_hours_ago = (now - timedelta(hours=3)).isoformat()
    _set_state("u1", last_outbound_message=three_hours_ago)
    with _mock_now(now):
        assert can_send("u1", "check_in") is True


# --- Mode transitions ---

def test_transition_active_to_quiet():
    """Last user message 37h ago, mode active -> transitions to quiet."""
    now = _utc(hour=10)
    old_msg = (now - timedelta(hours=37)).isoformat()
    _set_state("u1", mode="active", last_user_message=old_msg, daily_outbound_count=0)
    with _mock_now(now):
        # can_send triggers the transition
        can_send("u1", "check_in")
        state = db.get_engagement_state("u1")
        assert state["mode"] == "quiet"


def test_transition_quiet_to_paused():
    """Last user message 8 days ago, mode quiet -> transitions to paused."""
    now = _utc(hour=10)
    old_msg = (now - timedelta(days=8)).isoformat()
    _set_state("u1", mode="quiet", last_user_message=old_msg, daily_outbound_count=0)
    with _mock_now(now):
        can_send("u1", "check_in")
        state = db.get_engagement_state("u1")
        assert state["mode"] == "paused"


def test_transition_back_to_active_on_user_message():
    """User message resets mode to active."""
    _set_state("u1", mode="quiet", unanswered_count=3)
    with _mock_now(_utc(hour=10)):
        record_user_message("u1")
    state = db.get_engagement_state("u1")
    assert state["mode"] == "active"


# --- record_send ---

def test_record_send_increments_counts():
    """record_send increments daily count and unanswered count."""
    _set_state("u1", daily_outbound_count=0, unanswered_count=0)
    with _mock_now(_utc(hour=10)):
        record_send("u1")
    state = db.get_engagement_state("u1")
    assert state["daily_outbound_count"] == 1
    assert state["unanswered_count"] == 1
    assert state["last_outbound_message"] is not None


# --- reset_daily_counts ---

def test_reset_daily_counts():
    """After reset, daily count is 0."""
    _set_state("u1", daily_outbound_count=3)
    with _mock_now(_utc(hour=0)):
        reset_daily_counts()
    state = db.get_engagement_state("u1")
    assert state["daily_outbound_count"] == 0
    assert state["daily_outbound_reset_at"] is not None


# --- User message resets unanswered ---

def test_user_message_resets_unanswered_count():
    """After user message, unanswered count is 0."""
    _set_state("u1", unanswered_count=5)
    with _mock_now(_utc(hour=10)):
        record_user_message("u1")
    state = db.get_engagement_state("u1")
    assert state["unanswered_count"] == 0
