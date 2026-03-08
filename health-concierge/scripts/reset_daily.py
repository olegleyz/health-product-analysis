#!/usr/bin/env python
"""Reset daily outbound message counts for all users.

Intended to run via cron at midnight. Calls governor.reset_daily_counts()
which zeroes out daily_outbound_count in the engagement_state table.
"""

import logging
import sys

sys.path.insert(0, ".")

from config import settings
from src.db import init_db
from src.governor import reset_daily_counts

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("reset_daily")


def main() -> None:
    init_db()
    reset_daily_counts()
    logger.info("Daily counter reset complete")


if __name__ == "__main__":
    main()
