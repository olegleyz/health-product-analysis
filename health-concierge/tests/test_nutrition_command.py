"""Tests for /today command and nutrition context integration."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src import db
from src.bot import _handle_today, _pending
from src.prompts.persona import format_context_block


@pytest.fixture(autouse=True)
def _setup(test_settings, monkeypatch):
    """Initialize DB, patch settings before each test."""
    monkeypatch.setattr("src.bot.settings", test_settings)
    monkeypatch.setattr("src.db.settings", test_settings)
    db.init_db(test_settings.db_path)
    _pending.clear()
    yield
    _pending.clear()


USER_ID = "111111111"


def _save_event(meal_name: str, calories: float, protein: float,
                carbs: float, fat: float):
    db.save_nutrition_event(
        user_id=USER_ID, meal_name=meal_name,
        components=[], calories=calories, protein_g=protein,
        carbs_g=carbs, fat_g=fat, weight_g=200,
        confidence=0.8, model_version="test",
        assumptions=[], image_file_id="test",
        user_corrections=None,
    )


def _make_command_update(user_id: str = USER_ID):
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = int(user_id)
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    return update


class TestTodayCommand:
    def test_today_command_returns_summary(self):
        _save_event("breakfast", 400, 30, 50, 15)
        _save_event("lunch", 600, 45, 60, 25)

        update = _make_command_update()
        context = MagicMock()

        asyncio.run(_handle_today(update, context))

        update.message.reply_text.assert_called_once()
        msg = update.message.reply_text.call_args.args[0]
        assert "2 meal" in msg
        assert "1000" in msg  # total calories

    def test_today_command_empty_day(self):
        update = _make_command_update()
        context = MagicMock()

        asyncio.run(_handle_today(update, context))

        msg = update.message.reply_text.call_args.args[0]
        assert "no meals" in msg.lower()

    def test_today_command_includes_qualitative_status(self):
        # Low protein: 30g vs 120g target = 25%
        _save_event("light snack", 300, 30, 40, 10)

        update = _make_command_update()
        context = MagicMock()

        asyncio.run(_handle_today(update, context))

        msg = update.message.reply_text.call_args.args[0]
        assert "low" in msg


class TestNutritionContextInBrain:
    def test_context_block_includes_nutrition_summary(self):
        """format_context_block includes nutrition summary when provided."""
        block = format_context_block(
            nutrition_summary="Calories: 1200/2200 (low) | Protein: 80/120g (adequate)"
        )
        assert "1200" in block
        assert "Protein" in block

    def test_context_block_omits_nutrition_when_empty(self):
        """No nutrition section when nutrition_summary is empty/None."""
        block_none = format_context_block(nutrition_summary=None)
        block_empty = format_context_block(nutrition_summary="")

        assert "nutrition" not in block_none.lower()
        assert "nutrition" not in block_empty.lower()

    @patch("src.brain.get_daily_nutrition")
    @patch("src.brain.format_daily_summary")
    @patch("src.brain.call_llm")
    def test_brain_includes_nutrition_context(self, mock_llm, mock_fmt, mock_daily):
        """Brain loads and includes nutrition summary in context."""
        mock_daily.return_value = {
            "meals_count": 2,
            "totals": {"calories": 1200, "protein_g": 80, "carbs_g": 120, "fat_g": 45},
            "targets": {"calories": 2200, "protein_g": 120, "carbs_g": 250, "fat_g": 75},
            "status": {"calories": "low", "protein_g": "low", "carbs_g": "low", "fat_g": "adequate"},
        }
        mock_fmt.return_value = "Today: 2 meals | 1200 kcal"
        mock_llm.return_value = "Looks like a light day so far."

        # Need to set up user in DB for brain to load
        db.upsert_user(USER_ID, name="Test User", onboarding_complete=1)

        from src.brain import handle_message
        handle_message(USER_ID, "how's my nutrition today?")

        # Verify the LLM was called and nutrition context was in the prompt
        mock_llm.assert_called_once()
        system_prompt = mock_llm.call_args.args[0]
        assert "1200" in system_prompt or "nutrition" in system_prompt.lower()
