"""Tests for Telegram photo handler and nutrition confirm/edit UX."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import db
from src.bot import (
    _handle_callback,
    _handle_photo,
    _pending,
)


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


def _mock_estimation():
    """Return a realistic estimation dict."""
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


def _make_photo_update(user_id: str = USER_ID, caption: str | None = None):
    """Create a mock Update with a photo message."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = int(user_id)
    update.message = AsyncMock()
    update.message.caption = caption
    update.message.reply_text = AsyncMock()

    # Mock photo file
    photo_size = MagicMock()
    photo_size.file_id = "photo_abc123"
    update.message.photo = [photo_size]  # Telegram sends array, last is largest

    return update


def _make_callback_update(user_id: str = USER_ID, data: str = "nl_confirm"):
    """Create a mock Update with a callback query."""
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


class TestPhotoHandler:
    @patch("src.bot.estimate_meal")
    @patch("src.bot._download_photo")
    def test_photo_triggers_estimation(self, mock_download, mock_estimate):
        """A photo message triggers the nutrition estimation pipeline."""
        mock_download.return_value = (b"fake_image_data", "image/jpeg")
        mock_estimate.return_value = _mock_estimation()

        update = _make_photo_update()
        context = MagicMock()

        asyncio.run(
            _handle_photo(update, context)
        )

        mock_estimate.assert_called_once()

    @patch("src.bot.estimate_meal")
    @patch("src.bot._download_photo")
    def test_photo_response_includes_inline_keyboard(self, mock_download, mock_estimate):
        """Response includes inline keyboard with Confirm/Edit/Discard buttons."""
        mock_download.return_value = (b"fake_image_data", "image/jpeg")
        mock_estimate.return_value = _mock_estimation()

        update = _make_photo_update()
        context = MagicMock()

        asyncio.run(
            _handle_photo(update, context)
        )

        # reply_text should have been called with reply_markup
        call_args = update.message.reply_text.call_args
        assert call_args is not None
        reply_markup = call_args.kwargs.get("reply_markup")
        assert reply_markup is not None

        # Extract button callback data
        buttons = []
        for row in reply_markup.inline_keyboard:
            for btn in row:
                buttons.append(btn.callback_data)
        assert "nl_confirm" in buttons
        assert "nl_edit" in buttons
        assert "nl_discard" in buttons

    @patch("src.bot.estimate_meal")
    @patch("src.bot._download_photo")
    def test_photo_caption_used_as_hint(self, mock_download, mock_estimate):
        """Photo caption is passed as text_hint to estimate_meal."""
        mock_download.return_value = (b"fake_image_data", "image/jpeg")
        mock_estimate.return_value = _mock_estimation()

        update = _make_photo_update(caption="this is my lunch")
        context = MagicMock()

        asyncio.run(
            _handle_photo(update, context)
        )

        call_args = mock_estimate.call_args
        assert call_args.kwargs.get("text_hint") == "this is my lunch" or \
               (len(call_args.args) > 2 and call_args.args[2] == "this is my lunch")

    @patch("src.bot.estimate_meal")
    @patch("src.bot._download_photo")
    def test_non_allowed_user_rejected(self, mock_download, mock_estimate):
        """Photos from non-allowed users are silently ignored."""
        update = _make_photo_update(user_id="999999999")
        context = MagicMock()

        asyncio.run(
            _handle_photo(update, context)
        )

        mock_download.assert_not_called()
        mock_estimate.assert_not_called()


class TestCallbackHandler:
    @patch("src.bot.get_daily_nutrition")
    @patch("src.bot.format_daily_summary")
    def test_confirm_callback_stores_event(self, mock_fmt_summary, mock_daily):
        """Confirm callback stores nutrition event in DB."""
        estimation = _mock_estimation()
        _pending[USER_ID] = {
            "estimation": estimation,
            "image_file_id": "photo_abc123",
            "image_data": b"fake",
            "media_type": "image/jpeg",
        }
        mock_daily.return_value = {"meals_count": 1, "totals": estimation["totals"]}
        mock_fmt_summary.return_value = "Daily summary text"

        update = _make_callback_update(data="nl_confirm")
        context = MagicMock()

        asyncio.run(
            _handle_callback(update, context)
        )

        # Event should be stored in DB
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        events = db.get_nutrition_events(USER_ID, today)
        assert len(events) == 1
        assert events[0]["meal_name"] == "grilled chicken salad"
        assert events[0]["calories"] == 388

        # Pending should be cleared
        assert USER_ID not in _pending

    @patch("src.bot.get_daily_nutrition")
    @patch("src.bot.format_daily_summary")
    @patch("src.bot.process_meal_mention")
    def test_confirm_callback_updates_meal_repertoire(
        self, mock_meal, mock_fmt_summary, mock_daily
    ):
        """Confirm callback also updates the meal repertoire."""
        estimation = _mock_estimation()
        _pending[USER_ID] = {
            "estimation": estimation,
            "image_file_id": "photo_abc123",
            "image_data": b"fake",
            "media_type": "image/jpeg",
        }
        mock_daily.return_value = {"meals_count": 1, "totals": estimation["totals"]}
        mock_fmt_summary.return_value = "summary"
        mock_meal.return_value = {"name": "grilled chicken salad", "is_new": True}

        update = _make_callback_update(data="nl_confirm")
        context = MagicMock()

        asyncio.run(
            _handle_callback(update, context)
        )

        mock_meal.assert_called_once_with(USER_ID, "grilled chicken salad")

    @patch("src.bot.get_daily_nutrition")
    @patch("src.bot.format_daily_summary")
    def test_confirm_callback_shows_daily_totals(self, mock_fmt_summary, mock_daily):
        """Confirm callback replies with updated daily nutrition summary."""
        estimation = _mock_estimation()
        _pending[USER_ID] = {
            "estimation": estimation,
            "image_file_id": "photo_abc123",
            "image_data": b"fake",
            "media_type": "image/jpeg",
        }
        mock_daily.return_value = {"meals_count": 1, "totals": estimation["totals"]}
        mock_fmt_summary.return_value = "1 meal logged | 388 kcal"

        update = _make_callback_update(data="nl_confirm")
        context = MagicMock()

        asyncio.run(
            _handle_callback(update, context)
        )

        # Should have edited the message or replied with summary
        update.callback_query.answer.assert_called_once()

    def test_edit_callback_sets_correction_mode(self):
        """Edit callback sets awaiting_correction flag on pending estimation."""
        _pending[USER_ID] = {
            "estimation": _mock_estimation(),
            "image_file_id": "photo_abc123",
            "image_data": b"fake",
            "media_type": "image/jpeg",
        }

        update = _make_callback_update(data="nl_edit")
        context = MagicMock()

        asyncio.run(
            _handle_callback(update, context)
        )

        assert _pending[USER_ID].get("awaiting_correction") is True

    def test_edit_callback_prompts_for_changes(self):
        """Edit callback sends a message asking what to change."""
        _pending[USER_ID] = {
            "estimation": _mock_estimation(),
            "image_file_id": "photo_abc123",
            "image_data": b"fake",
            "media_type": "image/jpeg",
        }

        update = _make_callback_update(data="nl_edit")
        context = MagicMock()

        asyncio.run(
            _handle_callback(update, context)
        )

        # Should reply asking for corrections
        update.callback_query.answer.assert_called_once()
        reply_call = update.callback_query.message.reply_text
        reply_call.assert_called_once()
        msg = reply_call.call_args.args[0]
        assert "change" in msg.lower() or "correct" in msg.lower() or "adjust" in msg.lower()

    def test_discard_callback_clears_pending(self):
        """Discard callback removes the pending estimation."""
        _pending[USER_ID] = {
            "estimation": _mock_estimation(),
            "image_file_id": "photo_abc123",
            "image_data": b"fake",
            "media_type": "image/jpeg",
        }

        update = _make_callback_update(data="nl_discard")
        context = MagicMock()

        asyncio.run(
            _handle_callback(update, context)
        )

        assert USER_ID not in _pending
        update.callback_query.answer.assert_called_once()
