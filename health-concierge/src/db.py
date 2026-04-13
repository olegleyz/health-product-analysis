"""SQLite database layer.

Schema creation and thin Python access functions (no ORM).
Wraps raw parameterized SQL queries.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from config import settings

logger = logging.getLogger(__name__)

# Module-level db path, set by init_db()
_db_path: str | None = None


def _now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def user_today(user_id: str) -> str:
    """Return today's date (YYYY-MM-DD) in the user's local timezone.

    Falls back to UTC if the user has no timezone set or doesn't exist.
    """
    user = get_user(user_id)
    tz_name = (user or {}).get("timezone") or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except (KeyError, Exception):
        tz = timezone.utc
    return datetime.now(tz).strftime("%Y-%m-%d")


def init_db(db_path: str | None = None) -> None:
    """Create all tables if they don't exist.

    Sets the module-level _db_path so subsequent calls can find the DB.
    """
    global _db_path
    _db_path = db_path or settings.db_path

    # Ensure parent directory exists
    Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(_db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT,
                timezone TEXT DEFAULT 'Asia/Jerusalem',
                goals JSON,
                preferences JSON,
                onboarding_complete INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                direction TEXT,
                content TEXT,
                extracted_data JSON,
                trigger_type TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                date TEXT,
                summary TEXT,
                structured JSON,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS engagement_state (
                user_id TEXT PRIMARY KEY,
                mode TEXT DEFAULT 'active',
                last_user_message TEXT,
                last_outbound_message TEXT,
                unanswered_count INTEGER DEFAULT 0,
                daily_outbound_count INTEGER DEFAULT 0,
                daily_outbound_reset_at TEXT
            );

            CREATE TABLE IF NOT EXISTS device_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                source TEXT,
                data_type TEXT,
                data JSON,
                recorded_at TEXT,
                synced_at TEXT
            );

            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                name TEXT,
                description TEXT,
                tags JSON,
                times_mentioned INTEGER DEFAULT 1,
                last_mentioned TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS nutrition_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                meal_name TEXT,
                components JSON,
                calories REAL,
                protein_g REAL,
                carbs_g REAL,
                fat_g REAL,
                weight_g REAL,
                confidence REAL,
                model_version TEXT,
                assumptions JSON,
                image_file_id TEXT,
                user_corrections JSON,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS nutrition_targets (
                user_id TEXT PRIMARY KEY,
                calories REAL DEFAULT 2200,
                protein_g REAL DEFAULT 120,
                carbs_g REAL DEFAULT 250,
                fat_g REAL DEFAULT 75,
                updated_at TEXT
            );
        """)
    logger.info("Database initialized at %s", _db_path)


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Return a sqlite3 connection with row_factory set to sqlite3.Row."""
    path = db_path or _db_path or settings.db_path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convert a sqlite3.Row to a plain dict, or return None."""
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows: list) -> list[dict]:
    """Convert a list of sqlite3.Row to a list of dicts."""
    return [dict(r) for r in rows]


# --- Users ---

def get_user(user_id: str) -> dict | None:
    """Fetch a user by ID. Returns None if not found."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    for field in ("goals", "preferences"):
        if d.get(field):
            d[field] = json.loads(d[field])
    return d


def upsert_user(user_id: str, **fields) -> None:
    """Create a new user or update an existing one."""
    now = _now()
    existing = get_user(user_id)

    # Serialize JSON fields
    for field in ("goals", "preferences"):
        if field in fields and fields[field] is not None:
            fields[field] = json.dumps(fields[field])

    if existing is None:
        fields.setdefault("created_at", now)
        fields["updated_at"] = now
        fields["id"] = user_id
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        with get_connection() as conn:
            conn.execute(
                f"INSERT INTO users ({cols}) VALUES ({placeholders})",
                tuple(fields.values()),
            )
    else:
        fields["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        with get_connection() as conn:
            conn.execute(
                f"UPDATE users SET {set_clause} WHERE id = ?",
                (*fields.values(), user_id),
            )


# --- Messages ---

def save_message(
    user_id: str,
    direction: str,
    content: str,
    extracted_data: dict | None = None,
    trigger_type: str | None = None,
) -> None:
    """Insert a message record."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, direction, content, extracted_data, trigger_type, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                user_id,
                direction,
                content,
                json.dumps(extracted_data) if extracted_data else None,
                trigger_type,
                _now(),
            ),
        )


def get_recent_messages(user_id: str, limit: int = 20, days: int = 7) -> list[dict]:
    """Return the most recent messages for a user, newest first.

    Only returns messages from the last ``days`` days (default 7).
    The ``limit`` cap is still applied on top of the date filter.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE user_id = ? AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, cutoff, limit),
        ).fetchall()
    result = _rows_to_dicts(rows)
    for msg in result:
        if msg.get("extracted_data"):
            msg["extracted_data"] = json.loads(msg["extracted_data"])
    return result


def archive_old_messages(user_id: str, days: int = 30) -> int:
    """Delete messages older than ``days`` days for a user.

    Daily summaries serve as the permanent record, so raw messages
    beyond the retention window can safely be removed.

    Returns the number of deleted rows.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM messages WHERE user_id = ? AND created_at < ?",
            (user_id, cutoff),
        )
        deleted = cursor.rowcount
    if deleted:
        logger.info("Archived %d messages older than %d days for user=%s", deleted, days, user_id)
    return deleted


# --- Engagement State ---

def get_engagement_state(user_id: str) -> dict:
    """Return engagement state for a user, with defaults if no record exists."""
    defaults = {
        "user_id": user_id,
        "mode": "active",
        "last_user_message": None,
        "last_outbound_message": None,
        "unanswered_count": 0,
        "daily_outbound_count": 0,
        "daily_outbound_reset_at": None,
    }
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM engagement_state WHERE user_id = ?", (user_id,)
        ).fetchone()
    if row is None:
        return defaults
    return dict(row)


def update_engagement_state(user_id: str, **fields) -> None:
    """Update engagement state for a user, creating the row if needed."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT user_id FROM engagement_state WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing is None:
            fields["user_id"] = user_id
            cols = ", ".join(fields.keys())
            placeholders = ", ".join("?" for _ in fields)
            conn.execute(
                f"INSERT INTO engagement_state ({cols}) VALUES ({placeholders})",
                tuple(fields.values()),
            )
        else:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE engagement_state SET {set_clause} WHERE user_id = ?",
                (*fields.values(), user_id),
            )


# --- Device Data ---

def save_device_data(
    user_id: str, source: str, data_type: str, data: dict, recorded_at: str
) -> None:
    """Insert a device data record."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO device_data (user_id, source, data_type, data, recorded_at, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, source, data_type, json.dumps(data), recorded_at, _now()),
        )


def get_device_data(
    user_id: str,
    source: str | None = None,
    data_type: str | None = None,
    since: str | None = None,
) -> list[dict]:
    """Return device data records, optionally filtered by source, data_type, or since date."""
    query = "SELECT * FROM device_data WHERE user_id = ?"
    params: list = [user_id]

    if source is not None:
        query += " AND source = ?"
        params.append(source)
    if data_type is not None:
        query += " AND data_type = ?"
        params.append(data_type)
    if since is not None:
        query += " AND recorded_at >= ?"
        params.append(since)

    query += " ORDER BY recorded_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    result = _rows_to_dicts(rows)
    for rec in result:
        if rec.get("data"):
            rec["data"] = json.loads(rec["data"])
    return result


# --- Daily Summaries ---

def save_daily_summary(
    user_id: str, date: str, summary: str, structured: dict
) -> None:
    """Insert a daily summary record."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO daily_summaries (user_id, date, summary, structured, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, date, summary, json.dumps(structured), _now()),
        )


def get_daily_summaries(user_id: str, days: int = 7) -> list[dict]:
    """Return the most recent daily summaries for a user."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_summaries WHERE user_id = ? ORDER BY date DESC LIMIT ?",
            (user_id, days),
        ).fetchall()
    result = _rows_to_dicts(rows)
    for rec in result:
        if rec.get("structured"):
            rec["structured"] = json.loads(rec["structured"])
    return result


# --- Meals ---

def upsert_meal(
    user_id: str,
    name: str,
    description: str | None = None,
    tags: list | None = None,
    notes: str | None = None,
) -> None:
    """Create a new meal or increment times_mentioned if it already exists (matched by user_id + name)."""
    now = _now()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id, times_mentioned FROM meals WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO meals (user_id, name, description, tags, times_mentioned, last_mentioned, notes) "
                "VALUES (?, ?, ?, ?, 1, ?, ?)",
                (
                    user_id,
                    name,
                    description,
                    json.dumps(tags) if tags else None,
                    now,
                    notes,
                ),
            )
        else:
            new_count = existing["times_mentioned"] + 1
            update_fields = {"times_mentioned": new_count, "last_mentioned": now}
            if description is not None:
                update_fields["description"] = description
            if tags is not None:
                update_fields["tags"] = json.dumps(tags)
            if notes is not None:
                update_fields["notes"] = notes
            set_clause = ", ".join(f"{k} = ?" for k in update_fields)
            conn.execute(
                f"UPDATE meals SET {set_clause} WHERE id = ?",
                (*update_fields.values(), existing["id"]),
            )


def get_meals(user_id: str) -> list[dict]:
    """Return all meals for a user."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM meals WHERE user_id = ? ORDER BY last_mentioned DESC",
            (user_id,),
        ).fetchall()
    result = _rows_to_dicts(rows)
    for rec in result:
        if rec.get("tags"):
            rec["tags"] = json.loads(rec["tags"])
    return result


# --- Nutrition Events ---

def save_nutrition_event(
    user_id: str,
    meal_name: str,
    components: list[dict],
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    weight_g: float,
    confidence: float,
    model_version: str,
    assumptions: list[str],
    image_file_id: str,
    user_corrections: dict | None = None,
) -> int:
    """Insert an immutable nutrition event. Returns the event ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO nutrition_events "
            "(user_id, meal_name, components, calories, protein_g, carbs_g, fat_g, "
            "weight_g, confidence, model_version, assumptions, image_file_id, "
            "user_corrections, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                meal_name,
                json.dumps(components),
                calories,
                protein_g,
                carbs_g,
                fat_g,
                weight_g,
                confidence,
                model_version,
                json.dumps(assumptions),
                image_file_id,
                json.dumps(user_corrections) if user_corrections else None,
                _now(),
            ),
        )
        return cursor.lastrowid


def get_nutrition_events(user_id: str, date: str) -> list[dict]:
    """Return all nutrition events for a user on a given calendar date (YYYY-MM-DD)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM nutrition_events "
            "WHERE user_id = ? AND created_at LIKE ? "
            "ORDER BY created_at ASC",
            (user_id, f"{date}%"),
        ).fetchall()
    result = _rows_to_dicts(rows)
    for rec in result:
        for field in ("components", "assumptions", "user_corrections"):
            if rec.get(field):
                rec[field] = json.loads(rec[field])
    return result


# --- Nutrition Targets ---

_NUTRITION_TARGET_DEFAULTS = {
    "calories": 2200,
    "protein_g": 120,
    "carbs_g": 250,
    "fat_g": 75,
}


def get_nutrition_targets(user_id: str) -> dict:
    """Return nutrition targets for a user, with defaults if no record exists."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM nutrition_targets WHERE user_id = ?", (user_id,)
        ).fetchone()
    if row is None:
        return {"user_id": user_id, **_NUTRITION_TARGET_DEFAULTS}
    return dict(row)


def upsert_nutrition_targets(user_id: str, **fields) -> None:
    """Create or update nutrition targets for a user."""
    now = _now()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT user_id FROM nutrition_targets WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing is None:
            # Insert with defaults for unspecified fields
            all_fields = {**_NUTRITION_TARGET_DEFAULTS, **fields}
            all_fields["user_id"] = user_id
            all_fields["updated_at"] = now
            cols = ", ".join(all_fields.keys())
            placeholders = ", ".join("?" for _ in all_fields)
            conn.execute(
                f"INSERT INTO nutrition_targets ({cols}) VALUES ({placeholders})",
                tuple(all_fields.values()),
            )
        else:
            fields["updated_at"] = now
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE nutrition_targets SET {set_clause} WHERE user_id = ?",
                (*fields.values(), user_id),
            )
