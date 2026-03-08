"""Tests for the engagement state machine module."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src import db
from src.engagement import (
    check_mode_transition,
    get_re_engagement_message,
    update_on_outbound,
    update_on_user_message,
)


@pytest.fixture(autouse=True)
def setup_db(tmp_db_path, test_settings, monkeypatch):
    """Initialize a fresh DB and patch settings for every test."""
    monkeypatch.setattr("src.db.settings", test_settings)
    monkeypatch.setattr("config.settings", test_settings)
    db.init_db(str(tmp_db_path))
    db.upsert_user("u1", name="Test")
    yield


def _set_state(user_id: str, **fields) -> None:
    """Helper: set engagement state fields."""
    db.update_engagement_state(user_id, **fields)


def _utc(year=2026, month=3, day=7, hour=10, minute=0) -> datetime:
    """Helper: build a UTC datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _mock_now(dt: datetime):
    """Return a patcher that mocks _now_utc to return dt."""
    return patch("src.engagement._now_utc", return_value=dt)


# --- test_new_user_starts_active ---

def test_new_user_starts_active():
    """New engagement state defaults to active."""
    state = db.get_engagement_state("u1")
    assert state["mode"] == "active"
    assert state["unanswered_count"] == 0


# --- test_user_message_sets_active ---

def test_user_message_sets_active():
    """User in quiet mode, sends message -> active."""
    _set_state("u1", mode="quiet")
    with _mock_now(_utc()):
        update_on_user_message("u1")
    state = db.get_engagement_state("u1")
    assert state["mode"] == "active"


# --- test_user_message_resets_unanswered ---

def test_user_message_resets_unanswered():
    """Unanswered count was 3, user messages -> 0."""
    _set_state("u1", unanswered_count=3)
    with _mock_now(_utc()):
        update_on_user_message("u1")
    state = db.get_engagement_state("u1")
    assert state["unanswered_count"] == 0


# --- test_outbound_increments_unanswered ---

def test_outbound_increments_unanswered():
    """Unanswered was 0, outbound -> 1."""
    _set_state("u1", unanswered_count=0, daily_outbound_count=0)
    with _mock_now(_utc()):
        update_on_outbound("u1")
    state = db.get_engagement_state("u1")
    assert state["unanswered_count"] == 1
    assert state["daily_outbound_count"] == 1
    assert state["last_outbound_message"] is not None


# --- test_transitions_to_quiet_after_36h ---

def test_transitions_to_quiet_after_36h():
    """Last user message 37h ago, check_mode_transition -> 'quiet'."""
    now = _utc(hour=10)
    old_msg = (now - timedelta(hours=37)).isoformat()
    _set_state("u1", mode="active", last_user_message=old_msg)
    with _mock_now(now):
        mode = check_mode_transition("u1")
    assert mode == "quiet"
    state = db.get_engagement_state("u1")
    assert state["mode"] == "quiet"


# --- test_transitions_to_paused_after_7d ---

def test_transitions_to_paused_after_7d():
    """Last user message 8 days ago, mode quiet, check -> 'paused'."""
    now = _utc(hour=10)
    old_msg = (now - timedelta(days=8)).isoformat()
    _set_state("u1", mode="quiet", last_user_message=old_msg)
    with _mock_now(now):
        mode = check_mode_transition("u1")
    assert mode == "paused"
    state = db.get_engagement_state("u1")
    assert state["mode"] == "paused"


# --- test_re_engagement_sent_once ---

def test_re_engagement_sent_once():
    """In paused mode, first call returns message, second returns None."""
    _set_state("u1", mode="paused")

    with patch("src.engagement.call_llm", return_value="Hey Test, just checking in!"):
        msg = get_re_engagement_message("u1")
    assert msg == "Hey Test, just checking in!"

    # Simulate saving the re-engagement message to DB (as the caller would)
    db.save_message("u1", "outbound", msg, trigger_type="re_engagement")

    # Second call should return None
    with patch("src.engagement.call_llm") as mock_llm:
        msg2 = get_re_engagement_message("u1")
    assert msg2 is None
    mock_llm.assert_not_called()


# --- test_re_engagement_not_sent_if_already_sent ---

def test_re_engagement_not_sent_if_already_sent():
    """Insert a re_engagement message in DB, call -> None."""
    _set_state("u1", mode="paused")
    db.save_message("u1", "outbound", "Previous re-engagement", trigger_type="re_engagement")

    with patch("src.engagement.call_llm") as mock_llm:
        msg = get_re_engagement_message("u1")
    assert msg is None
    mock_llm.assert_not_called()


# --- test_user_returns_from_paused_to_active ---

def test_user_returns_from_paused_to_active():
    """Paused user sends message -> active."""
    _set_state("u1", mode="paused", unanswered_count=5)
    with _mock_now(_utc()):
        update_on_user_message("u1")
    state = db.get_engagement_state("u1")
    assert state["mode"] == "active"
    assert state["unanswered_count"] == 0
