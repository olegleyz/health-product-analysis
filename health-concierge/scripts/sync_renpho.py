#!/usr/bin/env python
"""Sync Renpho body composition data for all users."""

import logging
import sys

sys.path.insert(0, ".")

from config import settings
from src.db import init_db
from src.sync.renpho_sync import sync_renpho

logging.basicConfig(level=settings.log_level)

init_db()

for user_id in settings.user_telegram_ids:
    result = sync_renpho(user_id)
    print(f"Renpho sync for {user_id}: {result}")
