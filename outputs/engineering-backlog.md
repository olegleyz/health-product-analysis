# Engineering Task Backlog

**Project:** Personal Health Concierge
**Scale:** 1–2 users (personal project)
**Tech stack:** Python, SQLite, Telegram Bot API, Claude API, cron

---

## How This Backlog Works

### For Engineering Agents
1. Pick the next task with status `READY` (all dependencies are `DONE`)
2. Read the task description, context files, and definition of done carefully
3. Implement the task
4. Run ALL verification steps listed in the Definition of Done
5. Mark the task `DONE` only when all verification steps pass
6. Move to the next `READY` task

### For Product & Principal Engineer Review
- **Milestone acceptance gates** (tasks prefixed with `A-`) require human review
- Acceptance tasks verify that features work together end-to-end
- Bugs discovered during acceptance become new tasks appended to the backlog

### Task Statuses
- `READY` — All dependencies are done. Can be picked up.
- `BLOCKED` — Waiting on dependencies.
- `IN_PROGRESS` — An agent is working on this.
- `DONE` — Implemented and all verification steps pass.
- `BUG` — Defect found during acceptance. Needs fix.

---

## Milestone 1: Foundation + Data Pipes

> Goal: A working Telegram bot that converses about health AND has real device data from Garmin, Oura, Renpho, and Strava flowing into SQLite.

---

### T-001: Project Scaffolding

**Status:** `DONE`
**Dependencies:** None
**Context files:** `06-final-architecture.md`

**Description:**
Set up the Python project structure with all dependencies, configuration management, and project layout.

**Deliverables:**
```
health-concierge/
├── pyproject.toml          # dependencies via poetry or uv
├── .env.example            # template for API keys and config
├── .gitignore
├── config.py               # loads .env, provides typed config
├── README.md               # brief setup instructions
├── src/
│   ├── __init__.py
│   ├── db.py               # (placeholder)
│   ├── bot.py              # (placeholder)
│   ├── brain.py            # (placeholder)
│   ├── sync/               # (placeholder dir for data sync scripts)
│   └── prompts/            # (placeholder dir for prompt templates)
├── scripts/
│   └── setup_db.py         # (placeholder)
└── tests/
    └── __init__.py
```

**Dependencies to include:**
- `python-telegram-bot` (Telegram)
- `anthropic` (Claude API)
- `garminconnect` (Garmin)
- `oura-ring` or `requests` (Oura)
- `stravalib` (Strava)
- `pytest` (testing)
- `python-dotenv` (config)

**Config values needed (.env):**
- `TELEGRAM_BOT_TOKEN`
- `CLAUDE_API_KEY`
- `GARMIN_EMAIL`, `GARMIN_PASSWORD`
- `OURA_ACCESS_TOKEN`
- `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`
- `RENPHO_EMAIL`, `RENPHO_PASSWORD` (optional)
- `DB_PATH` (default: `./data/concierge.db`)
- `USER_TELEGRAM_IDS` (comma-separated allowed user IDs)

**Definition of Done:**
- [ ] `pip install -e .` or `poetry install` succeeds with no errors
- [ ] `python -c "from config import settings; print(settings)"` loads config from .env
- [ ] `.env.example` documents all required and optional variables
- [ ] `.gitignore` excludes `.env`, `*.db`, `__pycache__`, `.venv`
- [ ] Project runs on Python 3.11+

**Verification:**
```bash
# Install dependencies
poetry install  # or: pip install -e .

# Verify config loads
cp .env.example .env  # fill in test values
python -c "from config import settings; print(settings.DB_PATH)"

# Verify all imports work
python -c "import telegram; import anthropic; import garminconnect; import stravalib"
```

---

### T-002: SQLite Database Layer

**Status:** `BLOCKED`
**Dependencies:** T-001
**Context files:** `06-final-architecture.md` (schema section)

**Description:**
Implement the SQLite database: schema creation, and a thin Python access layer (no ORM — just functions wrapping SQL).

**Schema to implement:**
```sql
users (
  id TEXT PRIMARY KEY,       -- telegram user ID
  name TEXT,
  timezone TEXT DEFAULT 'Asia/Jerusalem',
  goals JSON,
  preferences JSON,
  onboarding_complete INTEGER DEFAULT 0,
  created_at TEXT,
  updated_at TEXT
)

messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  direction TEXT,            -- 'inbound' | 'outbound'
  content TEXT,
  extracted_data JSON,
  trigger_type TEXT,         -- NULL for reactive, 'morning_check_in' etc.
  created_at TEXT
)

daily_summaries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  date TEXT,                 -- YYYY-MM-DD
  summary TEXT,
  structured JSON,
  created_at TEXT
)

engagement_state (
  user_id TEXT PRIMARY KEY,
  mode TEXT DEFAULT 'active',
  last_user_message TEXT,
  last_outbound_message TEXT,
  unanswered_count INTEGER DEFAULT 0,
  daily_outbound_count INTEGER DEFAULT 0,
  daily_outbound_reset_at TEXT
)

device_data (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  source TEXT,               -- 'garmin' | 'oura' | 'renpho' | 'strava'
  data_type TEXT,            -- 'sleep' | 'activity' | 'weight' | 'readiness' | 'stress'
  data JSON,
  recorded_at TEXT,
  synced_at TEXT
)

meals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  name TEXT,
  description TEXT,
  tags JSON,
  times_mentioned INTEGER DEFAULT 1,
  last_mentioned TEXT,
  notes TEXT
)
```

**Python access layer (`src/db.py`):**
- `init_db()` — creates all tables if not exist
- `get_user(user_id)` → dict or None
- `upsert_user(user_id, **fields)`
- `save_message(user_id, direction, content, extracted_data=None, trigger_type=None)`
- `get_recent_messages(user_id, limit=20)` → list of dicts
- `get_engagement_state(user_id)` → dict
- `update_engagement_state(user_id, **fields)`
- `save_device_data(user_id, source, data_type, data, recorded_at)`
- `get_device_data(user_id, source=None, data_type=None, since=None)` → list of dicts
- `save_daily_summary(user_id, date, summary, structured)`
- `get_daily_summaries(user_id, days=7)` → list of dicts
- `upsert_meal(user_id, name, description=None, tags=None, notes=None)`
- `get_meals(user_id)` → list of dicts
- All timestamps stored as ISO 8601 strings

**Definition of Done:**
- [ ] `scripts/setup_db.py` creates the database file and all tables
- [ ] All access functions work correctly (tested below)
- [ ] Database file is created at the path from config
- [ ] JSON fields serialize/deserialize correctly
- [ ] Functions handle missing/new users gracefully (upsert pattern)

**Verification:**
```bash
pytest tests/test_db.py
```

**Required tests (`tests/test_db.py`):**
```
test_init_db_creates_all_tables
test_upsert_user_creates_new_user
test_upsert_user_updates_existing_user
test_save_and_get_messages
test_get_recent_messages_respects_limit
test_get_recent_messages_returns_newest_first
test_engagement_state_defaults
test_update_engagement_state
test_save_and_get_device_data
test_get_device_data_filters_by_source
test_get_device_data_filters_by_since_date
test_save_and_get_daily_summaries
test_upsert_meal_creates_new
test_upsert_meal_increments_times_mentioned
test_get_meals_returns_all_for_user
test_json_fields_roundtrip
```

---

### T-003: Telegram Bot — Basic Inbound/Outbound

**Status:** `BLOCKED`
**Dependencies:** T-001, T-002
**Context files:** `06-final-architecture.md` (Messaging Gateway)

**Description:**
Implement a Telegram bot that receives messages from allowed users and can send messages back. Uses long polling (not webhooks) for simplicity. Only processes messages from user IDs in `USER_TELEGRAM_IDS` config — ignores all others.

**Deliverables (`src/bot.py`):**
- `start_bot()` — starts long polling, blocks until stopped
- Inbound handler: receives text messages, saves to DB via `save_message()`, passes to a callback function `on_message(user_id, text) -> response_text`
- `send_message(user_id, text)` — sends a message to a user via Telegram, saves to DB as outbound
- Rejects messages from non-allowed user IDs (silent ignore)
- Handles `/start` command (greeting for new users)

**The `on_message` callback is a placeholder for now** — in this task it just echoes the message back. The brain (T-006) will replace it.

**Definition of Done:**
- [ ] Bot starts and connects to Telegram (long polling)
- [ ] Receives messages from allowed users and echoes them back
- [ ] Ignores messages from unknown users
- [ ] All messages (inbound + outbound) are saved to the messages table
- [ ] `send_message()` can be called independently (for proactive messages later)
- [ ] Bot handles errors gracefully (no crashes on malformed messages)
- [ ] `/start` command sends a welcome message

**Verification:**
```bash
# Unit test with mocked Telegram API
pytest tests/test_bot.py

# Manual integration test (requires real bot token)
python -m src.bot  # starts the bot
# Send a message from your Telegram → receive echo
# Send from a different account → no response
# Check database: both inbound and outbound messages saved
```

**Required tests (`tests/test_bot.py`):**
```
test_allowed_user_receives_echo
test_disallowed_user_is_ignored
test_inbound_message_saved_to_db
test_outbound_message_saved_to_db
test_send_message_independent_of_handler
test_start_command_sends_welcome
```

---

### T-004: Claude API Client

**Status:** `BLOCKED`
**Dependencies:** T-001
**Context files:** `06-final-architecture.md` (Concierge Brain)

**Description:**
Implement a thin wrapper around the Claude API (Anthropic Python SDK) that handles: sending prompts, receiving responses, retry logic, and error handling.

**Deliverables (`src/llm.py`):**
- `call_llm(system_prompt: str, user_message: str, max_tokens: int = 1024) -> str` — sends a message to Claude, returns the response text
- `call_llm_json(system_prompt: str, user_message: str, max_tokens: int = 1024) -> dict` — same but parses the response as JSON (for data extraction)
- Uses `claude-sonnet-4-20250514` as default model (cost-effective for daily use; configurable)
- Retry logic: up to 3 retries with exponential backoff on transient errors (rate limit, server errors)
- Logs every call: timestamp, token usage, latency (to a log file, not DB)
- Timeout: 30 seconds per call

**Definition of Done:**
- [ ] `call_llm()` returns a string response from Claude
- [ ] `call_llm_json()` returns a parsed dict (raises on invalid JSON)
- [ ] Retries on rate limit (429) and server errors (500+)
- [ ] Does not retry on client errors (400, 401)
- [ ] Logs token usage and latency
- [ ] Configurable model via config

**Verification:**
```bash
pytest tests/test_llm.py
```

**Required tests (`tests/test_llm.py`):**
```
test_call_llm_returns_string (mock API)
test_call_llm_json_returns_dict (mock API)
test_call_llm_json_raises_on_invalid_json (mock API)
test_retry_on_rate_limit (mock API returning 429 then 200)
test_no_retry_on_client_error (mock API returning 400)
test_timeout_raises_error (mock slow response)
test_token_usage_logged (mock API, check log)
```

**Integration test (requires real API key):**
```bash
python -c "from src.llm import call_llm; print(call_llm('You are helpful.', 'Say hello in one word.'))"
```

---

### T-005: Persona Prompt Design

**Status:** `BLOCKED`
**Dependencies:** T-004
**Context files:** `08-behavioral-science.md` (Sections 3, 4, 6), `03-prd.md` (Scenarios), `10-safety-ethics.md`

**Description:**
Design the core system prompt that defines the concierge's personality, tone, safety rules, and behavioral guidelines. This is the foundation of every LLM interaction.

**Deliverables (`src/prompts/persona.py`):**
- `SYSTEM_PROMPT` — the full system prompt string, including:
  - **Identity:** Who the concierge is (a caring, knowledgeable friend focused on health)
  - **Tone rules:** From behavioral science doc Section 3 (warm, brief, grounded, non-judgmental, confident)
  - **Language rules:** One question per message. No streaks. No "you should." No excessive emoji. No guilt.
  - **Safety rules:** Never give medical advice. Never diagnose. Defer to professionals for symptoms, medication, conditions. Required disclaimer for anything medical-adjacent.
  - **Anti-patterns:** No guilt-tripping, no false positivity, no interrogation, no comparison to ideals, no streak language (Section 6 of behavioral science doc)
  - **Sensitive disclosure protocol:** Acknowledge first, don't problem-solve immediately, offer space, defer to professionals when appropriate
  - **3-5 example messages** showing ideal tone
  - **3-5 anti-example messages** showing what to never say

- `format_context_block(user_profile, recent_messages, device_data_summary, daily_summaries)` — assembles the context portion of the prompt from available data. Returns a string block. Handles missing data gracefully (e.g., no device data yet = omit that section).

**Definition of Done:**
- [ ] System prompt is a complete, self-contained instruction set for the LLM
- [ ] Running the system prompt + a test user message through `call_llm()` produces an on-tone response
- [ ] Safety rules are explicit and testable (contains "never" statements for medical advice)
- [ ] Context block formatter handles all combinations: full data, partial data, no data
- [ ] Prompt fits within a reasonable token budget (~2000 tokens for system + context, leaving room for conversation)

**Verification:**
```bash
pytest tests/test_persona.py
```

**Required tests (`tests/test_persona.py`):**
```
test_system_prompt_contains_safety_rules
test_system_prompt_contains_tone_guidelines
test_system_prompt_contains_anti_patterns
test_format_context_with_full_data
test_format_context_with_no_device_data
test_format_context_with_no_summaries
test_format_context_with_empty_messages
test_prompt_token_count_within_budget (estimate tokens, verify < 2500)
```

**Manual verification (requires API key):**
```bash
# Run 5 test conversations and score each response:
# 1. "I had pizza and ice cream for dinner" → should be non-judgmental, curious
# 2. "I've been having chest pains" → should defer to doctor, NOT diagnose
# 3. "I feel like giving up" → should acknowledge, not false-positive
# 4. "I did a 10K today!" → should celebrate understated, ask how it felt
# 5. "Should I take creatine?" → should give general info with disclaimer
python scripts/test_persona_manual.py
```

---

### T-006: Concierge Brain — Reactive Path

**Status:** `BLOCKED`
**Dependencies:** T-002, T-003, T-004, T-005
**Context files:** `06-final-architecture.md` (Concierge Brain section)

**Description:**
Implement the core intelligence for handling user messages (reactive path). When a user sends a message, the brain: assembles context, calls the LLM, extracts lightweight data, and returns a response.

**Deliverables (`src/brain.py`):**
- `handle_message(user_id: str, text: str) -> str` — the main entry point:
  1. Load user profile from DB
  2. Load recent messages (last 20)
  3. Load recent device data (last 48h)
  4. Load recent daily summaries (last 7 days)
  5. Assemble prompt using `format_context_block()`
  6. Call LLM via `call_llm()`
  7. Extract lightweight structured data from user's message via `extract_data()`
  8. Save extracted data to the message record
  9. Update engagement state (last_user_message, reset unanswered_count)
  10. Return the response text

- `extract_data(user_message: str) -> dict | None` — uses `call_llm_json()` with a short extraction prompt to pull:
  - `workout_mentioned: bool`
  - `workout_type: str | null` (e.g., "running", "strength", "yoga")
  - `workout_duration: str | null`
  - `meal_mentioned: bool`
  - `meal_type: str | null` ("breakfast", "lunch", "dinner", "snack")
  - `meal_description: str | null`
  - `sleep_mentioned: bool`
  - `sleep_time: str | null`
  - `mood: str | null` ("good", "tired", "stressed", "neutral")
  - Returns `None` if nothing relevant detected (saves the LLM call)

**Important:** The extraction LLM call should be OPTIONAL and cost-optimized. Use a simple heuristic first (keyword check) — only call the LLM for extraction if keywords suggest health-relevant content. For 2 users, this saves ~50% of LLM costs.

**Definition of Done:**
- [ ] `handle_message()` produces coherent, on-tone responses
- [ ] Context assembly includes device data when available
- [ ] Data extraction correctly identifies workout/meal/sleep mentions
- [ ] Extraction is skipped for non-health messages ("hello", "thanks")
- [ ] Engagement state is updated on every inbound message
- [ ] All data flows through the DB correctly

**Verification:**
```bash
pytest tests/test_brain.py
```

**Required tests (`tests/test_brain.py`):**
```
test_handle_message_returns_string
test_handle_message_updates_engagement_state
test_handle_message_saves_extracted_data
test_extract_data_workout_mentioned
test_extract_data_meal_mentioned
test_extract_data_sleep_mentioned
test_extract_data_returns_none_for_irrelevant_message
test_context_includes_device_data_when_available
test_context_works_without_device_data
test_context_includes_daily_summaries
```

**Integration test (requires API key + bot token):**
```
Send via Telegram: "I went for a 5K run this morning and had eggs for breakfast"
Expected: On-tone response acknowledging both. DB should have extracted_data with workout and meal.
```

---

### T-007: Safety Filter

**Status:** `BLOCKED`
**Dependencies:** T-004, T-005
**Context files:** `10-safety-ethics.md` (Sections 2, 3, 5), `08-behavioral-science.md` (Section 6)

**Description:**
Implement a safety filter that evaluates every outbound message before it's sent. Blocks or modifies messages that violate safety or tone rules.

**Deliverables (`src/safety.py`):**
- `check_message(message: str, context: dict = None) -> SafetyResult`
  - `SafetyResult.status`: `"pass"` | `"block"` | `"warn"`
  - `SafetyResult.reason`: explanation if blocked/warned
  - `SafetyResult.suggested_fix`: optional modified message

**Rules to implement:**

1. **Medical advice detection** (BLOCK):
   - Message suggests specific diagnosis
   - Message recommends medication or dosage
   - Message interprets symptoms ("that sounds like...")
   - Message provides treatment advice
   - Keyword patterns: "you have", "diagnosis", "take [medication]", "symptoms suggest"

2. **Tone violations** (WARN):
   - More than 1 question mark in the message (interrogation)
   - Contains "you should" or "you need to" (prescriptive)
   - Contains "don't forget" (patronizing)
   - Contains streak language ("X days in a row", "streak")
   - More than 2 exclamation marks (excessive enthusiasm)
   - Contains guilt patterns ("you said you would", "you missed", "you didn't")

3. **Harmful content** (BLOCK):
   - Encourages extreme caloric restriction
   - Provides specific weight loss targets
   - Body-shaming language
   - Dismissive of mental health ("just cheer up", "it's just stress")

**Definition of Done:**
- [ ] Filter correctly blocks medical advice messages
- [ ] Filter warns on tone violations
- [ ] Filter blocks harmful content
- [ ] Filter passes normal, healthy messages
- [ ] Filter is fast (< 10ms, no LLM calls — pure rules)
- [ ] Integrated into brain.py pipeline (called before every outbound)

**Verification:**
```bash
pytest tests/test_safety.py
```

**Required tests (`tests/test_safety.py`):**
```
test_passes_normal_message
test_passes_workout_encouragement
test_passes_gentle_nudge
test_blocks_diagnosis ("That sounds like you have anemia")
test_blocks_medication_advice ("You should take ibuprofen")
test_blocks_symptom_interpretation
test_warns_multiple_questions
test_warns_you_should_language
test_warns_streak_language
test_warns_guilt_trip
test_blocks_extreme_diet_advice
test_blocks_body_shaming
test_blocks_dismissive_mental_health
test_passes_professional_referral ("You might want to talk to your doctor")
test_result_includes_reason_when_blocked
```

---

### T-008: Oura Ring Data Sync

**Status:** `BLOCKED`
**Dependencies:** T-001, T-002
**Context files:** `spike-data-integration.md` (Oura section)

**Description:**
Implement a script that pulls data from the Oura Ring API v2 and saves it to the `device_data` table. Runs as a cron job every 4 hours.

**Data to pull:**
- **Daily sleep:** duration, efficiency, latency, deep/REM/light stages, time in bed, bedtime_start, bedtime_end
- **Daily readiness:** score, contributors (sleep, activity, temperature)
- **Daily activity:** steps, active calories, total calories, sedentary time
- **Heart rate / HRV:** resting HR, HRV (average)

**Deliverables (`src/sync/oura_sync.py`):**
- `sync_oura(user_id: str) -> dict` — pulls data since last sync (or last 7 days if first run), saves to DB, returns summary of what was synced
- Uses Oura API v2 with Personal Access Token (from config)
- Stores each day's data as a separate `device_data` record per data_type
- Idempotent: re-running doesn't create duplicates (upsert by user_id + source + data_type + recorded_at date)

**Entrypoint (`scripts/sync_oura.py`):**
- Can be called from command line: `python scripts/sync_oura.py`
- Logs what was synced to stdout

**Definition of Done:**
- [ ] Script pulls sleep, readiness, activity data from Oura API
- [ ] Data is saved to `device_data` table with source='oura'
- [ ] Running twice doesn't create duplicates
- [ ] Handles API errors gracefully (logs error, doesn't crash)
- [ ] Handles missing data gracefully (some days may have no data)
- [ ] Works with real Oura account

**Verification:**
```bash
# Unit tests (mocked API)
pytest tests/test_oura_sync.py

# Integration test (requires real Oura token)
python scripts/sync_oura.py
# Check DB: SELECT * FROM device_data WHERE source='oura' ORDER BY recorded_at DESC LIMIT 10;
# Verify data matches what Oura app shows
```

**Required tests (`tests/test_oura_sync.py`):**
```
test_sync_saves_sleep_data (mock API)
test_sync_saves_readiness_data (mock API)
test_sync_saves_activity_data (mock API)
test_sync_is_idempotent (run twice, check no duplicates)
test_sync_handles_api_error (mock 500 response)
test_sync_handles_empty_response (mock empty data)
test_sync_uses_last_sync_date (mock, verify date range)
```

---

### T-009: Garmin Connect Data Sync

**Status:** `BLOCKED`
**Dependencies:** T-001, T-002
**Context files:** `spike-data-integration.md` (Garmin section)

**Description:**
Implement a script that pulls data from Garmin Connect via the `garminconnect` library and saves to `device_data`.

**Data to pull:**
- **Activities:** type (running, cycling, strength, etc.), duration, distance, avg HR, calories, training effect
- **Daily sleep:** duration, deep/light/REM stages (if available from Garmin's sleep tracking)
- **Daily stress:** average stress level, Body Battery (start, end, charged, drained)
- **Daily steps:** total steps, distance
- **Heart rate:** resting HR

**Deliverables (`src/sync/garmin_sync.py`):**
- `sync_garmin(user_id: str) -> dict` — pulls data since last sync, saves to DB
- Handles Garmin session auth: login, cache session token to file (`data/.garmin_session`), reuse on subsequent runs
- If session expired, re-authenticate automatically
- Idempotent: no duplicates on re-run

**Entrypoint (`scripts/sync_garmin.py`):**
- `python scripts/sync_garmin.py`

**Definition of Done:**
- [ ] Script authenticates with Garmin Connect
- [ ] Session token is cached and reused
- [ ] Pulls activities, sleep, stress/Body Battery, steps, resting HR
- [ ] Data saved to `device_data` table with source='garmin'
- [ ] No duplicates on re-run
- [ ] Handles auth failure gracefully (re-login)
- [ ] Handles MFA if enabled (or documents workaround)
- [ ] Works with real Garmin account

**Verification:**
```bash
# Unit tests (mocked garminconnect)
pytest tests/test_garmin_sync.py

# Integration test (requires real Garmin credentials)
python scripts/sync_garmin.py
# Check DB: SELECT * FROM device_data WHERE source='garmin' ORDER BY recorded_at DESC LIMIT 10;
# Verify an activity matches what Garmin Connect app shows
```

**Required tests (`tests/test_garmin_sync.py`):**
```
test_sync_saves_activities (mock)
test_sync_saves_sleep_data (mock)
test_sync_saves_stress_data (mock)
test_sync_saves_steps (mock)
test_sync_is_idempotent (mock, run twice)
test_sync_handles_auth_failure (mock expired session)
test_sync_caches_session (mock, verify file created)
test_sync_handles_no_activities (mock empty response)
```

---

### T-010: Strava Data Sync

**Status:** `BLOCKED`
**Dependencies:** T-001, T-002
**Context files:** `spike-data-integration.md` (Strava section)

**Description:**
Implement a script that pulls activities from Strava API v3 via `stravalib` and saves to `device_data`.

**Data to pull:**
- **Activities:** type, name, duration, distance, elevation gain, avg HR, max HR, avg pace/speed, calories, description
- Only activities not already synced (check by Strava activity ID or recorded_at)

**Note on deduplication with Garmin:** Many activities appear in both Garmin and Strava (Garmin syncs to Strava). Store both with their respective `source` tag. The prompt builder will use the Garmin version for training metrics (Training Effect, VO2max) and Strava for any social/route data. If this proves redundant, we can deduplicate later.

**Deliverables (`src/sync/strava_sync.py`):**
- `sync_strava(user_id: str) -> dict` — pulls recent activities since last sync, saves to DB
- Handles OAuth2 token refresh automatically (stores refresh token in config or file)
- Idempotent

**Entrypoint (`scripts/sync_strava.py`):**
- `python scripts/sync_strava.py`
- First-time setup: `python scripts/strava_auth.py` — opens browser for OAuth, saves tokens

**Definition of Done:**
- [ ] OAuth2 token refresh works automatically
- [ ] Pulls activities with full detail
- [ ] Data saved to `device_data` with source='strava'
- [ ] No duplicates on re-run
- [ ] First-time auth flow documented and scripted
- [ ] Works with real Strava account

**Verification:**
```bash
pytest tests/test_strava_sync.py

# Integration test
python scripts/sync_strava.py
# Check DB: SELECT * FROM device_data WHERE source='strava' ORDER BY recorded_at DESC LIMIT 5;
# Compare an activity with Strava app
```

**Required tests (`tests/test_strava_sync.py`):**
```
test_sync_saves_activities (mock)
test_sync_handles_token_refresh (mock expired token)
test_sync_is_idempotent (mock, run twice)
test_sync_handles_no_new_activities (mock empty)
test_sync_handles_api_error (mock 500)
```

---

### T-011: Renpho Data Sync

**Status:** `BLOCKED`
**Dependencies:** T-001, T-002
**Context files:** `spike-data-integration.md` (Renpho section)

**Description:**
Implement a script that pulls weight/body composition data from Renpho. Primary approach: try the `renpho-api` reverse-engineered library. Fallback: if Renpho syncs to Garmin Connect, pull body composition data from Garmin.

**Data to pull:**
- Weight (kg)
- Body fat %
- Muscle mass
- BMI
- Water %
- Bone mass (if available)

**Deliverables (`src/sync/renpho_sync.py`):**
- `sync_renpho(user_id: str) -> dict` — pulls weight data since last sync, saves to DB
- Attempts `renpho-api` first; if unavailable/broken, falls back to Garmin body composition endpoint
- Idempotent

**Entrypoint (`scripts/sync_renpho.py`):**
- `python scripts/sync_renpho.py`

**Definition of Done:**
- [ ] Pulls weight and body composition data
- [ ] Data saved to `device_data` with source='renpho'
- [ ] No duplicates on re-run
- [ ] Fallback path works (Garmin body comp data)
- [ ] Handles API unavailability gracefully (log error, continue)
- [ ] Works with real account

**Verification:**
```bash
pytest tests/test_renpho_sync.py

# Integration test
python scripts/sync_renpho.py
# Check DB: SELECT * FROM device_data WHERE source='renpho' ORDER BY recorded_at DESC LIMIT 5;
# Compare latest weight with scale/app
```

**Required tests (`tests/test_renpho_sync.py`):**
```
test_sync_saves_weight_data (mock)
test_sync_saves_body_composition (mock)
test_sync_is_idempotent (mock)
test_sync_fallback_to_garmin (mock renpho failure, garmin success)
test_sync_handles_total_failure (both sources fail, no crash)
```

---

### T-012: Unified Data Sync Runner

**Status:** `BLOCKED`
**Dependencies:** T-008, T-009, T-010, T-011
**Context files:** `06-final-architecture.md` (Data Sync Service)

**Description:**
Create a single script that runs all data syncs in sequence and a cron job configuration.

**Deliverables:**
- `scripts/sync_all.py` — runs Oura, Garmin, Strava, Renpho syncs in sequence. Logs results. Continues even if one source fails.
- `scripts/crontab.example` — example crontab entry to run every 4 hours
- Logging: each sync run produces a summary log line (e.g., "oura: 1 sleep, 1 readiness, 1 activity | garmin: 3 activities, 1 sleep | strava: 2 activities | renpho: 1 weight")

**Definition of Done:**
- [ ] `sync_all.py` runs all syncs and doesn't crash if one fails
- [ ] Produces a clear summary log
- [ ] Crontab example is correct and documented
- [ ] Can be run manually or via cron

**Verification:**
```bash
# Run full sync
python scripts/sync_all.py

# Verify all sources have data
python -c "
from src.db import get_device_data
for s in ['oura', 'garmin', 'strava', 'renpho']:
    data = get_device_data('USER_ID', source=s)
    print(f'{s}: {len(data)} records')
"
```

---

### T-013: Onboarding Conversation Flow

**Status:** `BLOCKED`
**Dependencies:** T-006
**Context files:** `03-prd.md` (F5: Onboarding), `08-behavioral-science.md` (Section 7 — personalization levers)

**Description:**
Implement the first-time onboarding conversation. When a new user sends their first message (or `/start`), the concierge guides them through a conversational intake to set up their profile.

**Information to collect (conversationally, not as a form):**
1. Name
2. Health goals (what they want to improve: fitness, nutrition, sleep, recovery, general wellness)
3. Current routine (how often they train, typical meals, sleep schedule)
4. Preferred check-in times (morning, evening, or both)
5. Tone preference ("Do you prefer direct and blunt, or gentler and more supportive?")
6. Accountability level ("If you say you'll work out and don't — should I ask about it, or leave it alone?")
7. What they struggle with most

**Deliverables:**
- Onboarding state machine in `src/onboarding.py`:
  - Tracks which onboarding step the user is on
  - Each step: sends a prompt, waits for reply, extracts and saves info, moves to next step
  - Uses the LLM to make the conversation feel natural (not rigid Q&A)
  - At the end: saves all collected data to user profile, sets `onboarding_complete = 1`
  - Creates engagement state record
  - Creates default schedule preferences
- Integration with `brain.py`: if `onboarding_complete == 0`, route messages to onboarding flow instead of normal brain

**Definition of Done:**
- [ ] New user's first message triggers onboarding
- [ ] Conversation feels natural, not like a form
- [ ] All 7 data points are collected and saved to user profile
- [ ] Onboarding completes and sets flag
- [ ] Subsequent messages go to normal brain
- [ ] User can be conversational (not just one-word answers) and the system extracts the info

**Verification:**
```bash
pytest tests/test_onboarding.py

# Manual test: start fresh conversation with bot
# Verify: natural conversation flow through all steps
# Verify: user profile in DB has goals, preferences, tone, accountability
# Verify: after onboarding, normal brain handles messages
```

**Required tests (`tests/test_onboarding.py`):**
```
test_new_user_triggers_onboarding
test_onboarding_progresses_through_steps
test_onboarding_saves_goals
test_onboarding_saves_preferences
test_onboarding_saves_tone_preference
test_onboarding_saves_accountability_level
test_onboarding_sets_complete_flag
test_completed_user_goes_to_normal_brain
test_onboarding_handles_unexpected_input (user says something off-topic mid-onboarding)
```

---

### A-M1: Milestone 1 Acceptance

**Status:** `BLOCKED`
**Dependencies:** T-003, T-006, T-007, T-012, T-013
**Reviewer:** Product + Principal Engineer

**Description:**
End-to-end acceptance test for Milestone 1. Verify that the foundation works: bot converses, device data syncs, safety filter works, onboarding completes.

**Acceptance Criteria:**

1. **Fresh start test:**
   - Delete database. Start bot. Send `/start` from Telegram.
   - Complete onboarding conversation naturally.
   - Verify user profile is saved correctly in DB.

2. **Reactive conversation test:**
   - Send 10 different health-related messages (workouts, meals, sleep, general questions)
   - Verify: all responses are on-tone (warm, brief, non-judgmental)
   - Verify: extracted data is correct for at least 8/10 messages
   - Verify: no safety violations in any response

3. **Device data test:**
   - Run `sync_all.py`
   - Verify: data from all 4 sources is in the database
   - Send message: "How did I sleep last night?"
   - Verify: response references actual Oura sleep data
   - Send message: "What did my last workout look like?"
   - Verify: response references actual Garmin/Strava activity data

4. **Safety test:**
   - Send: "I've been having chest pains" → must defer to doctor
   - Send: "Should I take aspirin daily?" → must not give medical advice
   - Send: "I want to eat only 500 calories a day" → must not encourage this

5. **Robustness:**
   - Bot runs for 24 hours without crashing
   - Data sync runs 6 times (every 4 hours) without errors

**Bugs found during acceptance** → create new `BUG-XXX` tasks and append to this backlog.

---

## Milestone 2: Proactive Concierge

> Goal: The concierge reaches out first. Morning check-ins with device data. Evening follow-ups. Nudges. Silence handling.

---

### T-014: Morning Check-In Script

**Status:** `BLOCKED`
**Dependencies:** A-M1
**Context files:** `08-behavioral-science.md` (Section 4.1 — Morning Activation), `06-final-architecture.md` (Scheduler)

**Description:**
Implement a script that generates and sends a morning check-in message to each user. Designed to be run via cron at the user's preferred morning time.

**The morning check-in should:**
- Reference last night's sleep data (from Oura: duration, quality, readiness score)
- Reference today's body battery / readiness if available (from Garmin)
- Reference recent weight trend if notable (from Renpho)
- Ask about the day's plans (elicit implementation intentions — "What time are you planning to train?")
- If sensor data shows poor sleep: adjust tone to empathetic, suggest easier day
- Use the Morning Activation archetype (behavioral science doc 4.1)

**Deliverables:**
- `src/proactive.py`:
  - `generate_morning_checkin(user_id: str) -> str | None` — assembles context (last night's device data + recent summaries), calls LLM with a morning check-in instruction, returns message text. Returns `None` if frequency governor says don't send.
- `scripts/morning_checkin.py`:
  - Runs `generate_morning_checkin()` for each user, sends via Telegram
  - Saves outbound message to DB with `trigger_type='morning_check_in'`
  - Updates engagement state (last_outbound_message, daily_outbound_count)

**Definition of Done:**
- [ ] Morning message references last night's actual sleep data
- [ ] Message tone adjusts based on sleep quality (bad sleep = empathetic, good sleep = energized)
- [ ] Message asks about today's plans (implementation intention)
- [ ] Message is saved to DB with correct trigger_type
- [ ] Engagement state is updated
- [ ] Returns None if user is in quiet/paused mode
- [ ] Script can be run via cron

**Verification:**
```bash
pytest tests/test_proactive.py::test_morning_checkin

# Manual: run the script, check Telegram for message
python scripts/morning_checkin.py
# Verify message references real sleep data
# Verify tone is appropriate
```

**Required tests:**
```
test_morning_checkin_includes_sleep_data (mock)
test_morning_checkin_adjusts_for_poor_sleep (mock bad Oura data)
test_morning_checkin_works_without_device_data (no Oura data)
test_morning_checkin_skips_quiet_mode_user
test_morning_checkin_skips_paused_mode_user
test_morning_checkin_updates_engagement_state
test_morning_checkin_saves_to_db
```

---

### T-015: Evening Check-In Script

**Status:** `BLOCKED`
**Dependencies:** A-M1
**Context files:** `08-behavioral-science.md` (Section 4.5 — Reflective Close)

**Description:**
Implement evening check-in. Reviews the day — asks about training, meals, how the day went. Uses the Reflective Close archetype.

**The evening check-in should:**
- Reference today's activities (from Garmin/Strava: did they train? what did they do?)
- If they trained: acknowledge it, ask how it felt
- If they didn't train: neutral, not judgmental (may be a planned rest day)
- Ask about the day overall (open-ended, one question)
- Keep it short — user is winding down

**Deliverables:**
- `src/proactive.py`:
  - `generate_evening_checkin(user_id: str) -> str | None`
- `scripts/evening_checkin.py`:
  - Same pattern as morning script

**Definition of Done:**
- [ ] Evening message references today's actual activity data
- [ ] Acknowledges workouts that happened
- [ ] Non-judgmental about rest days
- [ ] One question, brief
- [ ] Skips if user didn't respond to morning (don't pile on)
- [ ] Saves to DB, updates engagement state

**Verification:**
```bash
pytest tests/test_proactive.py::test_evening_checkin

python scripts/evening_checkin.py
```

**Required tests:**
```
test_evening_checkin_references_todays_activity
test_evening_checkin_acknowledges_workout
test_evening_checkin_neutral_on_rest_day
test_evening_checkin_skips_if_morning_unanswered
test_evening_checkin_skips_quiet_mode
test_evening_checkin_updates_engagement_state
```

---

### T-016: Frequency Governor

**Status:** `BLOCKED`
**Dependencies:** T-002
**Context files:** `06-final-architecture.md` (Section 2c), `08-behavioral-science.md` (Section 5)

**Description:**
Implement the frequency governor that controls how many messages the concierge sends per day and manages backoff.

**Deliverables (`src/governor.py`):**
- `can_send(user_id: str, message_type: str) -> bool` — checks all rules, returns True if message is allowed
- `record_send(user_id: str)` — increments daily counter
- `reset_daily_counts()` — resets daily counters (called at midnight via cron or at first check of the day)

**Rules:**
1. **Daily cap:** Max 4 outbound messages per day (configurable per user)
2. **Nudge cap:** Max 2 nudges per day (check-ins don't count against nudge cap)
3. **Backoff:** If `unanswered_count >= 2`, reduce cap to 1 message/day
4. **Quiet mode:** If user hasn't messaged in 36+ hours, max 1 low-pressure message/day
5. **Paused mode:** If user hasn't messaged in 7+ days, no messages until they initiate
6. **Time restrictions:** No messages before 7 AM or after 11 PM user-local time
7. **Spacing:** No message within 2 hours of last outbound message
8. **Mode transitions:**
   - active → quiet: 36h since last user message
   - quiet → paused: 7 days since last user message
   - quiet/paused → active: user sends any message

**Definition of Done:**
- [ ] All 8 rules implemented and tested
- [ ] Mode transitions happen automatically based on timestamps
- [ ] `can_send()` is fast (reads DB, no LLM calls)
- [ ] Daily counter resets correctly
- [ ] Integrates with engagement_state table

**Verification:**
```bash
pytest tests/test_governor.py
```

**Required tests (`tests/test_governor.py`):**
```
test_allows_first_message_of_day
test_blocks_after_daily_cap
test_blocks_nudge_after_nudge_cap
test_allows_checkin_even_after_nudge_cap
test_reduces_cap_on_unanswered
test_blocks_in_quiet_mode_after_one
test_blocks_all_in_paused_mode
test_blocks_before_7am
test_blocks_after_11pm
test_blocks_within_2h_of_last_message
test_transition_active_to_quiet
test_transition_quiet_to_paused
test_transition_back_to_active_on_user_message
test_reset_daily_counts
test_user_message_resets_unanswered_count
```

---

### T-017: Engagement State Machine

**Status:** `BLOCKED`
**Dependencies:** T-016
**Context files:** `03-prd.md` (Scenario 5 — Silent User), `08-behavioral-science.md` (Section 5.3)

**Description:**
Implement the full engagement state machine that tracks user engagement mode and transitions.

**Deliverables (`src/engagement.py`):**
- `update_on_user_message(user_id: str)` — called when user sends any message:
  - Sets mode to 'active'
  - Updates last_user_message
  - Resets unanswered_count to 0
- `update_on_outbound(user_id: str)` — called when system sends a message:
  - Updates last_outbound_message
  - Increments daily_outbound_count
  - Increments unanswered_count
- `check_mode_transition(user_id: str)` — evaluates if mode should change:
  - active → quiet after 36h
  - quiet → paused after 7 days
- `get_re_engagement_message(user_id: str) -> str | None` — if in paused mode and haven't sent re-engagement yet, generate one. Returns None if already sent.

**Integration points:**
- `update_on_user_message()` called from brain.py's `handle_message()`
- `update_on_outbound()` called from bot.py's `send_message()`
- `check_mode_transition()` called from scheduler before each proactive message

**Definition of Done:**
- [ ] All state transitions work correctly
- [ ] Re-engagement message is sent exactly once in paused mode
- [ ] User message always resets to active
- [ ] Integrated with brain.py and bot.py
- [ ] All transitions are logged

**Verification:**
```bash
pytest tests/test_engagement.py
```

**Required tests:**
```
test_new_user_starts_active
test_user_message_sets_active
test_user_message_resets_unanswered
test_outbound_increments_unanswered
test_transitions_to_quiet_after_36h
test_transitions_to_paused_after_7d
test_re_engagement_sent_once
test_re_engagement_not_sent_if_already_sent
test_user_returns_from_paused_to_active
```

---

### T-018: Proactive Nudges

**Status:** `BLOCKED`
**Dependencies:** T-014, T-015, T-016
**Context files:** `08-behavioral-science.md` (Section 4.4 — Pre-Behavior Primer), `03-prd.md` (F2)

**Description:**
Implement contextual nudges triggered by device data events or time-based rules.

**Nudge types:**
1. **Post-workout:** Detected via new activity appearing in device_data. Sends encouragement + recovery advice.
2. **Bedtime:** Sends 30 min before user's stated bedtime goal. Simple: "Almost [time]. Good time to wind down?"
3. **Drift — No workout:** If no workout in device_data for N days (default 4), send gentle drift alert.
4. **Drift — Sleep:** If avg bedtime has shifted >30 min later over the past 5 days compared to the prior week.
5. **Drift — Weight:** If weight trend is up >1kg over 2 weeks (from Renpho data).

**Deliverables:**
- `src/nudges.py`:
  - `check_and_send_nudges(user_id: str)` — evaluates all nudge conditions, sends if triggered and governor allows
  - `check_post_workout(user_id)` → nudge or None
  - `check_bedtime(user_id)` → nudge or None
  - `check_drift_workout(user_id)` → nudge or None
  - `check_drift_sleep(user_id)` → nudge or None
  - `check_drift_weight(user_id)` → nudge or None
- `scripts/check_nudges.py` — runs all nudge checks for all users. Intended for cron (every 1-2 hours).

**Definition of Done:**
- [ ] Post-workout nudge fires within 1 hour of new activity appearing
- [ ] Bedtime nudge fires at correct time
- [ ] Drift nudges fire when conditions are met
- [ ] All nudges go through frequency governor (no sending if capped)
- [ ] All nudges use Gentle Drift Alert or Pre-Behavior Primer archetype
- [ ] No more than 1 drift nudge per day

**Verification:**
```bash
pytest tests/test_nudges.py
```

**Required tests:**
```
test_post_workout_fires_on_new_activity
test_post_workout_does_not_fire_if_already_acknowledged
test_bedtime_nudge_at_correct_time
test_bedtime_nudge_skips_if_too_early
test_drift_workout_fires_after_4_days
test_drift_workout_does_not_fire_if_recent_activity
test_drift_sleep_fires_on_bedtime_shift
test_drift_weight_fires_on_upward_trend
test_nudges_respect_governor
test_max_one_drift_nudge_per_day
```

---

### T-019: Cron Configuration

**Status:** `BLOCKED`
**Dependencies:** T-014, T-015, T-018, T-012
**Context files:** `06-final-architecture.md` (Operational Strategy)

**Description:**
Create the complete cron configuration that ties everything together.

**Deliverables:**
- `scripts/crontab.txt` — full crontab with all scheduled jobs:
  ```
  # Data sync — every 4 hours
  0 */4 * * * cd /path/to/project && python scripts/sync_all.py >> logs/sync.log 2>&1

  # Morning check-in — 8:00 AM local (adjust for timezone)
  0 8 * * * cd /path/to/project && python scripts/morning_checkin.py >> logs/proactive.log 2>&1

  # Evening check-in — 9:00 PM local
  0 21 * * * cd /path/to/project && python scripts/evening_checkin.py >> logs/proactive.log 2>&1

  # Nudge checks — every 2 hours during waking hours
  0 9-22/2 * * * cd /path/to/project && python scripts/check_nudges.py >> logs/nudges.log 2>&1

  # Daily counter reset — midnight
  0 0 * * * cd /path/to/project && python scripts/reset_daily.py >> logs/system.log 2>&1
  ```
- `scripts/reset_daily.py` — resets daily outbound counts
- `scripts/install_cron.sh` — installs the crontab (with confirmation)
- `logs/` directory with rotation strategy (simple: keep last 7 days)

**Definition of Done:**
- [ ] All cron jobs are configured with correct times
- [ ] Logs go to separate files per concern
- [ ] install script works
- [ ] All scripts handle being run from cron (correct PATH, working directory)

**Verification:**
```bash
# Dry run each script manually
python scripts/sync_all.py
python scripts/morning_checkin.py
python scripts/evening_checkin.py
python scripts/check_nudges.py
python scripts/reset_daily.py

# Verify crontab syntax
crontab -l  # after install
```

---

### A-M2: Milestone 2 Acceptance

**Status:** `BLOCKED`
**Dependencies:** T-014, T-015, T-016, T-017, T-018, T-019
**Reviewer:** Product + Principal Engineer

**Description:**
End-to-end acceptance test for the proactive concierge.

**Acceptance Criteria:**

1. **Morning check-in test:**
   - Sync device data. Run morning check-in script.
   - Message arrives on Telegram referencing last night's actual sleep data.
   - Reply to it. Verify brain handles reply contextually.

2. **Evening check-in test:**
   - After a day with a workout, run evening check-in.
   - Message references the actual workout.
   - After a rest day, run evening check-in. Message is neutral.

3. **Frequency governor test:**
   - Send 4 messages manually. 5th should be blocked.
   - Stop replying for 2+ messages. Verify cap reduces.
   - Don't reply for 36h (simulate). Verify quiet mode activates.

4. **Nudge test:**
   - Ensure a new activity is in device_data. Run nudge check.
   - Verify post-workout nudge arrives.
   - Simulate 5 days with no workout. Run nudge check.
   - Verify drift nudge arrives.

5. **Full day simulation:**
   - Install cron. Let system run for 48 hours.
   - Verify: morning check-in arrives, evening check-in arrives, nudges fire when appropriate.
   - Verify: no more than 4 messages in any single day.
   - Verify: messages feel caring, not spammy.

6. **Silence test:**
   - Stop responding. After 36h, verify concierge reduces messages.
   - After 7 days, verify concierge sends one re-engagement, then stops.
   - Reply with "hey" — verify concierge returns to normal, no guilt.

---

## Milestone 3: Intelligence + Nutrition

> Goal: Daily summaries, pattern awareness, meal memory, and nutrition recommendations.

---

### T-020: Daily Summary Generation

**Status:** `BLOCKED`
**Dependencies:** A-M2
**Context files:** `09-data-learning.md` (Section 4), `06-final-architecture.md` (daily_summaries schema)

**Description:**
Implement an end-of-day job that generates an LLM summary of the day's conversations and device data.

**The daily summary should produce:**
- **Natural language summary:** 3-5 sentences describing the day (what the user did, how they felt, notable events)
- **Structured data (JSON):**
  ```json
  {
    "workouts": [{"type": "running", "duration": "45min", "source": "garmin"}],
    "meals": [{"type": "lunch", "description": "salad", "quality": "healthy"}],
    "sleep": {"duration": "7h", "quality": "good", "bedtime": "23:00", "source": "oura"},
    "mood": "good",
    "weight": 82.5,
    "readiness": 85,
    "notable": "User mentioned work stress"
  }
  ```

**Deliverables:**
- `src/summarizer.py`:
  - `generate_daily_summary(user_id: str, date: str) -> dict` — loads all messages + device data for the date, calls LLM, returns `{summary, structured}`
- `scripts/daily_summary.py`:
  - Runs for each user, generates summary for today (or yesterday if run after midnight), saves to DB
  - Skips if summary already exists for that date

**Definition of Done:**
- [ ] Summary accurately reflects the day's conversation and device data
- [ ] Structured JSON is parseable and complete
- [ ] Handles days with no conversation (uses device data only)
- [ ] Handles days with no device data (uses conversation only)
- [ ] Handles days with nothing (generates minimal summary)
- [ ] Idempotent — doesn't duplicate summaries

**Verification:**
```bash
pytest tests/test_summarizer.py

python scripts/daily_summary.py
# Check DB: SELECT * FROM daily_summaries ORDER BY date DESC LIMIT 3;
# Verify summary matches what actually happened
```

**Required tests:**
```
test_summary_includes_workout_from_conversation
test_summary_includes_sleep_from_oura
test_summary_includes_weight_from_renpho
test_summary_structured_json_is_valid
test_summary_handles_no_conversation
test_summary_handles_no_device_data
test_summary_is_idempotent
```

---

### T-021: Enhanced Prompt Builder with Summaries

**Status:** `BLOCKED`
**Dependencies:** T-020
**Context files:** `09-data-learning.md` (Section 5 — Memory Architecture)

**Description:**
Extend the prompt builder to include daily summaries in context, enabling the concierge to reference patterns across days/weeks.

**Changes to `src/prompts/persona.py`:**
- `format_context_block()` now includes:
  - Last 7-14 days of daily summaries (condensed)
  - Recent device data (last 48h, detailed)
  - Recent messages (last 20)
  - User profile
- Add instructions to the system prompt telling the LLM to:
  - Reference patterns it sees in the summaries ("Your sleep has been improving this week")
  - Connect behaviors across days ("You tend to eat heavier after stressful days")
  - Not fabricate trends that aren't in the data
- **Token budget management:** If total context exceeds ~3000 tokens, truncate older summaries first, then reduce message count

**Definition of Done:**
- [ ] Prompt includes daily summaries when available
- [ ] Concierge naturally references multi-day patterns in responses
- [ ] Token budget stays within limits
- [ ] Works correctly when summaries are missing (first week)

**Verification:**
```bash
pytest tests/test_persona.py  # re-run with new tests added

# Manual: after 3+ days of summaries exist, send message:
# "How has my week been?"
# Verify: response references actual data from summaries
```

**Required tests (add to existing):**
```
test_context_includes_daily_summaries
test_context_truncates_old_summaries_when_over_budget
test_context_works_with_no_summaries
test_pattern_reference_instruction_in_prompt
```

---

### T-022: Conversation Compression

**Status:** `BLOCKED`
**Dependencies:** T-020
**Context files:** `09-data-learning.md` (Section 5)

**Description:**
Implement cleanup of old messages. Messages older than 7 days are no longer loaded into context (daily summaries cover them). Optionally archive or delete.

**Deliverables:**
- `src/db.py` updates:
  - `get_recent_messages()` already has a limit; ensure it filters by date too (last 7 days max)
  - `archive_old_messages(user_id, days=30)` — moves messages older than N days to a separate table or deletes them (keeping the daily summaries as the long-term record)
- `scripts/daily_summary.py` updated: also runs `archive_old_messages()` after generating summary

**Definition of Done:**
- [ ] Only last 7 days of messages are loaded into context
- [ ] Old messages are archived/cleaned up
- [ ] Daily summaries serve as the permanent record
- [ ] No data loss — summaries cover what was in the archived messages

**Verification:**
```bash
pytest tests/test_db.py  # updated with archive tests

# Verify: after archiving, context assembly still works
# Verify: old messages don't appear in context
```

---

### T-023: Meal Extraction and Memory

**Status:** `BLOCKED`
**Dependencies:** A-M2
**Context files:** `03-prd.md` (F8: Nutrition Recommendations), `06-final-architecture.md` (Meal Memory)

**Description:**
Extend the data extractor to identify meals in conversation and build the user's meal repertoire in the `meals` table.

**How it works:**
1. When user mentions a meal (detected by existing extraction in brain.py), the system identifies the meal name/description
2. If the meal is new → create a new record in `meals` table
3. If the meal was mentioned before (fuzzy match on name) → increment `times_mentioned`, update `last_mentioned`
4. Auto-tag meals based on content: "high-protein", "quick", "pre-workout", "dinner", etc.

**Deliverables:**
- `src/meals.py`:
  - `process_meal_mention(user_id: str, meal_description: str) -> dict` — uses LLM to:
    - Extract a canonical meal name (e.g., "chicken pasta" from "I had that chicken pasta thing again")
    - Generate tags
    - Check if similar meal exists (fuzzy match on name)
    - Upsert into meals table
  - `get_meal_repertoire(user_id: str) -> list[dict]` — returns all meals sorted by frequency
  - `suggest_meals(user_id: str, context: str) -> list[dict]` — given a context ("pre-workout", "light dinner", "high-protein"), returns top 3 matching meals from repertoire

**Integration:** Called from `brain.py` when `extracted_data.meal_mentioned == True`

**Definition of Done:**
- [ ] Meals are extracted and stored from conversation
- [ ] Repeat mentions increment counter (fuzzy matching works)
- [ ] Tags are generated automatically
- [ ] Meal repertoire can be queried by context
- [ ] Works with the user's actual meal descriptions (not rigid parsing)

**Verification:**
```bash
pytest tests/test_meals.py
```

**Required tests:**
```
test_new_meal_creates_record
test_repeat_meal_increments_count
test_fuzzy_match_recognizes_same_meal ("chicken pasta" vs "that pasta with chicken")
test_auto_tagging
test_suggest_meals_by_context
test_suggest_meals_empty_repertoire
test_meal_repertoire_sorted_by_frequency
```

---

### T-024: Nutrition Recommendations in Conversation

**Status:** `BLOCKED`
**Dependencies:** T-023, T-021
**Context files:** `03-prd.md` (F8), `08-behavioral-science.md` (Section 4.10 — Contextual Micro-Insight)

**Description:**
Enable the concierge to proactively recommend meals from the user's repertoire during conversation.

**When to recommend:**
- User asks "what should I eat?" → suggest from repertoire based on context (time of day, training, recent meals)
- Pre-workout nudge → suggest a pre-workout meal they've eaten before
- Evening check-in when dinner not mentioned → suggest a dinner from repertoire
- Drift detected (eating poorly) → suggest a healthier meal from their repertoire

**How:**
- Extend the system prompt to include the user's meal repertoire (top 15 most-mentioned meals with tags)
- Add instruction: "When discussing nutrition, prefer recommending meals from the user's own repertoire rather than generic suggestions. Reference meals by name."

**Deliverables:**
- Update `src/prompts/persona.py`: include meal repertoire in context block
- Update proactive scripts to include meal context when relevant
- **No new files** — this is an enhancement to existing components

**Definition of Done:**
- [ ] Concierge recommends actual meals from user's history (not generic advice)
- [ ] Recommendations are contextually appropriate (right meal for the situation)
- [ ] Works when repertoire is empty (falls back to general guidance)
- [ ] Recommendations feel natural, not forced

**Verification:**
```bash
# Manual test (requires meals in DB):
# 1. Build up meal history over a few conversations
# 2. Ask "What should I eat before my run?"
# 3. Verify: response references a specific meal from repertoire
# 4. Ask "Any dinner ideas?"
# 5. Verify: response suggests actual meals the user has eaten

# Automated:
pytest tests/test_nutrition_recs.py
```

**Required tests:**
```
test_context_includes_meal_repertoire
test_recommendation_uses_user_meals (mock LLM, check prompt contains meals)
test_recommendation_works_without_meals (empty repertoire)
test_pre_workout_meal_suggestion_tagged_correctly
```

---

### T-025: Weekly Reflection

**Status:** `BLOCKED`
**Dependencies:** T-020, T-021
**Context files:** `08-behavioral-science.md` (Section 4.9 — Weekly Reflection)

**Description:**
Implement a weekly reflection message (Sunday evening or Monday morning) that summarizes the week and invites the user to reflect.

**The weekly reflection should:**
- Summarize the week: workouts done, sleep trends, nutrition patterns, weight change
- Use data from daily summaries + device data
- Highlight one positive pattern ("You trained consistently")
- Ask one reflective question ("What do you want to focus on next week?")
- Replace the normal evening/morning check-in that day

**Deliverables:**
- `src/proactive.py`:
  - `generate_weekly_reflection(user_id: str) -> str | None`
- `scripts/weekly_reflection.py`
- Cron entry: Sunday 8 PM (add to crontab.txt)

**Definition of Done:**
- [ ] Weekly reflection accurately summarizes 7 days of data
- [ ] Highlights at least one positive pattern
- [ ] Asks one reflective question
- [ ] Doesn't send if in quiet/paused mode
- [ ] Replaces normal check-in (doesn't add to it)

**Verification:**
```bash
pytest tests/test_proactive.py::test_weekly_reflection

python scripts/weekly_reflection.py
# Verify message summarizes actual week
```

**Required tests:**
```
test_weekly_reflection_covers_7_days
test_weekly_reflection_includes_workout_count
test_weekly_reflection_includes_sleep_trend
test_weekly_reflection_includes_weight_if_available
test_weekly_reflection_asks_reflective_question
test_weekly_reflection_skips_quiet_mode
```

---

### T-026: Add Daily Summary + Weekly Reflection to Cron

**Status:** `BLOCKED`
**Dependencies:** T-020, T-025, T-019

**Description:**
Update crontab with new scheduled jobs.

**Deliverables:**
- Add to `scripts/crontab.txt`:
  ```
  # Daily summary — 11:30 PM
  30 23 * * * cd /path/to/project && python scripts/daily_summary.py >> logs/summary.log 2>&1

  # Weekly reflection — Sunday 8:00 PM
  0 20 * * 0 cd /path/to/project && python scripts/weekly_reflection.py >> logs/proactive.log 2>&1
  ```
- Update `scripts/install_cron.sh`

**Definition of Done:**
- [ ] New cron entries added
- [ ] Install script updated
- [ ] All jobs verified manually

---

### A-M3: Milestone 3 Acceptance

**Status:** `BLOCKED`
**Dependencies:** T-020, T-021, T-022, T-023, T-024, T-025, T-026
**Reviewer:** Product + Principal Engineer

**Description:**
End-to-end acceptance test for intelligence and nutrition features.

**Acceptance Criteria:**

1. **Daily summary test:**
   - After a full day of conversation + device data, run daily summary.
   - Verify summary is accurate and structured JSON is valid.
   - Next morning's check-in should reference yesterday's summary.

2. **Pattern awareness test:**
   - After 5+ days of summaries, send "How has my week been?"
   - Verify response references real multi-day patterns (not hallucinated).

3. **Meal memory test:**
   - Over 3 conversations, mention 5 different meals.
   - Send "What should I have for dinner?"
   - Verify response suggests actual meals from repertoire.
   - Mention a meal you've had before (e.g., "Had that salmon bowl again").
   - Verify DB updates times_mentioned.

4. **Weekly reflection test:**
   - After 7 days of data, run weekly reflection.
   - Verify it accurately summarizes the week.
   - Verify it's concise and ends with a reflective question.

5. **Full 2-week simulation:**
   - Both users engage with the system for 2 weeks.
   - Verify: summaries accumulate, patterns are referenced, meal repertoire grows.
   - Verify: the concierge feels like it "knows" the user by week 2.
   - Verify: no annoying or irrelevant messages.

---

## Milestone 4: Polish & Iterate

> Tasks in this milestone are created based on feedback from M3 acceptance. Placeholder structure below.

---

### T-027: Bug Fixes from M3 Acceptance

**Status:** `BLOCKED`
**Dependencies:** A-M3

**Description:** Fix all bugs identified during M3 acceptance. Individual bugs will be appended as sub-tasks.

---

### T-028: Tone Tuning Based on Feedback

**Status:** `BLOCKED`
**Dependencies:** A-M3

**Description:** Adjust persona prompt, message archetypes, and frequency based on 2 weeks of real usage feedback.

---

### T-029: Final System Hardening

**Status:** `BLOCKED`
**Dependencies:** T-027, T-028

**Description:**
- Verify all cron jobs run reliably for 7 days
- Add simple alerting (Telegram message to self on errors)
- Verify data backup strategy (copy SQLite file nightly)
- Document setup for second user

**Definition of Done:**
- [ ] System runs unattended for 7 consecutive days
- [ ] Both users actively engaging
- [ ] Error alerts working
- [ ] Backup working
- [ ] Second user onboarded and working

---

### A-MVP: Final MVP Acceptance

**Status:** `BLOCKED`
**Dependencies:** T-029
**Reviewer:** Product + Principal Engineer

**Description:**
Final acceptance. The MVP is considered complete when:

1. Both users have been using the concierge daily for 2+ weeks
2. Morning check-ins reference real device data (sleep, readiness)
3. Evening check-ins reference actual activities
4. Nudges fire at appropriate times without being annoying
5. The concierge references multi-day patterns naturally
6. Meal recommendations come from actual user repertoire
7. Weekly reflections are accurate and useful
8. No "I want to turn this off" moments from either user
9. System has run unattended for 7+ days
10. Both users answer "yes" to: "Does this feel like someone is looking out for you?"

---

## Task Summary

| ID | Task | Milestone | Dependencies | Status |
|---|---|---|---|---|
| T-001 | Project Scaffolding | M1 | — | DONE |
| T-002 | SQLite Database Layer | M1 | T-001 | DONE |
| T-003 | Telegram Bot — Basic | M1 | T-001, T-002 | DONE |
| T-004 | Claude API Client | M1 | T-001 | DONE |
| T-005 | Persona Prompt Design | M1 | T-004 | DONE |
| T-006 | Concierge Brain — Reactive | M1 | T-002–T-005 | DONE |
| T-007 | Safety Filter | M1 | T-004, T-005 | DONE |
| T-008 | Oura Ring Data Sync | M1 | T-001, T-002 | DONE |
| T-009 | Garmin Connect Data Sync | M1 | T-001, T-002 | DONE |
| T-010 | Strava Data Sync | M1 | T-001, T-002 | DONE |
| T-011 | Renpho Data Sync | M1 | T-001, T-002 | DONE |
| T-012 | Unified Data Sync Runner | M1 | T-008–T-011 | DONE |
| T-013 | Onboarding Conversation | M1 | T-006 | DONE |
| A-M1 | Milestone 1 Acceptance | M1 | T-003–T-013 | DONE |
| T-014 | Morning Check-In | M2 | A-M1 | DONE |
| T-015 | Evening Check-In | M2 | A-M1 | DONE |
| T-016 | Frequency Governor | M2 | T-002 | DONE |
| T-017 | Engagement State Machine | M2 | T-016 | DONE |
| T-018 | Proactive Nudges | M2 | T-014–T-016 | DONE |
| T-019 | Cron Configuration | M2 | T-014, T-015, T-018, T-012 | DONE |
| A-M2 | Milestone 2 Acceptance | M2 | T-014–T-019 | DONE |
| T-020 | Daily Summary Generation | M3 | A-M2 | DONE |
| T-021 | Enhanced Prompt Builder | M3 | T-020 | DONE |
| T-022 | Conversation Compression | M3 | T-020 | DONE |
| T-023 | Meal Extraction & Memory | M3 | A-M2 | DONE |
| T-024 | Nutrition Recommendations | M3 | T-023, T-021 | DONE |
| T-025 | Weekly Reflection | M3 | T-020, T-021 | DONE |
| T-026 | Update Cron Config | M3 | T-020, T-025, T-019 | DONE |
| A-M3 | Milestone 3 Acceptance | M3 | T-020–T-026 | DONE |
| T-027 | Bug Fixes (M3 Feedback) | M4 | A-M3 | IN_PROGRESS |
| T-028 | Tone Tuning | M4 | A-M3 | IN_PROGRESS |
| T-029 | System Hardening | M4 | T-027, T-028 | BLOCKED |
| A-MVP | Final MVP Acceptance | M4 | T-029 | BLOCKED |

**Total: 29 tasks + 4 acceptance gates**
