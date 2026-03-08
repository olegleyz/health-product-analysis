# 09 — Data Learning & Adaptive Personalization

**Agent:** Data Learning Agent

---

## 1. Key Features to Track

The concierge learns from two streams: conversation (always available) and sensor data (optional enrichment). Tracked features are organized into three tiers.

### Raw Signals

These are extracted directly from messages or sensor APIs with minimal interpretation.

| Category | Signal | Source | Extraction Method |
|---|---|---|---|
| Workout | Activity mentioned (type, duration, intensity if stated) | Conversation | Data Extractor (LLM structured output) |
| Workout | Steps, active minutes, heart rate zones | Sensor (v2) | API sync |
| Nutrition | Meal mentioned (meal type, description) | Conversation | Data Extractor |
| Nutrition | Calorie/macro data | MyFitnessPal (v2) | API sync |
| Sleep | Bedtime / wake time stated | Conversation | Data Extractor |
| Sleep | Duration, stages, HRV | Wearable (v2) | API sync |
| Mood/Energy | Subjective state mentioned ("tired", "great", "stressed") | Conversation | Data Extractor |
| Recovery | Rest day mentioned, soreness, illness | Conversation | Data Extractor |
| Recovery | Recovery score, strain | Whoop (v2) | API sync |
| Engagement | Message timestamps, response latency, message length | System logs | Direct measurement |
| Engagement | Which nudges were responded to vs. ignored | System logs | Direct measurement |

### Derived Features

Computed from raw signals, typically within daily summaries.

| Feature | Derivation | Update Frequency |
|---|---|---|
| Workout adherence (days/week) | Count of workout mentions or sensor-confirmed activities over rolling 7 days | Daily summary |
| Sleep consistency | Standard deviation of bedtime/wake time over rolling 7 days | Daily summary |
| Average sleep duration | Mean of reported or measured sleep over rolling 7 days | Daily summary |
| Meal regularity | How often meals are mentioned/logged per day; consistency of meal timing | Daily summary |
| Nutrition quality trend | LLM-assessed quality trajectory based on meal descriptions (improving / stable / declining) | Daily summary |
| Energy trend | Directional assessment from mood/energy mentions (up / flat / down) | Daily summary |
| Response rate | Percentage of outbound check-ins that received a reply, rolling 7 days | Engagement state |
| Response latency (median) | Median time between outbound message and user reply, rolling 7 days | Engagement state |
| Conversation depth | Average message length and number of exchanges per check-in | Daily summary |

### Behavioral Patterns

Inferred over weeks from accumulated daily summaries. These are not stored as explicit records — the LLM reasons about them from summary history at generation time, per the architecture decision to use LLM reasoning in context rather than a pre-computed pattern store.

| Pattern | How It's Detected | Typical Detection Window |
|---|---|---|
| Workout rhythm | Recurring days/times of exercise across summaries | 2-3 weeks |
| Weekend behavior shift | Systematic differences in sleep, meals, or activity on weekends vs. weekdays | 2 weeks |
| Stress-eating correlation | Co-occurrence of stress mentions and nutrition quality drops | 3-4 weeks |
| Sleep debt accumulation | Progressive shortening of sleep across the work week, recovery on weekends | 2 weeks |
| Pre-workout routine | Consistent meal or activity patterns before workouts | 3 weeks |
| Seasonal or cyclical patterns | Monthly or seasonal shifts in activity, energy, or mood | 6-8 weeks |
| Disengagement precursors | Sequence of signals that precede periods of silence (shorter replies, fewer details, skipping evening check-ins) | 3-4 weeks |
| Post-travel recovery | How long it takes the user to return to routine after travel | After 2+ travel events |

---

## 2. User Model

The user model is the concierge's internal representation of who this person is, what they care about, and how they behave. It lives across three storage layers (profile, daily summaries, engagement state) and is assembled into context at generation time.

### Model Components

#### Identity & Goals (stored in `users.goals`, updated rarely)

```json
{
  "fitness": "Run 3x/week, build to half marathon by September",
  "nutrition": "Eat cleaner, reduce takeout to 1x/week",
  "sleep": "Consistent 11 PM bedtime, 7+ hours",
  "primary_motivation": "Energy and focus at work",
  "struggles": "Late-night snacking, skipping workouts when stressed"
}
```

Set during onboarding. Updated when the user explicitly changes goals or when the concierge detects a goal has been achieved or abandoned.

#### Preferences (stored in `users.preferences`, updated incrementally)

```json
{
  "tone": "direct",
  "check_in_morning": "07:30",
  "check_in_evening": "21:00",
  "topics_emphasized": ["workouts", "sleep"],
  "topics_deemphasized": ["nutrition"],
  "nudge_style": "brief",
  "workout_days": ["mon", "wed", "fri"],
  "typical_workout_time": "18:00",
  "bedtime_goal": "23:00",
  "sensitive_topics": ["weight"]
}
```

Initialized during onboarding, then refined continuously. Explicit user requests ("don't ask about dinner") update preferences immediately. Implicit signals (user consistently ignores nutrition questions) are flagged in daily summaries and influence the prompt builder.

#### Behavioral Baseline (inferred, not stored separately)

The LLM constructs an implicit behavioral baseline by reading the last 14-28 daily summaries. This baseline includes:

- Typical workout frequency and type
- Normal sleep range and bedtime
- Usual meal patterns and quality
- Baseline energy/mood
- Communication patterns (verbosity, emoji use, time-of-day preferences)

Deviations from this inferred baseline are what trigger drift detection and adaptive responses.

#### Engagement Profile (stored in `engagement_state`, updated per interaction)

- Current mode: active / quiet / paused
- Response rate trend (improving, stable, declining)
- Preferred response times (inferred from response timestamps)
- Nudge receptivity (which types of nudges get responses)
- Conversation style (brief vs. detailed, emoji use, question-asking)

### How the Model Evolves

| Timeframe | What Changes | Mechanism |
|---|---|---|
| Day 1-7 (Cold start) | Goals, preferences, schedule established | Onboarding conversation |
| Week 1-2 | Initial behavioral baseline forms | Daily summaries accumulate |
| Week 2-4 | Preferences refined, timing optimized | Implicit signals in summaries + explicit user feedback |
| Month 1-3 | Full behavioral patterns emerge | LLM reasons over 4-12 weeks of summary history |
| Ongoing | Goals updated, patterns recalibrated | Life changes detected, user-initiated updates |

---

## 3. Adaptive Personalization Strategies

### 3a. Timing Adaptation

**What adapts:** When the concierge sends check-ins and nudges.

**Signals used:**
- Response latency per time of day (if morning messages at 8 AM are replied to 3 hours later, but 7 AM messages get 10-minute replies, shift earlier)
- User-stated preferences ("I'm a morning person", "check in later")
- Day-of-week patterns (weekends may warrant later check-ins)
- Life context (user mentioned early meetings this week)

**Mechanism:**
- Start with onboarding-stated times
- The daily summary notes response timing patterns: "User responded to morning check-in within 5 minutes today (sent 7:30). Average response time for morning check-ins this week: 8 minutes."
- The prompt builder includes this timing context so the LLM can suggest schedule adjustments
- Schedule changes require either explicit user confirmation or consistent implicit signals over 7+ days
- The scheduler updates `schedules.scheduled_time` when adjustments are confirmed

**Constraints:**
- Never send before 6 AM or after 11 PM user-local time
- Maximum adjustment per iteration: 30 minutes
- Adjustments are mentioned to the user: "I noticed you're up earlier these days — mind if I check in at 7 instead of 8?"

### 3b. Content Adaptation

**What adapts:** What the concierge focuses on in each interaction.

**Signals used:**
- Goal priority (user's primary motivation)
- Recent behavioral gaps (where drift is happening)
- Topic receptivity (which topics get engaged responses vs. short/ignored replies)
- Day context (workout day vs. rest day, weekday vs. weekend)
- Seasonal/periodic patterns (Monday = fresh start energy, Friday = winding down)

**Mechanism:**
- The prompt builder constructs a `content_focus` section for each interaction:

```
Content focus for this check-in:
- Primary: Ask about today's planned run (user mentioned Mon/Wed/Fri schedule, today is Wednesday)
- Secondary: Note that sleep has been under 6.5h for 3 nights — ask how they're feeling
- Avoid: Nutrition — user has been terse about meal questions this week (3 one-word responses)
- Callback: User mentioned wanting to try yoga last Thursday — natural moment to follow up
```

- Content priority follows a hierarchy:
  1. User-initiated topics (always respond to what they bring up)
  2. Active drift areas (where behavior has deviated from goals)
  3. Goal-aligned check-ins (routine accountability)
  4. Exploratory questions (learning more about the user)

**Constraints:**
- Never focus exclusively on areas of struggle — balance with acknowledgment of what's going well
- Rotate topics across the week; avoid asking the same question two days in a row
- If a topic is consistently ignored (3+ times), back off for at least a week before trying again

### 3c. Tone Adaptation

**What adapts:** How the concierge communicates — formality, directness, warmth, humor.

**Signals used:**
- Onboarding preference ("more direct" vs. "more gentle")
- User's own communication style (mirroring)
- Emotional context (stressed, excited, frustrated, neutral)
- Response to different tones (which messages get the most engaged replies)

**Mechanism:**
- The persona block in the system prompt includes a per-user tone modifier:

```
Base persona: Warm, caring, knowledgeable friend.

User-specific tone adjustments:
- Directness: HIGH (user prefers concise, action-oriented messages)
- Humor: MODERATE (user uses casual language and occasional jokes)
- Empathy depth: MODERATE (acknowledge feelings briefly, don't dwell)
- Formality: LOW (contractions, casual phrasing)
- Emoji use: NONE (user never uses emoji)
```

- Tone calibration evolves through daily summaries, which note communication style observations: "User replied with detailed paragraph about their run — engaged and positive. Used humor about being slow. Short reply to nutrition question — possible disinterest or fatigue."

**Constraints:**
- Tone adjustments are gradual — never shift dramatically between messages
- Safety filter enforces hard tone guardrails regardless of adaptation: never guilt-inducing, never judgmental, never clinical
- If user is in a negative emotional state, default to empathetic and supportive regardless of usual tone preference

### 3d. Frequency Adaptation

**What adapts:** How many messages the concierge sends per day.

**Signals used:**
- Response rate (declining response rate = reduce frequency)
- Message engagement quality (one-word replies vs. detailed responses)
- User-stated preference ("check in less often")
- Life context (user mentioned busy week, travel, illness)
- Day of week patterns (user less responsive on weekends)

**Mechanism:**
- Start at default: 2 check-ins + up to 2 nudges = 4 max/day
- Frequency governor adjusts based on engagement state:

| Engagement Signal | Frequency Adjustment |
|---|---|
| Response rate > 80%, detailed replies | Maintain current; may add optional nudge |
| Response rate 50-80%, mixed quality | Maintain check-ins, reduce nudges to 1/day |
| Response rate 30-50% | Reduce to 1 check-in + 1 optional nudge |
| Response rate < 30% (2+ days) | Quiet mode: 1 low-pressure message/day |
| 7 days silence | Pause: stop until user re-initiates |
| User returns after pause | Gradual ramp: start with 1/day, increase over 3 days |

- Frequency changes are noted in daily summaries for context continuity

**Constraints:**
- Hard cap: never exceed `users.preferences.max_daily_messages` (default 4)
- Ramp-up after re-engagement is always gradual (never go from 0 to 4 in one day)
- Weekend/holiday frequency may differ from weekday without requiring explicit setting

---

## 4. Learning Mechanisms

### 4a. Daily Summary Content

The daily summary is the primary learning artifact. Generated by a scheduled LLM job at end of day (or early next morning), it processes all messages exchanged that day.

**Input to summary generation:**
- All messages for the day (inbound and outbound)
- Extracted data from each message (`messages.extracted_data`)
- External sensor data received that day (if any)
- Previous day's summary (for continuity)
- User profile and goals (for relevance assessment)

**Summary prompt structure:**

```
You are generating a daily health summary for the concierge's memory.

User profile: {profile}
User goals: {goals}
Yesterday's summary: {previous_summary}
Today's messages: {messages}
Today's sensor data: {external_data or "none"}

Generate two outputs:

1. STRUCTURED DATA (JSON):
{
  "date": "2026-03-07",
  "workouts": [{"type": "running", "duration_min": 30, "notes": "Easy pace, felt good"}],
  "meals": [
    {"type": "lunch", "description": "Salad with chicken", "quality": "good"},
    {"type": "dinner", "description": "Pizza", "quality": "indulgent", "context": "unplanned"}
  ],
  "sleep": {"bedtime": "23:30", "wake": "06:45", "quality": "self-reported good", "duration_h": 7.25},
  "mood_energy": "moderate energy, mentioned work stress",
  "engagement": {
    "response_rate": 1.0,
    "avg_response_time_min": 12,
    "conversation_depth": "detailed on workout, brief on meals",
    "topics_engaged": ["workout", "sleep"],
    "topics_avoided": ["nutrition detail"]
  },
  "notable": ["First run in 5 days — positive sign", "Mentioned knee discomfort during run"],
  "flags": ["Monitor knee issue — if persists, suggest seeing a professional"]
}

2. NARRATIVE SUMMARY (2-4 sentences):
Natural language summary focusing on what matters for future context.
Example: "Alex got back to running today after a 5-day gap — a 30-minute easy run that felt good despite some knee discomfort. Ate well at lunch but dinner was unplanned pizza. Sleep was solid at 7.25 hours. Engaged actively about the workout but gave brief responses about meals — may want to ease off nutrition questions for now."
```

### 4b. Pattern Inference from Summary History

Patterns are not pre-computed or stored as separate records. Instead, the prompt builder includes recent summaries and the LLM reasons about patterns at generation time. This keeps the system simple and avoids stale pattern data.

**What the LLM receives for pattern reasoning:**

```
Recent daily summaries (last 14 days):
{summaries}

Based on these summaries, note relevant patterns before generating your message:
- Workout consistency: How does this week compare to last week?
- Sleep trends: Is bedtime or duration shifting?
- Nutrition patterns: Any recurring issues?
- Engagement patterns: When and how does this user prefer to communicate?
- Drift indicators: Any areas moving away from stated goals?
```

**Why 14 days:** Two weeks provides enough data to distinguish a genuine pattern from a one-off event, while keeping the context window manageable (~2,000-4,000 tokens for 14 summaries at 150-300 tokens each).

**Scaling consideration:** As users accumulate months of data, older summaries are compressed into weekly and monthly rollups (see Section 5, Memory Architecture). The LLM always sees: last 14 daily summaries + last 4 weekly rollups + last 3 monthly rollups. This provides both recent detail and long-term trend awareness.

### 4c. How the Prompt Builder Uses Learned Context

The prompt builder assembles context in layers, with strict token budgets:

```
PROMPT STRUCTURE (total budget: ~6,000 tokens for context)

[1] System Persona (fixed, ~400 tokens)
    - Who the concierge is, safety rules, tone guidelines

[2] User Identity (from users table, ~200 tokens)
    - Name, goals, preferences, tone modifiers

[3] Recent Context (from daily_summaries, ~2,500 tokens)
    - Last 7 daily summaries (narrative form)
    - Current day's messages so far

[4] Pattern Context (from extended summaries, ~800 tokens)
    - LLM-distilled patterns from 14-day summary window
    - Weekly/monthly rollups for long-term trends

[5] Engagement Context (from engagement_state, ~200 tokens)
    - Current mode, response rate, nudge receptivity
    - Frequency governor state

[6] Trigger-Specific Instructions (~400 tokens)
    - What kind of interaction this is (morning check-in, response to user, nudge)
    - Content focus priorities for this interaction
    - What to avoid

[7] Current Message (~500 tokens)
    - The user's message (reactive) or trigger context (proactive)
```

**Token management:** If total context exceeds budget, compression is applied in this priority order: (1) trim older summaries first, (2) reduce pattern context to key points, (3) summarize current-day messages. Identity, persona, and safety blocks are never compressed.

### 4d. Cold Start Strategy (First Week)

The first week is critical. The system has no history, no baseline, and no patterns. The strategy is to learn fast while providing immediate value.

**Day 0: Onboarding (5-10 minutes)**
- Conversational goal-setting (not a form)
- Collect: fitness goals, current routine, sleep habits, nutrition challenges, preferred times, tone preference
- Set initial schedule based on stated preferences
- Store everything in `users.goals` and `users.preferences`

**Days 1-3: Active Learning Mode**
- Check-ins are slightly more question-heavy than usual (gathering data)
- Questions are direct but not interrogative:
  - "What did you have for lunch?" (establishing meal patterns)
  - "How'd you sleep?" (establishing sleep baseline)
  - "Any workout planned today?" (establishing exercise routine)
- Prompt builder flags `cold_start: true` so the LLM knows to:
  - Ask broader questions (not yet knowing what to focus on)
  - Avoid referencing "patterns" or "I've noticed" (there's nothing to notice yet)
  - Be more adaptive in conversation (follow the user's lead)
- Nudges are limited to 1/day (don't overwhelm before trust is established)

**Days 4-7: Baseline Formation**
- First daily summaries are accumulating (3-6 days of data)
- LLM begins noting initial patterns: "User works out Mon/Wed, eats takeout on Fridays, sleeps late on weekends"
- Prompt builder shifts from `cold_start` to `baseline_forming`
- Check-ins become more targeted based on emerging patterns
- Nudge frequency can increase to standard levels if engagement is good
- First drift detection becomes possible (but requires 2+ weeks for confidence)

**After Week 2: Normal Operation**
- `cold_start` flag removed
- Full pattern reasoning enabled
- Adaptive personalization fully active

---

## 5. Agent Memory Architecture

### 5a. Short-Term Memory (Current Conversation)

**What it holds:** The current conversation thread — all messages exchanged in the current interaction session.

**Storage:** Loaded from the `messages` table for the current day (or current interaction window). Passed directly to the LLM as part of the prompt.

**Lifecycle:** Persists in the prompt context for the duration of the conversation. If the user sends multiple messages across the day, all same-day messages are included as conversation context.

**Token budget:** ~500-1,000 tokens. If the day's conversation exceeds this, older exchanges within the day are summarized inline by the prompt builder.

### 5b. Medium-Term Memory (Recent Days)

**What it holds:** Daily summaries for the last 7-14 days. This is the primary working memory for the concierge.

**Storage:** `daily_summaries` table. Both structured JSON and narrative text.

**What it enables:**
- Day-over-day comparison ("You mentioned being tired yesterday — feeling better today?")
- Short-term trend detection ("Third day in a row with less than 6 hours of sleep")
- Continuity of conversations ("Last Thursday you said you wanted to try yoga")
- Drift detection (comparison of recent behavior against goals)

**Token budget:** ~2,000-2,500 tokens for 7 summaries. The prompt builder includes full narrative summaries for the last 3 days and condensed versions (key facts only) for days 4-7.

### 5c. Long-Term Memory (Weeks to Months)

**What it holds:** Compressed representations of the user's history — established patterns, preferences, and significant events.

**Storage:** Two mechanisms:

1. **Weekly rollups** (stored in `daily_summaries` with `date` = week-start and a `type` = `weekly` flag in structured data):

```json
{
  "type": "weekly_rollup",
  "week_of": "2026-02-23",
  "workouts": {"count": 3, "types": ["running", "strength"], "trend": "stable"},
  "sleep": {"avg_duration_h": 6.8, "avg_bedtime": "23:45", "consistency": "moderate"},
  "nutrition": {"quality_trend": "slight decline", "notable": "Increased takeout on Thu/Fri"},
  "engagement": {"response_rate": 0.75, "trend": "declining slightly"},
  "narrative": "Consistent 3x/week workout routine maintained. Sleep declining slightly — bedtime creeping past midnight midweek. Nutrition looser toward end of week. Engagement slightly lower than previous week, particularly on nutrition topics."
}
```

2. **Monthly rollups** (same table, `type` = `monthly`):

```json
{
  "type": "monthly_rollup",
  "month": "2026-02",
  "highlights": ["Started running consistently (up from 1x to 3x/week)", "Sleep improved first 2 weeks then regressed", "Set new goal: half marathon in September"],
  "established_patterns": ["Mon/Wed/Fri workout days", "Late-night eating on weekends", "More responsive in mornings"],
  "goal_progress": {"fitness": "on track", "sleep": "needs attention", "nutrition": "mixed"},
  "narrative": "February was a strong month for fitness — Alex built a consistent 3x/week running habit. Sleep was a mixed story: improved in the first half but bedtime crept later after a stressful project at work. Nutrition remains the biggest opportunity area, particularly weekend indulgences."
}
```

**Rollup generation:** Weekly rollups are generated every Sunday night from that week's daily summaries. Monthly rollups are generated on the 1st from that month's weekly rollups. Both are LLM-generated.

**What the LLM sees at generation time:**
- Last 7-14 daily summaries (full detail)
- Last 4 weekly rollups (compressed)
- Last 3 monthly rollups (highly compressed)
- Total long-term context: ~800-1,200 tokens

### 5d. Memory Compression and Management

**Compression cascade:**

```
Raw messages (kept 30 days)
  → Daily summaries (kept 90 days)
    → Weekly rollups (kept 12 months)
      → Monthly rollups (kept indefinitely)
```

**Raw message retention:** Full conversation logs in the `messages` table are retained for 30 days for debugging, audit, and detailed context. After 30 days, messages are purged (only daily summaries remain). Users can request earlier deletion.

**Daily summary retention:** Kept for 90 days. After 90 days, only weekly/monthly rollups persist. The weekly rollups capture everything the concierge needs for long-term reasoning.

**Index maintenance:** The `daily_summaries` table is indexed on `(user_id, date)` for efficient range queries. The prompt builder queries: last 14 dailies, last 4 weeklies, last 3 monthlies — a maximum of 21 rows per prompt assembly.

**Context window management:** If even compressed memory exceeds the token budget, the prompt builder applies progressive summarization:
1. Monthly rollups reduced to 1-sentence highlights
2. Weekly rollups reduced to key metrics only
3. Daily summaries beyond day 7 reduced to structured data only (no narrative)

---

## 6. Feedback Loops

### 6a. Measuring Response to Nudges

Every outbound message is tagged with its trigger type in the `messages` table. Response measurement is straightforward:

| Metric | Measurement | Storage |
|---|---|---|
| Response received | Did the user reply within 4 hours? | Derived from message timestamps |
| Response latency | Time between outbound and inbound message | Derived from message timestamps |
| Response quality | Word count, detail level, sentiment | Assessed in daily summary |
| Nudge type effectiveness | Response rate broken down by nudge type | Included in weekly rollup |

**Effectiveness tracking per nudge type:**

```json
// Example weekly rollup engagement section
{
  "nudge_effectiveness": {
    "morning_check_in": {"sent": 7, "responded": 6, "avg_latency_min": 8},
    "evening_check_in": {"sent": 5, "responded": 3, "avg_latency_min": 45},
    "pre_workout": {"sent": 3, "responded": 3, "avg_latency_min": 5},
    "bedtime": {"sent": 4, "responded": 1, "avg_latency_min": null},
    "drift": {"sent": 1, "responded": 1, "avg_latency_min": 20}
  }
}
```

**How this feeds back:** The prompt builder includes nudge effectiveness data so the LLM can reason: "Bedtime nudges are largely ignored — either stop sending them or try a different approach." The frequency governor also uses this data to suppress low-performing nudge types.

### 6b. Tracking Behavior Change After Interventions

The daily summary captures behavioral data, making it possible to assess whether specific interventions influenced behavior.

**Intervention-outcome tracking (within daily/weekly summaries):**

The LLM is prompted to note correlations during summary generation:

```
When generating the weekly rollup, note any apparent connections between
concierge interventions and subsequent behavior changes:
- Did a drift nudge lead to resumed activity?
- Did a sleep reminder correlate with earlier bedtime?
- Did a nutrition conversation change meal choices the next day?

Be honest about uncertainty. Correlation is not causation. Note the observation
without claiming credit.
```

**Example in weekly rollup:**

```json
{
  "intervention_observations": [
    "Drift nudge on Tuesday about 5-day workout gap → user ran Wednesday and Friday. Possible positive effect.",
    "Bedtime reminders Mon-Thu showed no measurable impact on bedtime (still ~midnight). Consider adjusting approach.",
    "Pre-workout hydration reminder consistently followed by user mentioning water — appears effective."
  ]
}
```

**Long-term outcome tracking:** Monthly rollups compare goal metrics against baseline:
- Workout frequency: month-over-month trend
- Sleep duration and consistency: month-over-month trend
- Nutrition quality: month-over-month trend
- Overall engagement: month-over-month trend

### 6c. Detecting Message Fatigue and Disengagement

Disengagement is a critical signal. The system tracks it at multiple levels:

**Early warning signals (detected in daily summaries):**
- Replies getting shorter (word count trending down)
- Response latency increasing
- Skipping evening check-ins (responds to morning only)
- Fewer user-initiated messages
- Terse or dismissive replies ("fine", "ok", "yeah")
- Stopping mid-conversation (replies to first question, ignores follow-up)

**Escalating disengagement (detected by engagement state):**

```
Level 0: Fully engaged
  → Response rate > 70%, detailed replies, user-initiated messages

Level 1: Reduced engagement (warning)
  → Response rate 40-70%, shorter replies, no user-initiated messages
  → Action: Reduce frequency, lighten tone, ask fewer questions per message

Level 2: Low engagement
  → Response rate 20-40%, one-word replies, long response latencies
  → Action: Reduce to 1 check-in/day, make messages low-pressure,
    explicitly acknowledge: "I know I've been checking in a lot — happy to
    dial it back. Just let me know what works."

Level 3: Quiet mode
  → 2+ messages unanswered, 36+ hours since last reply
  → Action: 1 message/day max, no questions, pure supportive presence

Level 4: Paused
  → 7+ days of silence
  → Action: Single re-engagement message, then stop until user returns
```

**Re-engagement after silence:**

When a user returns after a quiet or paused period, the concierge:
1. Welcomes them back without guilt or pressure
2. Does not ask where they've been or why they went quiet
3. Ramps frequency back up gradually (1/day for 2 days, then 2/day, then normal)
4. Notes the silence pattern in the weekly rollup for future reference

**Anti-pattern detection:** The system tracks whether interventions themselves are causing disengagement:
- If a user consistently disengages after nutrition questions → nutrition is a sensitive topic, back off
- If disengagement follows a week of high nudge frequency → the system was too aggressive
- If disengagement coincides with stressful life events mentioned in conversation → temporary, not system-caused

These observations are noted in weekly rollups and influence the prompt builder's content focus decisions.

---

## 7. Privacy-Preserving Learning

### Core Principles

1. **Learn patterns, not transcripts.** The system retains derived knowledge (summaries, patterns, rollups), not raw conversations, beyond a short retention window.
2. **Minimize what's stored.** If a piece of data doesn't improve the concierge's ability to help, don't store it.
3. **User controls their data.** Full transparency on what's stored and immediate deletion on request.
4. **No cross-user learning in v1.** Each user's data is siloed. No aggregation, no model fine-tuning on user data, no shared patterns.

### Data Retention Policy

| Data Type | Retention Period | Rationale |
|---|---|---|
| Raw messages | 30 days | Needed for context continuity and debugging. Deleted after daily summaries capture the essential content. |
| Daily summaries | 90 days | Primary working memory. Compressed into weekly rollups after 90 days. |
| Weekly rollups | 12 months | Long-term pattern tracking. Compressed into monthly rollups after 12 months. |
| Monthly rollups | Indefinite (until user deletes) | Minimal data, maximum utility for long-term personalization. |
| Extracted data (structured) | Same as parent message (30 days) | Deleted with raw messages. Relevant data is captured in daily summaries. |
| External sensor data | 30 days | Raw sensor data purged after being incorporated into daily summaries. |
| Audit log | 90 days | Debugging and safety review. No user content, only metadata. |

### Sensitive Data Handling

**What the concierge never stores explicitly:**
- Medical conditions, diagnoses, or medications (unless user explicitly sets as context in their profile)
- Mental health disclosures (noted in summaries only as "user mentioned feeling stressed" — no clinical detail)
- Body weight or measurements (unless user explicitly opts in to tracking)
- Identifiable health records or lab values (processed in-session, not persisted in raw form)

**Summary sanitization:** The daily summary generation prompt includes instructions to abstract sensitive details:

```
When generating the summary, follow these privacy rules:
- Abstract health details: "user mentioned a health concern" not "user said they have [condition]"
- Do not include specific body measurements unless the user has opted into weight/measurement tracking
- For emotional content, note the general state ("stressed", "frustrated") without quoting the user's words
- Do not include names of other people, workplaces, or specific locations mentioned in conversation
- If the user disclosed something sensitive, note that a sensitive topic was discussed
  and the general nature (health concern, personal issue) without specifics
```

### User Data Controls

| Action | Implementation |
|---|---|
| View stored data | User can request a data export (all summaries, profile, preferences) |
| Delete all data | Full account deletion: all messages, summaries, rollups, profile removed within 24 hours |
| Delete specific data | User can say "forget what I told you about X" — concierge flags for deletion in next summary cycle |
| Pause learning | User can request "don't track this conversation" — messages stored but excluded from daily summary |
| Opt out of sensor data | Disconnect integration at any time; stored sensor data deleted within 24 hours |

### Technical Safeguards

- **Encryption at rest:** All user data encrypted in PostgreSQL (column-level encryption for messages and summaries, or full-disk encryption at minimum)
- **Encryption in transit:** TLS for all API calls (Telegram, Claude, database connections)
- **Access control:** Service-level access only. No admin can read raw messages without audit trail entry.
- **LLM data isolation:** Claude API calls use the Anthropic data retention policy (no training on API inputs). User data sent to Claude is ephemeral — not stored by Anthropic.
- **No cross-user leakage:** Each LLM call includes only one user's data. No shared context across users. User IDs are UUIDs with no personally identifiable information.
- **Audit trail:** Every LLM call that processes user data is logged (metadata only: timestamp, user_id, trigger_type, outcome). Prompt content in audit log is retained for 90 days only.

---

## Summary: How Learning Flows Through the System

```
User message arrives
  │
  ├─→ Data Extractor: Extract structured signals (workout, meal, sleep, mood)
  │     └─→ Store in messages.extracted_data
  │
  ├─→ Prompt Builder: Assemble context
  │     ├── User profile + goals + preferences (long-term)
  │     ├── Last 7-14 daily summaries (medium-term)
  │     ├── Weekly/monthly rollups (long-term trends)
  │     ├── Current conversation (short-term)
  │     ├── Engagement state (adaptation signals)
  │     └── Trigger-specific instructions
  │
  ├─→ LLM generates response (informed by full context)
  │     └─→ Response reflects learned patterns, adapted tone, personalized content
  │
  └─→ End of day: Daily Summary Job
        ├── Summarize all interactions
        ├── Update structured data (workouts, sleep, meals, engagement)
        ├── Note behavioral observations and intervention outcomes
        ├── Flag drift, disengagement signals, or preference changes
        └── Weekly/monthly: Generate rollups, compress older data
              └── The concierge is now smarter for tomorrow
```

The learning loop is continuous but never invasive. The concierge gets better not by collecting more data, but by building richer understanding from the data it already has — and knowing when to forget.
