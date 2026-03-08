# Milestone 1 Demo Report — Foundation + Data Pipes

**Date:** 2026-03-08
**Milestone:** M1 — Foundation + Data Pipes
**Status:** PASS

---

## What Was Built

13 tasks completed across 5 waves:

| Wave | Tasks | Tests |
|------|-------|-------|
| W1 | T-001 Project Scaffolding | - |
| W2 | T-002 SQLite DB, T-004 Claude API Client | 23 |
| W3 | T-003 Telegram Bot, T-005 Persona, T-008 Oura, T-009 Garmin, T-010 Strava, T-011 Renpho | 42 |
| W4 | T-006 Brain, T-007 Safety Filter, T-012 Sync Runner, T-016 Governor | 55 |
| W5 | T-013 Onboarding, T-017 Engagement | 22 |

**Total: 142 tests, all passing.**

---

## Acceptance Criteria Verification

### 1. Project Structure
- `health-concierge/` with proper Python package structure
- `pyproject.toml` with all dependencies (telegram, anthropic, garminconnect, stravalib, etc.)
- `config.py` loading from `.env` with typed settings
- `pip install -e .` works, all imports succeed

### 2. Database Layer (T-002)
- 6 tables: users, messages, daily_summaries, engagement_state, device_data, meals
- 14 access functions with parameterized SQL
- JSON fields serialize/deserialize correctly
- 16 tests covering all CRUD operations

### 3. Telegram Bot (T-003)
- Long polling with python-telegram-bot v22
- Allow-list filtering by user_telegram_ids
- Inbound/outbound message persistence
- Independent `send_message()` for proactive use
- `/start` command handling
- 7 tests

### 4. Claude API Client (T-004)
- `call_llm()` and `call_llm_json()` with retry logic
- Exponential backoff on rate limits (429) and server errors (500+)
- No retry on client errors (400, 401)
- Token usage and latency logging
- 7 tests

### 5. Persona Prompt (T-005)
- Complete system prompt with identity, tone rules, safety rules, anti-patterns
- 5 example messages, 5 anti-examples
- `format_context_block()` handles all data combinations gracefully
- Estimated ~1500 tokens, within budget
- 10 tests

### 6. Concierge Brain (T-006)
- `handle_message()` assembles full context (profile, messages, device data, summaries)
- Cost-optimized `extract_data()` with keyword heuristic pre-filter
- Extracts workout, meal, sleep, mood from user messages
- Updates engagement state on every inbound message
- 12 tests

### 7. Safety Filter (T-007)
- Rule-based, <10ms, no LLM calls
- Blocks: medical advice, symptom interpretation, medication recommendations
- Warns: multiple questions, "you should", streak language, guilt patterns
- Blocks: extreme diets, body-shaming, dismissive mental health
- Handles edge cases (professional referrals pass, "take a walk" passes)
- 23 tests

### 8. Data Syncs (T-008 through T-012)
- **Oura:** Sleep, readiness, activity via API v2 + PAT (7 tests)
- **Garmin:** Activities, sleep, stress, steps, HR via garminconnect with session caching (8 tests)
- **Strava:** Activities via stravalib with OAuth2 token refresh (5 tests)
- **Renpho:** Weight/body comp via reverse-engineered API with Garmin fallback (5 tests)
- **Sync Runner:** Runs all 4, continues on failure, summary logging (2 tests)
- All syncs are idempotent (no duplicates on re-run)

### 9. Frequency Governor (T-016)
- 7 rules: daily cap, nudge cap, backoff, quiet/paused mode, time restrictions, spacing
- Mode transitions: active→quiet (36h), quiet→paused (7d), back to active on user message
- 18 tests

### 10. Engagement State Machine (T-017)
- Tracks user engagement mode and transitions
- Re-engagement message sent once in paused mode
- All transitions logged
- 9 tests

### 11. Onboarding (T-013)
- 7-step conversational flow (name, goals, routine, times, tone, accountability, struggles)
- LLM-driven extraction — feels natural, not like a form
- Saves all data to user profile
- Routes to normal brain after completion
- 13 tests (9 onboarding + 4 brain integration)

---

## Test Summary

```
142 passed in 1.08s
```

All tests run with mocked external APIs (Telegram, Claude, Garmin, Oura, Strava, Renpho).

---

## Items for Stakeholder Review

1. **No git remote configured** — all work is local. Need to add GitHub remote before M2.
2. **Manual integration testing needed** — requires real API keys/tokens for Telegram, Claude, Oura, Garmin, Strava.
3. **Safety filter edge cases** — may need tuning after real conversation testing.

---

## Recommendation

**PASS** — All M1 deliverables are complete. Foundation is solid for M2 (Proactive Concierge).
