"""Tests for the SQLite database layer."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.db import (
    init_db,
    get_connection,
    get_user,
    upsert_user,
    save_message,
    get_recent_messages,
    archive_old_messages,
    get_engagement_state,
    update_engagement_state,
    save_device_data,
    get_device_data,
    save_daily_summary,
    get_daily_summaries,
    upsert_meal,
    get_meals,
)


def test_init_db_creates_all_tables(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    table_names = sorted(r["name"] for r in rows)
    expected = sorted([
        "users", "messages", "daily_summaries",
        "engagement_state", "device_data", "meals",
    ])
    assert table_names == expected


def test_upsert_user_creates_new_user(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    upsert_user("u1", name="Alice", timezone="UTC")
    user = get_user("u1")
    assert user is not None
    assert user["name"] == "Alice"
    assert user["timezone"] == "UTC"
    assert user["onboarding_complete"] == 0
    assert user["created_at"] is not None


def test_upsert_user_updates_existing_user(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    upsert_user("u1", name="Alice")
    upsert_user("u1", name="Bob", goals={"weight": 80})
    user = get_user("u1")
    assert user is not None
    assert user["name"] == "Bob"
    assert user["goals"] == {"weight": 80}


def test_save_and_get_messages(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    save_message("u1", "inbound", "Hello!")
    save_message("u1", "outbound", "Hi there!", trigger_type="greeting")
    msgs = get_recent_messages("u1")
    assert len(msgs) == 2
    assert msgs[0]["content"] == "Hi there!"  # newest first
    assert msgs[1]["content"] == "Hello!"


def test_get_recent_messages_respects_limit(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    for i in range(10):
        save_message("u1", "inbound", f"msg {i}")
    msgs = get_recent_messages("u1", limit=3)
    assert len(msgs) == 3


def test_get_recent_messages_returns_newest_first(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    save_message("u1", "inbound", "first")
    save_message("u1", "inbound", "second")
    save_message("u1", "inbound", "third")
    msgs = get_recent_messages("u1")
    assert msgs[0]["content"] == "third"
    assert msgs[1]["content"] == "second"
    assert msgs[2]["content"] == "first"


def test_engagement_state_defaults(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    state = get_engagement_state("u1")
    assert state["user_id"] == "u1"
    assert state["mode"] == "active"
    assert state["unanswered_count"] == 0
    assert state["daily_outbound_count"] == 0


def test_update_engagement_state(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    update_engagement_state("u1", mode="quiet", unanswered_count=3)
    state = get_engagement_state("u1")
    assert state["mode"] == "quiet"
    assert state["unanswered_count"] == 3

    # Update again
    update_engagement_state("u1", unanswered_count=0)
    state = get_engagement_state("u1")
    assert state["unanswered_count"] == 0
    assert state["mode"] == "quiet"  # unchanged


def test_save_and_get_device_data(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    save_device_data("u1", "garmin", "heart_rate", {"bpm": 72}, "2025-01-01T10:00:00+00:00")
    data = get_device_data("u1")
    assert len(data) == 1
    assert data[0]["data"] == {"bpm": 72}
    assert data[0]["source"] == "garmin"


def test_get_device_data_filters_by_source(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    save_device_data("u1", "garmin", "heart_rate", {"bpm": 72}, "2025-01-01T10:00:00+00:00")
    save_device_data("u1", "oura", "sleep", {"score": 85}, "2025-01-01T10:00:00+00:00")
    garmin_data = get_device_data("u1", source="garmin")
    assert len(garmin_data) == 1
    assert garmin_data[0]["source"] == "garmin"


def test_get_device_data_filters_by_since_date(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    save_device_data("u1", "garmin", "hr", {"bpm": 60}, "2025-01-01T00:00:00+00:00")
    save_device_data("u1", "garmin", "hr", {"bpm": 70}, "2025-01-10T00:00:00+00:00")
    data = get_device_data("u1", since="2025-01-05T00:00:00+00:00")
    assert len(data) == 1
    assert data[0]["data"] == {"bpm": 70}


def test_save_and_get_daily_summaries(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    save_daily_summary("u1", "2025-01-01", "Good day", {"steps": 10000})
    save_daily_summary("u1", "2025-01-02", "Rest day", {"steps": 3000})
    summaries = get_daily_summaries("u1")
    assert len(summaries) == 2
    assert summaries[0]["date"] == "2025-01-02"  # newest first
    assert summaries[0]["structured"] == {"steps": 3000}


def test_upsert_meal_creates_new(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    upsert_meal("u1", "Shakshuka", description="Eggs in tomato", tags=["breakfast", "protein"])
    meals = get_meals("u1")
    assert len(meals) == 1
    assert meals[0]["name"] == "Shakshuka"
    assert meals[0]["times_mentioned"] == 1
    assert meals[0]["tags"] == ["breakfast", "protein"]


def test_upsert_meal_increments_times_mentioned(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    upsert_meal("u1", "Shakshuka")
    upsert_meal("u1", "Shakshuka")
    upsert_meal("u1", "Shakshuka")
    meals = get_meals("u1")
    assert len(meals) == 1
    assert meals[0]["times_mentioned"] == 3


def test_get_meals_returns_all_for_user(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    upsert_meal("u1", "Shakshuka")
    upsert_meal("u1", "Hummus")
    upsert_meal("u2", "Pasta")  # different user
    meals = get_meals("u1")
    assert len(meals) == 2
    names = {m["name"] for m in meals}
    assert names == {"Shakshuka", "Hummus"}


def test_json_fields_roundtrip(tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))

    # User goals/preferences
    goals = {"target_weight": 75, "weekly_runs": 3}
    prefs = {"units": "metric", "notifications": True}
    upsert_user("u1", goals=goals, preferences=prefs)
    user = get_user("u1")
    assert user["goals"] == goals
    assert user["preferences"] == prefs

    # Message extracted_data
    extracted = {"meal": "shakshuka", "calories": 350}
    save_message("u1", "inbound", "Had shakshuka", extracted_data=extracted)
    msgs = get_recent_messages("u1")
    assert msgs[0]["extracted_data"] == extracted

    # Device data
    data = {"deep_sleep_minutes": 90, "rem_minutes": 60}
    save_device_data("u1", "oura", "sleep", data, "2025-01-01T00:00:00+00:00")
    records = get_device_data("u1")
    assert records[0]["data"] == data

    # Daily summary structured
    structured = {"steps": 8000, "active_calories": 500}
    save_daily_summary("u1", "2025-01-01", "Active day", structured)
    summaries = get_daily_summaries("u1")
    assert summaries[0]["structured"] == structured

    # Meal tags
    tags = ["lunch", "vegetarian", "quick"]
    upsert_meal("u1", "Salad", tags=tags)
    meals = get_meals("u1")
    salad = [m for m in meals if m["name"] == "Salad"][0]
    assert salad["tags"] == tags


# --- Conversation compression (T-022) ---

def _insert_message_at(user_id: str, content: str, created_at: str) -> None:
    """Helper: insert a message with a specific created_at timestamp."""
    import json
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, direction, content, extracted_data, trigger_type, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, "inbound", content, None, None, created_at),
        )


def test_get_recent_messages_filters_by_date(tmp_db_path: Path) -> None:
    """Messages older than the days window should not be returned."""
    init_db(str(tmp_db_path))
    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=10)).isoformat()
    recent_ts = (now - timedelta(days=1)).isoformat()

    _insert_message_at("u1", "old message", old_ts)
    _insert_message_at("u1", "recent message", recent_ts)

    msgs = get_recent_messages("u1", days=7)
    assert len(msgs) == 1
    assert msgs[0]["content"] == "recent message"


def test_archive_old_messages_removes_old(tmp_db_path: Path) -> None:
    """archive_old_messages should delete messages older than the threshold."""
    init_db(str(tmp_db_path))
    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=45)).isoformat()
    _insert_message_at("u1", "ancient message", old_ts)

    deleted = archive_old_messages("u1", days=30)
    assert deleted == 1

    # Verify it's actually gone (use a wide window so date filter doesn't hide it)
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM messages WHERE user_id = ?", ("u1",)).fetchall()
    assert len(rows) == 0


def test_archive_old_messages_keeps_recent(tmp_db_path: Path) -> None:
    """archive_old_messages should not delete messages within the retention window."""
    init_db(str(tmp_db_path))
    now = datetime.now(timezone.utc)
    recent_ts = (now - timedelta(days=5)).isoformat()
    old_ts = (now - timedelta(days=45)).isoformat()

    _insert_message_at("u1", "recent message", recent_ts)
    _insert_message_at("u1", "old message", old_ts)

    deleted = archive_old_messages("u1", days=30)
    assert deleted == 1

    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM messages WHERE user_id = ?", ("u1",)).fetchall()
    assert len(rows) == 1
    assert dict(rows[0])["content"] == "recent message"
