# 02 — Product Challenge Review

**Agent:** Product Challenge Agent (Senior PM)

---

## Risks

### 1. The "Nagging Problem"
The entire value proposition rests on proactive engagement. But the line between **caring check-in** and **annoying notification** is razor-thin and deeply personal. What feels supportive on Monday morning may feel intrusive on Friday night. If the concierge crosses this line even a few times, the user will mute it — and the product is dead.

**Challenge:** How does the system learn the user's tolerance boundary *before* crossing it? First impressions matter. The onboarding period is the highest-risk window.

### 2. Conversation Fatigue
Daily check-ins sound appealing in theory. In practice, responding to "Did you work out today?" every single day becomes a chore. The novelty wears off within 2–3 weeks for most users.

**Challenge:** The vision assumes sustained engagement. What is the retention strategy beyond week 3? How does the concierge keep conversations fresh without becoming a survey?

### 3. The "Reply Burden"
The system works on conversation. But typing replies takes effort. Even "yes/no" responses add friction. If the user is busy (which is the whole premise), they may not reply — and the system loses its primary data input.

**Challenge:** How does the concierge maintain awareness when the user goes silent? Silence could mean "I'm busy" or "I've disengaged" — the system must distinguish between the two.

### 4. Accuracy of Self-Reported Data
Without sensors, the system relies on what the user tells it. People underreport bad meals, overestimate exercise, and forget to mention poor sleep. The concierge's understanding may be systematically biased toward a rosier picture than reality.

**Challenge:** How does the system gracefully validate or cross-reference self-reports without feeling interrogative?

### 5. Personalization Cold Start
The vision promises a concierge that "learns over time." But the first 1–2 weeks are critical, and the system knows almost nothing. Generic check-ins during onboarding may feel hollow compared to the promise of a personalized concierge.

**Challenge:** What is the day-1 experience? How does the system feel personal before it has learned anything?

---

## Ambiguities

### 1. What exactly is a "nudge" vs. a "check-in" vs. "guidance"?
The vision uses these terms loosely. Are they different interaction types with different rules? Different tones? Different frequencies? The implementation team needs clear definitions.

### 2. Who decides the health goals?
The vision says the concierge helps you stay aligned with "the life you want to live." But it doesn't specify how goals are set. Does the user declare them explicitly? Does the system infer them? What happens when goals conflict (e.g., user wants to lose weight but also mentions stress eating)?

### 3. What channel, exactly?
"WhatsApp or similar" is vague. The choice of channel has massive implications for:
- Message formatting (rich media? buttons? voice?)
- API availability and cost
- Notification behavior
- User expectations

### 4. What does "works without sensors" really mean?
The vision says sensors are optional. But the experience with sensors vs. without sensors could be vastly different. Are these two different products? Or one product with graceful degradation?

### 5. Scope of health domains
Workouts, sleep, nutrition, and "habits" are mentioned. But "habits" is unbounded. Does it include hydration? Meditation? Alcohol? Medication adherence? Screen time? Stress management? The scope needs a clear boundary.

---

## Scope Refinements

### Tighten to four domains initially
Lock the MVP to: **workouts, nutrition, sleep, and recovery/rest**. Do not expand to open-ended "habits" until the core four are working well. This prevents scope creep and keeps the concierge's expertise focused.

### Define exactly three interaction types
1. **Check-in** — Scheduled touchpoints (morning, post-workout, evening). User expects them.
2. **Nudge** — Unscheduled, triggered by drift or context. User doesn't expect them.
3. **Response** — Concierge replies when user initiates conversation.

Each type should have its own frequency rules, tone guidelines, and escalation logic.

### Explicit onboarding phase
Define a structured first-week experience where the concierge:
- Learns schedule, preferences, and goals through a conversational intake
- Sets expectations about check-in frequency
- Lets the user calibrate tone and intensity

This is not "learning over time" — it is an intentional onboarding conversation.

### Two-tier engagement model
- **Active mode:** User is responsive. Full check-ins, nudges, follow-ups.
- **Quiet mode:** User has gone silent. Reduce to 1 message/day max. Acknowledge silence without guilt-tripping. Easy re-engagement path.

---

## Suggested Clarifications

1. **Define the "do nothing" baseline.** What happens if the concierge has zero data and the user never replies? This edge case reveals the minimum viable behavior.

2. **Define the tone spectrum.** "Caring" is subjective. Provide 3–5 example messages that represent the ideal tone, and 3–5 anti-examples that represent what the concierge should never sound like.

3. **Clarify the role of data integrations.** If wearables are optional, what is the *minimum* the concierge can do without any data? And what is the *maximum* it can do with full data integration? Define both ends of the spectrum explicitly.

4. **Define "success" for the user, not just for the product.** The success criteria are product metrics (response rate, retention). But what does success look like from the user's perspective? "I feel healthier" is vague. Can we define a concrete user outcome?

5. **Address the trust question.** The concierge is asking about personal health behaviors. Why should the user trust it? What builds trust in the first interaction? This is especially important for an AI system that proactively messages you about what you ate.
