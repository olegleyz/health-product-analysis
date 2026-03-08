"""Tests for the safety filter (T-007)."""

from src.safety import SafetyResult, check_message


class TestPassesNormalMessages:
    def test_passes_normal_message(self):
        result = check_message("That's a solid morning routine.")
        assert result.status == "pass"

    def test_passes_workout_encouragement(self):
        result = check_message("Nice work getting that run in today!")
        assert result.status == "pass"

    def test_passes_gentle_nudge(self):
        result = check_message("How did you feel after the workout?")
        assert result.status == "pass"

    def test_passes_professional_referral(self):
        result = check_message("You might want to talk to your doctor about that")
        assert result.status == "pass"


class TestBlocksMedicalAdvice:
    def test_blocks_diagnosis(self):
        result = check_message("That sounds like you have anemia")
        assert result.status == "block"

    def test_blocks_medication_advice(self):
        result = check_message("You should take ibuprofen")
        assert result.status == "block"

    def test_blocks_symptom_interpretation(self):
        result = check_message("Those symptoms suggest a thyroid issue")
        assert result.status == "block"

    def test_result_includes_reason_when_blocked(self):
        result = check_message("That sounds like you have anemia")
        assert result.status == "block"
        assert result.reason != ""
        assert len(result.reason) > 0


class TestWarnsToneViolations:
    def test_warns_multiple_questions(self):
        result = check_message(
            "How was your workout? Did you eat well? How did you sleep?"
        )
        assert result.status == "warn"

    def test_warns_you_should_language(self):
        result = check_message("You should really focus on your diet")
        assert result.status == "warn"

    def test_warns_streak_language(self):
        result = check_message("That's 5 days in a row!")
        assert result.status == "warn"

    def test_warns_guilt_trip(self):
        result = check_message("You said you would work out today")
        assert result.status == "warn"


class TestBlocksHarmfulContent:
    def test_blocks_extreme_diet_advice(self):
        result = check_message("Try eating only 500 calories a day")
        assert result.status == "block"

    def test_blocks_body_shaming(self):
        result = check_message("You're getting too fat")
        assert result.status == "block"

    def test_blocks_dismissive_mental_health(self):
        result = check_message("Just cheer up, it's not that bad")
        assert result.status == "block"


class TestEdgeCases:
    def test_take_a_walk_is_safe(self):
        result = check_message("Take a walk after lunch")
        assert result.status == "pass"

    def test_take_a_break_is_safe(self):
        result = check_message("Take a break if you need one")
        assert result.status == "pass"

    def test_single_question_is_fine(self):
        result = check_message("How are you feeling?")
        assert result.status == "pass"

    def test_single_exclamation_is_fine(self):
        result = check_message("Great workout today!")
        assert result.status == "pass"

    def test_two_exclamations_is_fine(self):
        result = check_message("Great workout! Nice job!")
        assert result.status == "pass"

    def test_three_exclamations_warns(self):
        result = check_message("Great! Amazing! Wonderful! Keep going!")
        assert result.status == "warn"

    def test_1000_calories_is_fine(self):
        result = check_message("You burned about 1000 calories today")
        assert result.status == "pass"

    def test_you_have_to_is_not_blocked(self):
        """'you have to' is not a diagnosis."""
        result = check_message("You have to try this recipe")
        assert result.status != "block" or "diagnosis" not in result.reason
