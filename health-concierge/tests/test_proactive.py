"""Tests for proactive message generation (morning + evening check-ins)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

from src import db
from src.proactive import (
    generate_morning_checkin,
    generate_evening_checkin,
    _build_evening_prompt,
    _build_morning_prompt,
)


@pytest.fixture(autouse=True)
def setup_db(tmp_db_path, test_settings, monkeypatch):
    """Initialize a fresh DB and patch settings for every test."""
    monkeypatch.setattr("src.db.settings", test_settings)
    monkeypatch.setattr("config.settings", test_settings)
    db.init_db(str(tmp_db_path))
    db.upsert_user("u1", name="Test", timezone="Asia/Jerusalem")
    yield


def _utc(year=2026, month=3, day=7, hour=10, minute=0) -> datetime:
    """Helper: build a UTC datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _mock_now(dt: datetime):
    """Return a patcher that mocks _now_utc in the governor to return dt."""
    return patch("src.governor._now_utc", return_value=dt)


def _mock_today(date_str: str):
    """Return a patcher that mocks _today_iso in proactive to return date_str."""
    return patch("src.proactive._today_iso", return_value=date_str)


def _insert_activity(user_id: str, source: str, name: str, duration: int, recorded_at: str):
    """Insert an activity record into device_data."""
    db.save_device_data(
        user_id,
        source=source,
        data_type="activity",
        data={"name": name, "duration_minutes": duration, "type": "running"},
        recorded_at=recorded_at,
    )


def _insert_morning_checkin(user_id: str, created_at: str):
    """Insert a morning check-in outbound message."""
    db.save_message(
        user_id, "outbound", "Good morning!", trigger_type="morning_check_in"
    )
    # Overwrite the created_at to the desired time
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE messages SET created_at = ? "
            "WHERE id = (SELECT id FROM messages "
            "WHERE user_id = ? AND trigger_type = 'morning_check_in' "
            "ORDER BY id DESC LIMIT 1)",
            (created_at, user_id),
        )


def _insert_user_reply(user_id: str, created_at: str):
    """Insert an inbound message from the user."""
    db.save_message(user_id, "inbound", "Hey there!")
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE messages SET created_at = ? "
            "WHERE id = (SELECT id FROM messages "
            "WHERE user_id = ? AND direction = 'inbound' "
            "ORDER BY id DESC LIMIT 1)",
            (created_at, user_id),
        )


# --- Evening check-in: activity references ---


def test_evening_checkin_references_todays_activity():
    """Insert garmin activity for today, verify LLM prompt mentions it."""
    today = "2026-03-07"
    recorded_at = f"{today}T14:00:00+00:00"
    _insert_activity("u1", "garmin", "Morning Run", 45, recorded_at)

    with _mock_now(_utc(hour=18)), \
         _mock_today(today), \
         patch("src.proactive.call_llm", return_value="Nice run today!") as mock_llm:
        result = generate_evening_checkin("u1")

    assert result is not None
    # Check the prompt passed to call_llm references the activity
    prompt_arg = mock_llm.call_args[0][1]
    assert "Morning Run" in prompt_arg
    assert "45 min" in prompt_arg


def test_evening_checkin_acknowledges_workout():
    """Verify prompt includes workout acknowledgement instruction when activity exists."""
    today = "2026-03-07"
    recorded_at = f"{today}T10:00:00+00:00"
    _insert_activity("u1", "strava", "Cycling", 60, recorded_at)

    with _mock_now(_utc(hour=18)), \
         _mock_today(today), \
         patch("src.proactive.call_llm", return_value="Great ride!") as mock_llm:
        generate_evening_checkin("u1")

    prompt_arg = mock_llm.call_args[0][1]
    assert "trained today" in prompt_arg.lower() or "acknowledge the workout" in prompt_arg.lower()


def test_evening_checkin_neutral_on_rest_day():
    """No activities in DB, verify prompt says rest day is fine."""
    today = "2026-03-07"

    with _mock_now(_utc(hour=18)), \
         _mock_today(today), \
         patch("src.proactive.call_llm", return_value="How was your day?") as mock_llm:
        result = generate_evening_checkin("u1")

    assert result is not None
    prompt_arg = mock_llm.call_args[0][1]
    assert "rest day" in prompt_arg.lower()
    assert "not be judgmental" in prompt_arg.lower() or "perfectly fine" in prompt_arg.lower()


# --- Evening check-in: skip logic ---


def test_evening_checkin_skips_if_morning_unanswered():
    """Morning check-in sent today but user hasn't replied -> returns None."""
    today = "2026-03-07"
    morning_ts = f"{today}T07:00:00+00:00"
    _insert_morning_checkin("u1", morning_ts)

    with _mock_now(_utc(hour=18)), \
         _mock_today(today), \
         patch("src.proactive.call_llm") as mock_llm:
        result = generate_evening_checkin("u1")

    assert result is None
    mock_llm.assert_not_called()


def test_evening_checkin_sends_if_morning_answered():
    """Morning check-in sent today and user replied -> should generate."""
    today = "2026-03-07"
    morning_ts = f"{today}T07:00:00+00:00"
    reply_ts = f"{today}T08:00:00+00:00"
    _insert_morning_checkin("u1", morning_ts)
    _insert_user_reply("u1", reply_ts)

    with _mock_now(_utc(hour=18)), \
         _mock_today(today), \
         patch("src.proactive.call_llm", return_value="Evening!"):
        result = generate_evening_checkin("u1")

    assert result is not None


def test_evening_checkin_skips_quiet_mode():
    """Mock can_send returning False -> returns None."""
    with patch("src.proactive.can_send", return_value=False), \
         patch("src.proactive.call_llm") as mock_llm:
        result = generate_evening_checkin("u1")

    assert result is None
    mock_llm.assert_not_called()


def test_evening_checkin_updates_engagement_state():
    """Verify that the evening script pattern records the send properly."""
    today = "2026-03-07"

    with _mock_now(_utc(hour=18)), \
         _mock_today(today), \
         patch("src.proactive.call_llm", return_value="Good evening!"):
        msg = generate_evening_checkin("u1")

    assert msg is not None

    # Simulate what the script does after getting the message
    from src.governor import record_send
    with _mock_now(_utc(hour=18)):
        db.save_message("u1", "outbound", msg, trigger_type="evening_check_in")
        record_send("u1")

    state = db.get_engagement_state("u1")
    assert state["daily_outbound_count"] == 1
    assert state["unanswered_count"] == 1
    assert state["last_outbound_message"] is not None
