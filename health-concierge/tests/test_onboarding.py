"""Tests for the onboarding conversation flow."""

from pathlib import Path
from unittest.mock import patch

from src.brain import handle_message
from src.db import get_user, init_db, upsert_user
from src.onboarding import (
    ONBOARDING_STEPS,
    get_onboarding_step,
    handle_onboarding_message,
)


def _init(tmp_db_path: Path) -> None:
    """Helper: initialise DB (no user record yet)."""
    init_db(str(tmp_db_path))


def _init_with_user(tmp_db_path: Path, **kwargs) -> None:
    """Helper: initialise DB and create a user with given fields."""
    init_db(str(tmp_db_path))
    upsert_user("u1", **kwargs)


# --- get_onboarding_step ---


def test_new_user_triggers_onboarding(tmp_db_path: Path) -> None:
    """New user with no record returns 'welcome' step."""
    _init(tmp_db_path)
    # User doesn't exist yet — should still get "welcome"
    step = get_onboarding_step("u1")
    assert step == "welcome"


def test_user_without_onboarding_complete_returns_step(tmp_db_path: Path) -> None:
    """User exists but onboarding_complete=0 returns current step."""
    _init_with_user(tmp_db_path, name="Alice", preferences={"onboarding_step": "goals", "collected": {}})
    step = get_onboarding_step("u1")
    assert step == "goals"


def test_completed_user_returns_none(tmp_db_path: Path) -> None:
    """User with onboarding_complete=1 returns None."""
    _init_with_user(tmp_db_path, name="Alice", onboarding_complete=1)
    step = get_onboarding_step("u1")
    assert step is None


# --- handle_onboarding_message: step progression ---


@patch("src.onboarding.call_llm", return_value="Great to meet you! What are your health goals?")
@patch("src.onboarding.call_llm_json", return_value={"name": "Alice"})
def test_onboarding_progresses_through_steps(mock_json, mock_llm, tmp_db_path: Path) -> None:
    """Walk through all steps and verify progression."""
    _init(tmp_db_path)
    upsert_user("u1", preferences={"onboarding_step": "welcome", "collected": {}})

    # Mock extraction returns for each step
    extraction_returns = [
        {"name": "Alice"},           # welcome
        {"goals": ["run more"]},     # goals
        {"routine": "3x/week gym"},  # routine
        {"checkin_times": "morning"},# checkin_times
        {"tone": "direct"},          # tone
        {"accountability": "high"},  # accountability
        {"struggles": "consistency"},# struggles
    ]

    for i, step in enumerate(ONBOARDING_STEPS):
        mock_json.return_value = extraction_returns[i]
        current = get_onboarding_step("u1")
        assert current == step, f"Expected step {step}, got {current}"
        handle_onboarding_message("u1", f"answer for {step}")

    # After all steps, onboarding should be complete
    assert get_onboarding_step("u1") is None
    user = get_user("u1")
    assert user["onboarding_complete"] == 1


# --- Data saving tests ---


@patch("src.onboarding.call_llm", return_value="What are your goals?")
@patch("src.onboarding.call_llm_json", return_value={"name": "Bob"})
def test_onboarding_saves_name(mock_json, mock_llm, tmp_db_path: Path) -> None:
    """After welcome step, name is saved in collected data."""
    _init(tmp_db_path)
    upsert_user("u1", preferences={"onboarding_step": "welcome", "collected": {}})
    handle_onboarding_message("u1", "Hi, I'm Bob")

    user = get_user("u1")
    prefs = user["preferences"]
    assert prefs["collected"]["name"] == "Bob"


@patch("src.onboarding.call_llm", return_value="Tell me about your routine.")
@patch("src.onboarding.call_llm_json", return_value={"goals": ["lose weight", "run 5k"]})
def test_onboarding_saves_goals(mock_json, mock_llm, tmp_db_path: Path) -> None:
    """After goals step, goals are saved in collected data."""
    _init(tmp_db_path)
    upsert_user("u1", preferences={"onboarding_step": "goals", "collected": {"name": "Alice"}})
    handle_onboarding_message("u1", "I want to lose weight and run a 5k")

    user = get_user("u1")
    prefs = user["preferences"]
    assert prefs["collected"]["goals"] == ["lose weight", "run 5k"]


@patch("src.onboarding.call_llm", return_value="What tone do you prefer?")
@patch("src.onboarding.call_llm_json", return_value={"checkin_times": "8am and 8pm"})
def test_onboarding_saves_preferences(mock_json, mock_llm, tmp_db_path: Path) -> None:
    """After checkin_times step, times are saved in collected data."""
    _init(tmp_db_path)
    upsert_user("u1", preferences={
        "onboarding_step": "checkin_times",
        "collected": {"name": "Alice", "goals": ["run"], "routine": "3x/week"},
    })
    handle_onboarding_message("u1", "Morning and evening, around 8am and 8pm")

    user = get_user("u1")
    prefs = user["preferences"]
    assert prefs["collected"]["checkin_times"] == "8am and 8pm"


@patch("src.onboarding.call_llm", return_value="How much accountability?")
@patch("src.onboarding.call_llm_json", return_value={"tone": "direct"})
def test_onboarding_saves_tone_preference(mock_json, mock_llm, tmp_db_path: Path) -> None:
    """After tone step, tone is saved in collected data."""
    _init(tmp_db_path)
    upsert_user("u1", preferences={
        "onboarding_step": "tone",
        "collected": {"name": "Alice", "goals": ["run"], "routine": "3x", "checkin_times": "morning"},
    })
    handle_onboarding_message("u1", "Direct and to the point please")

    user = get_user("u1")
    prefs = user["preferences"]
    assert prefs["collected"]["tone"] == "direct"


@patch("src.onboarding.call_llm", return_value="What do you struggle with?")
@patch("src.onboarding.call_llm_json", return_value={"accountability": "high"})
def test_onboarding_saves_accountability_level(mock_json, mock_llm, tmp_db_path: Path) -> None:
    """After accountability step, level is saved in collected data."""
    _init(tmp_db_path)
    upsert_user("u1", preferences={
        "onboarding_step": "accountability",
        "collected": {
            "name": "Alice", "goals": ["run"], "routine": "3x",
            "checkin_times": "morning", "tone": "direct",
        },
    })
    handle_onboarding_message("u1", "Yes, please nudge me if I go quiet")

    user = get_user("u1")
    prefs = user["preferences"]
    assert prefs["collected"]["accountability"] == "high"


@patch("src.onboarding.call_llm", return_value="All set! Let's get started.")
@patch("src.onboarding.call_llm_json", return_value={"struggles": "staying consistent"})
def test_onboarding_sets_complete_flag(mock_json, mock_llm, tmp_db_path: Path) -> None:
    """After the last step (struggles), onboarding_complete is set to 1."""
    _init(tmp_db_path)
    upsert_user("u1", preferences={
        "onboarding_step": "struggles",
        "collected": {
            "name": "Alice", "goals": ["run"], "routine": "3x",
            "checkin_times": "morning", "tone": "direct", "accountability": "high",
        },
    })
    response = handle_onboarding_message("u1", "Consistency is my biggest challenge")

    assert isinstance(response, str)
    user = get_user("u1")
    assert user["onboarding_complete"] == 1
    assert get_onboarding_step("u1") is None


# --- Integration with brain.py ---


@patch("src.brain.call_llm_json", return_value=None)
@patch("src.brain.call_llm", return_value="Normal brain response.")
def test_completed_user_goes_to_normal_brain(mock_llm, mock_json, tmp_db_path: Path) -> None:
    """User with onboarding_complete=1 — handle_message uses normal brain."""
    _init(tmp_db_path)
    upsert_user("u1", name="Alice", onboarding_complete=1)

    result = handle_message("u1", "Good morning")
    assert result == "Normal brain response."
    mock_llm.assert_called_once()


@patch("src.onboarding.call_llm", return_value="Welcome! What's your name?")
@patch("src.onboarding.call_llm_json", return_value={"name": "Alice"})
def test_new_user_routed_to_onboarding_via_brain(mock_json, mock_llm, tmp_db_path: Path) -> None:
    """New user (no record) — handle_message routes to onboarding."""
    _init(tmp_db_path)
    upsert_user("u1", preferences={"onboarding_step": "welcome", "collected": {}})

    result = handle_message("u1", "Hello")
    assert isinstance(result, str)
    # Should have advanced from welcome
    step = get_onboarding_step("u1")
    assert step == "goals"


# --- Edge cases ---


@patch("src.onboarding.call_llm", return_value="I hear you! So what are your health goals?")
@patch("src.onboarding.call_llm_json", return_value={"name": None})
def test_onboarding_handles_unexpected_input(mock_json, mock_llm, tmp_db_path: Path) -> None:
    """Off-topic or unclear message during onboarding still produces a response."""
    _init(tmp_db_path)
    upsert_user("u1", preferences={"onboarding_step": "welcome", "collected": {}})

    # User sends something random instead of their name
    result = handle_onboarding_message("u1", "What's the weather like?")
    assert isinstance(result, str)
    assert len(result) > 0
    # Step should still advance (extraction returned null name, but flow continues)
    step = get_onboarding_step("u1")
    assert step == "goals"
