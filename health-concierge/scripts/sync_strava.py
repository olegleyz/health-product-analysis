#!/usr/bin/env python
"""Sync Strava data for all users."""

import logging
import sys

sys.path.insert(0, ".")

from config import settings
from src.db import init_db
from src.sync.strava_sync import sync_strava

logging.basicConfig(level=settings.log_level)

init_db()

for user_id in settings.user_telegram_ids:
    result = sync_strava(user_id)
    print(f"Strava sync for {user_id}: {result}")
