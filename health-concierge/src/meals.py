"""Meal extraction, memory, and suggestion.

Identifies meals from user messages, maintains a meal repertoire
with fuzzy matching, and suggests meals by context/tags.
"""

import json
import logging
from difflib import SequenceMatcher

from src import db
from src.llm import call_llm_json

logger = logging.getLogger(__name__)

_FUZZY_THRESHOLD = 0.7
_STOP_WORDS = {"a", "an", "the", "with", "and", "or", "of", "for", "in", "on", "that", "some", "my"}

_EXTRACT_SYSTEM_PROMPT = """You are a meal extraction assistant. Given a user's message about food they ate,
extract the canonical meal name and relevant tags.

Return ONLY a JSON object with these fields:
- "name": a short canonical meal name (lowercase, e.g. "chicken pasta", "greek salad")
- "tags": a list of relevant tags from this set: "high-protein", "low-carb", "quick", "pre-workout", "post-workout", "breakfast", "lunch", "dinner", "snack", "light", "heavy", "vegetarian", "vegan"

Only include tags that clearly apply. Be concise with the name."""


def _similarity(a: str, b: str) -> float:
    """Compute similarity between two meal names.

    Uses the higher of: character-level SequenceMatcher ratio, and
    word-overlap Jaccard similarity. This handles word reordering
    (e.g. "chicken pasta" vs "pasta with chicken").
    """
    char_ratio = SequenceMatcher(None, a, b).ratio()
    words_a = set(a.split()) - _STOP_WORDS
    words_b = set(b.split()) - _STOP_WORDS
    union = words_a | words_b
    jaccard = len(words_a & words_b) / len(union) if union else 0.0
    return max(char_ratio, jaccard)


def _fuzzy_match(name: str, existing_meals: list[dict]) -> dict | None:
    """Find the best fuzzy match among existing meals.

    Returns the matched meal dict if similarity >= threshold, else None.
    """
    best_match = None
    best_ratio = 0.0
    name_lower = name.lower().strip()

    for meal in existing_meals:
        meal_name_lower = meal["name"].lower().strip()
        ratio = _similarity(name_lower, meal_name_lower)
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = meal

    if best_ratio >= _FUZZY_THRESHOLD and best_match is not None:
        return best_match
    return None


def process_meal_mention(user_id: str, meal_description: str) -> dict:
    """Process a meal mention from the user.

    Uses LLM to extract canonical name and tags, then upserts into the
    meals table with fuzzy matching to recognize repeat meals.

    Returns a dict with: name, tags, is_new, times_mentioned.
    """
    # Extract meal info via LLM
    extracted = call_llm_json(
        _EXTRACT_SYSTEM_PROMPT,
        meal_description,
        max_tokens=256,
    )
    canonical_name = extracted.get("name", meal_description).lower().strip()
    tags = extracted.get("tags", [])

    # Check for fuzzy match in existing meals
    existing_meals = db.get_meals(user_id)
    match = _fuzzy_match(canonical_name, existing_meals)

    if match is not None:
        # Use the existing meal's name for consistency
        db.upsert_meal(user_id, match["name"], tags=tags)
        # Fetch updated record
        updated_meals = db.get_meals(user_id)
        updated = next(
            (m for m in updated_meals if m["name"] == match["name"]), match
        )
        logger.info(
            "Repeat meal '%s' for user %s (matched '%s', count=%d)",
            canonical_name,
            user_id,
            match["name"],
            updated.get("times_mentioned", match["times_mentioned"] + 1),
        )
        return {
            "name": match["name"],
            "tags": updated.get("tags", tags),
            "is_new": False,
            "times_mentioned": updated.get(
                "times_mentioned", match["times_mentioned"] + 1
            ),
        }
    else:
        # New meal
        db.upsert_meal(user_id, canonical_name, tags=tags)
        logger.info("New meal '%s' for user %s", canonical_name, user_id)
        return {
            "name": canonical_name,
            "tags": tags,
            "is_new": True,
            "times_mentioned": 1,
        }


def get_meal_repertoire(user_id: str) -> list[dict]:
    """Return all meals for a user, sorted by frequency (most mentioned first)."""
    meals = db.get_meals(user_id)
    meals.sort(key=lambda m: m.get("times_mentioned", 0), reverse=True)
    return meals


def suggest_meals(user_id: str, context: str) -> list[dict]:
    """Suggest up to 3 meals matching a context string.

    Matches context words against meal tags. Returns meals sorted by
    relevance (tag match count) then frequency, limited to 3.
    """
    meals = db.get_meals(user_id)
    if not meals:
        return []

    context_lower = context.lower()
    context_words = context_lower.split()

    scored: list[tuple[int, int, dict]] = []
    for meal in meals:
        tags = meal.get("tags") or []
        if isinstance(tags, str):
            tags = json.loads(tags)

        # Count how many context words appear in any tag
        tag_str = " ".join(tags)
        match_count = sum(1 for word in context_words if word in tag_str)

        if match_count > 0:
            scored.append(
                (match_count, meal.get("times_mentioned", 0), meal)
            )

    # Sort by match count desc, then frequency desc
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [item[2] for item in scored[:3]]
