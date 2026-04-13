"""Tests for nutrition estimation pipeline."""

import base64
from unittest.mock import patch

import pytest

from src.nutrition import estimate_meal, format_estimation_message, ESTIMATION_PROMPT


# Tiny test image bytes
_TEST_IMAGE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50


def _mock_estimation():
    """Return a realistic estimation dict."""
    return {
        "meal_name": "grilled chicken salad",
        "components": [
            {"name": "chicken breast", "weight_g": 150, "calories": 248, "protein_g": 46, "carbs_g": 0, "fat_g": 5},
            {"name": "mixed greens", "weight_g": 100, "calories": 20, "protein_g": 2, "carbs_g": 3, "fat_g": 0},
            {"name": "olive oil dressing", "weight_g": 15, "calories": 120, "protein_g": 0, "carbs_g": 0, "fat_g": 14},
        ],
        "totals": {
            "calories": 388,
            "protein_g": 48,
            "carbs_g": 3,
            "fat_g": 19,
            "weight_g": 265,
        },
        "confidence": 0.75,
        "assumptions": [
            "portion size estimated from plate diameter",
            "dressing assumed olive oil based",
        ],
    }


class TestEstimateMeal:
    @patch("src.nutrition.call_llm_vision_json")
    def test_estimate_meal_calls_vision_api(self, mock_vision):
        """estimate_meal calls call_llm_vision_json with image data."""
        mock_vision.return_value = _mock_estimation()

        estimate_meal(_TEST_IMAGE, "image/jpeg")

        mock_vision.assert_called_once()
        call_args = mock_vision.call_args
        # First positional arg is system prompt, second is image data
        assert call_args.args[1] == _TEST_IMAGE
        assert call_args.args[2] == "image/jpeg"

    @patch("src.nutrition.call_llm_vision_json")
    def test_estimate_meal_returns_required_fields(self, mock_vision):
        """Estimation result includes all required fields."""
        mock_vision.return_value = _mock_estimation()

        result = estimate_meal(_TEST_IMAGE, "image/jpeg")

        assert "meal_name" in result
        assert "components" in result
        assert "totals" in result
        assert "confidence" in result
        assert "assumptions" in result

        totals = result["totals"]
        assert "calories" in totals
        assert "protein_g" in totals
        assert "carbs_g" in totals
        assert "fat_g" in totals
        assert "weight_g" in totals

    @patch("src.nutrition.call_llm_vision_json")
    def test_estimate_meal_passes_text_hint(self, mock_vision):
        """Text hint is forwarded to the vision API call."""
        mock_vision.return_value = _mock_estimation()

        estimate_meal(_TEST_IMAGE, "image/jpeg", text_hint="this is my lunch")

        call_args = mock_vision.call_args
        assert call_args.kwargs.get("text_hint") == "this is my lunch" or \
               (len(call_args.args) > 3 and "this is my lunch" in call_args.args[3])

    def test_estimate_meal_prompt_requests_json(self):
        """The estimation prompt asks for JSON output."""
        assert "JSON" in ESTIMATION_PROMPT or "json" in ESTIMATION_PROMPT

    def test_estimate_meal_prompt_requests_confidence(self):
        """The estimation prompt asks for a confidence score."""
        assert "confidence" in ESTIMATION_PROMPT.lower()


class TestFormatEstimationMessage:
    def test_format_estimation_shows_meal_name(self):
        msg = format_estimation_message(_mock_estimation())
        assert "grilled chicken salad" in msg.lower()

    def test_format_estimation_shows_macros(self):
        msg = format_estimation_message(_mock_estimation())
        assert "388" in msg  # calories
        assert "48" in msg   # protein
        assert "3" in msg    # carbs
        assert "19" in msg   # fat

    def test_format_estimation_shows_confidence(self):
        msg = format_estimation_message(_mock_estimation())
        assert "75" in msg or "0.75" in msg  # confidence as percentage or decimal
