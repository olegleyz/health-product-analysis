"""Tests for proactive nutrition integration in check-ins and summaries."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src import db
from src.proactive import _build_evening_prompt, generate_evening_checkin
from src.summarizer import _build_day_context


@pytest.fixture(autouse=True)
def _init_db(test_settings, monkeypatch):
    """Initialize DB with test settings before each test."""
    monkeypatch.setattr("src.db.settings", test_settings)
    db.init_db(test_settings.db_path)


USER = "user-1"


def _save_nutrition_event(meal_name: str, calories: float, protein: float):
    db.save_nutrition_event(
        user_id=USER, meal_name=meal_name,
        components=[], calories=calories, protein_g=protein,
        carbs_g=30, fat_g=15, weight_g=200,
        confidence=0.8, model_version="test",
        assumptions=[], image_file_id="test",
        user_corrections=None,
    )


class TestEveningCheckinNutrition:
    def test_evening_checkin_includes_nutrition_context(self):
        """Evening check-in prompt includes nutrition when meals were logged."""
        _save_nutrition_event("breakfast", 400, 30)
        _save_nutrition_event("lunch", 600, 45)

        prompt = _build_evening_prompt(
            user_profile={"name": "Test"},
            activities=[],
            activities_summary="",
            recent_messages=[],
            nutrition_summary="Today: 2 meals | 1000 kcal | Protein: 75g",
        )

        assert "1000" in prompt or "nutrition" in prompt.lower()

    def test_evening_checkin_no_nutrition_when_no_meals(self):
        """Evening check-in prompt has no nutrition section when no meals logged."""
        prompt = _build_evening_prompt(
            user_profile={"name": "Test"},
            activities=[],
            activities_summary="",
            recent_messages=[],
            nutrition_summary=None,
        )

        assert "nutrition" not in prompt.lower() or "Today's nutrition" not in prompt


class TestDailySummaryNutrition:
    def test_daily_summary_includes_nutrition(self):
        """Daily summary context includes nutrition events."""
        nutrition_events = [
            {"meal_name": "chicken salad", "calories": 400, "protein_g": 45},
            {"meal_name": "pasta", "calories": 600, "protein_g": 25},
        ]

        context = _build_day_context(
            messages=[],
            device_data=[],
            nutrition_events=nutrition_events,
        )

        assert "chicken salad" in context
        assert "pasta" in context
        assert "400" in context
        assert "Nutrition" in context

    def test_daily_summary_no_nutrition_when_no_meals(self):
        """Daily summary context omits nutrition section when no meals logged."""
        context = _build_day_context(
            messages=[],
            device_data=[],
            nutrition_events=[],
        )

        assert "Nutrition" not in context
