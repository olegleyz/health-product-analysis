"""Onboarding conversation flow.

LLM-driven state machine that collects user profile data through
natural conversation. Steps: welcome, goals, routine, checkin_times,
tone, accountability, struggles, then marks onboarding complete.
"""

import logging

from src.db import get_user, upsert_user
from src.llm import call_llm, call_llm_json

logger = logging.getLogger(__name__)

ONBOARDING_STEPS = [
    "welcome",
    "goals",
    "routine",
    "checkin_times",
    "tone",
    "accountability",
    "struggles",
]

# What to extract from the user's answer at each step
_EXTRACTION_PROMPTS: dict[str, str] = {
    "welcome": (
        "The user is introducing themselves. Extract their name from the message.\n"
        'Return JSON only: {"name": "<string or null>"}'
    ),
    "goals": (
        "The user is describing their health goals. Extract a concise list.\n"
        'Return JSON only: {"goals": ["<goal1>", "<goal2>", ...]}'
    ),
    "routine": (
        "The user is describing their current exercise/health routine. Summarize it.\n"
        'Return JSON only: {"routine": "<short summary>"}'
    ),
    "checkin_times": (
        "The user is telling you their preferred check-in times. Extract them.\n"
        'Return JSON only: {"checkin_times": "<description of preferred times>"}'
    ),
    "tone": (
        "The user is describing their preferred communication style. "
        "Classify as 'direct', 'supportive', or 'balanced'.\n"
        'Return JSON only: {"tone": "<direct|supportive|balanced>"}'
    ),
    "accountability": (
        "The user is describing how much accountability they want. "
        "Classify as 'high', 'medium', or 'low'.\n"
        'Return JSON only: {"accountability": "<high|medium|low>"}'
    ),
    "struggles": (
        "The user is sharing what they struggle with regarding health/fitness. "
        "Extract a concise summary.\n"
        'Return JSON only: {"struggles": "<short summary>"}'
    ),
}

# The question to ask after processing each step (i.e. what to ask next)
_STEP_QUESTIONS: dict[str, str] = {
    "welcome": (
        "You are a personal health concierge starting onboarding with a new user. "
        "Greet them warmly and ask for their name. Keep it brief and friendly — "
        "1-2 sentences max. Do not ask multiple questions."
    ),
    "goals": (
        "The user just told you their name. Thank them briefly and ask about "
        "their health and fitness goals. What are they working towards? "
        "Keep it to 1-2 sentences. One question only."
    ),
    "routine": (
        "The user shared their goals. Acknowledge briefly and ask about their "
        "current routine — what does a typical week look like for exercise, "
        "sleep, nutrition? Keep it to 1-2 sentences. One question only."
    ),
    "checkin_times": (
        "The user described their routine. Acknowledge briefly and ask when "
        "they'd prefer to hear from you — morning, evening, or specific times? "
        "Keep it to 1-2 sentences. One question only."
    ),
    "tone": (
        "The user shared their preferred check-in times. Acknowledge briefly and ask "
        "about communication style — do they prefer direct and to-the-point, "
        "or more supportive and encouraging? Keep it to 1-2 sentences. One question only."
    ),
    "accountability": (
        "The user shared their tone preference. Acknowledge briefly and ask how much "
        "accountability they want — should you nudge them when they go quiet, "
        "or take a more hands-off approach? Keep it to 1-2 sentences. One question only."
    ),
    "struggles": (
        "The user shared their accountability preference. Acknowledge briefly and ask "
        "what they tend to struggle with most — consistency, nutrition, sleep, motivation, "
        "or something else? This is the last question. Keep it to 1-2 sentences."
    ),
    "complete": (
        "The user just finished onboarding by sharing what they struggle with. "
        "Wrap up warmly. Summarize what you learned about them in 1-2 sentences "
        "and let them know you're ready to start. Keep it brief and genuine."
    ),
}


def get_onboarding_step(user_id: str) -> str | None:
    """Return current onboarding step, or None if onboarding is complete."""
    user = get_user(user_id)
    if user and user.get("onboarding_complete"):
        return None
    prefs = user.get("preferences", {}) if user else {}
    if not isinstance(prefs, dict):
        prefs = {}
    return prefs.get("onboarding_step", "welcome")


def handle_onboarding_message(user_id: str, text: str) -> str:
    """Handle a message during onboarding. Returns response text."""
    step = get_onboarding_step(user_id)
    if step is None:
        # Should not happen — caller checks first
        return "Onboarding is already complete."

    # Ensure user exists in DB
    user = get_user(user_id)
    if user is None:
        upsert_user(user_id, preferences={"onboarding_step": "welcome", "collected": {}})
        user = get_user(user_id)

    prefs = user.get("preferences", {}) if user else {}
    if not isinstance(prefs, dict):
        prefs = {}
    collected = prefs.get("collected", {})

    if step == "welcome":
        # First message — don't extract from it, just generate the welcome
        # and advance to goals (the user's reply will be extracted at "goals" step)
        # But if we're at welcome and the user sent something, we extract name
        # and move to goals
        extracted = _extract_step_data(step, text)
        if extracted:
            collected.update(extracted)
        next_step = _next_step(step)
    else:
        # Extract data from user's answer
        extracted = _extract_step_data(step, text)
        if extracted:
            collected.update(extracted)
        next_step = _next_step(step)

    # Save progress
    prefs["onboarding_step"] = next_step
    prefs["collected"] = collected

    if next_step is None:
        # Onboarding complete — save collected data to user profile
        _save_onboarding_data(user_id, collected)
        upsert_user(user_id, onboarding_complete=1, preferences=prefs)
        # Generate completion message
        context = f"Collected info: {collected}"
        response = call_llm(_STEP_QUESTIONS["complete"], context)
        return response
    else:
        upsert_user(user_id, preferences=prefs)
        # Generate the next question
        context = f"User's last message: {text}\nCollected so far: {collected}"
        response = call_llm(_STEP_QUESTIONS[next_step], context)
        return response


def _extract_step_data(step: str, text: str) -> dict | None:
    """Use the LLM to extract structured data from the user's freeform answer."""
    prompt = _EXTRACTION_PROMPTS.get(step)
    if not prompt:
        return None
    try:
        result = call_llm_json(prompt, text)
        return result
    except (ValueError, Exception) as exc:
        logger.warning("Onboarding extraction failed at step %s: %s", step, exc)
        return None


def _next_step(current: str) -> str | None:
    """Return the step after `current`, or None if onboarding is done."""
    try:
        idx = ONBOARDING_STEPS.index(current)
    except ValueError:
        return None
    if idx + 1 < len(ONBOARDING_STEPS):
        return ONBOARDING_STEPS[idx + 1]
    return None  # all steps done


def _save_onboarding_data(user_id: str, collected: dict) -> None:
    """Persist collected onboarding data into the user profile fields."""
    updates: dict = {}

    if "name" in collected and collected["name"]:
        updates["name"] = collected["name"]

    if "goals" in collected:
        updates["goals"] = collected["goals"]

    if updates:
        upsert_user(user_id, **updates)
