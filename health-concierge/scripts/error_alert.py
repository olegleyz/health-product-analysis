#!/usr/bin/env python
"""Run a command and send a Telegram alert if it fails.

Usage:
    .venv/bin/python scripts/error_alert.py .venv/bin/python scripts/sync_all.py

Wraps any shell command. If the command exits non-zero, sends a Telegram
message to the first configured user with the error details.
"""

import asyncio
import logging
import subprocess
import sys

sys.path.insert(0, ".")

from config import settings
from src.bot import send_message

logger = logging.getLogger("error_alert")


def run_and_alert(args: list[str]) -> int:
    """Run *args* as a subprocess; alert via Telegram on failure.

    Returns the subprocess exit code.
    """
    cmd_str = " ".join(args)
    logger.info("Running: %s", cmd_str)

    result = subprocess.run(args, capture_output=True, text=True)

    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-500:]
        msg = (
            f"[Health Concierge Alert]\n"
            f"Command failed: {cmd_str}\n"
            f"Exit code: {result.returncode}\n"
            f"Stderr (last 500 chars):\n{stderr_tail}"
        )
        logger.error(msg)

        # Send alert to first configured user
        if settings.user_telegram_ids:
            admin_id = settings.user_telegram_ids[0]
            try:
                asyncio.run(send_message(admin_id, msg))
                logger.info("Alert sent to %s", admin_id)
            except Exception as e:
                logger.error("Failed to send Telegram alert: %s", e)
        else:
            logger.warning("No user_telegram_ids configured; cannot send alert")
    else:
        logger.info("Command succeeded: %s", cmd_str)

    return result.returncode


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/error_alert.py <command> [args...]")
        sys.exit(1)
    exit_code = run_and_alert(sys.argv[1:])
    sys.exit(exit_code)
