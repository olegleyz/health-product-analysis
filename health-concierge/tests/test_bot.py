"""Tests for the Telegram bot module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import db
from src.bot import (
    WELCOME_MESSAGE,
    _handle_message,
    _start_command,
    send_message,
    set_message_handler,
)


@pytest.fixture(autouse=True)
def setup_db(test_settings, monkeypatch):
    """Initialize a temp DB and patch settings for every test."""
    monkeypatch.setattr("src.bot.settings", test_settings)
    monkeypatch.setattr("src.db.settings", test_settings)
    db.init_db(test_settings.db_path)
    # Reset the handler to default echo before each test
    set_message_handler(lambda user_id, text: text)
    yield


def _make_update(user_id: int, text: str) -> MagicMock:
    """Create a mock Update with a user and text message."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.message = AsyncMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def _make_context() -> MagicMock:
    """Create a mock context."""
    return MagicMock()


class TestAllowedUserReceivesEcho:
    def test_allowed_user_receives_echo(self):
        update = _make_update(111111111, "hello")
        context = _make_context()

        asyncio.run(_handle_message(update, context))

        update.message.reply_text.assert_awaited_once_with("hello")


class TestDisallowedUserIsIgnored:
    def test_disallowed_user_is_ignored(self):
        update = _make_update(999999999, "hello")
        context = _make_context()

        asyncio.run(_handle_message(update, context))

        update.message.reply_text.assert_not_awaited()


class TestInboundMessageSavedToDb:
    def test_inbound_message_saved_to_db(self):
        update = _make_update(111111111, "I ran 5k today")
        context = _make_context()

        asyncio.run(_handle_message(update, context))

        messages = db.get_recent_messages("111111111")
        inbound = [m for m in messages if m["direction"] == "inbound"]
        assert len(inbound) == 1
        assert inbound[0]["content"] == "I ran 5k today"


class TestOutboundMessageSavedToDb:
    def test_outbound_message_saved_to_db(self):
        update = _make_update(111111111, "I ran 5k today")
        context = _make_context()

        asyncio.run(_handle_message(update, context))

        messages = db.get_recent_messages("111111111")
        outbound = [m for m in messages if m["direction"] == "outbound"]
        assert len(outbound) == 1
        assert outbound[0]["content"] == "I ran 5k today"  # echo
        assert outbound[0]["trigger_type"] == "reactive"


class TestSendMessageIndependentOfHandler:
    @patch("src.bot.Bot")
    def test_send_message_independent_of_handler(self, mock_bot_class):
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot

        asyncio.run(send_message("111111111", "Time for a morning check-in!"))

        mock_bot.send_message.assert_awaited_once_with(
            chat_id=111111111, text="Time for a morning check-in!"
        )

        # Verify saved to DB
        messages = db.get_recent_messages("111111111")
        outbound = [m for m in messages if m["direction"] == "outbound"]
        assert len(outbound) == 1
        assert outbound[0]["content"] == "Time for a morning check-in!"
        assert outbound[0]["trigger_type"] == "proactive"


class TestStartCommandSendsWelcome:
    def test_start_command_sends_welcome(self):
        update = _make_update(111111111, "/start")
        context = _make_context()

        asyncio.run(_start_command(update, context))

        update.message.reply_text.assert_awaited_once_with(WELCOME_MESSAGE)

        # Verify saved to DB
        messages = db.get_recent_messages("111111111")
        assert len(messages) == 1
        assert messages[0]["direction"] == "outbound"
        assert messages[0]["content"] == WELCOME_MESSAGE

    def test_start_command_rejected_for_non_allowed_user(self):
        update = _make_update(999999999, "/start")
        context = _make_context()

        asyncio.run(_start_command(update, context))

        update.message.reply_text.assert_not_awaited()
