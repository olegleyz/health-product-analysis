"""Tests for the nutrition correction loop (re-estimation with constraints)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import db
from src.bot import _handle_callback, _handle_message, _pending
from src.nutrition import re_estimate_meal


@pytest.fixture(autouse=True)
def _setup(test_settings, monkeypatch):
    """Initialize DB, patch settings, and clear pending before each test."""
    monkeypatch.setattr("src.bot.settings", test_settings)
    monkeypatch.setattr("src.db.settings", test_settings)
    db.init_db(test_settings.db_path)
    _pending.clear()
    yield
    _pending.clear()


USER_ID = "111111111"
_TEST_IMAGE = b"fake_image_data"


def _mock_estimation():
    return {
        "meal_name": "grilled chicken salad",
        "components": [
            {"name": "chicken breast", "weight_g": 150, "calories": 248,
             "protein_g": 46, "carbs_g": 0, "fat_g": 5},
        ],
        "totals": {
            "calories": 388, "protein_g": 48, "carbs_g": 3,
            "fat_g": 19, "weight_g": 265,
        },
        "confidence": 0.75,
        "assumptions": ["portion estimated from plate"],
    }


def _corrected_estimation():
    """Return a corrected estimation (smaller portion)."""
    return {
        "meal_name": "grilled chicken salad",
        "components": [
            {"name": "chicken breast", "weight_g": 75, "calories": 124,
             "protein_g": 23, "carbs_g": 0, "fat_g": 3},
        ],
        "totals": {
            "calories": 194, "protein_g": 24, "carbs_g": 2,
            "fat_g": 10, "weight_g": 133,
        },
        "confidence": 0.80,
        "assumptions": ["portion halved per user correction"],
    }


def _make_text_update(user_id: str = USER_ID, text: str = "smaller portion"):
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = int(user_id)
    update.message = AsyncMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def _make_callback_update(user_id: str = USER_ID, data: str = "nl_edit"):
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = int(user_id)
    update.callback_query = AsyncMock()
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.message = MagicMock()
    update.callback_query.message.reply_text = AsyncMock()
    return update


class TestReEstimateMeal:
    @patch("src.nutrition.call_llm_vision_json")
    def test_re_estimate_sends_original_and_corrections(self, mock_vision):
        """Re-estimation prompt includes the original estimation and corrections."""
        mock_vision.return_value = _corrected_estimation()
        original = _mock_estimation()

        re_estimate_meal(_TEST_IMAGE, "image/jpeg", original, "portion was smaller, about half")

        call_args = mock_vision.call_args
        system_prompt = call_args.args[0]
        assert "correction" in system_prompt.lower()
        assert "portion was smaller" in system_prompt or "chicken" in system_prompt

    @patch("src.nutrition.call_llm_vision_json")
    def test_re_estimate_includes_image(self, mock_vision):
        """Re-estimation sends the original image."""
        mock_vision.return_value = _corrected_estimation()

        re_estimate_meal(_TEST_IMAGE, "image/jpeg", _mock_estimation(), "less oil")

        call_args = mock_vision.call_args
        assert call_args.args[1] == _TEST_IMAGE
        assert call_args.args[2] == "image/jpeg"

    @patch("src.nutrition.call_llm_vision_json")
    def test_re_estimate_returns_structured_format(self, mock_vision):
        """Re-estimation returns the same structured format as estimate_meal."""
        mock_vision.return_value = _corrected_estimation()

        result = re_estimate_meal(_TEST_IMAGE, "image/jpeg", _mock_estimation(), "smaller portion")

        assert "meal_name" in result
        assert "components" in result
        assert "totals" in result
        assert "confidence" in result
        assert "assumptions" in result


class TestCorrectionFlow:
    @patch("src.nutrition.call_llm_vision_json")
    def test_correction_mode_routes_text_to_re_estimate(self, mock_vision):
        """When in correction mode, text messages trigger re-estimation."""
        mock_vision.return_value = _corrected_estimation()

        _pending[USER_ID] = {
            "estimation": _mock_estimation(),
            "image_file_id": "photo_abc",
            "image_data": _TEST_IMAGE,
            "media_type": "image/jpeg",
            "awaiting_correction": True,
        }

        update = _make_text_update(text="the portion was smaller")
        context = MagicMock()

        asyncio.run(_handle_message(update, context))

        mock_vision.assert_called_once()

    @patch("src.nutrition.call_llm_vision_json")
    def test_correction_clears_awaiting_flag(self, mock_vision):
        """After correction, awaiting_correction is set to False."""
        mock_vision.return_value = _corrected_estimation()

        _pending[USER_ID] = {
            "estimation": _mock_estimation(),
            "image_file_id": "photo_abc",
            "image_data": _TEST_IMAGE,
            "media_type": "image/jpeg",
            "awaiting_correction": True,
        }

        update = _make_text_update(text="less oil")
        context = MagicMock()

        asyncio.run(_handle_message(update, context))

        assert _pending[USER_ID].get("awaiting_correction") is False

    @patch("src.nutrition.call_llm_vision_json")
    def test_correction_shows_updated_estimation(self, mock_vision):
        """After correction, the updated estimation is sent with buttons."""
        mock_vision.return_value = _corrected_estimation()

        _pending[USER_ID] = {
            "estimation": _mock_estimation(),
            "image_file_id": "photo_abc",
            "image_data": _TEST_IMAGE,
            "media_type": "image/jpeg",
            "awaiting_correction": True,
        }

        update = _make_text_update(text="smaller portion")
        context = MagicMock()

        asyncio.run(_handle_message(update, context))

        # reply_text should have been called with updated estimation and keyboard
        call_args = update.message.reply_text.call_args
        assert call_args is not None
        reply_markup = call_args.kwargs.get("reply_markup")
        assert reply_markup is not None

    @patch("src.nutrition.call_llm_vision_json")
    def test_multiple_correction_rounds(self, mock_vision):
        """User can correct multiple times before confirming."""
        first_correction = _corrected_estimation()
        second_correction = _corrected_estimation()
        second_correction["totals"]["calories"] = 150
        mock_vision.side_effect = [first_correction, second_correction]

        _pending[USER_ID] = {
            "estimation": _mock_estimation(),
            "image_file_id": "photo_abc",
            "image_data": _TEST_IMAGE,
            "media_type": "image/jpeg",
            "awaiting_correction": True,
        }

        # First correction
        update1 = _make_text_update(text="smaller portion")
        asyncio.run(_handle_message(update1, MagicMock()))

        # Set correction mode again (simulating user pressing Edit)
        _pending[USER_ID]["awaiting_correction"] = True

        # Second correction
        update2 = _make_text_update(text="actually no dressing")
        asyncio.run(_handle_message(update2, MagicMock()))

        assert mock_vision.call_count == 2
        # Final estimation should reflect second correction
        assert _pending[USER_ID]["estimation"]["totals"]["calories"] == 150
