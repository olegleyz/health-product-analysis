# 04 — High-Level Architecture

**Agent:** Principal Architecture Agent (Lead Engineer)

---

## Hardest Technical Problems (Identified First)

### 1. Proactive Engagement Engine
The system must **initiate** conversations at the right time, with the right content, at the right frequency — without becoming annoying. This is the core technical challenge. It requires:
- A scheduler that understands user context (not just cron jobs)
- Frequency/backoff logic that adapts per user
- Content generation that feels personal, not templated

### 2. Conversational Data Extraction
The system must extract structured health data from unstructured messages. "Had pasta and a salad for lunch, then hit the gym for about an hour" must become: meal(lunch, moderate), workout(strength/general, 60min). This requires reliable NLU on messy, short-form text.

### 3. Drift Detection Across Sparse Data
The system must detect behavioral drift (fewer workouts, worse sleep) from incomplete, self-reported data. There is no continuous signal — only sporadic conversation fragments. Statistical methods need to work with missing data and few observations.

### 4. Tone Consistency at Scale
Every outbound message must feel like it comes from the same caring person. LLM outputs can vary in tone, verbosity, and style. Maintaining consistent personality across thousands of interactions is a prompt engineering and evaluation challenge.

---

## Core Components / Services

```
┌─────────────────────────────────────────────────────┐
│                   MESSAGING LAYER                    │
│  (WhatsApp Business API ↔ Webhook Gateway)          │
└──────────────┬──────────────────────┬───────────────┘
               │ inbound              │ outbound
               ▼                      ▲
┌──────────────────────────┐  ┌───────────────────────┐
│   CONVERSATION ENGINE    │  │  ENGAGEMENT ENGINE     │
│                          │  │  (Proactive Scheduler) │
│  - Message handling      │  │                        │
│  - Context assembly      │  │  - Check-in scheduler  │
│  - LLM orchestration     │  │  - Nudge trigger logic │
│  - Response generation   │  │  - Frequency/backoff   │
│                          │  │  - Drift detection     │
└──────────┬───────────────┘  └──────────┬────────────┘
           │                             │
           ▼                             ▼
┌─────────────────────────────────────────────────────┐
│                    USER CONTEXT STORE                │
│                                                      │
│  - Profile (goals, preferences, schedule)            │
│  - Health log (workouts, meals, sleep — extracted)   │
│  - Conversation history                              │
│  - Engagement state (active/quiet, last contact)     │
│  - Patterns & drift indicators                       │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────┐
│              DATA INTEGRATION LAYER (optional)       │
│                                                      │
│  - Wearable adapters (Apple Health, Garmin, Whoop)   │
│  - Nutrition app adapters (MyFitnessPal)             │
│  - Lab result parser (PDF/image → structured data)   │
└─────────────────────────────────────────────────────┘
```

---

## Service Descriptions

### 1. Messaging Layer
**Purpose:** Handles inbound/outbound messaging via WhatsApp Business API.

- Receives webhooks for incoming user messages
- Sends outbound messages (check-ins, nudges, responses)
- Handles message delivery status (sent, delivered, read)
- Abstracts channel specifics so the system can later support Telegram/SMS

**Technology:** Webhook endpoint (serverless function or lightweight service) + WhatsApp Cloud API

### 2. Conversation Engine
**Purpose:** Core intelligence. Processes user messages and generates responses.

- Receives inbound messages from the messaging layer
- Assembles context: user profile, recent conversation, health log, engagement state
- Calls LLM (Claude) with structured prompt including context and persona instructions
- Extracts structured data from conversation (meals, workouts, sleep) and writes to user context store
- Applies safety guardrails before sending response

**Technology:** LLM orchestration service (Python/Node). Claude API as the LLM backbone.

### 3. Engagement Engine (Proactive Scheduler)
**Purpose:** Decides **when** to proactively reach out and **what** to say.

- Runs scheduled check-ins (morning/evening based on user timezone and preferences)
- Evaluates nudge triggers:
  - Time-based (bedtime approaching, pre-workout window)
  - Pattern-based (no workout logged in X days, sleep times drifting)
  - Silence-based (user hasn't responded in X hours)
- Enforces frequency caps and backoff rules
- Generates the nudge/check-in content via the Conversation Engine (not independently)

**Technology:** Scheduled job system (cron-like, per user) + trigger evaluation logic. Can be a queue-based system with per-user schedules.

### 4. User Context Store
**Purpose:** Persistent memory of everything the concierge knows about the user.

**Data model (conceptual):**

```
User Profile
├── user_id
├── name
├── timezone
├── goals: [fitness, nutrition, sleep, recovery]
├── preferences: {check_in_times, tone, frequency}
├── onboarding_complete: bool
│
Health Log (append-only)
├── timestamp
├── domain: workout | meal | sleep | recovery
├── source: conversation | wearable | nutrition_app
├── data: {type, duration, quality, notes}
│
Conversation History
├── timestamp
├── direction: inbound | outbound
├── message_text
├── extracted_data: [references to health log entries]
│
Engagement State
├── mode: active | quiet | paused
├── last_user_message: timestamp
├── last_outbound_message: timestamp
├── unanswered_count: int
├── daily_message_count: int
│
Pattern Summary (computed periodically)
├── weekly_workout_count: rolling average
├── avg_bedtime: rolling average
├── meal_quality_trend: improving | stable | declining
├── engagement_trend: improving | stable | declining
```

**Technology:** PostgreSQL for structured data. Conversation history can overflow to blob storage if needed.

### 5. Data Integration Layer
**Purpose:** Ingests external health data to enrich the concierge's awareness.

- **Wearable adapters:** Poll or receive webhooks from Apple Health (via HealthKit proxy), Garmin Connect API, Whoop API
- **Nutrition adapters:** Sync with MyFitnessPal API or similar
- **Lab result parser:** Accept uploaded PDFs/images, extract key values via OCR + LLM interpretation

**Principle:** All external data feeds into the same User Context Store. The Conversation Engine treats it the same as self-reported data, just with a different `source` tag.

**Technology:** Adapter services per integration. Likely serverless functions triggered by webhooks or scheduled syncs.

---

## Data Flow

### Inbound (user sends message)
```
User → WhatsApp → Webhook → Conversation Engine
  → Extract structured data → Write to User Context Store
  → Assemble context → Call LLM → Generate response
  → Apply safety check → Send via WhatsApp → User
```

### Proactive (system initiates)
```
Engagement Engine (scheduled/triggered)
  → Evaluate user context + patterns
  → Decide: send check-in / nudge / stay silent
  → If send: generate content via Conversation Engine
  → Apply safety check + frequency cap
  → Send via WhatsApp → User
```

### Data Integration (sensor data arrives)
```
Wearable/App → Adapter → Normalize → Write to User Context Store
  → Engagement Engine evaluates (may trigger nudge)
```

---

## External Integrations

| Integration | Priority | Complexity | Notes |
|---|---|---|---|
| WhatsApp Business API | **Must-have (v1)** | Medium | Requires Meta business verification. Rate limits apply. |
| Claude API | **Must-have (v1)** | Low | Core LLM. Well-documented API. |
| Apple Health (via proxy) | v2 | High | No direct API; requires a companion iOS app or HealthKit bridge |
| Garmin Connect API | v2 | Medium | OAuth2, well-documented |
| Whoop API | v2 | Medium | OAuth2, well-documented |
| MyFitnessPal API | v2 | Medium | API access may require partnership |
| Lab result parsing | v2 | High | OCR + LLM interpretation. Accuracy validation needed. |
| Telegram Bot API | v2 | Low | Simpler than WhatsApp. Good fallback channel. |

---

## High-Risk Areas

### 1. WhatsApp Business API Constraints
- **24-hour window rule:** You can only send free-form messages within 24 hours of the user's last message. Outside this window, you must use pre-approved template messages.
- **Impact:** This directly conflicts with proactive engagement. If the user hasn't messaged in 24+ hours, the concierge can only send template messages (which feel less personal).
- **Mitigation:** Design check-ins to keep the 24-hour window open. Have pre-approved templates for re-engagement. Consider Telegram as a less restricted alternative.

### 2. LLM Reliability for Data Extraction
- Extracting structured data from casual text is error-prone
- "I had a light lunch" — what does "light" mean?
- **Mitigation:** Accept imprecision. Use confidence scores. Ask clarifying questions sparingly. Never surface extracted data back to the user as "facts" without confirmation.

### 3. Tone Drift in LLM Outputs
- LLM personality can vary across calls
- **Mitigation:** Strong system prompts with examples. Tone evaluation pipeline. Periodic human review of sample outputs.

### 4. Privacy and Data Sensitivity
- Health data is sensitive. Conversation logs contain personal health information.
- **Mitigation:** Encryption at rest/transit. Minimal data retention policy. User data deletion on request. No third-party data sharing.

---

## Build vs Buy Decisions

| Component | Decision | Rationale |
|---|---|---|
| LLM | **Buy** (Claude API) | Core intelligence. No reason to train custom models for v1. |
| Messaging | **Buy** (WhatsApp Cloud API) | Standard integration. No value in building a messaging platform. |
| Conversation orchestration | **Build** | Core IP. Context assembly, prompt engineering, safety checks are proprietary. |
| Engagement engine | **Build** | Core IP. The scheduling and trigger logic is the product's differentiator. |
| User context store | **Build** | Standard database design. No off-the-shelf product fits this specific data model. |
| Wearable integrations | **Build adapters** | Thin adapter layers on top of existing APIs. |
| Infrastructure | **Buy** (cloud) | Standard cloud hosting. Serverless where possible to minimize ops. |
| Monitoring/observability | **Buy** | Use existing tools (Datadog, Sentry, or similar). |
