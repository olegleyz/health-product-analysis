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


class TestContextIncludesDailySummaries:
    """test_context_includes_daily_summaries"""

    def test_context_includes_daily_summaries(self) -> None:
        summaries = [
            {"date": "2026-03-01", "summary": "Ran 5K, slept 7h"},
            {"date": "2026-03-02", "summary": "Rest day, ate well"},
            {"date": "2026-03-03", "summary": "Strength session, HRV 50"},
        ]
        result = format_context_block(daily_summaries=summaries)
        assert "## Recent daily summaries" in result
        assert "2026-03-01" in result
        assert "2026-03-02" in result
        assert "2026-03-03" in result
        assert "Ran 5K" in result
        assert "Rest day" in result
        assert "Strength session" in result


class TestContextTruncatesOldSummaries:
    """test_context_truncates_old_summaries_when_over_budget"""

    def test_context_truncates_old_summaries_when_over_budget(self) -> None:
        # Create summaries that collectively exceed a small budget.
        summaries = [
            {"date": f"2026-03-{i:02d}", "summary": "A" * 200}
            for i in range(1, 15)
        ]
        result = format_context_block(
            daily_summaries=summaries,
            token_budget=300,  # ~1200 chars — will force trimming
        )
        # The most recent summaries should survive; oldest should be dropped.
        assert "2026-03-14" in result  # newest kept
        assert "2026-03-01" not in result  # oldest trimmed

    def test_truncation_then_reduces_messages(self) -> None:
        summaries = [
            {"date": f"2026-03-{i:02d}", "summary": "X" * 100}
            for i in range(1, 5)
        ]
        messages = [
            {"role": "user", "content": f"msg {i} " + "Y" * 100}
            for i in range(1, 10)
        ]
        result = format_context_block(
            daily_summaries=summaries,
            recent_messages=messages,
            token_budget=200,  # very tight — both summaries and messages trimmed
        )
        # Newest message should survive over oldest.
        assert "msg 9" in result
        # Oldest messages should have been trimmed.
        assert "msg 1" not in result


class TestContextWorksWithNoSummaries:
    """test_context_works_with_no_summaries"""

    def test_context_works_with_no_summaries(self) -> None:
        result = format_context_block(
            user_profile={"name": "Alex"},
            recent_messages=[
                {"role": "user", "content": "Hi"},
            ],
            device_data_summary="HRV: 45ms",
            daily_summaries=None,
        )
        assert "Alex" in result
        assert "Hi" in result
        assert "HRV: 45ms" in result
        assert "summar" not in result.lower()

    def test_context_works_with_empty_summaries(self) -> None:
        result = format_context_block(
            user_profile={"name": "Alex"},
            daily_summaries=[],
        )
        assert "Alex" in result
        assert "summar" not in result.lower()


class TestPatternReferenceInstructionInPrompt:
    """test_pattern_reference_instruction_in_prompt"""

    def test_pattern_reference_instruction_in_prompt(self) -> None:
        prompt_lower = SYSTEM_PROMPT.lower()
        assert "pattern" in prompt_lower
        assert "fabricate" in prompt_lower or "never fabricate" in prompt_lower
        # Ensure we instruct the LLM to reference patterns from summaries.
        assert "summaries" in prompt_lower
        # Ensure we warn against making up trends.
        assert "not" in prompt_lower and "fabricate" in prompt_lower


class TestPromptTokenBudget:
    def test_prompt_token_count_within_budget(self) -> None:
        estimated_tokens = len(SYSTEM_PROMPT) / 4
        assert estimated_tokens < 2500, (
            f"SYSTEM_PROMPT estimated at {estimated_tokens:.0f} tokens, "
            f"must be under 2500"
        )
