# Nutrition Ledger — Architecture Mapping

## Overview

The Nutrition Ledger adds photo-based meal tracking to the existing Health Concierge. Users send meal photos via Telegram; Claude Vision estimates nutritional content; the user confirms or corrects; the result is stored as an immutable event. Daily aggregation computes totals vs. targets and feeds qualitative status ("low / adequate / high") into the concierge's proactive messages.

This feature reuses the existing Telegram bot, Claude API client, SQLite database, persona/prompt system, and cron infrastructure. No new services, no REST API, no additional deployment targets.

---

## Design Principles

1. **Append-only events.** Meals are stored as immutable events. Daily state is always derived, never stored as primary truth. This allows recalculation if estimation logic improves.
2. **Probabilistic estimation, not ground truth.** Claude's output is a nutritional hypothesis with a confidence score. The system never claims precision.
3. **Qualitative feedback over raw numbers.** Users see "protein is low" rather than "42g / 120g target." This reduces cognitive overload and avoids diet-culture fixation on numbers.
4. **Minimal friction.** Photo → estimate → confirm → done. Corrections are conversational, not form-based.
5. **Reuse existing infrastructure.** Every component maps onto what already exists. No new frameworks, no new deployment concerns.

---

## Component Changes

### 1. Database Layer (`src/db.py`)

Two new tables added to `init_db()`:

**`nutrition_events`** — Immutable meal event log.

```sql
CREATE TABLE IF NOT EXISTS nutrition_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    meal_name TEXT,
    components JSON,          -- [{"name": "chicken breast", "weight_g": 150, ...}, ...]
    calories REAL,
    protein_g REAL,
    carbs_g REAL,
    fat_g REAL,
    weight_g REAL,            -- total estimated weight
    confidence REAL,          -- 0.0–1.0
    model_version TEXT,       -- Claude model used for estimation
    assumptions JSON,         -- ["portion estimated from plate size", ...]
    image_file_id TEXT,       -- Telegram file_id for the photo
    user_corrections JSON,    -- corrections applied, if any
    created_at TEXT           -- ISO 8601 UTC
);
```

**`nutrition_targets`** — Per-user daily nutritional targets.

```sql
CREATE TABLE IF NOT EXISTS nutrition_targets (
    user_id TEXT PRIMARY KEY,
    calories REAL DEFAULT 2200,
    protein_g REAL DEFAULT 120,
    carbs_g REAL DEFAULT 250,
    fat_g REAL DEFAULT 75,
    updated_at TEXT
);
```

New access functions follow the existing pattern (parameterized SQL, JSON serialization, `_rows_to_dicts`):

- `save_nutrition_event(user_id, meal_name, components, calories, protein_g, carbs_g, fat_g, weight_g, confidence, model_version, assumptions, image_file_id, user_corrections) → int` — returns the event ID
- `get_nutrition_events(user_id, date) → list[dict]` — all events for a calendar date
- `get_nutrition_targets(user_id) → dict` — targets with defaults if no record
- `upsert_nutrition_targets(user_id, **fields)` — create or update targets

No update or delete on `nutrition_events` — the table is append-only by design.

### 2. Claude Vision API (`src/llm.py`)

New function alongside the existing `call_llm` and `call_llm_json`:

```python
def call_llm_vision(
    system_prompt: str,
    image_data: bytes,
    media_type: str,
    text_hint: str = "",
    max_tokens: int = 1024,
) -> str:
```

Sends a message with mixed content blocks: an `image` block (base64-encoded) followed by a `text` block. Uses the same retry logic, client singleton, and model config as `call_llm`. A companion `call_llm_vision_json` wraps it with JSON parsing.

The image is sent as base64 inline (not URL) since Telegram photos are downloaded as bytes. Media type is typically `image/jpeg`.

### 3. Nutrition Module (`src/nutrition.py`) — NEW

Core logic for estimation, correction, aggregation, and state queries. Pure functions where possible; no Telegram or bot dependencies.

**Estimation:**

```python
def estimate_meal(image_data: bytes, media_type: str, text_hint: str = "") -> dict:
```

Calls `call_llm_vision_json` with a structured system prompt that instructs Claude to return:
```json
{
    "meal_name": "grilled chicken salad",
    "components": [
        {"name": "chicken breast", "weight_g": 150, "calories": 248, "protein_g": 46, "carbs_g": 0, "fat_g": 5},
        {"name": "mixed greens", "weight_g": 100, "calories": 20, "protein_g": 2, "carbs_g": 3, "fat_g": 0}
    ],
    "totals": {"calories": 380, "protein_g": 52, "carbs_g": 15, "fat_g": 12, "weight_g": 320},
    "confidence": 0.75,
    "assumptions": ["portion size estimated from plate diameter", "dressing assumed olive oil based"]
}
```

**Re-estimation with corrections:**

```python
def re_estimate_meal(
    image_data: bytes, media_type: str, original_estimation: dict, corrections: str
) -> dict:
```

Sends the original estimation + user's natural-language correction as constraints. Claude re-calculates while respecting the correction (e.g., "portion was smaller", "no dressing", "it was turkey not chicken").

**Aggregation:**

```python
def get_daily_nutrition(user_id: str, date: str) -> dict:
```

Queries `nutrition_events` for the date, sums totals, compares against targets, and returns:
```json
{
    "date": "2026-04-12",
    "meals_count": 3,
    "totals": {"calories": 1850, "protein_g": 95, "carbs_g": 220, "fat_g": 65},
    "targets": {"calories": 2200, "protein_g": 120, "carbs_g": 250, "fat_g": 75},
    "status": {"calories": "adequate", "protein_g": "low", "carbs_g": "adequate", "fat_g": "adequate"},
    "meals": [...]
}
```

**Qualitative status:**

```python
def get_qualitative_status(value: float, target: float) -> str:
```

Returns `"low"` (< 70% of target), `"adequate"` (70–130%), or `"high"` (> 130%). These thresholds are simple and avoid false precision.

### 4. Telegram Bot (`src/bot.py`)

Three additions to the existing bot:

**Photo handler.** Registered alongside the existing text handler. When a user sends a photo:
1. Download the largest available photo size as bytes
2. Pass image + caption (if any) to the nutrition estimation pipeline
3. Format the result as a message with an inline keyboard: `[✓ Confirm] [✏️ Edit] [✗ Discard]`
4. Store the pending estimation in memory (keyed by user_id)

**Callback query handler.** Handles button presses from inline keyboards:
- **Confirm:** Stores the estimation as a `nutrition_event`. Replies with a brief confirmation including updated daily totals.
- **Edit:** Prompts the user to describe what to change. Sets a flag so the next text message is routed to the correction flow.
- **Discard:** Removes the pending estimation. Acknowledges.

**`/today` command handler.** Returns a formatted daily nutrition summary: meals logged, total macros, qualitative status vs. targets.

**Pending state management.** A module-level dict `_pending: dict[str, dict]` holds in-flight estimations keyed by user_id. For 2 users this is trivial. If the bot restarts mid-flow, the user simply re-sends the photo — no data loss since nothing was persisted yet.

### 5. Brain Integration (`src/brain.py`)

Minimal changes:

- The `handle_message` function checks whether the user is in "correction mode" (pending estimation + edit flag). If so, routes the text message to the re-estimation flow in `nutrition.py` instead of the normal LLM conversation path.
- Nutrition context (today's running totals) is added to `format_context_block` so the concierge is aware of what the user has eaten when responding to general conversation.

### 6. Persona / Prompts (`src/prompts/persona.py`)

**Estimation prompt** (used by `nutrition.py`): a dedicated system prompt for the vision model that emphasizes:
- Conservative estimation (round up uncertainty, not down)
- Structured JSON output only
- Component-level breakdown
- Explicit assumptions
- Confidence scoring guidelines

**Context block extension:** `format_context_block` gains an optional `nutrition_summary` parameter — a pre-formatted string of today's nutrition state that's appended to the context when available.

### 7. Proactive Integration (`src/proactive.py`)

- **Evening check-in:** Loads today's nutrition state and includes it in the prompt context. The concierge can naturally mention: "Protein's been a bit low today — maybe the chicken rice bowl for dinner?"
- **Daily summary (`src/summarizer.py`):** Includes nutrition totals in the structured summary JSON.

No changes to the governor, engagement, safety, or onboarding modules.

---

## Data Flow

### Meal Submission (Happy Path)

```
User sends photo (+ optional caption)
    │
    ▼
bot.py: _handle_photo()
    ├── Downloads photo bytes from Telegram
    ├── Calls nutrition.estimate_meal(image_data, media_type, caption)
    │       │
    │       ▼
    │   nutrition.py: estimate_meal()
    │       ├── Builds estimation prompt
    │       ├── Calls llm.call_llm_vision_json(prompt, image, media_type, caption)
    │       │       │
    │       │       ▼
    │       │   llm.py: call_llm_vision_json()
    │       │       ├── Base64-encodes image
    │       │       ├── Sends to Claude API (messages.create with image content)
    │       │       ├── Parses JSON response
    │       │       └── Returns structured estimation dict
    │       │
    │       └── Returns estimation dict
    │
    ├── Stores estimation in _pending[user_id]
    ├── Formats estimation as Telegram message
    ├── Sends message with inline keyboard [Confirm] [Edit] [Discard]
    └── Saves outbound message to DB

User presses [✓ Confirm]
    │
    ▼
bot.py: _handle_callback()
    ├── Reads _pending[user_id]
    ├── Calls db.save_nutrition_event(...)
    ├── Clears _pending[user_id]
    ├── Calls nutrition.get_daily_nutrition(user_id, today)
    ├── Sends confirmation with updated daily totals
    └── Saves outbound message to DB
```

### Correction Flow

```
User presses [✏️ Edit]
    │
    ▼
bot.py: _handle_callback()
    ├── Sets _pending[user_id]["awaiting_correction"] = True
    └── Sends: "What would you like to change?"

User types: "the portion was smaller, about half"
    │
    ▼
bot.py: _handle_message() → detects correction mode
    │
    ▼
nutrition.py: re_estimate_meal(image_data, media_type, original, corrections)
    ├── Builds re-estimation prompt with original + corrections as constraints
    ├── Calls call_llm_vision_json(...)
    └── Returns updated estimation dict
    │
    ▼
bot.py: Updates _pending, sends new estimation with inline keyboard
```

---

## Integration with Existing Meal Memory

The existing `meals.py` module tracks meal names and tags for the concierge's repertoire. When a nutrition event is confirmed, the system also calls `process_meal_mention(user_id, meal_name)` to update the meal repertoire. This keeps the two systems connected: nutrition tracking feeds the meal memory, and the meal memory continues to power conversational recommendations.

---

## Configuration

No new environment variables required. The system uses:
- `CLAUDE_API_KEY` — already configured (vision uses the same API)
- `CLAUDE_MODEL` — already configured (Claude Sonnet 4.x supports vision)
- `TELEGRAM_BOT_TOKEN` — already configured (photo handling is built into the Telegram Bot API)

Default nutrition targets (2200 cal, 120g protein, 250g carbs, 75g fat) are stored in the `nutrition_targets` table and can be adjusted per user via a future `/targets` command or during onboarding.

---

## Cost Impact

Vision API calls are more expensive than text-only calls. With the current model (Claude Sonnet):
- Estimated ~3–5 meal photos per day per user
- Each vision call: ~2–4K input tokens (image + prompt), ~500 output tokens
- Additional cost: ~$0.05–0.15/day per user, or ~$2–5/month for 2 users
- Re-estimations (corrections) add ~50% more calls for meals that need adjustment

Total project cost increase: ~$4–10/month on top of existing ~$6–15/month.

---

## What This Does NOT Include (Future Scope)

- **Barcode scanning** — could be added later as an alternative to photos
- **Restaurant menu integration** — not needed for MVP
- **Historical re-estimation** — event immutability supports this but no batch re-run pipeline yet
- **Nutrition goal setting via conversation** — targets are DB defaults for now; a `/targets` command could be added later
- **Weekly nutrition trends** — the data supports it but MVP focuses on daily feedback
