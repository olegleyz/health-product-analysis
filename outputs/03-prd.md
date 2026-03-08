# 03 — Product Requirements Document (PRD)

**Agent:** Final Product Definition Agent (Group PM Review)

---

## Product Vision

A personal health concierge that **proactively checks in** with the user about workouts, nutrition, sleep, and recovery — creating continuous awareness and gentle accountability through conversation.

The concierge behaves like a thoughtful person who cares about your health. It reaches out first. It notices when things drift. It guides you back on track with timely, specific, caring messages.

It works through simple messaging. No app required. Sensor data from existing devices (Garmin, Oura, Renpho) is integrated from day one to give the concierge real awareness of sleep, activity, body composition, and training load.

**Scale: This is a personal project for 1–2 users. Success = working reliably for 2 people. Not a scalable service.**

---

## User Scenarios

### Scenario 1: Morning Planning
*8:00 AM. The user receives a message.*

> "Good morning. What's the plan today — any workout?"

User replies: "Going for a run after work."

> "Nice. Make sure you hydrate well this afternoon. What time do you think you'll go?"

User: "Around 6."

> "Got it. I'll check in around 7 to see how it went."

---

### Scenario 2: Drift Detection
*The user has not mentioned a workout in 5 days. Concierge notices.*

> "Hey — I noticed you haven't trained since Monday. Everything okay? Even a 20-minute walk today would be great."

User: "Yeah, busy week at work."

> "Understood. No pressure. But a short walk might actually help with the stress. Up to you."

---

### Scenario 3: Nutrition Follow-Up
*Evening. The user mentioned lunch earlier but nothing about dinner.*

> "How was dinner tonight?"

User: "Had pizza and ice cream."

> "No judgment. Was it a conscious choice or just what happened?"

User: "Just happened."

> "That's useful to notice. Tomorrow, try deciding what you'll eat for dinner before 3 PM. Planning ahead makes a big difference."

---

### Scenario 4: Sleep Nudge
*11:15 PM. User's stated bedtime goal is 11:00 PM.*

> "It's past 11. Time to wind down?"

---

### Scenario 5: Silent User
*User hasn't responded to the last 2 messages (over 36 hours).*

Concierge switches to quiet mode. Next morning, sends a single low-pressure message:

> "No need to reply. Just wanted you to know I'm here when you're ready."

*Waits 48 hours before next message. No guilt. No escalation.*

---

### Scenario 6: Sensor-Enhanced Check-In
*User has a connected wearable. Concierge sees last night's sleep was 5.2 hours.*

> "Looks like you got about 5 hours of sleep last night. Rough night? You might want to take it easy on training today and prioritize rest."

---

## Core Features

### F1: Scheduled Check-Ins
- **Morning check-in** (daily): Ask about the day's plans — workout, meals, energy
- **Evening check-in** (daily): Ask how things went — training, meals, sleep intentions
- **Frequency:** User-configurable. Default is morning + evening. Can reduce to once daily.
- **Tone:** Warm, brief, conversational. Never robotic.

### F2: Proactive Nudges
- Triggered by context, not schedule:
  - Pre-workout nutrition reminder
  - Bedtime reminder based on stated goals
  - Hydration reminders on training days
  - Rest day suggestion after consecutive hard training days
- **Frequency cap:** Maximum 2 nudges per day beyond scheduled check-ins
- **Backoff rule:** If user ignores 2 nudges in a row, pause nudges for 24 hours

### F3: Drift Detection & Re-Engagement
- System tracks patterns across days/weeks:
  - Workout frequency drops
  - Sleep times shift later
  - Meal quality declines (based on user descriptions)
  - Response rate drops (user disengaging)
- Drift triggers a caring, non-judgmental message
- Never accusatory. Always offer a small, achievable action.

### F4: Conversational Data Collection
- The concierge gathers information through natural conversation, not forms
- Extracts structured data from unstructured replies:
  - "I did upper body today" → workout logged (strength, upper body)
  - "Had a salad for lunch" → meal logged (lunch, healthy)
  - "Went to bed at midnight" → sleep logged (00:00)
- No mandatory logging. Partial information is fine.

### F5: Onboarding Conversation
- Structured first-session conversation (not a form):
  - Health goals (fitness, weight, energy, sleep, general wellness)
  - Current routine (workout frequency, typical meals, sleep schedule)
  - Preferred check-in times
  - Tone preference (more direct vs. more gentle)
  - What they struggle with most
- Sets expectations about how the concierge will communicate
- Takes 5–10 minutes

### F6: User-Initiated Conversation
- User can message the concierge anytime to:
  - Ask for advice ("What should I eat before a workout?")
  - Log something ("Just did a 5K run")
  - Adjust settings ("Check in later in the morning")
  - Vent or share context ("Stressful week")
- Concierge responds helpfully and remembers the context

### F7: Device Data Integrations (Day 1)
- **Garmin Forerunner 945:** Training load, activities, heart rate, steps, stress, Body Battery
- **Oura Ring:** Sleep stages, readiness score, HRV, temperature trends
- **Renpho Scales:** Weight, body fat %, muscle mass, trends
- **Data also available via:** Apple Health (aggregates all above), Strava & Garmin Connect (training activities)
- **Integration approach:** Automated scripts that pull data programmatically — no manual export. User should never have to do anything.
- **Principle:** Data enriches the concierge's awareness but never replaces conversation. Even with full sensor data, the concierge still asks how you feel.

### F8: Nutrition Recommendations
- User shares meals they eat (via conversation or photos)
- Concierge **remembers the user's meal repertoire** over time
- Recommends meals from the user's own repertoire based on context:
  - Pre-workout: suggest a meal they've eaten before that's high in carbs
  - Recovery day: suggest a protein-rich meal from their history
  - When patterns drift: "You haven't had that salmon bowl in a while — good option for tonight?"
- Over time, suggests **adjustments** to existing meals (e.g., "Try adding more greens to your pasta dish")
- Does not generate generic meal plans. Works with what the user actually eats.

---

## Non-Goals

1. **Not a medical system.** Will not diagnose, prescribe, or interpret symptoms. Defers to professionals for anything medical.
2. **Not a workout planner.** Will not generate detailed training programs. May suggest general actions (e.g., "take a rest day") but not specific routines.
3. **Not a generic meal planner.** Will not generate abstract meal plans or count macros. Instead, learns the user's actual meals and recommends from their own repertoire, with gradual adjustments over time.
4. **Not a social or community product.** Strictly 1:1. No leaderboards, no sharing, no groups.
5. **Not a data analytics platform.** No charts, graphs, or dashboards in v1. The concierge communicates insights through conversation.
6. **Not a replacement for willpower.** The concierge helps awareness and accountability. It does not force behavior change.

---

## Success Metrics

### Success = Working for 2 People
This is not a SaaS product. Success is measured qualitatively:

| Metric | Target |
|---|---|
| Both users engage with the concierge most days | Feels natural, not forced |
| Concierge uses device data in messages accurately | References sleep, training, weight correctly |
| Users report feeling "someone is watching out for me" | Qualitative check after 2 weeks |
| Nutrition recommendations are relevant | Suggests meals the user actually eats |
| No annoying or irrelevant messages | Zero "I want to turn this off" moments |
| System runs unattended | No daily manual intervention required |

---

## Constraints

1. **Channel:** Telegram as primary channel. Simple, no business verification needed, no 24-hour window constraint.
2. **Privacy:** All health data encrypted at rest and in transit. User can delete all data at any time. No data sold or shared. Compliant with GDPR and HIPAA principles.
3. **Safety:** Hard guardrails against medical advice. Any message touching diagnosis, medication, or symptoms must include a disclaimer and referral to a professional.
4. **Tone:** Must pass the "friend test" — every message should sound like it could come from a caring, knowledgeable friend. Never clinical, never robotic, never guilt-inducing.
5. **Frequency:** Hard cap of 4 outbound messages per day (2 check-ins + 2 nudges max). User can lower this.
6. **Silence handling:** If user is unresponsive for 36+ hours, switch to quiet mode (1 message/day max, low-pressure). After 7 days of silence, send one re-engagement message then pause until user initiates.
7. **Health domains (v1):** Workouts, nutrition, sleep, recovery/rest. No open-ended "habits" category until v2.
