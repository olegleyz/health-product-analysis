"""Tests for meal extraction, memory, and suggestion."""

from unittest.mock import patch

import pytest

from src import db
from src.meals import get_meal_repertoire, process_meal_mention, suggest_meals


@pytest.fixture(autouse=True)
def _init_db(test_settings):
    """Initialize DB with test settings before each test."""
    db.init_db(test_settings.db_path)


USER = "user-1"


def _mock_llm_json(name: str, tags: list[str]):
    """Return a mock for call_llm_json that returns a canned response."""
    return lambda *args, **kwargs: {"name": name, "tags": tags}


class TestProcessMealMention:
    @patch("src.meals.call_llm_json")
    def test_new_meal_creates_record(self, mock_llm):
        mock_llm.return_value = {
            "name": "chicken pasta",
            "tags": ["dinner", "high-protein"],
        }

        result = process_meal_mention(USER, "I had chicken pasta for dinner")

        assert result["is_new"] is True
        assert result["name"] == "chicken pasta"
        assert result["times_mentioned"] == 1
        assert "dinner" in result["tags"]
        assert "high-protein" in result["tags"]

        # Verify in DB
        meals = db.get_meals(USER)
        assert len(meals) == 1
        assert meals[0]["name"] == "chicken pasta"

    @patch("src.meals.call_llm_json")
    def test_repeat_meal_increments_count(self, mock_llm):
        mock_llm.return_value = {
            "name": "chicken pasta",
            "tags": ["dinner", "high-protein"],
        }

        # First mention
        process_meal_mention(USER, "chicken pasta")
        # Second mention — exact same name
        result = process_meal_mention(USER, "chicken pasta again")

        assert result["is_new"] is False
        assert result["times_mentioned"] == 2
        assert result["name"] == "chicken pasta"

    @patch("src.meals.call_llm_json")
    def test_fuzzy_match_recognizes_same_meal(self, mock_llm):
        # First call: create the meal
        mock_llm.return_value = {
            "name": "chicken pasta",
            "tags": ["dinner"],
        }
        process_meal_mention(USER, "chicken pasta")

        # Second call: slightly different name that should fuzzy match
        mock_llm.return_value = {
            "name": "pasta with chicken",
            "tags": ["dinner", "high-protein"],
        }
        result = process_meal_mention(USER, "that pasta with chicken thing")

        # Should match existing meal, not create new one
        assert result["is_new"] is False
        assert result["name"] == "chicken pasta"
        assert result["times_mentioned"] == 2

        # Only one meal in DB
        meals = db.get_meals(USER)
        assert len(meals) == 1

    @patch("src.meals.call_llm_json")
    def test_auto_tagging(self, mock_llm):
        mock_llm.return_value = {
            "name": "protein shake",
            "tags": ["high-protein", "post-workout", "quick"],
        }

        result = process_meal_mention(USER, "had a protein shake after gym")

        assert "high-protein" in result["tags"]
        assert "post-workout" in result["tags"]
        assert "quick" in result["tags"]


class TestSuggestMeals:
    def _seed_meals(self):
        """Seed some meals for suggestion tests."""
        db.upsert_meal(USER, "protein shake", tags=["high-protein", "post-workout", "quick"])
        db.upsert_meal(USER, "chicken pasta", tags=["dinner", "high-protein"])
        db.upsert_meal(USER, "greek salad", tags=["light", "lunch", "vegetarian"])
        db.upsert_meal(USER, "oatmeal", tags=["breakfast", "quick"])
        # Bump chicken pasta frequency
        db.upsert_meal(USER, "chicken pasta", tags=["dinner", "high-protein"])
        db.upsert_meal(USER, "chicken pasta", tags=["dinner", "high-protein"])

    def test_suggest_meals_by_context(self):
        self._seed_meals()

        results = suggest_meals(USER, "high-protein")
        assert len(results) >= 1
        names = [m["name"] for m in results]
        assert "protein shake" in names or "chicken pasta" in names

    def test_suggest_meals_empty_repertoire(self):
        results = suggest_meals(USER, "dinner")
        assert results == []

    def test_meal_repertoire_sorted_by_frequency(self):
        self._seed_meals()

        repertoire = get_meal_repertoire(USER)
        assert len(repertoire) == 4
        # chicken pasta was mentioned 3 times, should be first
        assert repertoire[0]["name"] == "chicken pasta"
        assert repertoire[0]["times_mentioned"] == 3

        # Verify descending order
        for i in range(len(repertoire) - 1):
            assert repertoire[i]["times_mentioned"] >= repertoire[i + 1]["times_mentioned"]
