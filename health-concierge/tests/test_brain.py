"""Tests for the concierge brain — reactive path."""

from pathlib import Path
from unittest.mock import patch

from src.brain import extract_data, handle_message, _format_device_data_summary
from src.db import (
    init_db,
    get_engagement_state,
    get_recent_messages,
    save_device_data,
    save_daily_summary,
    upsert_user,
)


def _init(tmp_db_path: Path) -> None:
    """Helper: initialise DB and create a test user."""
    init_db(str(tmp_db_path))
    upsert_user("u1", name="Alice")


# --- handle_message ---


@patch("src.brain.call_llm_json", return_value=None)
@patch("src.brain.call_llm", return_value="Hello there!")
def test_handle_message_returns_string(mock_llm, mock_json, tmp_db_path: Path) -> None:
    _init(tmp_db_path)
    result = handle_message("u1", "hi")
    assert isinstance(result, str)
    assert result == "Hello there!"
    mock_llm.assert_called_once()


@patch("src.brain.call_llm_json", return_value=None)
@patch("src.brain.call_llm", return_value="Got it.")
def test_handle_message_updates_engagement_state(mock_llm, mock_json, tmp_db_path: Path) -> None:
    _init(tmp_db_path)
    handle_message("u1", "hello")
    state = get_engagement_state("u1")
    assert state["last_user_message"] is not None
    assert state["unanswered_count"] == 0


@patch("src.brain.call_llm_json", return_value={
    "workout_mentioned": True,
    "workout_type": "running",
    "workout_duration": "30min",
    "meal_mentioned": False,
    "meal_type": None,
    "meal_description": None,
    "sleep_mentioned": False,
    "sleep_time": None,
    "mood": None,
})
@patch("src.brain.call_llm", return_value="Nice run!")
def test_handle_message_saves_extracted_data(mock_llm, mock_json, tmp_db_path: Path) -> None:
    _init(tmp_db_path)
    handle_message("u1", "I went for a run today")
    messages = get_recent_messages("u1", limit=5)
    # Find the inbound message
    inbound = [m for m in messages if m["direction"] == "inbound"]
    assert len(inbound) >= 1
    assert inbound[0]["extracted_data"] is not None
    assert inbound[0]["extracted_data"]["workout_mentioned"] is True


# --- extract_data ---


@patch("src.brain.call_llm_json", return_value={
    "workout_mentioned": True,
    "workout_type": "running",
    "workout_duration": None,
    "meal_mentioned": False,
    "meal_type": None,
    "meal_description": None,
    "sleep_mentioned": False,
    "sleep_time": None,
    "mood": None,
})
def test_extract_data_workout_mentioned(mock_json) -> None:
    result = extract_data("I went for a run")
    assert result is not None
    assert result["workout_mentioned"] is True
    mock_json.assert_called_once()


@patch("src.brain.call_llm_json", return_value={
    "workout_mentioned": False,
    "workout_type": None,
    "workout_duration": None,
    "meal_mentioned": True,
    "meal_type": "lunch",
    "meal_description": "pasta",
    "sleep_mentioned": False,
    "sleep_time": None,
    "mood": None,
})
def test_extract_data_meal_mentioned(mock_json) -> None:
    result = extract_data("I had pasta for lunch")
    assert result is not None
    assert result["meal_mentioned"] is True
    mock_json.assert_called_once()


@patch("src.brain.call_llm_json", return_value={
    "workout_mentioned": False,
    "workout_type": None,
    "workout_duration": None,
    "meal_mentioned": False,
    "meal_type": None,
    "meal_description": None,
    "sleep_mentioned": True,
    "sleep_time": "8 hours",
    "mood": None,
})
def test_extract_data_sleep_mentioned(mock_json) -> None:
    result = extract_data("I slept 8 hours")
    assert result is not None
    assert result["sleep_mentioned"] is True
    mock_json.assert_called_once()


@patch("src.brain.call_llm_json")
def test_extract_data_returns_none_for_irrelevant_message(mock_json) -> None:
    result = extract_data("hello")
    assert result is None
    mock_json.assert_not_called()


# --- context assembly ---


@patch("src.brain.call_llm_json", return_value=None)
@patch("src.brain.call_llm", return_value="Looks like you had a good sleep.")
def test_context_includes_device_data_when_available(mock_llm, mock_json, tmp_db_path: Path) -> None:
    _init(tmp_db_path)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    save_device_data("u1", "Oura", "sleep", {"sleep_duration": "7h 20m", "efficiency": 88}, now)

    handle_message("u1", "how did I sleep?")

    # Verify the system prompt passed to call_llm includes device data
    system_prompt_arg = mock_llm.call_args[0][0]
    assert "Oura" in system_prompt_arg
    assert "7h 20m" in system_prompt_arg


@patch("src.brain.call_llm_json", return_value=None)
@patch("src.brain.call_llm", return_value="Morning!")
def test_context_works_without_device_data(mock_llm, mock_json, tmp_db_path: Path) -> None:
    _init(tmp_db_path)
    result = handle_message("u1", "good morning")
    assert result == "Morning!"
    mock_llm.assert_called_once()


@patch("src.brain.call_llm_json", return_value=None)
@patch("src.brain.call_llm", return_value="Solid week.")
def test_context_includes_daily_summaries(mock_llm, mock_json, tmp_db_path: Path) -> None:
    _init(tmp_db_path)
    save_daily_summary("u1", "2026-03-06", "Ran 5k, ate well, slept 7h.", {"steps": 8000})

    handle_message("u1", "how was my week?")

    system_prompt_arg = mock_llm.call_args[0][0]
    assert "2026-03-06" in system_prompt_arg
    assert "Ran 5k" in system_prompt_arg


# --- _format_device_data_summary ---


def test_format_device_data_summary_empty() -> None:
    assert _format_device_data_summary([]) == ""


def test_format_device_data_summary_with_data() -> None:
    data = [
        {
            "source": "Garmin",
            "data_type": "activity",
            "recorded_at": "2026-03-06T10:00:00",
            "data": {"activity_type": "Running", "duration": "45min", "distance": "5.2km"},
        },
        {
            "source": "Oura",
            "data_type": "sleep",
            "recorded_at": "2026-03-06T07:00:00",
            "data": {"sleep_duration": "7h 20m", "efficiency": 88, "readiness_score": 82},
        },
    ]
    summary = _format_device_data_summary(data)
    assert "Garmin" in summary
    assert "Running" in summary
    assert "45min" in summary
    assert "Oura" in summary
    assert "7h 20m" in summary
    assert "efficiency 88%" in summary
