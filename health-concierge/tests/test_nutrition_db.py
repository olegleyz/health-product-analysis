"""Tests for nutrition database schema and access functions."""

import json
from datetime import datetime, timezone

import pytest

from src import db


@pytest.fixture(autouse=True)
def _init_db(test_settings):
    """Initialize DB with test settings before each test."""
    db.init_db(test_settings.db_path)


USER = "user-1"


class TestNutritionEventsTable:
    def test_nutrition_events_table_created(self, test_settings):
        """init_db creates the nutrition_events table."""
        import sqlite3

        conn = sqlite3.connect(test_settings.db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nutrition_events'"
        ).fetchall()
        conn.close()
        assert len(tables) == 1

    def test_save_nutrition_event_returns_id(self):
        event_id = db.save_nutrition_event(
            user_id=USER,
            meal_name="chicken salad",
            components=[{"name": "chicken", "weight_g": 150}],
            calories=350,
            protein_g=40,
            carbs_g=10,
            fat_g=15,
            weight_g=250,
            confidence=0.8,
            model_version="claude-sonnet-4-20250514",
            assumptions=["portion estimated from plate"],
            image_file_id="abc123",
            user_corrections=None,
        )
        assert isinstance(event_id, int)
        assert event_id > 0

    def test_save_nutrition_event_stores_all_fields(self):
        components = [
            {"name": "chicken breast", "weight_g": 150, "calories": 248},
            {"name": "mixed greens", "weight_g": 100, "calories": 20},
        ]
        assumptions = ["grilled, no oil", "dressing on side"]
        corrections = {"note": "less dressing"}

        event_id = db.save_nutrition_event(
            user_id=USER,
            meal_name="grilled chicken salad",
            components=components,
            calories=380,
            protein_g=52,
            carbs_g=15,
            fat_g=12,
            weight_g=320,
            confidence=0.75,
            model_version="claude-sonnet-4-20250514",
            assumptions=assumptions,
            image_file_id="file_xyz",
            user_corrections=corrections,
        )

        # Retrieve via date and verify all fields
        now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        events = db.get_nutrition_events(USER, now_date)
        assert len(events) == 1

        event = events[0]
        assert event["id"] == event_id
        assert event["user_id"] == USER
        assert event["meal_name"] == "grilled chicken salad"
        assert event["components"] == components
        assert event["calories"] == 380
        assert event["protein_g"] == 52
        assert event["carbs_g"] == 15
        assert event["fat_g"] == 12
        assert event["weight_g"] == 320
        assert event["confidence"] == 0.75
        assert event["model_version"] == "claude-sonnet-4-20250514"
        assert event["assumptions"] == assumptions
        assert event["image_file_id"] == "file_xyz"
        assert event["user_corrections"] == corrections
        assert event["created_at"] is not None

    def test_get_nutrition_events_filters_by_date(self):
        # Save event for "today"
        db.save_nutrition_event(
            user_id=USER, meal_name="breakfast",
            components=[], calories=300, protein_g=20,
            carbs_g=30, fat_g=10, weight_g=200,
            confidence=0.7, model_version="test",
            assumptions=[], image_file_id="f1",
            user_corrections=None,
        )

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        events_today = db.get_nutrition_events(USER, today)
        assert len(events_today) == 1

        # Different date should return empty
        events_other = db.get_nutrition_events(USER, "2020-01-01")
        assert len(events_other) == 0

    def test_get_nutrition_events_empty_date(self):
        events = db.get_nutrition_events(USER, "2026-04-12")
        assert events == []

    def test_get_nutrition_events_deserializes_json(self):
        components = [{"name": "rice", "weight_g": 200}]
        assumptions = ["white rice, steamed"]

        db.save_nutrition_event(
            user_id=USER, meal_name="rice bowl",
            components=components, calories=400, protein_g=8,
            carbs_g=90, fat_g=1, weight_g=200,
            confidence=0.9, model_version="test",
            assumptions=assumptions, image_file_id="f2",
            user_corrections=None,
        )

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        events = db.get_nutrition_events(USER, today)
        event = events[0]

        # JSON fields should be deserialized to Python objects, not strings
        assert isinstance(event["components"], list)
        assert isinstance(event["assumptions"], list)
        assert event["components"][0]["name"] == "rice"
        assert event["assumptions"][0] == "white rice, steamed"


class TestNutritionTargets:
    def test_nutrition_targets_defaults(self):
        """get_nutrition_targets returns defaults when no record exists."""
        targets = db.get_nutrition_targets(USER)
        assert targets["user_id"] == USER
        assert targets["calories"] == 2200
        assert targets["protein_g"] == 120
        assert targets["carbs_g"] == 250
        assert targets["fat_g"] == 75

    def test_upsert_nutrition_targets_creates(self):
        db.upsert_nutrition_targets(USER, calories=2500, protein_g=150)

        targets = db.get_nutrition_targets(USER)
        assert targets["calories"] == 2500
        assert targets["protein_g"] == 150
        # Unset fields get table defaults
        assert targets["carbs_g"] == 250
        assert targets["fat_g"] == 75

    def test_upsert_nutrition_targets_updates(self):
        db.upsert_nutrition_targets(USER, calories=2000)
        db.upsert_nutrition_targets(USER, calories=2500)

        targets = db.get_nutrition_targets(USER)
        assert targets["calories"] == 2500

    def test_nutrition_targets_preserves_unset_fields(self):
        """Updating one field should not reset others."""
        db.upsert_nutrition_targets(USER, calories=2500, protein_g=150, carbs_g=300, fat_g=80)
        db.upsert_nutrition_targets(USER, protein_g=160)

        targets = db.get_nutrition_targets(USER)
        assert targets["calories"] == 2500  # not reset
        assert targets["protein_g"] == 160  # updated
        assert targets["carbs_g"] == 300    # not reset
        assert targets["fat_g"] == 80       # not reset
