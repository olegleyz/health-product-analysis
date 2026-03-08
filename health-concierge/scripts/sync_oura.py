#!/usr/bin/env python
"""Sync Oura Ring data for all users."""

import logging
import sys

sys.path.insert(0, ".")

from config import settings
from src.db import init_db
from src.sync.oura_sync import sync_oura

logging.basicConfig(level=settings.log_level)

init_db()

for user_id in settings.user_telegram_ids:
    result = sync_oura(user_id)
    print(f"Oura sync for {user_id}: {result}")
