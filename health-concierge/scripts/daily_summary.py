#!/usr/bin/env python3
"""End-of-day summary generation script.

Runs for each configured user, generates a daily summary, and saves it to the DB.
If run after midnight, summarizes yesterday; otherwise summarizes today.
Skips if a summary already exists for that date (idempotent).
"""

import logging
import sys
from datetime import datetime, timezone

from config import settings
from src import db
from src.summarizer import generate_daily_summary, _summary_exists

logger = logging.getLogger(__name__)


def _target_date() -> str:
    """Return the date to summarize (YYYY-MM-DD).

    If run before 04:00 UTC, summarize yesterday. Otherwise today.
    """
    now = datetime.now(timezone.utc)
    if now.hour < 4:
        from datetime import timedelta
        target = now - timedelta(days=1)
    else:
        target = now
    return target.strftime("%Y-%m-%d")


def main() -> None:
    db.init_db()
    date = _target_date()
    user_ids = settings.user_telegram_ids

    if not user_ids:
        logger.warning("No user IDs configured, nothing to do")
        return

    for user_id in user_ids:
        if _summary_exists(user_id, date):
            logger.info("Summary already exists for user=%s date=%s, skipping", user_id, date)
            continue

        try:
            result = generate_daily_summary(user_id, date)
            db.save_daily_summary(user_id, date, result["summary"], result["structured"])
            logger.info("Saved daily summary for user=%s date=%s", user_id, date)
        except Exception:
            logger.exception("Failed to generate summary for user=%s date=%s", user_id, date)

        # Clean up old messages (daily summaries serve as permanent record)
        try:
            db.archive_old_messages(user_id, days=30)
        except Exception:
            logger.exception("Failed to archive old messages for user=%s", user_id)


if __name__ == "__main__":
    main()
