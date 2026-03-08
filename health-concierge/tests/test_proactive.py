"""Tests for proactive message generation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src import db
from src.proactive import generate_morning_checkin


USER_ID = "u1"


@pytest.fixture(autouse=True)
def setup_db(tmp_db_path, test_settings, monkeypatch):
    """Initialize a fresh DB and patch settings for every test."""
    monkeypatch.setattr("src.db.settings", test_settings)
    monkeypatch.setattr("config.settings", test_settings)
    db.init_db(str(tmp_db_path))
    db.upsert_user(USER_ID, name="Test User", timezone="Asia/Jerusalem")
    yield


def _utc(hour=10) -> datetime:
    return datetime(2026, 3, 7, hour, 0, tzinfo=timezone.utc)


def _mock_governor_allow():
    return patch("src.proactive.can_send", return_value=True)


def _mock_governor_block():
    return patch("src.proactive.can_send", return_value=False)


def _mock_llm(return_value="Good morning!"):
    return patch("src.proactive.call_llm", return_value=return_value)


def _insert_sleep_data(user_id: str, score: int = 85, duration: float = 7.5):
    """Insert oura sleep data for yesterday."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    db.save_device_data(
        user_id,
        source="oura",
        data_type="sleep",
        data={
            "score": score,
            "duration_hours": duration,
            "quality": "good" if score >= 75 else ("fair" if score >= 60 else "poor"),
            "deep_sleep_hours": 1.5,
            "rem_sleep_hours": 2.0,
        },
        recorded_at=f"{yesterday}T06:00:00+00:00",
    )


def _insert_readiness_data(user_id: str, score: int = 80):
    """Insert readiness data for yesterday."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    db.save_device_data(
        user_id,
        source="oura",
        data_type="readiness",
        data={"score": score},
        recorded_at=f"{yesterday}T06:00:00+00:00",
    )


def _insert_weight_data(user_id: str, weight_kg: float = 80.5):
    """Insert renpho weight data for yesterday."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    db.save_device_data(
        user_id,
        source="renpho",
        data_type="weight",
        data={"weight_kg": weight_kg},
        recorded_at=f"{yesterday}T07:00:00+00:00",
    )


class TestMorningCheckinIncludesSleepData:
    """test_morning_checkin_includes_sleep_data"""

    def test_prompt_mentions_sleep_when_data_exists(self):
        """When oura sleep data exists, the LLM prompt should reference it."""
        _insert_sleep_data(USER_ID, score=85, duration=7.5)

        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="Morning!") as mock_llm:
            result = generate_morning_checkin(USER_ID)

        assert result == "Morning!"
        # The prompt sent to LLM should contain sleep data
        prompt_arg = mock_llm.call_args[0][1]  # user_message (2nd positional arg)
        assert "Sleep" in prompt_arg or "sleep" in prompt_arg.lower()
        assert "7.5" in prompt_arg
        assert "85" in prompt_arg


class TestMorningCheckinAdjustsForPoorSleep:
    """test_morning_checkin_adjusts_for_poor_sleep"""

    def test_poor_sleep_triggers_empathetic_tone(self):
        """When sleep score < 60, prompt should instruct empathetic tone."""
        _insert_sleep_data(USER_ID, score=45, duration=4.5)

        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="Rough night.") as mock_llm:
            result = generate_morning_checkin(USER_ID)

        prompt_arg = mock_llm.call_args[0][1]
        assert "empathetic" in prompt_arg.lower() or "gentle" in prompt_arg.lower()
        assert "poorly" in prompt_arg.lower() or "rough" in prompt_arg.lower()

    def test_good_sleep_triggers_energized_tone(self):
        """When sleep score >= 75, prompt should instruct energized tone."""
        _insert_sleep_data(USER_ID, score=90, duration=8.0)

        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="Great morning!") as mock_llm:
            result = generate_morning_checkin(USER_ID)

        prompt_arg = mock_llm.call_args[0][1]
        assert "energized" in prompt_arg.lower() or "upbeat" in prompt_arg.lower()


class TestMorningCheckinWithoutDeviceData:
    """test_morning_checkin_works_without_device_data"""

    def test_generates_message_without_any_device_data(self):
        """No device data at all — should still generate and ask about sleep."""
        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="How'd you sleep?") as mock_llm:
            result = generate_morning_checkin(USER_ID)

        assert result == "How'd you sleep?"
        prompt_arg = mock_llm.call_args[0][1]
        # Should instruct LLM to ask about sleep since no data
        assert "ask" in prompt_arg.lower() and "sleep" in prompt_arg.lower()


class TestMorningCheckinSkipsQuietModeUser:
    """test_morning_checkin_skips_quiet_mode_user"""

    def test_returns_none_when_governor_blocks(self):
        """Governor returns False (e.g. quiet mode) -> returns None."""
        with _mock_governor_block():
            result = generate_morning_checkin(USER_ID)
        assert result is None


class TestMorningCheckinSkipsPausedModeUser:
    """test_morning_checkin_skips_paused_mode_user"""

    def test_returns_none_when_paused(self):
        """Governor returns False (paused mode) -> returns None."""
        with _mock_governor_block():
            result = generate_morning_checkin(USER_ID)
        assert result is None


class TestMorningCheckinWithMultipleDataSources:
    """Additional tests for device data formatting."""

    def test_includes_readiness_and_weight(self):
        """Readiness and weight data should appear in the prompt."""
        _insert_sleep_data(USER_ID, score=80)
        _insert_readiness_data(USER_ID, score=75)
        _insert_weight_data(USER_ID, weight_kg=81.2)

        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="Morning!") as mock_llm:
            generate_morning_checkin(USER_ID)

        prompt_arg = mock_llm.call_args[0][1]
        assert "Readiness" in prompt_arg
        assert "75" in prompt_arg
        assert "81.2" in prompt_arg

    def test_prompt_asks_about_training_plans(self):
        """The prompt should instruct LLM to ask about today's plans."""
        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="Morning!") as mock_llm:
            generate_morning_checkin(USER_ID)

        prompt_arg = mock_llm.call_args[0][1]
        assert "plan" in prompt_arg.lower() or "train" in prompt_arg.lower()

    def test_uses_persona_system_prompt(self):
        """The system prompt passed to LLM should be the persona SYSTEM_PROMPT."""
        from src.prompts.persona import SYSTEM_PROMPT

        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="Morning!") as mock_llm:
            generate_morning_checkin(USER_ID)

        system_arg = mock_llm.call_args[0][0]
        assert system_arg == SYSTEM_PROMPT

    def test_includes_daily_summaries_in_context(self):
        """Recent daily summaries should be included in the prompt."""
        db.save_daily_summary(
            USER_ID, "2026-03-06", "Ran 5k, slept okay", {"steps": 8000}
        )

        with _mock_governor_allow(), \
             patch("src.proactive.call_llm", return_value="Morning!") as mock_llm:
            generate_morning_checkin(USER_ID)

        prompt_arg = mock_llm.call_args[0][1]
        assert "Ran 5k" in prompt_arg
