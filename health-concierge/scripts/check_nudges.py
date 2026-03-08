#!/usr/bin/env python
"""Run all nudge checks for all users. Intended for cron (every 1-2 hours)."""

import asyncio
import logging
import sys

sys.path.insert(0, ".")

from config import settings
from src.bot import send_message
from src.db import init_db
from src.nudges import check_and_send_nudges

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


async def main() -> None:
    init_db()
    for user_id in settings.user_telegram_ids:
        sent = check_and_send_nudges(user_id)
        for msg in sent:
            await send_message(user_id, msg)
        if sent:
            logger.info("Sent %d nudge(s) to user %s", len(sent), user_id)
        else:
            logger.debug("No nudges triggered for user %s", user_id)


if __name__ == "__main__":
    asyncio.run(main())
