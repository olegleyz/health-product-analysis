"""Tests for proactive nudges."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src import db
from src.nudges import (
    check_and_send_nudges,
    check_bedtime,
    check_drift_sleep,
    check_drift_weight,
    check_drift_workout,
    check_post_workout,
)


USER_ID = "u1"


@pytest.fixture(autouse=True)
def setup_db(tmp_db_path, test_settings, monkeypatch):
    """Initialize a fresh DB and patch settings for every test."""
    monkeypatch.setattr("src.db.settings", test_settings)
    monkeypatch.setattr("config.settings", test_settings)
    db.init_db(str(tmp_db_path))
    db.upsert_user(USER_ID, name="Test User", timezone="Asia/Jerusalem")
    yield


def _utc(year=2026, month=3, day=7, hour=10, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _mock_now(dt: datetime):
    return patch("src.nudges._now_utc", return_value=dt)


def _mock_governor_now(dt: datetime):
    return patch("src.governor._now_utc", return_value=dt)


def _mock_llm(response: str = "Great workout!"):
    return patch("src.nudges.call_llm", return_value=response)


def _insert_activity(user_id: str, source: str, name: str, duration: int, recorded_at: str):
    db.save_device_data(
        user_id,
        source=source,
        data_type="activity",
        data={"name": name, "duration_minutes": duration, "type": "running"},
        recorded_at=recorded_at,
    )


def _insert_sleep(user_id: str, recorded_at: str, bedtime: str = "23:00"):
    db.save_device_data(
        user_id,
        source="oura",
        data_type="sleep",
        data={"bedtime": bedtime, "duration_hours": 7.5, "score": 80},
        recorded_at=recorded_at,
    )


def _insert_weight(user_id: str, weight_kg: float, recorded_at: str):
    db.save_device_data(
        user_id,
        source="renpho",
        data_type="weight",
        data={"weight_kg": weight_kg},
        recorded_at=recorded_at,
    )


# ===== Post-workout nudge =====


def test_post_workout_fires_on_new_activity():
    """Post-workout nudge fires when a new activity appears within the last hour."""
    now = _utc(hour=10)
    activity_time = (now - timedelta(minutes=30)).isoformat()
    _insert_activity(USER_ID, "garmin", "Morning Run", 45, activity_time)

    with _mock_now(now), _mock_llm("Nice run! Remember to hydrate.") as mock:
        result = check_post_workout(USER_ID)

    assert result is not None
    assert result == "Nice run! Remember to hydrate."
    # Verify LLM was called with workout context
    prompt = mock.call_args[0][1]
    assert "Morning Run" in prompt
    assert "45 min" in prompt


def test_post_workout_does_not_fire_if_already_acknowledged():
    """Post-workout nudge does not fire if a nudge was already sent for this workout."""
    now = _utc(hour=10)
    activity_time = (now - timedelta(minutes=30)).isoformat()
    _insert_activity(USER_ID, "garmin", "Morning Run", 45, activity_time)

    # Insert an existing post-workout nudge message
    nudge_time = (now - timedelta(minutes=20)).isoformat()
    db.save_message(
        USER_ID, "outbound", "Great run!", trigger_type="nudge_post_workout"
    )
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE messages SET created_at = ? "
            "WHERE id = (SELECT id FROM messages "
            "WHERE user_id = ? AND trigger_type = 'nudge_post_workout' "
            "ORDER BY id DESC LIMIT 1)",
            (nudge_time, USER_ID),
        )

    with _mock_now(now), _mock_llm():
        result = check_post_workout(USER_ID)

    assert result is None


# ===== Bedtime nudge =====


def test_bedtime_nudge_at_correct_time():
    """Bedtime nudge fires when it's ~30 min before stated bedtime goal."""
    # User bedtime goal is 23:00 Israel time. Nudge should fire at ~22:30.
    # Israel is UTC+2 in winter, so 22:30 Israel = 20:30 UTC.
    import json
    db.upsert_user(USER_ID, goals={"bedtime": "23:00"})

    now = _utc(hour=20, minute=30)  # 22:30 Israel time

    with _mock_now(now), _mock_llm("Almost bedtime. Good time to wind down?"):
        result = check_bedtime(USER_ID)

    assert result is not None
    assert "wind down" in result


def test_bedtime_nudge_skips_if_too_early():
    """Bedtime nudge does not fire if it's too far from bedtime."""
    db.upsert_user(USER_ID, goals={"bedtime": "23:00"})

    # 18:00 Israel time (16:00 UTC) -- way too early for 23:00 bedtime
    now = _utc(hour=16, minute=0)

    with _mock_now(now), _mock_llm():
        result = check_bedtime(USER_ID)

    assert result is None


# ===== Drift — workout =====


def test_drift_workout_fires_after_4_days():
    """Drift workout nudge fires when no activity for 4+ days."""
    now = _utc(hour=10)
    # No activities in last 4 days

    with _mock_now(now), _mock_llm("Haven't seen you train recently. Everything okay?"):
        result = check_drift_workout(USER_ID)

    assert result is not None


def test_drift_workout_does_not_fire_if_recent_activity():
    """Drift workout nudge does not fire if there's a recent activity."""
    now = _utc(hour=10)
    # Activity 2 days ago — within the 4-day window
    activity_time = (now - timedelta(days=2)).isoformat()
    _insert_activity(USER_ID, "strava", "Cycling", 60, activity_time)

    with _mock_now(now), _mock_llm():
        result = check_drift_workout(USER_ID)

    assert result is None


# ===== Drift — sleep =====


def test_drift_sleep_fires_on_bedtime_shift():
    """Drift sleep nudge fires when avg bedtime shifts >30 min later."""
    now = _utc(hour=10)

    # Baseline: 7-12 days ago, bedtime at 23:00
    for i in range(5, 12):
        recorded = (now - timedelta(days=i)).isoformat()
        _insert_sleep(USER_ID, recorded, bedtime="23:00")

    # Recent: last 5 days, bedtime at 00:00 (1 hour later)
    for i in range(0, 5):
        recorded = (now - timedelta(days=i)).isoformat()
        _insert_sleep(USER_ID, recorded, bedtime="00:00")

    with _mock_now(now), _mock_llm("Noticed your bedtime has been shifting a bit later."):
        result = check_drift_sleep(USER_ID)

    assert result is not None


# ===== Drift — weight =====


def test_drift_weight_fires_on_upward_trend():
    """Drift weight nudge fires when weight is up >1kg over 2 weeks."""
    now = _utc(hour=10)

    # 2 weeks ago: 80.0 kg
    old_time = (now - timedelta(weeks=2) + timedelta(hours=1)).isoformat()
    _insert_weight(USER_ID, 80.0, old_time)

    # Now: 81.5 kg (up 1.5 kg)
    recent_time = (now - timedelta(hours=1)).isoformat()
    _insert_weight(USER_ID, 81.5, recent_time)

    with _mock_now(now), _mock_llm("Weight has been trending up a bit."):
        result = check_drift_weight(USER_ID)

    assert result is not None


# ===== Governor integration =====


def test_nudges_respect_governor():
    """Nudges are not sent when governor blocks."""
    now = _utc(hour=10)
    activity_time = (now - timedelta(minutes=30)).isoformat()
    _insert_activity(USER_ID, "garmin", "Run", 30, activity_time)

    with _mock_now(now), \
         _mock_governor_now(now), \
         patch("src.nudges.can_send", return_value=False), \
         _mock_llm():
        result = check_and_send_nudges(USER_ID)

    assert result == []


# ===== Max one drift nudge per day =====


def test_max_one_drift_nudge_per_day():
    """Only one drift nudge is sent per day, even if multiple conditions are met."""
    now = _utc(hour=10)

    # Set up conditions for both workout drift and weight drift
    # No activities (workout drift)
    # Weight up (weight drift)
    old_time = (now - timedelta(weeks=2) + timedelta(hours=1)).isoformat()
    _insert_weight(USER_ID, 80.0, old_time)
    recent_time = (now - timedelta(hours=1)).isoformat()
    _insert_weight(USER_ID, 81.5, recent_time)

    sent_messages: list[str] = []

    def mock_llm_side_effect(system, prompt, max_tokens=128):
        msg = f"Nudge message {len(sent_messages) + 1}"
        return msg

    with _mock_now(now), \
         _mock_governor_now(now), \
         patch("src.nudges.can_send", return_value=True), \
         patch("src.nudges.call_llm", side_effect=mock_llm_side_effect):
        result = check_and_send_nudges(USER_ID)

    # Count drift nudges in the result
    drift_types = {"nudge_drift_workout", "nudge_drift_sleep", "nudge_drift_weight"}
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT trigger_type FROM messages "
            "WHERE user_id = ? AND direction = 'outbound' "
            "AND trigger_type IN ('nudge_drift_workout', 'nudge_drift_sleep', 'nudge_drift_weight')",
            (USER_ID,),
        ).fetchall()

    drift_count = len(rows)
    assert drift_count == 1, f"Expected 1 drift nudge, got {drift_count}"
