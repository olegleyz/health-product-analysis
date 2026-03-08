"""Tests for the persona system prompt and context formatter."""

from src.prompts.persona import SYSTEM_PROMPT, format_context_block


class TestSystemPromptSafety:
    def test_system_prompt_contains_safety_rules(self) -> None:
        prompt_lower = SYSTEM_PROMPT.lower()
        assert "never" in prompt_lower
        assert "medical" in prompt_lower
        assert "diagnos" in prompt_lower

    def test_system_prompt_contains_tone_guidelines(self) -> None:
        prompt_lower = SYSTEM_PROMPT.lower()
        assert any(
            word in prompt_lower for word in ("warm", "brief", "non-judgmental")
        )

    def test_system_prompt_contains_anti_patterns(self) -> None:
        prompt_lower = SYSTEM_PROMPT.lower()
        assert "never" in prompt_lower
        assert "guilt" in prompt_lower or "streak" in prompt_lower


class TestFormatContextBlock:
    def test_format_context_with_full_data(self) -> None:
        result = format_context_block(
            user_profile={
                "name": "Alex",
                "goals": "Run a half-marathon",
                "preferences": "Morning check-ins",
                "tone_preference": "direct",
            },
            recent_messages=[
                {"role": "user", "content": "I ran 5K today"},
                {"role": "assistant", "content": "Nice. How did it feel?"},
            ],
            device_data_summary="Sleep: 7.2h, HRV: 45ms, Steps: 8200",
            daily_summaries=[
                {"date": "2026-03-06", "summary": "Ran 5K, ate well, slept 7h"},
            ],
        )
        assert "Alex" in result
        assert "half-marathon" in result
        assert "Morning check-ins" in result
        assert "direct" in result
        assert "I ran 5K today" in result
        assert "Nice. How did it feel?" in result
        assert "Recent device data" in result
        assert "Sleep: 7.2h" in result
        assert "Recent daily summaries" in result
        assert "2026-03-06" in result

    def test_format_context_with_no_device_data(self) -> None:
        result = format_context_block(
            user_profile={"name": "Alex"},
            device_data_summary=None,
        )
        assert "Alex" in result
        assert "device" not in result.lower()

    def test_format_context_with_no_summaries(self) -> None:
        result = format_context_block(
            user_profile={"name": "Alex"},
            daily_summaries=None,
        )
        assert "Alex" in result
        assert "summar" not in result.lower()

    def test_format_context_with_empty_messages(self) -> None:
        result = format_context_block(
            user_profile={"name": "Alex"},
            recent_messages=[],
        )
        assert "Alex" in result
        assert "conversation" not in result.lower()

    def test_format_context_all_none(self) -> None:
        result = format_context_block()
        assert result == ""

    def test_format_context_partial_profile(self) -> None:
        result = format_context_block(user_profile={"name": "Alex"})
        assert "Alex" in result
        assert "Goals" not in result


class TestPromptTokenBudget:
    def test_prompt_token_count_within_budget(self) -> None:
        estimated_tokens = len(SYSTEM_PROMPT) / 4
        assert estimated_tokens < 2500, (
            f"SYSTEM_PROMPT estimated at {estimated_tokens:.0f} tokens, "
            f"must be under 2500"
        )
