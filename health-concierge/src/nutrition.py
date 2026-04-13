"""Nutrition estimation, correction, and aggregation.

Core logic for the Nutrition Ledger feature. Handles meal photo
estimation via Claude Vision, user corrections, daily aggregation,
and qualitative status computation.
"""

import logging

from src import db
from src.llm import call_llm_vision_json

logger = logging.getLogger(__name__)

ESTIMATION_PROMPT = """\
You are a nutrition estimation assistant. Given a photo of a meal and an optional \
text description, identify the visible food components, estimate portion sizes in \
grams, and compute macronutrient values.

Return ONLY a JSON object with this exact structure:
{
    "meal_name": "short descriptive name",
    "components": [
        {
            "name": "ingredient name",
            "weight_g": estimated weight in grams,
            "calories": estimated calories,
            "protein_g": estimated protein in grams,
            "carbs_g": estimated carbohydrates in grams,
            "fat_g": estimated fat in grams
        }
    ],
    "totals": {
        "calories": total calories,
        "protein_g": total protein in grams,
        "carbs_g": total carbohydrates in grams,
        "fat_g": total fat in grams,
        "weight_g": total weight in grams
    },
    "confidence": a number between 0.0 and 1.0,
    "assumptions": ["list of assumptions made during estimation"]
}

Guidelines:
- Be conservative: when uncertain about portion size, estimate moderately rather than \
aggressively in either direction.
- List each visible component separately with its own nutritional breakdown.
- Express uncertainty via the confidence score: 0.9+ for clearly visible, well-known \
meals; 0.5-0.7 for partially visible or ambiguous meals; below 0.5 for very uncertain.
- List all assumptions explicitly (cooking method, oil usage, dressing, hidden \
ingredients).
- Do not guess ingredients that are not visible or mentioned in the text hint.
- Round nutritional values to whole numbers.
"""


def estimate_meal(
    image_data: bytes, media_type: str, text_hint: str = ""
) -> dict:
    """Estimate nutritional content of a meal from a photo.

    Sends the image to Claude Vision with the estimation prompt.
    Returns a structured dict with meal_name, components, totals,
    confidence, and assumptions.
    """
    result = call_llm_vision_json(
        ESTIMATION_PROMPT,
        image_data,
        media_type,
        text_hint=text_hint,
        max_tokens=1024,
    )
    logger.info(
        "Estimated meal '%s' (confidence=%.2f, %d components)",
        result.get("meal_name", "unknown"),
        result.get("confidence", 0),
        len(result.get("components", [])),
    )
    return result


def format_estimation_message(estimation: dict) -> str:
    """Format a nutrition estimation as a readable Telegram message."""
    meal_name = estimation.get("meal_name", "Unknown meal")
    totals = estimation.get("totals", {})
    confidence = estimation.get("confidence", 0)
    components = estimation.get("components", [])
    assumptions = estimation.get("assumptions", [])

    lines = [f"*{meal_name.title()}*"]
    lines.append("")

    # Component breakdown
    if components:
        for comp in components:
            name = comp.get("name", "?")
            weight = comp.get("weight_g", "?")
            lines.append(f"  {name}: {weight}g")
        lines.append("")

    # Totals
    cal = totals.get("calories", 0)
    pro = totals.get("protein_g", 0)
    carbs = totals.get("carbs_g", 0)
    fat = totals.get("fat_g", 0)
    lines.append(f"Calories: {cal} kcal")
    lines.append(f"Protein: {pro}g | Carbs: {carbs}g | Fat: {fat}g")
    lines.append("")

    # Confidence
    conf_pct = int(confidence * 100)
    lines.append(f"Confidence: {conf_pct}%")

    # Assumptions
    if assumptions:
        lines.append("")
        lines.append("Assumptions:")
        for a in assumptions:
            lines.append(f"  - {a}")

    return "\n".join(lines)


def re_estimate_meal(
    image_data: bytes,
    media_type: str,
    original_estimation: dict,
    corrections: str,
) -> dict:
    """Re-estimate a meal with user corrections as constraints.

    Sends the original estimation and user's correction text back to
    Claude along with the image, so it can recalculate while respecting
    the correction.
    """
    correction_prompt = ESTIMATION_PROMPT + (
        "\n\nYou previously estimated this meal as follows:\n"
        f"{_format_estimation_for_prompt(original_estimation)}\n\n"
        "The user has provided the following correction:\n"
        f"{corrections}\n\n"
        "Please re-estimate the meal taking this correction into account. "
        "Return the updated JSON in the same format."
    )

    result = call_llm_vision_json(
        correction_prompt,
        image_data,
        media_type,
        max_tokens=1024,
    )
    logger.info(
        "Re-estimated meal '%s' with corrections: %s",
        result.get("meal_name", "unknown"),
        corrections[:80],
    )
    return result


def _format_estimation_for_prompt(estimation: dict) -> str:
    """Format an estimation dict as a string for inclusion in a prompt."""
    import json
    return json.dumps(estimation, indent=2)


def get_qualitative_status(value: float, target: float) -> str:
    """Return qualitative status for a nutritional value vs target.

    Returns "low" (<70%), "adequate" (70-130%), or "high" (>130%).
    """
    if target <= 0:
        return "adequate"
    ratio = value / target
    if ratio < 0.7:
        return "low"
    elif ratio > 1.3:
        return "high"
    return "adequate"


def get_daily_nutrition(user_id: str, date: str) -> dict:
    """Aggregate all nutrition events for a date into a daily summary.

    Returns dict with: date, meals_count, meals, totals, targets, status.
    """
    events = db.get_nutrition_events(user_id, date)
    targets = db.get_nutrition_targets(user_id)

    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    meals = []

    for event in events:
        totals["calories"] += event.get("calories", 0) or 0
        totals["protein_g"] += event.get("protein_g", 0) or 0
        totals["carbs_g"] += event.get("carbs_g", 0) or 0
        totals["fat_g"] += event.get("fat_g", 0) or 0
        meals.append({
            "meal_name": event.get("meal_name", ""),
            "calories": event.get("calories", 0),
            "protein_g": event.get("protein_g", 0),
        })

    status = {}
    for key in ("calories", "protein_g", "carbs_g", "fat_g"):
        target_val = targets.get(key, 0)
        status[key] = get_qualitative_status(totals[key], target_val)

    return {
        "date": date,
        "meals_count": len(events),
        "meals": meals,
        "totals": totals,
        "targets": {k: targets.get(k, 0) for k in ("calories", "protein_g", "carbs_g", "fat_g")},
        "status": status,
    }


def format_daily_summary(daily: dict) -> str:
    """Format daily nutrition state as a readable Telegram message."""
    meals_count = daily.get("meals_count", 0)
    if meals_count == 0:
        return "No meals logged today."

    totals = daily.get("totals", {})
    targets = daily.get("targets", {})
    status = daily.get("status", {})

    lines = [f"Today: {meals_count} meal{'s' if meals_count != 1 else ''} logged"]
    lines.append("")

    cal = totals.get("calories", 0)
    cal_target = targets.get("calories", 0)
    cal_status = status.get("calories", "")
    lines.append(f"Calories: {cal:.0f} / {cal_target:.0f} kcal ({cal_status})")

    pro = totals.get("protein_g", 0)
    pro_target = targets.get("protein_g", 0)
    pro_status = status.get("protein_g", "")
    lines.append(f"Protein: {pro:.0f} / {pro_target:.0f}g ({pro_status})")

    carbs = totals.get("carbs_g", 0)
    carbs_target = targets.get("carbs_g", 0)
    carbs_status = status.get("carbs_g", "")
    lines.append(f"Carbs: {carbs:.0f} / {carbs_target:.0f}g ({carbs_status})")

    fat = totals.get("fat_g", 0)
    fat_target = targets.get("fat_g", 0)
    fat_status = status.get("fat_g", "")
    lines.append(f"Fat: {fat:.0f} / {fat_target:.0f}g ({fat_status})")

    return "\n".join(lines)
