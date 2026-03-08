"""Database setup script.

Creates the SQLite database and initializes the schema.
Run this once before first use.
"""

import sys
from pathlib import Path

# Add project root to path so we can import src modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import init_db
from config import settings


def main() -> None:
    init_db()
    print(f"Database initialized at {settings.db_path}")


if __name__ == "__main__":
    main()
