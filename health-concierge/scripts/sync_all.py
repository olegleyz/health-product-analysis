#!/usr/bin/env python
"""Run all data syncs in sequence. Continues even if one fails."""

import sys
import logging

sys.path.insert(0, ".")

from config import settings
from src.db import init_db
from src.sync.oura_sync import sync_oura
from src.sync.garmin_sync import sync_garmin
from src.sync.strava_sync import sync_strava
from src.sync.renpho_sync import sync_renpho

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("sync_all")


def sync_all():
    """Run all device syncs for every configured user.

    Iterates over user_telegram_ids from config and runs each sync function.
    If one sync raises an exception, it is caught and logged; the remaining
    syncs still run.

    Returns a dict mapping user_id -> {source_name: result_dict}.
    """
    init_db()
    results = {}

    for user_id in settings.user_telegram_ids:
        user_results = {}

        syncs = [
            ("oura", sync_oura),
            ("garmin", sync_garmin),
            ("strava", sync_strava),
            ("renpho", sync_renpho),
        ]

        for name, sync_fn in syncs:
            try:
                result = sync_fn(user_id)
                user_results[name] = result
                logger.info("Sync %s for user %s: %s", name, user_id, result)
            except Exception as e:
                user_results[name] = {"error": str(e)}
                logger.error("Sync %s failed for user %s: %s", name, user_id, e)

        results[user_id] = user_results

        # Summary line
        parts = []
        for name, result in user_results.items():
            if "error" in result:
                parts.append(f"{name}: ERROR")
            else:
                counts = " ".join(f"{k}={v}" for k, v in result.items())
                parts.append(f"{name}: {counts}")
        logger.info("User %s summary: %s", user_id, " | ".join(parts))

    return results


if __name__ == "__main__":
    sync_all()
