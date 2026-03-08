"""Safety guardrails.

Enforces medical boundaries, detects concerning patterns,
and ensures the concierge stays within safe advice limits.

Pure rule-based filter — no LLM calls. Must run in < 10ms.
"""

import re
from dataclasses import dataclass


@dataclass
class SafetyResult:
    status: str  # "pass" | "block" | "warn"
    reason: str = ""
    suggested_fix: str = ""


# ---------------------------------------------------------------------------
# Medical advice patterns (BLOCK)
# ---------------------------------------------------------------------------

# "you have [condition]" or "you might have [condition]"
_RE_YOU_HAVE = re.compile(
    r"\byou\s+(have|might\s+have)\s+(?!to\b)\w+", re.IGNORECASE
)

# "diagnosis" / "diagnose"
_RE_DIAGNOSIS = re.compile(r"\bdiagnos[ei]s?\b", re.IGNORECASE)

# "take [medication]" — but NOT "take a walk/break/rest/look/moment/breath/step/seat/nap"
_TAKE_SAFE_WORDS = (
    "a walk", "a break", "a rest", "a look", "a moment", "a breath",
    "a step", "a seat", "a nap", "it easy", "your time", "care",
    "a day off", "some time", "the time", "the day off",
)
_RE_TAKE = re.compile(r"\btake\s+(.{1,30})", re.IGNORECASE)

# "symptoms suggest" / "that sounds like"
_RE_SYMPTOM_INTERPRET = re.compile(
    r"\bsymptoms?\s+suggest\b|\bthat\s+sounds\s+like\s+(?!a\s+(plan|good|great|idea))",
    re.IGNORECASE,
)

# "treatment" in imperative/prescriptive context
_RE_TREATMENT = re.compile(
    r"\b(try\s+(this|that|the)\s+treatment|the\s+treatment\s+is)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Tone violation patterns (WARN)
# ---------------------------------------------------------------------------

_RE_YOU_SHOULD = re.compile(r"\byou\s+(should|need\s+to)\b", re.IGNORECASE)
_RE_DONT_FORGET = re.compile(r"\bdon'?t\s+forget\b", re.IGNORECASE)
_RE_STREAK = re.compile(
    r"\bdays?\s+in\s+a\s+row\b|\bstreak\b|\bconsecutive\s+days?\b",
    re.IGNORECASE,
)
_RE_GUILT = re.compile(
    r"\byou\s+said\s+you\s+would\b|\byou\s+missed\b|\byou\s+didn'?t\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Harmful content patterns (BLOCK)
# ---------------------------------------------------------------------------

# Extreme caloric restriction: number < 800 + "calories"
_RE_LOW_CALORIES = re.compile(
    r"\b([1-7]\d{0,2})\s*calories?\b", re.IGNORECASE
)

# Body-shaming
_RE_BODY_SHAME = re.compile(
    r"\btoo\s+fat\b|\boverweight\b|\bobese\b", re.IGNORECASE
)

# Dismissive of mental health
_RE_DISMISSIVE_MENTAL = re.compile(
    r"\bjust\s+cheer\s+up\b|\bit'?s\s+just\s+stress\b|\bstop\s+worrying\b",
    re.IGNORECASE,
)

# Professional referral — safe override
_RE_PROFESSIONAL_REFERRAL = re.compile(
    r"\b(talk\s+to|see|consult|speak\s+(to|with)|visit)\s+(your\s+)?(a\s+)?"
    r"(doctor|physician|healthcare|medical|professional|therapist|counselor)\b",
    re.IGNORECASE,
)


def _count_char(text: str, char: str) -> int:
    return text.count(char)


def _check_take_medication(message: str) -> bool:
    """Return True if 'take X' looks like medication advice."""
    for m in _RE_TAKE.finditer(message):
        after = m.group(1).lower().strip()
        if any(after.startswith(safe) for safe in _TAKE_SAFE_WORDS):
            continue
        # It's a 'take' that doesn't match safe words — likely medication
        return True
    return False


def check_message(message: str, context: dict | None = None) -> SafetyResult:
    """Check a message against safety rules.

    Returns a SafetyResult with status "pass", "block", or "warn".
    Pure rule-based — no LLM calls, runs in < 10ms.
    """
    # Professional referral is always safe — early return for messages
    # that are clearly referrals
    is_referral = bool(_RE_PROFESSIONAL_REFERRAL.search(message))

    # --- BLOCK: Medical advice ---
    if not is_referral and _RE_YOU_HAVE.search(message):
        return SafetyResult(
            status="block",
            reason="Medical advice: implies diagnosis ('you have' / 'you might have')",
            suggested_fix="Remove diagnostic language. Suggest consulting a doctor instead.",
        )

    if _RE_DIAGNOSIS.search(message):
        return SafetyResult(
            status="block",
            reason="Medical advice: contains diagnostic terminology",
            suggested_fix="Remove diagnostic language. Suggest consulting a doctor instead.",
        )

    if _check_take_medication(message):
        return SafetyResult(
            status="block",
            reason="Medical advice: recommends taking medication",
            suggested_fix="Remove medication recommendation. Suggest consulting a doctor.",
        )

    if not is_referral and _RE_SYMPTOM_INTERPRET.search(message):
        return SafetyResult(
            status="block",
            reason="Medical advice: interprets symptoms",
            suggested_fix="Remove symptom interpretation. Suggest consulting a doctor.",
        )

    if _RE_TREATMENT.search(message):
        return SafetyResult(
            status="block",
            reason="Medical advice: prescribes treatment",
            suggested_fix="Remove treatment recommendation. Suggest consulting a doctor.",
        )

    # --- BLOCK: Harmful content ---
    match = _RE_LOW_CALORIES.search(message)
    if match:
        val = int(match.group(1))
        if val < 800:
            return SafetyResult(
                status="block",
                reason=f"Harmful content: extreme caloric restriction ({val} calories)",
                suggested_fix="Remove specific calorie target. Never recommend very low calorie diets.",
            )

    if _RE_BODY_SHAME.search(message):
        return SafetyResult(
            status="block",
            reason="Harmful content: body-shaming language",
            suggested_fix="Remove body-shaming language. Focus on how the user feels, not appearance.",
        )

    if _RE_DISMISSIVE_MENTAL.search(message):
        return SafetyResult(
            status="block",
            reason="Harmful content: dismissive of mental health",
            suggested_fix="Acknowledge the user's feelings. Suggest professional support if appropriate.",
        )

    # --- WARN: Tone violations ---
    warns: list[str] = []

    if _count_char(message, "?") > 1:
        warns.append("Multiple questions in one message (interrogation mode)")

    if _RE_YOU_SHOULD.search(message):
        warns.append("Uses 'you should' / 'you need to' (authoritarian tone)")

    if _RE_DONT_FORGET.search(message):
        warns.append("Uses 'don't forget' (implies user is forgetful)")

    if _RE_STREAK.search(message):
        warns.append("Uses streak/consecutive language (creates fragile motivation)")

    if _count_char(message, "!") > 2:
        warns.append("Excessive exclamation marks (performative enthusiasm)")

    if _RE_GUILT.search(message):
        warns.append("Guilt-tripping language detected")

    if warns:
        return SafetyResult(
            status="warn",
            reason="; ".join(warns),
            suggested_fix="Rephrase to be more curious and less directive.",
        )

    return SafetyResult(status="pass")
