#!/usr/bin/env python
"""Back up the SQLite database with timestamp. Keeps last 7 backups.

Usage:
    .venv/bin/python scripts/backup_db.py
"""

import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

from config import settings

logger = logging.getLogger("backup_db")

DEFAULT_BACKUP_DIR = "./backups"
MAX_BACKUPS = 7


def backup_database(
    db_path: str | None = None,
    backup_dir: str | None = None,
    max_backups: int = MAX_BACKUPS,
) -> Path | None:
    """Copy the database file to backup_dir with a timestamp suffix.

    Deletes the oldest backups if more than *max_backups* exist.
    Returns the path to the new backup, or None if the DB file is missing.
    """
    db_file = Path(db_path or settings.db_path)
    if not db_file.exists():
        logger.warning("Database file not found: %s", db_file)
        return None

    dest_dir = Path(backup_dir or DEFAULT_BACKUP_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"concierge_{ts}.db"
    dest_path = dest_dir / backup_name

    shutil.copy2(str(db_file), str(dest_path))
    logger.info("Backup created: %s", dest_path)

    # Rotate old backups
    existing = sorted(dest_dir.glob("concierge_*.db"))
    if len(existing) > max_backups:
        for old in existing[: len(existing) - max_backups]:
            old.unlink()
            logger.info("Deleted old backup: %s", old)

    return dest_path


if __name__ == "__main__":
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    result = backup_database()
    if result:
        print(f"Backup: {result}")
    else:
        print("No database to back up.")
        sys.exit(1)
