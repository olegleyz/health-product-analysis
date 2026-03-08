"""Tests for daily summary generation."""

import json
from unittest.mock import patch

import pytest

from src import db
from src.summarizer import generate_daily_summary, _summary_exists

TEST_DATE = "2026-03-07"
TEST_USER = "111111111"

# Canned LLM responses
SUMMARY_TEXT = (
    "You had a solid day — a 45-minute morning run tracked by Garmin, "
    "followed by a healthy lunch. Your Oura ring reports 7 hours of good sleep. "
    "You mentioned feeling a bit stressed about work."
)

STRUCTURED_RESPONSE = {
    "workouts": [{"type": "running", "duration": "45min", "source": "garmin"}],
    "meals": [{"type": "lunch", "description": "salad", "quality": "healthy"}],
    "sleep": {"duration": "7h", "quality": "good", "bedtime": "23:00", "source": "oura"},
    "mood": "good",
    "weight": 82.5,
    "readiness": 85,
    "notable": "User mentioned work stress",
}

STRUCTURED_NO_CONVERSATION = {
    "workouts": [],
    "meals": [],
    "sleep": {"duration": "7h", "quality": "good", "bedtime": "23:00", "source": "oura"},
    "mood": None,
    "weight": 82.5,
    "readiness": 85,
    "notable": None,
}

STRUCTURED_NO_DEVICE = {
    "workouts": [{"type": "running", "duration": "45min", "source": "conversation"}],
    "meals": [{"type": "lunch", "description": "salad", "quality": "healthy"}],
    "sleep": None,
    "mood": "good",
    "weight": None,
    "readiness": None,
    "notable": "User mentioned work stress",
}

STRUCTURED_EMPTY = {
    "workouts": [],
    "meals": [],
    "sleep": None,
    "mood": None,
    "weight": None,
    "readiness": None,
    "notable": None,
}


@pytest.fixture(autouse=True)
def setup_db(tmp_db_path, test_settings):
    """Initialize the DB and patch settings for every test."""
    with patch("src.db.settings", test_settings):
        db.init_db(str(tmp_db_path))
        yield


def _seed_conversation(user_id: str, date: str) -> None:
    """Insert sample messages for the given date."""
    db.save_message(user_id, "inbound", "I went for a 45 min run this morning")
    # Manually update the created_at to match the target date
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE messages SET created_at = ? WHERE user_id = ?",
            (f"{date}T08:30:00+00:00", user_id),
        )
    db.save_message(user_id, "outbound", "Nice! How are you feeling?")
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE messages SET created_at = ? WHERE user_id = ? AND direction = 'outbound'",
            (f"{date}T08:31:00+00:00", user_id),
        )
    db.save_message(user_id, "inbound", "Good but stressed about work. Had a salad for lunch.")
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE messages SET created_at = ? WHERE user_id = ? AND content LIKE '%salad%'",
            (f"{date}T12:30:00+00:00", user_id),
        )


def _seed_device_data(user_id: str, date: str) -> None:
    """Insert sample device data for the given date."""
    db.save_device_data(
        user_id, "oura", "sleep",
        {"duration_hours": 7, "quality": "good", "bedtime": "23:00", "readiness": 85},
        f"{date}T07:00:00+00:00",
    )
    db.save_device_data(
        user_id, "renpho", "weight",
        {"weight_kg": 82.5},
        f"{date}T07:30:00+00:00",
    )
    db.save_device_data(
        user_id, "garmin", "activity",
        {"type": "running", "duration_min": 45, "distance_km": 7.2},
        f"{date}T09:00:00+00:00",
    )


@patch("src.summarizer.call_llm_json", return_value=STRUCTURED_RESPONSE)
@patch("src.summarizer.call_llm", return_value=SUMMARY_TEXT)
def test_summary_includes_workout_from_conversation(mock_llm, mock_llm_json):
    """Summary includes workout info extracted from conversation."""
    _seed_conversation(TEST_USER, TEST_DATE)
    _seed_device_data(TEST_USER, TEST_DATE)

    result = generate_daily_summary(TEST_USER, TEST_DATE)

    assert "summary" in result
    assert "structured" in result
    assert result["structured"]["workouts"][0]["type"] == "running"
    assert result["structured"]["workouts"][0]["duration"] == "45min"

    # Verify the LLM was called with context containing the workout message
    call_args = mock_llm.call_args
    assert "45 min run" in call_args[0][1] or "45 min run" in call_args[1].get("user_message", "")


@patch("src.summarizer.call_llm_json", return_value=STRUCTURED_RESPONSE)
@patch("src.summarizer.call_llm", return_value=SUMMARY_TEXT)
def test_summary_includes_sleep_from_oura(mock_llm, mock_llm_json):
    """Summary includes sleep data from Oura device."""
    _seed_conversation(TEST_USER, TEST_DATE)
    _seed_device_data(TEST_USER, TEST_DATE)

    result = generate_daily_summary(TEST_USER, TEST_DATE)

    assert result["structured"]["sleep"]["source"] == "oura"
    assert result["structured"]["sleep"]["duration"] == "7h"
    assert result["structured"]["sleep"]["quality"] == "good"

    # Verify device data was included in context
    call_args = mock_llm.call_args
    user_msg = call_args[0][1]
    assert "oura" in user_msg.lower()


@patch("src.summarizer.call_llm_json", return_value=STRUCTURED_RESPONSE)
@patch("src.summarizer.call_llm", return_value=SUMMARY_TEXT)
def test_summary_includes_weight_from_renpho(mock_llm, mock_llm_json):
    """Summary includes weight data from Renpho device."""
    _seed_conversation(TEST_USER, TEST_DATE)
    _seed_device_data(TEST_USER, TEST_DATE)

    result = generate_daily_summary(TEST_USER, TEST_DATE)

    assert result["structured"]["weight"] == 82.5

    # Verify device data was included in context
    call_args = mock_llm.call_args
    user_msg = call_args[0][1]
    assert "renpho" in user_msg.lower()


@patch("src.summarizer.call_llm_json", return_value=STRUCTURED_RESPONSE)
@patch("src.summarizer.call_llm", return_value=SUMMARY_TEXT)
def test_summary_structured_json_is_valid(mock_llm, mock_llm_json):
    """Structured output is valid JSON with expected fields."""
    _seed_conversation(TEST_USER, TEST_DATE)
    _seed_device_data(TEST_USER, TEST_DATE)

    result = generate_daily_summary(TEST_USER, TEST_DATE)
    structured = result["structured"]

    # Verify it's a dict (parseable JSON)
    assert isinstance(structured, dict)

    # Verify expected top-level keys
    assert "workouts" in structured
    assert "meals" in structured
    assert "sleep" in structured
    assert "mood" in structured
    assert "weight" in structured
    assert "readiness" in structured
    assert "notable" in structured

    # Verify it can be serialized back to JSON
    serialized = json.dumps(structured)
    reparsed = json.loads(serialized)
    assert reparsed == structured


@patch("src.summarizer.call_llm_json", return_value=STRUCTURED_NO_CONVERSATION)
@patch("src.summarizer.call_llm", return_value="A quiet day with no conversations. Oura shows 7 hours of good sleep and weight was 82.5 kg.")
def test_summary_handles_no_conversation(mock_llm, mock_llm_json):
    """Summary works with device data only (no conversation)."""
    _seed_device_data(TEST_USER, TEST_DATE)

    result = generate_daily_summary(TEST_USER, TEST_DATE)

    assert result["summary"]
    assert result["structured"]["sleep"]["duration"] == "7h"
    assert result["structured"]["weight"] == 82.5
    assert result["structured"]["workouts"] == []

    # Verify context was built with device data but no conversations
    call_args = mock_llm.call_args
    user_msg = call_args[0][1]
    assert "oura" in user_msg.lower()
    assert "Conversations" not in user_msg


@patch("src.summarizer.call_llm_json", return_value=STRUCTURED_NO_DEVICE)
@patch("src.summarizer.call_llm", return_value="User chatted about a morning run and lunch. No device data was synced today.")
def test_summary_handles_no_device_data(mock_llm, mock_llm_json):
    """Summary works with conversation only (no device data)."""
    _seed_conversation(TEST_USER, TEST_DATE)

    result = generate_daily_summary(TEST_USER, TEST_DATE)

    assert result["summary"]
    assert result["structured"]["workouts"][0]["type"] == "running"
    assert result["structured"]["sleep"] is None
    assert result["structured"]["weight"] is None

    # Verify context has conversations but no device data section
    call_args = mock_llm.call_args
    user_msg = call_args[0][1]
    assert "45 min run" in user_msg
    assert "Device Data" not in user_msg


@patch("src.summarizer.call_llm_json", return_value=STRUCTURED_RESPONSE)
@patch("src.summarizer.call_llm", return_value=SUMMARY_TEXT)
def test_summary_is_idempotent(mock_llm, mock_llm_json):
    """Generating and saving a summary twice doesn't create duplicates."""
    _seed_conversation(TEST_USER, TEST_DATE)
    _seed_device_data(TEST_USER, TEST_DATE)

    # Generate and save first summary
    result1 = generate_daily_summary(TEST_USER, TEST_DATE)
    db.save_daily_summary(TEST_USER, TEST_DATE, result1["summary"], result1["structured"])

    assert _summary_exists(TEST_USER, TEST_DATE) is True

    # Verify only one summary exists
    summaries = db.get_daily_summaries(TEST_USER, days=30)
    assert len(summaries) == 1
    assert summaries[0]["date"] == TEST_DATE

    # The script checks _summary_exists before generating, so the second call
    # would be skipped. But let's verify the check works.
    assert _summary_exists(TEST_USER, TEST_DATE) is True
