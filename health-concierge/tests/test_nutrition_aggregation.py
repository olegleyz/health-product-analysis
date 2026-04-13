"""Tests for daily nutrition aggregation and qualitative status."""

from datetime import datetime, timezone

import pytest

from src import db
from src.nutrition import (
    format_daily_summary,
    get_daily_nutrition,
    get_qualitative_status,
)


@pytest.fixture(autouse=True)
def _init_db(test_settings):
    """Initialize DB with test settings before each test."""
    db.init_db(test_settings.db_path)


USER = "user-1"


def _save_event(meal_name: str, calories: float, protein: float,
                carbs: float, fat: float, weight: float = 200):
    """Helper to save a nutrition event for today."""
    db.save_nutrition_event(
        user_id=USER, meal_name=meal_name,
        components=[], calories=calories, protein_g=protein,
        carbs_g=carbs, fat_g=fat, weight_g=weight,
        confidence=0.8, model_version="test",
        assumptions=[], image_file_id="test",
        user_corrections=None,
    )


class TestGetQualitativeStatus:
    def test_qualitative_status_low(self):
        assert get_qualitative_status(50, 120) == "low"

    def test_qualitative_status_adequate(self):
        assert get_qualitative_status(100, 120) == "adequate"

    def test_qualitative_status_high(self):
        assert get_qualitative_status(200, 120) == "high"

    def test_qualitative_status_boundary_low(self):
        """Exactly 70% of target is adequate, not low."""
        assert get_qualitative_status(84, 120) == "adequate"
        assert get_qualitative_status(83.9, 120) == "low"

    def test_qualitative_status_boundary_high(self):
        """Exactly 130% of target is adequate, not high."""
        assert get_qualitative_status(156, 120) == "adequate"
        assert get_qualitative_status(156.1, 120) == "high"


class TestGetDailyNutrition:
    def test_daily_nutrition_sums_multiple_meals(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        _save_event("breakfast", calories=400, protein=30, carbs=50, fat=15)
        _save_event("lunch", calories=600, protein=45, carbs=60, fat=25)
        _save_event("dinner", calories=700, protein=50, carbs=70, fat=30)

        result = get_daily_nutrition(USER, today)

        assert result["meals_count"] == 3
        assert result["totals"]["calories"] == 1700
        assert result["totals"]["protein_g"] == 125
        assert result["totals"]["carbs_g"] == 180
        assert result["totals"]["fat_g"] == 70

    def test_daily_nutrition_empty_day(self):
        result = get_daily_nutrition(USER, "2026-04-12")

        assert result["meals_count"] == 0
        assert result["totals"]["calories"] == 0
        assert result["totals"]["protein_g"] == 0

    def test_daily_nutrition_includes_targets(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        _save_event("snack", calories=200, protein=10, carbs=20, fat=8)

        result = get_daily_nutrition(USER, today)

        assert "targets" in result
        assert result["targets"]["calories"] == 2200  # default
        assert result["targets"]["protein_g"] == 120  # default

    def test_daily_nutrition_includes_qualitative_status(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Low protein (40 vs 120 target = 33%)
        _save_event("light lunch", calories=1500, protein=40, carbs=200, fat=60)

        result = get_daily_nutrition(USER, today)

        assert result["status"]["protein_g"] == "low"
        assert result["status"]["calories"] == "low"  # 1500/2200 = 68% < 70% threshold

    def test_daily_nutrition_with_custom_targets(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        db.upsert_nutrition_targets(USER, calories=1800, protein_g=100)

        _save_event("meal", calories=1800, protein=100, carbs=200, fat=60)

        result = get_daily_nutrition(USER, today)
        assert result["targets"]["calories"] == 1800
        assert result["status"]["calories"] == "adequate"
        assert result["status"]["protein_g"] == "adequate"


class TestFormatDailySummary:
    def test_format_daily_summary_includes_totals(self):
        daily = {
            "meals_count": 2,
            "totals": {"calories": 1200, "protein_g": 80, "carbs_g": 120, "fat_g": 45},
            "targets": {"calories": 2200, "protein_g": 120, "carbs_g": 250, "fat_g": 75},
            "status": {"calories": "low", "protein_g": "low", "carbs_g": "low", "fat_g": "adequate"},
        }
        msg = format_daily_summary(daily)

        assert "1200" in msg
        assert "80" in msg
        assert "2 meal" in msg

    def test_format_daily_summary_includes_status(self):
        daily = {
            "meals_count": 1,
            "totals": {"calories": 500, "protein_g": 10, "carbs_g": 50, "fat_g": 20},
            "targets": {"calories": 2200, "protein_g": 120, "carbs_g": 250, "fat_g": 75},
            "status": {"calories": "low", "protein_g": "low", "carbs_g": "low", "fat_g": "low"},
        }
        msg = format_daily_summary(daily)

        assert "low" in msg

    def test_format_daily_summary_empty_day(self):
        daily = {"meals_count": 0, "totals": {}, "targets": {}, "status": {}}
        msg = format_daily_summary(daily)

        assert "no meals" in msg.lower()
