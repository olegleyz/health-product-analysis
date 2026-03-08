"""Telegram bot interface.

Handles incoming messages, command routing, and outbound notifications
using python-telegram-bot async API.
"""

import asyncio
import logging
from typing import Callable

from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import settings
from src.db import save_message

logger = logging.getLogger(__name__)

# Default echo handler — brain.py replaces this via set_message_handler()
_on_message: Callable[[str, str], str] = lambda user_id, text: text

WELCOME_MESSAGE = (
    "Welcome to your Personal Health Concierge! "
    "I'll help you track workouts, nutrition, sleep, and recovery. "
    "Just send me a message to get started."
)


def set_message_handler(handler: Callable[[str, str], str]) -> None:
    """Replace the default echo handler with a custom one (e.g. brain.py)."""
    global _on_message
    _on_message = handler


async def _start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command — send welcome message to allowed users."""
    if update.effective_user is None or update.message is None:
        return

    user_id = str(update.effective_user.id)

    if user_id not in settings.user_telegram_ids:
        logger.warning("Rejected /start from non-allowed user: %s", user_id)
        return

    await update.message.reply_text(WELCOME_MESSAGE)
    save_message(user_id, "outbound", WELCOME_MESSAGE, trigger_type="start_command")
    logger.info("Sent welcome message to user %s", user_id)


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inbound text messages from allowed users."""
    if update.effective_user is None or update.message is None or update.message.text is None:
        return

    user_id = str(update.effective_user.id)
    text = update.message.text

    # Reject non-allowed users silently
    if user_id not in settings.user_telegram_ids:
        logger.warning("Ignored message from non-allowed user: %s", user_id)
        return

    # Save inbound message
    save_message(user_id, "inbound", text)
    logger.info("Received message from user %s: %s", user_id, text[:50])

    # Get response from handler
    response = _on_message(user_id, text)

    # Send response
    await update.message.reply_text(response)
    save_message(user_id, "outbound", response, trigger_type="reactive")
    logger.info("Sent response to user %s: %s", user_id, response[:50])


def start_bot() -> None:
    """Start the Telegram bot with long polling. Blocks until stopped."""
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in config")

    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", _start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))

    logger.info("Starting Telegram bot with long polling...")
    app.run_polling()


def main() -> None:
    """Wire up the brain and start the bot."""
    from src.brain import handle_message

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    set_message_handler(handle_message)
    start_bot()


async def send_message(user_id: str, text: str) -> None:
    """Send a proactive message to a user.

    Creates its own Bot instance so it can be called independently
    of the polling loop (e.g. from cron scripts).
    """
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in config")

    bot = Bot(token=settings.telegram_bot_token)
    async with bot:
        await bot.send_message(chat_id=int(user_id), text=text)

    save_message(user_id, "outbound", text, trigger_type="proactive")
    logger.info("Sent proactive message to user %s: %s", user_id, text[:50])


if __name__ == "__main__":
    main()
