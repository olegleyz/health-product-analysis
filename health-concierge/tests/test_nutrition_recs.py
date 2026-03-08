"""Tests for nutrition recommendations in conversation (T-024)."""

from unittest.mock import patch

import pytest

from src import db
from src.prompts.persona import SYSTEM_PROMPT, format_context_block


USER_ID = "u1"

SAMPLE_MEALS = [
    {"name": "chicken pasta", "tags": ["dinner", "high-protein"], "times_mentioned": 8},
    {"name": "greek salad", "tags": ["lunch", "light", "vegetarian"], "times_mentioned": 5},
    {"name": "oatmeal with banana", "tags": ["breakfast", "quick"], "times_mentioned": 12},
    {"name": "protein shake", "tags": ["snack", "pre-workout", "quick"], "times_mentioned": 7},
    {"name": "salmon with rice", "tags": ["dinner", "high-protein"], "times_mentioned": 4},
]


class TestContextIncludesMealRepertoire:
    """test_context_includes_meal_repertoire"""

    def test_context_includes_meal_repertoire(self) -> None:
        """Meal repertoire section appears in context when meals are provided."""
        result = format_context_block(
            user_profile={"name": "Alex"},
            meal_repertoire=SAMPLE_MEALS,
        )
        assert "Meal repertoire" in result
        assert "chicken pasta" in result
        assert "greek salad" in result
        assert "oatmeal with banana" in result
        assert "protein shake" in result
        assert "salmon with rice" in result

    def test_context_includes_tags_and_counts(self) -> None:
        """Meal entries show tags and mention counts."""
        result = format_context_block(
            meal_repertoire=SAMPLE_MEALS,
        )
        assert "high-protein" in result
        assert "x8" in result  # chicken pasta count
        assert "x12" in result  # oatmeal count

    def test_context_limits_to_15_meals(self) -> None:
        """Only top 15 meals are included even if more are provided."""
        many_meals = [
            {"name": f"meal_{i}", "tags": [], "times_mentioned": 20 - i}
            for i in range(20)
        ]
        result = format_context_block(meal_repertoire=many_meals)
        # First 15 should be present
        for i in range(15):
            assert f"meal_{i}" in result
        # 16th and beyond should not
        for i in range(15, 20):
            assert f"meal_{i}" not in result

    def test_tags_as_json_string(self) -> None:
        """Tags stored as JSON strings are parsed correctly."""
        meals = [
            {"name": "steak", "tags": '["dinner", "high-protein"]', "times_mentioned": 3},
        ]
        result = format_context_block(meal_repertoire=meals)
        assert "dinner" in result
        assert "high-protein" in result


class TestRecommendationUsesUserMeals:
    """test_recommendation_uses_user_meals"""

    def test_recommendation_uses_user_meals(self) -> None:
        """When LLM is called via proactive, the prompt contains user meals."""
        captured_prompts: list[str] = []

        def fake_call_llm(system: str, user_msg: str, **kwargs: object) -> str:
            captured_prompts.append(user_msg)
            return "How about some chicken pasta tonight?"

        with patch("src.proactive.can_send", return_value=True), \
             patch("src.proactive.call_llm", side_effect=fake_call_llm), \
             patch("src.proactive.db") as mock_db, \
             patch("src.proactive.get_meal_repertoire", return_value=SAMPLE_MEALS):

            mock_db.get_user.return_value = {"name": "Alex"}
            mock_db.get_device_data.return_value = []
            mock_db.get_daily_summaries.return_value = []

            from src.proactive import generate_morning_checkin
            result = generate_morning_checkin(USER_ID)

        assert result is not None
        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        assert "chicken pasta" in prompt
        assert "Meal repertoire" in prompt

    def test_evening_checkin_includes_meals(self) -> None:
        """Evening check-in prompt also includes meal repertoire."""
        captured_prompts: list[str] = []

        def fake_call_llm(system: str, user_msg: str, **kwargs: object) -> str:
            captured_prompts.append(user_msg)
            return "How was dinner?"

        with patch("src.proactive.can_send", return_value=True), \
             patch("src.proactive._morning_checkin_sent_today", return_value=False), \
             patch("src.proactive.call_llm", side_effect=fake_call_llm), \
             patch("src.proactive.db") as mock_db, \
             patch("src.proactive.get_meal_repertoire", return_value=SAMPLE_MEALS):

            mock_db.get_user.return_value = {"name": "Alex"}
            mock_db.get_device_data.return_value = []
            mock_db.get_recent_messages.return_value = []
            mock_db.get_daily_summaries.return_value = []

            from src.proactive import generate_evening_checkin, _get_todays_activities
            with patch("src.proactive._get_todays_activities", return_value=[]):
                result = generate_evening_checkin(USER_ID)

        assert result is not None
        assert len(captured_prompts) == 1
        assert "Meal repertoire" in captured_prompts[0]


class TestRecommendationWorksWithoutMeals:
    """test_recommendation_works_without_meals"""

    def test_recommendation_works_without_meals(self) -> None:
        """Empty meal repertoire does not break context or produce a section."""
        result = format_context_block(
            user_profile={"name": "Alex"},
            meal_repertoire=[],
        )
        assert "Meal repertoire" not in result
        # Should still have user profile
        assert "Alex" in result

    def test_recommendation_works_with_none_meals(self) -> None:
        """None meal repertoire (default) does not break context."""
        result = format_context_block(
            user_profile={"name": "Alex"},
            meal_repertoire=None,
        )
        assert "Meal repertoire" not in result
        assert "Alex" in result

    def test_proactive_works_with_empty_repertoire(self) -> None:
        """Morning check-in works when user has no meals."""
        captured_prompts: list[str] = []

        def fake_call_llm(system: str, user_msg: str, **kwargs: object) -> str:
            captured_prompts.append(user_msg)
            return "Morning! What's the plan today?"

        with patch("src.proactive.can_send", return_value=True), \
             patch("src.proactive.call_llm", side_effect=fake_call_llm), \
             patch("src.proactive.db") as mock_db, \
             patch("src.proactive.get_meal_repertoire", return_value=[]):

            mock_db.get_user.return_value = {"name": "Alex"}
            mock_db.get_device_data.return_value = []
            mock_db.get_daily_summaries.return_value = []

            from src.proactive import generate_morning_checkin
            result = generate_morning_checkin(USER_ID)

        assert result is not None
        assert "Meal repertoire" not in captured_prompts[0]


class TestPreWorkoutMealSuggestionTaggedCorrectly:
    """test_pre_workout_meal_suggestion_tagged_correctly"""

    def test_pre_workout_meal_suggestion_tagged_correctly(self) -> None:
        """Meals with pre-workout tag appear in context with correct tags."""
        pre_workout_meals = [
            {"name": "protein shake", "tags": ["pre-workout", "quick"], "times_mentioned": 7},
            {"name": "banana with peanut butter", "tags": ["pre-workout", "snack"], "times_mentioned": 4},
            {"name": "chicken pasta", "tags": ["dinner", "high-protein"], "times_mentioned": 8},
        ]
        result = format_context_block(meal_repertoire=pre_workout_meals)
        assert "pre-workout" in result
        assert "protein shake" in result
        assert "banana with peanut butter" in result

    def test_pre_workout_tag_in_context_for_morning_checkin(self) -> None:
        """Morning check-in includes pre-workout tagged meals when available."""
        pre_workout_meals = [
            {"name": "protein shake", "tags": ["pre-workout", "quick"], "times_mentioned": 7},
        ]
        captured_prompts: list[str] = []

        def fake_call_llm(system: str, user_msg: str, **kwargs: object) -> str:
            captured_prompts.append(user_msg)
            return "Morning! Maybe a protein shake before training?"

        with patch("src.proactive.can_send", return_value=True), \
             patch("src.proactive.call_llm", side_effect=fake_call_llm), \
             patch("src.proactive.db") as mock_db, \
             patch("src.proactive.get_meal_repertoire", return_value=pre_workout_meals):

            mock_db.get_user.return_value = {"name": "Alex"}
            mock_db.get_device_data.return_value = []
            mock_db.get_daily_summaries.return_value = []

            from src.proactive import generate_morning_checkin
            generate_morning_checkin(USER_ID)

        assert "pre-workout" in captured_prompts[0]
        assert "protein shake" in captured_prompts[0]


class TestSystemPromptNutritionGuidelines:
    """Verify SYSTEM_PROMPT includes nutrition recommendation instructions."""

    def test_system_prompt_has_nutrition_section(self) -> None:
        assert "Nutrition recommendations" in SYSTEM_PROMPT

    def test_system_prompt_prefers_user_repertoire(self) -> None:
        prompt_lower = SYSTEM_PROMPT.lower()
        assert "repertoire" in prompt_lower
        assert "recommend" in prompt_lower or "suggest" in prompt_lower
