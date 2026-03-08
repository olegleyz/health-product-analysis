#!/usr/bin/env python
"""Sync Garmin Connect data for all users."""

import logging
import sys

sys.path.insert(0, ".")

from config import settings
from src.db import init_db
from src.sync.garmin_sync import sync_garmin

logging.basicConfig(level=settings.log_level)

init_db()

for user_id in settings.user_telegram_ids:
    result = sync_garmin(user_id)
    print(f"Garmin sync for {user_id}: {result}")
