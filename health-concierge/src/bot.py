"""Telegram bot interface.

Handles incoming messages, command routing, and outbound notifications
using python-telegram-bot async API. Includes photo-based nutrition
estimation with inline keyboard confirm/edit/discard flow.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import settings
from src.db import save_message, save_nutrition_event
from src.meals import process_meal_mention
from src.nutrition import (
    estimate_meal,
    format_daily_summary,
    format_estimation_message,
    get_daily_nutrition,
)

logger = logging.getLogger(__name__)

# Default echo handler — brain.py replaces this via set_message_handler()
_on_message: Callable[[str, str], str] = lambda user_id, text: text

# In-memory pending estimations keyed by user_id
_pending: dict[str, dict] = {}

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

    # Check if user is in nutrition correction mode
    if user_id in _pending and _pending[user_id].get("awaiting_correction"):
        await _handle_correction(update, user_id, text)
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


async def _download_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[bytes, str]:
    """Download the largest photo from a message. Returns (bytes, media_type)."""
    photo = update.message.photo[-1]  # Last element is largest
    file = await context.bot.get_file(photo.file_id)
    data = await file.download_as_bytearray()
    return bytes(data), "image/jpeg"


async def _handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inbound photo messages — run nutrition estimation."""
    if update.effective_user is None or update.message is None or not update.message.photo:
        return

    user_id = str(update.effective_user.id)

    if user_id not in settings.user_telegram_ids:
        logger.warning("Ignored photo from non-allowed user: %s", user_id)
        return

    caption = update.message.caption or ""
    logger.info("Received photo from user %s (caption: %s)", user_id, caption[:50] if caption else "none")

    # Download photo
    image_data, media_type = await _download_photo(update, context)
    image_file_id = update.message.photo[-1].file_id

    # Run estimation
    estimation = estimate_meal(image_data, media_type, text_hint=caption)

    # Store pending estimation
    _pending[user_id] = {
        "estimation": estimation,
        "image_file_id": image_file_id,
        "image_data": image_data,
        "media_type": media_type,
    }

    # Format and send with inline keyboard
    msg = format_estimation_message(estimation)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✓ Confirm", callback_data="nl_confirm"),
            InlineKeyboardButton("✏️ Edit", callback_data="nl_edit"),
            InlineKeyboardButton("✗ Discard", callback_data="nl_discard"),
        ]
    ])

    await update.message.reply_text(msg, reply_markup=keyboard)
    save_message(user_id, "outbound", msg, trigger_type="nutrition_estimate")


async def _handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries from inline keyboard buttons."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return

    user_id = str(update.effective_user.id)
    data = query.data

    if data == "nl_confirm":
        await _confirm_estimation(query, user_id)
    elif data == "nl_edit":
        await _edit_estimation(query, user_id)
    elif data == "nl_discard":
        await _discard_estimation(query, user_id)


async def _confirm_estimation(query, user_id: str) -> None:
    """Store the confirmed nutrition event and update meal repertoire."""
    pending = _pending.get(user_id)
    if not pending:
        await query.answer("No pending estimation found.")
        return

    estimation = pending["estimation"]
    totals = estimation.get("totals", {})

    # Store nutrition event
    save_nutrition_event(
        user_id=user_id,
        meal_name=estimation.get("meal_name", ""),
        components=estimation.get("components", []),
        calories=totals.get("calories", 0),
        protein_g=totals.get("protein_g", 0),
        carbs_g=totals.get("carbs_g", 0),
        fat_g=totals.get("fat_g", 0),
        weight_g=totals.get("weight_g", 0),
        confidence=estimation.get("confidence", 0),
        model_version=settings.claude_model,
        assumptions=estimation.get("assumptions", []),
        image_file_id=pending.get("image_file_id", ""),
        user_corrections=estimation.get("user_corrections"),
    )

    # Update meal repertoire
    meal_name = estimation.get("meal_name", "")
    if meal_name:
        try:
            process_meal_mention(user_id, meal_name)
        except Exception as exc:
            logger.warning("Failed to update meal repertoire: %s", exc)

    # Clear pending
    del _pending[user_id]

    # Get daily nutrition summary
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = get_daily_nutrition(user_id, today)
    summary = format_daily_summary(daily)

    await query.answer("Meal logged!")
    await query.edit_message_text(
        f"✓ {estimation.get('meal_name', 'Meal')} logged.\n\n{summary}"
    )

    save_message(user_id, "outbound", f"Meal logged: {meal_name}", trigger_type="nutrition_confirm")
    logger.info("Confirmed nutrition event for user %s: %s", user_id, meal_name)


async def _edit_estimation(query, user_id: str) -> None:
    """Set correction mode and prompt user for changes."""
    pending = _pending.get(user_id)
    if not pending:
        await query.answer("No pending estimation found.")
        return

    pending["awaiting_correction"] = True
    await query.answer("Edit mode")
    await query.message.reply_text(
        "What would you like to adjust? "
        "(e.g., 'portion was smaller', 'no dressing', 'it was turkey not chicken')"
    )


async def _discard_estimation(query, user_id: str) -> None:
    """Discard the pending estimation."""
    _pending.pop(user_id, None)
    await query.answer("Discarded.")
    await query.edit_message_text("Estimation discarded.")
    logger.info("Discarded nutrition estimation for user %s", user_id)


async def _handle_correction(update: Update, user_id: str, text: str) -> None:
    """Handle a correction message when user is in edit mode."""
    from src.nutrition import re_estimate_meal

    pending = _pending.get(user_id)
    if not pending:
        return

    pending["awaiting_correction"] = False

    # Re-estimate with corrections
    estimation = re_estimate_meal(
        pending["image_data"],
        pending["media_type"],
        pending["estimation"],
        text,
    )

    # Update pending with new estimation
    pending["estimation"] = estimation

    # Format and send with inline keyboard
    msg = format_estimation_message(estimation)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✓ Confirm", callback_data="nl_confirm"),
            InlineKeyboardButton("✏️ Edit", callback_data="nl_edit"),
            InlineKeyboardButton("✗ Discard", callback_data="nl_discard"),
        ]
    ])

    await update.message.reply_text(msg, reply_markup=keyboard)
    save_message(user_id, "outbound", msg, trigger_type="nutrition_re_estimate")


async def _handle_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /today command — show daily nutrition summary."""
    if update.effective_user is None or update.message is None:
        return

    user_id = str(update.effective_user.id)

    if user_id not in settings.user_telegram_ids:
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = get_daily_nutrition(user_id, today)
    summary = format_daily_summary(daily)

    await update.message.reply_text(summary)
    save_message(user_id, "outbound", summary, trigger_type="today_command")


def start_bot() -> None:
    """Start the Telegram bot with long polling. Blocks until stopped."""
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in config")

    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", _start_command))
    app.add_handler(CommandHandler("today", _handle_today))
    app.add_handler(MessageHandler(filters.PHOTO, _handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))
    app.add_handler(CallbackQueryHandler(_handle_callback))

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
