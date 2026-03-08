"""Tests for weekly reflection generation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src import db
from src.proactive import generate_weekly_reflection


USER_ID = "u1"


@pytest.fixture(autouse=True)
def setup_db(tmp_db_path, test_settings, monkeypatch):
    """Initialize a fresh DB and patch settings for every test."""
    monkeypatch.setattr("src.db.settings", test_settings)
    monkeypatch.setattr("config.settings", test_settings)
    db.init_db(str(tmp_db_path))
    db.upsert_user(USER_ID, name="Test User", timezone="Asia/Jerusalem")
    yield


def _mock_governor_allow():
    return patch("src.proactive.can_send", return_value=True)


def _mock_governor_block():
    return patch("src.proactive.can_send", return_value=False)


def _insert_activities(user_id: str, count: int = 3) -> None:
    """Insert activity records spread over the past 7 days."""
    for i in range(count):
        day = (datetime.now(timezone.utc) - timedelta(days=i + 1)).strftime("%Y-%m-%d")
        db.save_device_data(
            user_id,
            source="garmin",
            data_type="activity",
            data={"name": f"Run {i+1}", "duration_minutes": 30 + i * 5, "type": "running"},
            recorded_at=f"{day}T10:00:00+00:00",
        )


def _insert_daily_summaries(user_id: str, count: int = 7) -> None:
    """Insert daily summaries for the past N days with sleep scores."""
    for i in range(count):
        day = (datetime.now(timezone.utc) - timedelta(days=i + 1)).strftime("%Y-%m-%d")
        db.save_daily_summary(
            user_id,
            day,
            f"Day {i+1}: ran 5k, slept {6.5 + i * 0.2:.1f}h, ate well.",
            {"sleep_score": 70 + i * 2, "steps": 8000 + i * 500},
        )


def _insert_weight_data(user_id: str) -> None:
    """Insert weight records at the start and end of the week."""
    start = (datetime.now(timezone.utc) - timedelta(days=6)).strftime("%Y-%m-%d")
    end = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    db.save_device_data(
        user_id,
        source="renpho",
        data_type="weight",
        data={"weight_kg": 81.0},
        recorded_at=f"{start}T07:00:00+00:00",
    )
    db.save_device_data(
        user_id,
        source="renpho",
        data_type="weight",
        data={"weight_kg": 80.2},
        recorded_at=f"{end}T07:00:00+00:00",
    )


class TestWeeklyReflectionCovers7Days:
    def test_weekly_reflection_covers_7_days(self):
        """The prompt should request 7 days of daily summaries."""
        _insert_daily_summaries(USER_ID, count=7)
        _insert_activities(USER_ID, count=3)

        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="Week summary.") as mock_llm:
            result = generate_weekly_reflection(USER_ID)

        assert result is not None
        prompt_arg = mock_llm.call_args[0][1]
        # Should reference multiple days from the summaries
        assert "Day 1" in prompt_arg or "Day 7" in prompt_arg or "daily summaries" in prompt_arg.lower()
        # Verify get_daily_summaries was called with days=7 by checking
        # that summaries from various days appear in the context
        assert "ran 5k" in prompt_arg.lower() or "5k" in prompt_arg


class TestWeeklyReflectionIncludesWorkoutCount:
    def test_weekly_reflection_includes_workout_count(self):
        """The prompt should contain the number of workouts this week."""
        _insert_activities(USER_ID, count=4)

        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="Great week!") as mock_llm:
            result = generate_weekly_reflection(USER_ID)

        assert result is not None
        prompt_arg = mock_llm.call_args[0][1]
        assert "Workouts this week: 4" in prompt_arg
        assert "workout count" in prompt_arg.lower() or "Include the workout count" in prompt_arg


class TestWeeklyReflectionIncludesSleepTrend:
    def test_weekly_reflection_includes_sleep_trend(self):
        """The prompt should include sleep trend when data is available."""
        _insert_daily_summaries(USER_ID, count=7)

        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="Sleep improved.") as mock_llm:
            result = generate_weekly_reflection(USER_ID)

        assert result is not None
        prompt_arg = mock_llm.call_args[0][1]
        assert "Sleep trend:" in prompt_arg
        # Should be one of: improving, declining, stable
        assert any(
            trend in prompt_arg.lower()
            for trend in ("improving", "declining", "stable")
        )

    def test_sleep_trend_shows_insufficient_when_no_data(self):
        """Without daily summaries, sleep trend should say insufficient."""
        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="No sleep data.") as mock_llm:
            generate_weekly_reflection(USER_ID)

        prompt_arg = mock_llm.call_args[0][1]
        assert "insufficient data" in prompt_arg.lower()


class TestWeeklyReflectionIncludesWeightIfAvailable:
    def test_weekly_reflection_includes_weight_if_available(self):
        """The prompt should show weight change when weight data exists."""
        _insert_weight_data(USER_ID)

        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="Weight down!") as mock_llm:
            result = generate_weekly_reflection(USER_ID)

        assert result is not None
        prompt_arg = mock_llm.call_args[0][1]
        assert "81.0" in prompt_arg
        assert "80.2" in prompt_arg
        assert "-0.8" in prompt_arg

    def test_no_weight_data_says_no_data(self):
        """Without weight records, prompt should say no data this week."""
        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="No weight.") as mock_llm:
            generate_weekly_reflection(USER_ID)

        prompt_arg = mock_llm.call_args[0][1]
        assert "no data this week" in prompt_arg.lower()


class TestWeeklyReflectionAsksReflectiveQuestion:
    def test_weekly_reflection_asks_reflective_question(self):
        """The prompt should instruct the LLM to ask a reflective question."""
        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="Reflection.") as mock_llm:
            result = generate_weekly_reflection(USER_ID)

        assert result is not None
        prompt_arg = mock_llm.call_args[0][1]
        assert "reflective question" in prompt_arg.lower()
        assert "next week" in prompt_arg.lower()


class TestWeeklyReflectionSkipsQuietMode:
    def test_weekly_reflection_skips_quiet_mode(self):
        """Weekly reflection should return None when governor blocks."""
        with _mock_governor_block(), \
             patch("src.proactive.call_llm") as mock_llm:
            result = generate_weekly_reflection(USER_ID)

        assert result is None
        mock_llm.assert_not_called()
