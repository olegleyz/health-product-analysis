# Nutrition Ledger — Engineering Backlog

## Overview

9 implementation tasks + 1 acceptance gate, organized into 5 waves. Each task follows TDD: write failing tests first, then implement until tests pass. All tasks reference the architecture at `outputs/nutrition-ledger-architecture.md`.

Task ID prefix: **NL-** (Nutrition Ledger), to distinguish from existing T-series tasks.

---

## Milestone NL: Nutrition Ledger MVP

**Goal:** Users can photograph meals, receive AI nutritional estimates, confirm or correct them, and see daily nutrition summaries with qualitative feedback. Integrated into the existing concierge's proactive check-ins.

---

### Wave 1 — Foundation

---

### NL-001: Nutrition Database Schema + Access Functions

**Status:** READY
**Dependencies:** None
**Context files:** `outputs/nutrition-ledger-architecture.md`, `src/db.py`, `tests/conftest.py`

**Description:**
Add `nutrition_events` and `nutrition_targets` tables to the SQLite schema. Implement thin access functions following the existing db.py patterns: parameterized SQL, JSON serialization, `_rows_to_dicts` helpers.

**Deliverables:**
- `src/db.py`: Add table creation to `init_db()`, plus functions:
  - `save_nutrition_event(user_id, meal_name, components, calories, protein_g, carbs_g, fat_g, weight_g, confidence, model_version, assumptions, image_file_id, user_corrections) → int`
  - `get_nutrition_events(user_id, date) → list[dict]`
  - `get_nutrition_targets(user_id) → dict`
  - `upsert_nutrition_targets(user_id, **fields) → None`
- `tests/test_nutrition_db.py`: All required tests

**Definition of Done:**
- [ ] `nutrition_events` table created by `init_db()`
- [ ] `nutrition_targets` table created by `init_db()`
- [ ] `save_nutrition_event` inserts a record and returns its ID
- [ ] `get_nutrition_events` filters by user and calendar date, deserializes JSON fields
- [ ] `get_nutrition_targets` returns defaults when no record exists
- [ ] `upsert_nutrition_targets` creates or updates targets
- [ ] No update/delete functions for `nutrition_events` (append-only)
- [ ] All JSON fields (components, assumptions, user_corrections) round-trip correctly
- [ ] Full test suite passes (`pytest`) — no regressions

**Verification:**
```bash
.venv/bin/python -m pytest tests/test_nutrition_db.py -v
.venv/bin/python -m pytest tests/ -q  # no regressions
```

**Required tests (`tests/test_nutrition_db.py`):**
```
test_nutrition_events_table_created
test_save_nutrition_event_returns_id
test_save_nutrition_event_stores_all_fields
test_get_nutrition_events_filters_by_date
test_get_nutrition_events_empty_date
test_get_nutrition_events_deserializes_json
test_nutrition_targets_defaults
test_upsert_nutrition_targets_creates
test_upsert_nutrition_targets_updates
test_nutrition_targets_preserves_unset_fields
```

---

### NL-002: Claude Vision API Integration

**Status:** READY
**Dependencies:** None
**Context files:** `outputs/nutrition-ledger-architecture.md`, `src/llm.py`, `tests/test_llm.py`

**Description:**
Add `call_llm_vision` and `call_llm_vision_json` to the LLM module. These send image+text content to the Claude messages API using base64-encoded image blocks, with the same retry logic and client singleton as the existing `call_llm`.

**Deliverables:**
- `src/llm.py`: Add functions:
  - `call_llm_vision(system_prompt, image_data, media_type, text_hint, max_tokens) → str`
  - `call_llm_vision_json(system_prompt, image_data, media_type, text_hint, max_tokens) → dict`
- `tests/test_llm_vision.py`: All required tests

**Definition of Done:**
- [ ] `call_llm_vision` sends image as base64 content block + text hint
- [ ] `call_llm_vision` uses the same model, client, and retry logic as `call_llm`
- [ ] `call_llm_vision` handles empty text_hint gracefully (omits text block or sends empty)
- [ ] `call_llm_vision_json` parses JSON response, strips markdown fences
- [ ] `call_llm_vision_json` raises `ValueError` on invalid JSON
- [ ] Retries on rate limit and 5xx errors (same as `call_llm`)
- [ ] Full test suite passes — no regressions

**Verification:**
```bash
.venv/bin/python -m pytest tests/test_llm_vision.py -v
.venv/bin/python -m pytest tests/ -q
```

**Required tests (`tests/test_llm_vision.py`):**
```
test_call_llm_vision_sends_image_content_block
test_call_llm_vision_includes_text_hint
test_call_llm_vision_empty_text_hint
test_call_llm_vision_retries_on_rate_limit
test_call_llm_vision_retries_on_server_error
test_call_llm_vision_no_retry_on_client_error
test_call_llm_vision_json_parses_response
test_call_llm_vision_json_strips_markdown_fences
test_call_llm_vision_json_raises_on_invalid_json
```

---

### Wave 2 — Core Pipeline

---

### NL-003: Nutrition Estimation Pipeline

**Status:** BLOCKED
**Dependencies:** NL-001, NL-002
**Context files:** `outputs/nutrition-ledger-architecture.md`, `src/llm.py`, `src/meals.py`

**Description:**
Create `src/nutrition.py` with the `estimate_meal` function that sends a meal photo to Claude Vision and returns a structured nutritional estimation. Includes the estimation system prompt with guidelines for conservative estimation, component-level breakdown, and confidence scoring.

**Deliverables:**
- `src/nutrition.py`: Module with:
  - `ESTIMATION_PROMPT` — system prompt for nutrition estimation
  - `estimate_meal(image_data, media_type, text_hint) → dict` — returns structured estimation
  - `format_estimation_message(estimation) → str` — formats estimation for Telegram display
- `tests/test_nutrition.py`: All required tests

**Definition of Done:**
- [ ] `estimate_meal` calls `call_llm_vision_json` with proper prompt and image
- [ ] Returns dict with: meal_name, components, totals (calories, protein_g, carbs_g, fat_g, weight_g), confidence, assumptions
- [ ] `format_estimation_message` produces a readable Telegram message with macros and confidence
- [ ] System prompt enforces JSON-only output, conservative estimation, explicit assumptions
- [ ] Handles text hints (e.g., "this is my lunch, chicken with rice")
- [ ] Full test suite passes — no regressions

**Verification:**
```bash
.venv/bin/python -m pytest tests/test_nutrition.py -v
.venv/bin/python -m pytest tests/ -q
```

**Required tests (`tests/test_nutrition.py`):**
```
test_estimate_meal_calls_vision_api
test_estimate_meal_returns_required_fields
test_estimate_meal_passes_text_hint
test_estimate_meal_prompt_requests_json
test_estimate_meal_prompt_requests_confidence
test_format_estimation_shows_meal_name
test_format_estimation_shows_macros
test_format_estimation_shows_confidence
```

---

### NL-004: Telegram Photo Handler + Confirm/Edit UX

**Status:** BLOCKED
**Dependencies:** NL-003
**Context files:** `outputs/nutrition-ledger-architecture.md`, `src/bot.py`, `tests/test_bot.py`

**Description:**
Add photo message handling to the Telegram bot: receive photos, run estimation, display result with inline keyboard (Confirm / Edit / Discard), handle callback queries. Manage pending estimations in memory.

**Deliverables:**
- `src/bot.py`: Add:
  - `_handle_photo(update, context)` — photo message handler
  - `_handle_callback(update, context)` — callback query handler for inline buttons
  - `_pending: dict[str, dict]` — in-memory pending estimation store
  - Register PhotoHandler and CallbackQueryHandler in `start_bot()`
- `tests/test_nutrition_bot.py`: All required tests

**Definition of Done:**
- [ ] Photo messages trigger estimation pipeline and return formatted result with inline keyboard
- [ ] Inline keyboard has three buttons: ✓ Confirm, ✏️ Edit, ✗ Discard
- [ ] Confirm callback stores nutrition event via `db.save_nutrition_event` and updates meal repertoire
- [ ] Confirm callback replies with daily totals update
- [ ] Edit callback sets correction mode and prompts user for changes
- [ ] Discard callback clears pending estimation and acknowledges
- [ ] Non-allowed users are rejected (same as existing text handler)
- [ ] Photo caption used as text hint for estimation
- [ ] Full test suite passes — no regressions

**Verification:**
```bash
.venv/bin/python -m pytest tests/test_nutrition_bot.py -v
.venv/bin/python -m pytest tests/ -q
```

**Required tests (`tests/test_nutrition_bot.py`):**
```
test_photo_triggers_estimation
test_photo_response_includes_inline_keyboard
test_photo_caption_used_as_hint
test_confirm_callback_stores_event
test_confirm_callback_updates_meal_repertoire
test_confirm_callback_shows_daily_totals
test_edit_callback_sets_correction_mode
test_edit_callback_prompts_for_changes
test_discard_callback_clears_pending
test_non_allowed_user_rejected
```

---

### Wave 3 — Correction & Aggregation

---

### NL-005: Correction Loop with Re-estimation

**Status:** BLOCKED
**Dependencies:** NL-004
**Context files:** `outputs/nutrition-ledger-architecture.md`, `src/nutrition.py`

**Description:**
Implement the correction flow: when a user edits an estimation, their natural-language correction is sent back to Claude along with the original estimation and image. Claude re-estimates respecting the correction as a constraint. The updated estimation replaces the pending one.

**Deliverables:**
- `src/nutrition.py`: Add:
  - `re_estimate_meal(image_data, media_type, original_estimation, corrections) → dict`
  - `CORRECTION_PROMPT` — system prompt for constrained re-estimation
- `src/bot.py`: Route text messages to correction flow when correction mode is active
- `tests/test_nutrition_correction.py`: All required tests

**Definition of Done:**
- [ ] `re_estimate_meal` sends original estimation + corrections + image to Claude Vision
- [ ] Corrections are treated as constraints (e.g., "smaller portion" → reduced weights)
- [ ] Re-estimation returns the same structured format as `estimate_meal`
- [ ] Bot routes text messages to correction flow when `_pending[user_id]["awaiting_correction"]` is True
- [ ] After re-estimation, user sees updated result with Confirm/Edit/Discard buttons again
- [ ] Multiple correction rounds supported (user can edit again)
- [ ] Full test suite passes — no regressions

**Verification:**
```bash
.venv/bin/python -m pytest tests/test_nutrition_correction.py -v
.venv/bin/python -m pytest tests/ -q
```

**Required tests (`tests/test_nutrition_correction.py`):**
```
test_re_estimate_sends_original_and_corrections
test_re_estimate_includes_image
test_re_estimate_returns_structured_format
test_correction_mode_routes_text_to_re_estimate
test_correction_clears_awaiting_flag
test_correction_shows_updated_estimation
test_multiple_correction_rounds
```

---

### NL-006: Daily Nutrition Aggregation + Qualitative Status

**Status:** BLOCKED
**Dependencies:** NL-001
**Context files:** `outputs/nutrition-ledger-architecture.md`, `src/nutrition.py`

**Description:**
Implement daily aggregation that sums all nutrition events for a date and compares against user targets. Compute qualitative status (low/adequate/high) for each macro dimension.

**Deliverables:**
- `src/nutrition.py`: Add:
  - `get_daily_nutrition(user_id, date) → dict` — aggregated daily state
  - `get_qualitative_status(value, target) → str` — returns "low", "adequate", or "high"
  - `format_daily_summary(daily_nutrition) → str` — Telegram-formatted daily summary
- `tests/test_nutrition_aggregation.py`: All required tests

**Definition of Done:**
- [ ] `get_daily_nutrition` sums calories, protein_g, carbs_g, fat_g across all events for a date
- [ ] Includes meals_count and list of individual meals
- [ ] Compares totals against targets from `get_nutrition_targets`
- [ ] Computes qualitative status for each dimension
- [ ] `get_qualitative_status` returns "low" at <70%, "adequate" at 70–130%, "high" at >130%
- [ ] `format_daily_summary` produces readable Telegram text with totals, targets, and status
- [ ] Handles empty days (zero meals) gracefully
- [ ] Full test suite passes — no regressions

**Verification:**
```bash
.venv/bin/python -m pytest tests/test_nutrition_aggregation.py -v
.venv/bin/python -m pytest tests/ -q
```

**Required tests (`tests/test_nutrition_aggregation.py`):**
```
test_daily_nutrition_sums_multiple_meals
test_daily_nutrition_empty_day
test_daily_nutrition_includes_targets
test_daily_nutrition_includes_qualitative_status
test_qualitative_status_low
test_qualitative_status_adequate
test_qualitative_status_high
test_qualitative_status_boundary_low
test_qualitative_status_boundary_high
test_format_daily_summary_includes_totals
test_format_daily_summary_includes_status
test_format_daily_summary_empty_day
```

---

### Wave 4 — User-Facing Commands

---

### NL-007: `/today` Command + Nutrition Context in Conversations

**Status:** BLOCKED
**Dependencies:** NL-006
**Context files:** `outputs/nutrition-ledger-architecture.md`, `src/bot.py`, `src/brain.py`, `src/prompts/persona.py`

**Description:**
Add a `/today` command that returns the current daily nutrition summary. Also integrate nutrition context into the brain's conversation context so the concierge is aware of what the user has eaten when responding to general messages.

**Deliverables:**
- `src/bot.py`: Add `/today` command handler
- `src/brain.py`: Load and include nutrition summary in context block
- `src/prompts/persona.py`: Add `nutrition_summary` parameter to `format_context_block`
- `tests/test_nutrition_command.py`: All required tests

**Definition of Done:**
- [ ] `/today` command returns formatted daily nutrition summary
- [ ] `/today` shows totals, targets, qualitative status, and meal list
- [ ] `/today` on empty day shows "No meals logged today"
- [ ] Brain includes today's nutrition summary in LLM context
- [ ] `format_context_block` accepts and formats optional `nutrition_summary`
- [ ] Full test suite passes — no regressions

**Verification:**
```bash
.venv/bin/python -m pytest tests/test_nutrition_command.py -v
.venv/bin/python -m pytest tests/ -q
```

**Required tests (`tests/test_nutrition_command.py`):**
```
test_today_command_returns_summary
test_today_command_empty_day
test_today_command_includes_qualitative_status
test_brain_includes_nutrition_context
test_context_block_includes_nutrition_summary
test_context_block_omits_nutrition_when_empty
```

---

### Wave 5 — Proactive Integration

---

### NL-008: Proactive Nutrition Feedback in Check-ins

**Status:** BLOCKED
**Dependencies:** NL-007
**Context files:** `outputs/nutrition-ledger-architecture.md`, `src/proactive.py`, `src/summarizer.py`

**Description:**
Integrate nutrition state into the concierge's proactive messages. Evening check-ins include today's nutrition context. Daily summaries include nutrition totals in structured data. The concierge can naturally suggest meals from the repertoire when protein is low.

**Deliverables:**
- `src/proactive.py`: Load nutrition state in `generate_evening_checkin` context
- `src/summarizer.py`: Include nutrition totals in daily summary structured data
- `tests/test_nutrition_proactive.py`: All required tests

**Definition of Done:**
- [ ] Evening check-in prompt includes today's nutrition state
- [ ] Daily summary structured JSON includes nutrition totals when meals were logged
- [ ] No nutrition section in proactive messages when no meals logged that day
- [ ] Full test suite passes — no regressions

**Verification:**
```bash
.venv/bin/python -m pytest tests/test_nutrition_proactive.py -v
.venv/bin/python -m pytest tests/ -q
```

**Required tests (`tests/test_nutrition_proactive.py`):**
```
test_evening_checkin_includes_nutrition_context
test_evening_checkin_no_nutrition_when_no_meals
test_daily_summary_includes_nutrition
test_daily_summary_no_nutrition_when_no_meals
```

---

### Wave 6 — Acceptance

---

### A-NL: Nutrition Ledger Acceptance Gate

**Status:** BLOCKED
**Dependencies:** NL-001 through NL-008

**Description:**
Verify the complete Nutrition Ledger feature end-to-end. All acceptance criteria must pass.

**Acceptance Criteria:**
- [ ] Send a meal photo → receive estimation with macros and confidence
- [ ] Confirm estimation → event stored, daily totals updated
- [ ] Edit estimation → correction applied, re-estimation returned
- [ ] Discard estimation → acknowledged, nothing stored
- [ ] `/today` returns accurate daily summary with qualitative status
- [ ] Evening check-in naturally references nutrition when meals were logged
- [ ] Daily summary includes nutrition data
- [ ] No regressions in existing 242+ tests
- [ ] Multiple meals in a day aggregate correctly
- [ ] Correction loop handles multiple rounds
- [ ] Non-allowed users cannot submit photos
- [ ] Bot handles poor-quality or ambiguous photos gracefully (confidence score reflects uncertainty)

---

## Wave Summary

| Wave | Tasks | Description |
|------|-------|-------------|
| W1 | NL-001, NL-002 | DB schema + Vision API (parallel) |
| W2 | NL-003, NL-004 | Estimation pipeline + Telegram UX (sequential: NL-003 → NL-004) |
| W3 | NL-005, NL-006 | Correction loop + Aggregation (parallel after W2 / W1) |
| W4 | NL-007 | /today command + brain context |
| W5 | NL-008 | Proactive integration |
| W6 | A-NL | Acceptance gate |

---

## TDD Protocol

Every task follows this sequence:
1. **Write tests first.** Create the test file with all required tests. Tests reference the expected function signatures and behaviors.
2. **Run tests — they should fail.** This confirms the tests are testing the right things and not accidentally passing.
3. **Implement the code.** Write the minimum code to make tests pass.
4. **Run tests — they should pass.** All required tests green.
5. **Run full suite.** `pytest tests/ -q` — no regressions in existing 242+ tests.
6. **Commit.** `NL-{number}: {description}` with Co-Authored-By trailer.
