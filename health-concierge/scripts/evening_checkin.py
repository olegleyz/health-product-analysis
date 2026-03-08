#!/usr/bin/env python
"""Send evening check-in to all users."""

import asyncio
import logging
import sys

sys.path.insert(0, ".")

from config import settings
from src.bot import send_message
from src.db import init_db, save_message
from src.governor import record_send
from src.proactive import generate_evening_checkin

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


async def main() -> None:
    init_db()
    for user_id in settings.user_telegram_ids:
        msg = generate_evening_checkin(user_id)
        if msg:
            await send_message(user_id, msg)
            save_message(user_id, "outbound", msg, trigger_type="evening_check_in")
            record_send(user_id)
            logger.info("Evening check-in sent to %s", user_id)
        else:
            logger.info("Evening check-in skipped for %s", user_id)


if __name__ == "__main__":
    asyncio.run(main())
