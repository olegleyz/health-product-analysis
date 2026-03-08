# 06 — Final Architecture Specification

**Agent:** Final Architecture Agent

---

## Scope & Philosophy

**This system serves 1–2 users. It is a personal project, not a scalable service.**

This means:
- No cloud infrastructure required — can run on a Mac or a single cheap VPS
- No need for horizontal scaling, load balancing, or multi-tenant architecture
- SQLite instead of PostgreSQL is fine
- Scripts can run as cron jobs on the local machine
- Authentication is trivial (hardcoded user IDs)
- Data integrations can use unofficial Python libraries and personal API tokens

---

## Design Decisions

| Decision | Resolution |
|---|---|
| Scale | **1–2 users. Personal project.** No cloud infra needed. |
| Intelligence | **Unified "Concierge Brain"** — single Python process, two input paths (reactive + proactive). |
| Channel | **Telegram.** Simple bot API, no business verification, no 24-hour window. |
| Data integrations | **Day 1.** Garmin (garminconnect lib), Oura (API), Renpho (reverse-engineered/Apple Health), Strava (API). Automated scripts, no manual export. |
| Data extraction | **Hybrid.** Lightweight real-time extraction for key signals. Daily LLM summaries for nuanced analysis. |
| Pattern detection | **LLM reasoning in context.** No pre-computed patterns. LLM receives recent summaries + device data and reasons at generation time. |
| Nutrition | **In scope.** Concierge remembers meals, builds a repertoire, recommends from user's own meals. |
| Storage | **SQLite.** Single file database. More than enough for 2 users. |
| Deployment | **Single Python process** on a Mac, Raspberry Pi, or cheap VPS. Cron for scheduled tasks. |

---

## Services / Components

### 1. Messaging Gateway
**Purpose:** Abstracts messaging channels. Routes inbound messages to the Concierge Brain. Sends outbound messages to users.

**Interface:**
```
InboundMessage {
  user_id: string
  channel: telegram | whatsapp
  text: string
  timestamp: datetime
  media: optional[attachment]
}

OutboundMessage {
  user_id: string
  text: string
  reply_markup: optional[buttons/quick_replies]
}
```

**Implementation:**
- Telegram Bot API webhook receiver (v1)
- WhatsApp Cloud API webhook receiver (v2)
- Outbound sender with delivery tracking
- Channel-specific formatting adapters

**Technology:** Python script using python-telegram-bot library. Runs as a long-running process or via webhook on a simple server.

---

### 2. Concierge Brain
**Purpose:** The core intelligence. Handles all message generation — reactive and proactive.

**Input paths:**
1. **Reactive:** User sent a message → process and respond
2. **Proactive:** Scheduler fired a check-in or nudge trigger → generate and send
3. **Data event:** New sensor data arrived → evaluate and optionally engage

**Pipeline (all paths converge here):**
```
1. Load user context (profile, engagement state, recent conversations, daily summaries)
2. Determine intent:
   - Reactive: understand user message, extract data
   - Proactive: determine appropriate check-in/nudge content
3. Assemble prompt:
   - System prompt (persona, tone, safety rules)
   - User context block
   - Current trigger/message
4. Call LLM (Claude API)
5. Post-process:
   - Safety filter (block medical advice, check tone)
   - Frequency governor (enforce daily caps, backoff rules)
   - Extract lightweight structured data (workout: yes/no, meal mentioned, sleep time)
6. If approved: send via Messaging Gateway
7. Log everything to audit trail
```

**Sub-components:**

#### 2a. Prompt Builder
Assembles the full prompt for each LLM call:
- **Persona block:** Consistent personality definition, tone guidelines, example messages, anti-examples
- **Context block:** User profile, goals, preferences, recent health log, daily summaries (last 7 days), engagement state
- **Instruction block:** Specific to trigger type (check-in template, nudge template, response guidelines)
- **Safety block:** Hard rules (no diagnosis, no medication, defer to professionals)

#### 2b. Safety Filter
Evaluates outbound messages before sending:
- **Medical content detection:** Flags messages that could be interpreted as medical advice
- **Tone check:** Ensures message isn't guilt-inducing, judgmental, or overly clinical
- **Repetition check:** Compares against recent messages to avoid repetitive phrasing
- **Implementation:** Rule-based for obvious cases (keyword/pattern matching) + optional lightweight LLM evaluation for ambiguous cases

#### 2c. Frequency Governor
Enforces engagement rules:
- Daily outbound cap: 4 messages (configurable per user)
- Nudge-specific cap: 2 per day
- Backoff: if 2+ messages unanswered, reduce to 1/day
- Quiet mode: after 36h silence, max 1 low-pressure message/day
- Pause: after 7 days silence, stop until user re-initiates
- Timezone-aware: no messages before 7 AM or after 11 PM user-local time

#### 2d. Data Extractor (lightweight)
Extracts key signals from user messages in real-time:
- Workout mentioned (type, duration if stated)
- Meal mentioned (meal type, quality indicator)
- Sleep time mentioned
- Mood/energy indicator
- **Not a full NLU pipeline.** Simple extraction. Ambiguous cases stay unstructured. Daily summaries handle the nuance.

**Technology:** Python module within the main process. Claude API for LLM calls. Structured prompts with JSON output mode for extraction.

---

### 3. Scheduler
**Purpose:** Triggers proactive engagement at the right times.

**Implementation:**
- Per-user schedule stored in database: `{user_id, check_in_type, scheduled_time_utc, enabled}`
- Worker process evaluates due schedules every minute
- Fires trigger to Concierge Brain with context: `{user_id, trigger_type: morning_check_in | evening_check_in | nudge}`
- Nudge triggers are also evaluated by the worker: checks user context for drift conditions (no workout in X days, sleep drift, etc.)

**Schedules (default, user-configurable):**
| Trigger | Default Time | Condition |
|---|---|---|
| Morning check-in | 8:00 AM local | Daily |
| Evening check-in | 9:00 PM local | Daily, only if user responded to morning |
| Pre-workout nudge | 1h before stated workout time | Only on workout days |
| Bedtime nudge | 30 min before goal bedtime | Daily, if bedtime goal set |
| Drift nudge | 10:00 AM local | Only when drift detected |

**Technology:** Cron jobs on the host machine that invoke Python scripts. Schedule config in a simple YAML file or SQLite table. For 2 users, a cron job per check-in type is perfectly fine.

---

### 4. User Memory Store
**Purpose:** Everything the concierge knows about the user.

**Schema:**

```sql
-- Core profile
users (
  id TEXT PRIMARY KEY,       -- telegram user ID
  name TEXT,
  timezone TEXT DEFAULT 'Asia/Jerusalem',
  goals JSON,                -- {fitness: "...", nutrition: "...", sleep: "..."}
  preferences JSON,          -- {tone: "gentle", check_in_morning: "08:00", ...}
  onboarding_complete INTEGER DEFAULT 0,
  created_at TEXT,
  updated_at TEXT
)

-- Raw conversation log
messages (
  id INTEGER PRIMARY KEY,
  user_id TEXT,
  direction TEXT,            -- 'inbound' | 'outbound'
  content TEXT,
  extracted_data JSON,       -- {workout: true, meal: "lunch", ...}
  trigger_type TEXT,         -- NULL for reactive, 'morning_check_in' etc. for proactive
  created_at TEXT
)

-- Daily summaries (LLM-generated)
daily_summaries (
  id INTEGER PRIMARY KEY,
  user_id TEXT,
  date TEXT,                 -- YYYY-MM-DD
  summary TEXT,              -- Natural language summary of the day
  structured JSON,           -- {workouts: [...], meals: [...], sleep: {...}, mood: "..."}
  created_at TEXT
)

-- Engagement state
engagement_state (
  user_id TEXT PRIMARY KEY,
  mode TEXT DEFAULT 'active',    -- 'active' | 'quiet' | 'paused'
  last_user_message TEXT,
  last_outbound_message TEXT,
  unanswered_count INTEGER DEFAULT 0,
  daily_outbound_count INTEGER DEFAULT 0,
  daily_outbound_reset_at TEXT
)

-- Device data (day 1 — Garmin, Oura, Renpho, Strava)
device_data (
  id INTEGER PRIMARY KEY,
  user_id TEXT,
  source TEXT,          -- 'garmin' | 'oura' | 'renpho' | 'strava'
  data_type TEXT,       -- 'sleep' | 'activity' | 'weight' | 'readiness' | 'stress' | 'body_battery'
  data JSON,
  recorded_at TEXT,     -- ISO timestamp
  synced_at TEXT
)

-- Meal memory (nutrition recommendations)
meals (
  id INTEGER PRIMARY KEY,
  user_id TEXT,
  name TEXT,              -- "salmon bowl", "chicken pasta"
  description TEXT,
  tags JSON,             -- ["high-protein", "pre-workout", "quick"]
  times_mentioned INTEGER DEFAULT 1,
  last_mentioned TEXT,
  notes TEXT
)

-- Simple log (replaces complex audit trail — just log to file for 2 users)
-- For debugging, also log LLM prompts/responses to a log file on disk
```

**Technology:** SQLite. Single file. For 2 users generating ~10 messages/day each, this database will stay tiny for years. No need for PostgreSQL.

### 5. Data Sync Service
**Purpose:** Pulls health data from Garmin, Oura, Renpho, and Strava on a schedule. No manual export.

**Implementation:**
- **Garmin Connect:** `garminconnect` Python library (unofficial, uses session auth). Pulls activities, sleep, stress, Body Battery, steps.
- **Oura Ring:** Official Oura API v2 (personal access token). Pulls sleep stages, readiness, HRV, activity.
- **Renpho Scales:** Data syncs to Apple Health. Extract via Apple Health export or `renpho` Python library (reverse-engineered API).
- **Strava:** Official API (OAuth2 with refresh token). Pulls activities with detailed metrics.
- **Apple Health:** Backup path — automated export via Shortcuts + XML parsing, or `apple-health-exporter` scripts.

**Schedule:** Runs every 2–4 hours via cron. Pulls latest data since last sync. Writes normalized records to SQLite `device_data` table.

**Data model:**
```sql
device_data (
  id INTEGER PRIMARY KEY,
  user_id TEXT,
  source TEXT,         -- 'garmin' | 'oura' | 'renpho' | 'strava'
  data_type TEXT,      -- 'sleep' | 'activity' | 'weight' | 'readiness' | 'stress'
  data JSON,           -- normalized payload
  recorded_at TEXT,    -- ISO timestamp
  synced_at TEXT
)
```

### 6. Meal Memory
**Purpose:** Remembers meals the user has eaten and builds a personal meal repertoire for recommendations.

**Data model:**
```sql
meals (
  id INTEGER PRIMARY KEY,
  user_id TEXT,
  name TEXT,              -- "salmon bowl", "chicken pasta", "overnight oats"
  description TEXT,       -- user's description or concierge's summary
  tags JSON,             -- ["high-protein", "pre-workout", "quick", "dinner"]
  times_mentioned INT,    -- how often this meal appears
  last_mentioned TEXT,    -- ISO date
  notes TEXT              -- any adjustments suggested or user preferences
)
```

The concierge uses this table to:
- Recommend meals from the user's own repertoire based on context (training day, rest day, time of day)
- Notice when the user hasn't had a nutritious meal in a while
- Suggest gradual adjustments ("Try adding avocado to your morning toast")

---

## Integration Points (All Day 1)

| System | Direction | Method | Auth |
|---|---|---|---|
| Telegram Bot API | Bidirectional | Long polling or webhooks | Bot token |
| Claude API | Outbound | HTTP API | API key |
| Garmin Connect | Inbound (pull) | `garminconnect` Python lib | Username/password session |
| Oura Ring | Inbound (pull) | Official REST API v2 | Personal access token |
| Renpho | Inbound (pull) | Via Apple Health export or reverse-engineered API | Session auth |
| Strava | Inbound (pull) | Official REST API | OAuth2 refresh token |
| SQLite | Internal | Direct file access | N/A |

---

## Operational Strategy

### Deployment
- **Single Python process** running on a Mac, Raspberry Pi, or $5/month VPS
- Telegram bot runs as a long-polling process (no webhook server needed)
- Cron jobs handle: scheduled check-ins, data sync, daily summaries
- SQLite file stored locally with periodic backup (rsync or git)

### Monitoring (Keep It Simple)
- Log file with all outbound messages and LLM calls
- Simple error notification (e.g., Telegram message to self if a sync fails)
- Monthly cost check on Claude API usage

### Failure Modes
| Failure | Impact | Mitigation |
|---|---|---|
| LLM API down | No responses | Retry with backoff. Log for later. Fallback: static "Good morning!" message. |
| Telegram API down | Can't send/receive | Retry. Messages are not life-critical. |
| Data sync fails | Missing device data | Log error. Concierge works fine without it — asks the user instead. |
| Process crashes | Everything stops | Systemd/launchd auto-restart. Simple health check. |

### Cost Model (2 users)
| Component | Cost/month |
|---|---|
| Claude API (~8 calls/day × 2 users, ~2K tokens avg) | ~$6–10 |
| VPS (if not running on Mac) | ~$5 |
| Telegram API | Free |
| Garmin/Oura/Strava APIs | Free (personal use) |
| **Total** | **~$6–15/month** |

---

## Verification Strategy

### Unit Testing
- Prompt builder: verify context assembly for various user states
- Safety filter: test against known-bad messages (medical advice, guilt-tripping, etc.)
- Frequency governor: test all state transitions and edge cases
- Data extractor: test against corpus of sample messages

### Integration Testing
- Full pipeline: simulate inbound message → response cycle
- Proactive pipeline: simulate scheduled trigger → message generation → delivery
- Mode transitions: test active→quiet→paused→re-engagement flows

### Conversation Quality Testing
- **Tone evaluation:** Score a sample of generated messages (human review or LLM-as-judge)
- **Repetition check:** Verify messages don't repeat over a 7-day simulated conversation
- **Safety evaluation:** Red-team the system with messages designed to elicit medical advice

### End-to-End Testing
- Simulate a full week of user interaction (automated)
- Verify: check-ins fire on time, nudges appear when expected, drift detection triggers correctly, quiet mode activates, re-engagement works
- Verify: daily summaries are accurate, context is correctly assembled

### User Acceptance Testing
- 2 real users (the target audience)
- Daily engagement for 2 weeks
- Qualitative feedback on tone, timing, helpfulness
- Simple question: "Does this feel like someone is looking out for me?"
