# 05 — Architecture Challenge Review

**Agent:** Engineering Challenge Agent (Peer Principal Engineer)

---

## Risks

### 1. Over-Reliance on WhatsApp 24-Hour Window
The architecture correctly identifies the 24-hour messaging window as a risk but underestimates its severity. This is not a "mitigation" problem — it is a **fundamental constraint that shapes the entire product**.

If the user skips a day, the concierge loses its ability to send personalized messages. You're reduced to template messages, which directly contradict the "caring friend" tone. This means:

- The proactive engagement engine is effectively **disabled** for any user who goes quiet for 24+ hours
- The drift detection system can detect a problem but cannot respond naturally
- The re-engagement flow (the most critical moment) is the most constrained

**Recommendation:** Do not treat WhatsApp as a reliable channel for proactive engagement. Either:
- Design the product to work within the 24-hour constraint (morning check-in keeps the window open daily)
- Use a channel without this constraint (Telegram) as primary for power users
- Build a lightweight companion app for push notifications as a fallback

### 2. The Engagement Engine Is Underspecified
The architecture describes it as a "scheduled job system with per-user schedules" but this is the hardest component in the entire system. Questions unanswered:

- How does it decide between "send a nudge" and "stay silent"? What's the decision model?
- How are check-in times adjusted when users travel across timezones?
- How does it handle conflicting triggers (e.g., drift detected + user in quiet mode)?
- What's the state machine for engagement mode transitions?

This is not a cron job. This is a **context-aware decision engine** and deserves deeper architectural thought.

### 3. LLM Cost at Daily Engagement
Each interaction requires:
- Context assembly (loading profile, health log, recent conversations, patterns)
- LLM call with substantial context window
- Potentially multiple calls (extraction + response generation)

At 2 check-ins + 2 nudges + user replies per day, that's 6–10 LLM calls per user per day. At scale:
- 1,000 users × 8 calls/day = 8,000 calls/day
- 10,000 users = 80,000 calls/day

**Concern:** The architecture doesn't mention cost management, context window optimization, or caching strategies. At Claude API pricing, this could become expensive quickly.

### 4. Data Extraction Pipeline Is a Single Point of Failure
The system relies on extracting structured data from conversation to feed the User Context Store, which feeds drift detection, which feeds the Engagement Engine. If extraction is wrong:
- Health log is wrong
- Patterns are wrong
- Nudges are wrong or missing

There's no validation loop. The user never sees or confirms what was extracted. Errors compound silently.

### 5. No Offline or Degraded Mode
What happens when:
- The LLM API is down?
- The WhatsApp API is down?
- The database is unreachable?

A proactive system that suddenly goes silent damages trust more than a reactive system. If the concierge misses a morning check-in, the user notices.

---

## Missing Components

### 1. Message Quality Evaluation
There is no mechanism to evaluate whether outbound messages are:
- On-tone (caring, not robotic)
- Appropriate (not asking about workouts when user mentioned being sick)
- Non-repetitive (not saying "Great job!" for the third time this week)

**Need:** A lightweight evaluation layer — either rule-based or a separate LLM call — that scores outbound messages before sending.

### 2. User Feedback Mechanism
The user has no way to tell the system:
- "That message was annoying"
- "Check in less often"
- "Don't ask about nutrition"

**Need:** In-conversation commands or natural language preferences that adjust the system. "Can you stop asking about dinner?" should modify the engagement rules.

### 3. Conversation Summarization / Compression
Conversation history grows indefinitely. Loading full history into context for every LLM call is unsustainable.

**Need:** A periodic summarization service that compresses older conversations into structured summaries. Recent conversations (last 48h) stay raw; older ones become summaries.

### 4. Observability and Debugging
When a user says "the concierge sent me a weird message," there's no way to debug why.

**Need:** Full audit trail: what context was assembled, what prompt was sent, what the LLM returned, what was delivered. Essential for both debugging and safety review.

### 5. A/B Testing and Experimentation Framework
The system needs to continuously improve message quality, timing, and frequency. Without experimentation infrastructure, improvements are guesswork.

---

## Simplification Suggestions

### 1. Merge Conversation Engine and Engagement Engine
The current architecture separates these as two services, but the Engagement Engine always delegates content generation to the Conversation Engine anyway. In practice, you have one intelligence layer with two triggers:

- **Trigger A:** User sent a message (reactive)
- **Trigger B:** Scheduler/trigger fired (proactive)

Both end up in the same pipeline: assemble context → call LLM → generate message → safety check → send.

**Suggestion:** Single "Concierge Brain" service with two input paths. Simpler to build, deploy, and debug.

### 2. Start Without Real-Time Data Extraction
Instead of extracting structured data from every message in real-time, consider:
- Use the LLM to generate a **daily summary** of the conversation (once per day, off-peak)
- The daily summary produces the structured health log entries
- Drift detection runs on daily summaries, not real-time events

This is simpler, cheaper, and more accurate (the LLM has full daily context instead of individual messages).

### 3. Skip the Pattern Summary Computation
The architecture has a "Pattern Summary" computed periodically. But the LLM can infer patterns directly from the health log + recent summaries when generating messages. Don't pre-compute patterns — let the LLM reason about them in context.

This removes a component and a potential source of stale/incorrect data.

### 4. Use Telegram First, Not WhatsApp
Telegram Bot API has:
- No 24-hour messaging window
- Free API access
- Rich message formatting (buttons, inline keyboards)
- Easier to set up (no Meta business verification)

WhatsApp is the right long-term channel (larger user base), but Telegram is a better **first channel** to validate the product without fighting platform constraints.

---

## Revised Architecture Recommendations

```
┌─────────────────────────────────────────────────────┐
│              MESSAGING GATEWAY                       │
│  Telegram (v1) → WhatsApp (v2) → Multi-channel     │
└──────────────┬──────────────────────┬───────────────┘
               │ inbound              │ outbound
               ▼                      ▲
┌─────────────────────────────────────────────────────┐
│              CONCIERGE BRAIN (unified)               │
│                                                      │
│  Input paths:                                        │
│  1. User message (reactive)                          │
│  2. Scheduled trigger (proactive)                    │
│  3. Data event (sensor data arrived)                 │
│                                                      │
│  Pipeline:                                           │
│  Context assembly → LLM call → Safety check → Send  │
│                                                      │
│  Sub-components:                                     │
│  - Prompt builder (assembles persona + context)      │
│  - Safety filter (blocks medical advice, checks tone)│
│  - Frequency governor (enforces caps, backoff)       │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────┐
│              USER MEMORY                             │
│                                                      │
│  - Profile + preferences                             │
│  - Raw conversation log (last 48h)                   │
│  - Daily summaries (LLM-generated, older than 48h)   │
│  - Engagement state                                  │
│  - External data (wearables, when available)         │
└─────────────────────────────────────────────────────┘
```

**Key changes from original:**
1. Single "Concierge Brain" instead of split Conversation + Engagement engines
2. Telegram first, WhatsApp second
3. Daily summaries replace real-time data extraction
4. No pre-computed pattern summaries — LLM reasons in context
5. Added safety filter and frequency governor as explicit sub-components
6. Added observability (audit trail for every outbound message)
