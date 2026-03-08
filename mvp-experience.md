# MVP Experience Document

**What the user sees, what the system does, and how it all connects.**

---

## 1. What Is the MVP?

A Telegram bot that:
- **Proactively checks in** every morning and evening with messages that reference your real health data
- **Responds** when you message it — about workouts, meals, sleep, anything health-related
- **Knows your data** — pulls from Garmin watch, Oura ring, Renpho scales, and Strava automatically
- **Remembers your meals** and recommends from your own repertoire
- **Notices drift** — if your workouts drop, sleep shifts, or weight trends up, it gently flags it
- **Adapts to your silence** — backs off when you're busy, re-engages when you're ready
- **Summarizes your week** every Sunday with a reflection

**What it is NOT:** an app, a dashboard, a fitness tracker, or a medical advisor. It's a conversation partner in Telegram that acts like a caring friend who has access to your health data.

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         YOUR DEVICES                                  │
│                                                                      │
│   🏃 Garmin 945    💍 Oura Ring    ⚖️ Renpho Scale    🚴 Strava     │
└────────┬──────────────┬──────────────┬──────────────┬───────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    DATA SYNC SCRIPTS (cron, every 4h)                │
│                                                                      │
│   garmin_sync.py   oura_sync.py   renpho_sync.py   strava_sync.py  │
│                                                                      │
│   Pull data via APIs → Normalize → Store in SQLite                   │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         SQLite DATABASE                               │
│                                                                      │
│   users │ messages │ device_data │ daily_summaries │ meals           │
│         │          │             │                 │ engagement_state │
└─────────────┬────────────────────────┬──────────────────────────────┘
              │                        │
              ▼                        ▼
┌─────────────────────────┐  ┌─────────────────────────────────────────┐
│     TELEGRAM BOT        │  │          PROACTIVE SCRIPTS (cron)       │
│   (long polling)        │  │                                         │
│                         │  │  8:00 AM  → morning_checkin.py          │
│  User sends message ──┐ │  │  9:00 PM  → evening_checkin.py          │
│                       │ │  │  every 2h → check_nudges.py             │
│                       ▼ │  │  11:30 PM → daily_summary.py            │
│              ┌──────────┴──┴──────────┐  Sun 8 PM → weekly_reflection│
│              │   CONCIERGE BRAIN      │                               │
│              │                        │◄──────────────────────────────┘
│              │  1. Load user context  │
│              │  2. Load device data   │
│              │  3. Load summaries     │
│              │  4. Assemble prompt    │
│              │  5. Call Claude API    │
│              │  6. Safety filter      │
│              │  7. Frequency governor │
│              │  8. Send response      │
│              └────────────────────────┘
│                         │
│  ◄── Response ──────────┘
│                         │
│  User sees message ◄────┘
└─────────────────────────┘
              │
              ▼
┌─────────────────────────┐
│      Claude API         │
│  (Anthropic)            │
│                         │
│  Generates all messages │
│  with persona + context │
└─────────────────────────┘
```

**Everything runs on a single machine** (your Mac or a $5 VPS). No cloud services except Claude API and Telegram.

---

## 3. A Day in the Life — User Experience

### The Full Day Sequence

```
TIME        WHAT HAPPENS                                    WHO INITIATES
─────────── ─────────────────────────────────────────────── ─────────────
06:30 AM    Oura/Garmin data syncs (cron)                   System
08:00 AM    Morning check-in arrives on Telegram            System
08:05 AM    User reads and replies                          User
08:06 AM    Concierge responds                              System
            ─── morning conversation (1-3 exchanges) ───
12:30 PM    User messages about lunch                       User
12:31 PM    Concierge responds, notes the meal              System
02:00 PM    Device data syncs again (cron)                  System
03:30 PM    Nudge: dinner planning (if enabled)             System
05:45 PM    User messages: "heading to the gym"             User
05:46 PM    Concierge: "Nice. Hydrate well. I'll check in   System
             after to see how it went."
07:00 PM    New Garmin activity detected in sync            System
07:15 PM    Nudge check finds new workout                   System
07:16 PM    Post-workout nudge: "Saw you did a 45-min       System
             strength session. How'd it feel?"
09:00 PM    Evening check-in                                System
09:05 PM    User replies about dinner                       User
09:06 PM    Concierge responds, meal noted                  System
10:30 PM    Bedtime nudge (30 min before goal)              System
11:30 PM    Daily summary generated (cron)                  System
```

---

## 4. What the User Sees — Conversation Mock-ups

### 4.1 Morning Check-In (with device data)

```
╔══════════════════════════════════════════════════════════╗
║  Health Concierge                              8:00 AM  ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Morning. Oura shows 7h15m of sleep, readiness    │   ║
║  │ at 82. Solid night. Any workout planned today?   │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
║                          ┌──────────────────────────┐   ║
║                          │ Planning a run after work │   ║
║                          │ around 6pm               │   ║
║                          └──────────────────────────┘   ║
║                                             👤 You      ║
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Good plan. Your Body Battery is at 78, so you've │   ║
║  │ got energy for it. Make sure you eat something    │   ║
║  │ decent by 4. I'll check in after.                 │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

### 4.2 Morning Check-In (after bad sleep)

```
╔══════════════════════════════════════════════════════════╗
║  Health Concierge                              8:00 AM  ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Morning. Rough night — Oura shows 4h50m, and     │   ║
║  │ your readiness is at 54. How are you feeling?     │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
║                          ┌──────────────────────────┐   ║
║                          │ Terrible. Couldn't fall   │   ║
║                          │ asleep until 2am          │   ║
║                          └──────────────────────────┘   ║
║                                             👤 You      ║
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ That's rough. Today might be better as a rest    │   ║
║  │ day or a light walk. Don't push training on low  │   ║
║  │ sleep — it usually backfires. How's your energy? │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

### 4.3 Post-Workout Nudge

```
╔══════════════════════════════════════════════════════════╗
║  Health Concierge                              7:15 PM  ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Saw a 45-min strength session on your Garmin.    │   ║
║  │ How did it feel?                                  │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
║                          ┌──────────────────────────┐   ║
║                          │ Good! Felt strong today.  │   ║
║                          │ Did some deadlifts and    │   ║
║                          │ pull-ups                  │   ║
║                          └──────────────────────────┘   ║
║                                             👤 You      ║
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Nice. Make sure dinner has some protein for      │   ║
║  │ recovery. How about that chicken pasta you had   │   ║
║  │ last week?                                        │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

### 4.4 Nutrition Recommendation (from meal memory)

```
╔══════════════════════════════════════════════════════════╗
║  Health Concierge                              3:30 PM  ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║                          ┌──────────────────────────┐   ║
║                          │ What should I eat for     │   ║
║                          │ dinner? Can't think of    │   ║
║                          │ anything                  │   ║
║                          └──────────────────────────┘   ║
║                                             👤 You      ║
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ You had that salmon bowl a couple times this     │   ║
║  │ month and seemed to enjoy it. Also, you haven't  │   ║
║  │ made the stir-fry in a while — that one's quick  │   ║
║  │ and high-protein. Either would be a good pick    │   ║
║  │ after today's training.                           │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

### 4.5 Evening Check-In

```
╔══════════════════════════════════════════════════════════╗
║  Health Concierge                              9:00 PM  ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Winding down? Good training day — strength       │   ║
║  │ session plus you ate well. How's the evening      │   ║
║  │ going?                                            │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
║                          ┌──────────────────────────┐   ║
║                          │ Good. Had the salmon bowl │   ║
║                          │ btw. Feeling tired now    │   ║
║                          └──────────────────────────┘   ║
║                                             👤 You      ║
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Good choice. Being tired after training is       │   ║
║  │ normal. Try to get to bed by 11 tonight —        │   ║
║  │ your body will thank you tomorrow.                │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

### 4.6 Drift Detection

```
╔══════════════════════════════════════════════════════════╗
║  Health Concierge                    Thursday 10:00 AM  ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ I noticed your last workout was Sunday. That's   │   ║
║  │ 4 days without training — unusual for you. Busy  │   ║
║  │ week, or has motivation dipped? Even a short     │   ║
║  │ walk would help.                                  │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
║                          ┌──────────────────────────┐   ║
║                          │ Yeah just been slammed    │   ║
║                          │ at work                   │   ║
║                          └──────────────────────────┘   ║
║                                             👤 You      ║
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Understood. No pressure. But 20 minutes outside  │   ║
║  │ might actually help with the work stress. Up     │   ║
║  │ to you.                                           │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

### 4.7 Weekly Reflection (Sunday)

```
╔══════════════════════════════════════════════════════════╗
║  Health Concierge                      Sunday 8:00 PM   ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Week in review:                                   │   ║
║  │                                                    │   ║
║  │ Training: 3 sessions (1 run, 2 strength).         │   ║
║  │ Sleep: averaged 6h45m, bedtime crept to 11:30    │   ║
║  │ by Friday. Readiness stayed around 75.            │   ║
║  │ Weight: stable at 82.3 kg.                        │   ║
║  │ Meals: mostly good, sweets crept in Wed+Thu.      │   ║
║  │                                                    │   ║
║  │ The training was consistent — that's a solid      │   ║
║  │ pattern. Sleep is the thing to watch.             │   ║
║  │                                                    │   ║
║  │ What do you want to focus on next week?           │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

### 4.8 Silence Handling

```
╔══════════════════════════════════════════════════════════╗
║  Health Concierge                                       ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  ── User hasn't replied in 2 days ──                    ║
║                                                          ║
║  🤖 Concierge (quiet mode):                            ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ No need to reply. Just here when you're ready.   │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
║  ── 5 more days pass. No reply. ──                      ║
║                                                          ║
║  🤖 Concierge (paused → re-engagement):                ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Hey. Whenever you want to pick back up, I'm      │   ║
║  │ here. No catch-up needed.                         │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
║  ── System goes fully silent. Waits. ──                 ║
║                                                          ║
║  ── 3 days later, user messages ──                      ║
║                          ┌──────────────────────────┐   ║
║                          │ Hey, I'm back            │   ║
║                          └──────────────────────────┘   ║
║                                             👤 You      ║
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Welcome back. How are things? Want to do a       │   ║
║  │ quick reset — what are you focusing on this      │   ║
║  │ week?                                             │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

### 4.9 Onboarding (First Interaction)

```
╔══════════════════════════════════════════════════════════╗
║  Health Concierge                                       ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║                          ┌──────────────────────────┐   ║
║                          │ /start                    │   ║
║                          └──────────────────────────┘   ║
║                                             👤 You      ║
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Hey. I'm your health concierge — I'll check in  │   ║
║  │ with you about workouts, meals, sleep, and       │   ║
║  │ recovery. I have access to your Garmin, Oura,    │   ║
║  │ and scale data, so I already know some things.   │   ║
║  │                                                    │   ║
║  │ Let's set things up. What's your name?            │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
║                          ┌──────────────────────────┐   ║
║                          │ Oleg                      │   ║
║                          └──────────────────────────┘   ║
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ Good to meet you, Oleg. What are you most        │   ║
║  │ trying to improve — fitness, nutrition, sleep,    │   ║
║  │ or just staying consistent overall?               │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
║                          ┌──────────────────────────┐   ║
║                          │ Mostly consistency. I     │   ║
║                          │ know what to do but I     │   ║
║                          │ drift when work gets busy │   ║
║                          └──────────────────────────┘   ║
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ That's exactly what I'm here for. I'll check in │   ║
║  │ daily to keep things on your radar.              │   ║
║  │                                                    │   ║
║  │ How often do you typically train when things are  │   ║
║  │ going well?                                       │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
║        ... continues through goals, schedule, tone ...  ║
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ All set. I'll check in tomorrow morning around   │   ║
║  │ 8. Talk to you then.                              │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

### 4.10 Safety — Medical Question Handling

```
╔══════════════════════════════════════════════════════════╗
║  Health Concierge                                       ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║                          ┌──────────────────────────┐   ║
║                          │ I've been having knee     │   ║
║                          │ pain after runs. Should   │   ║
║                          │ I take ibuprofen?         │   ║
║                          └──────────────────────────┘   ║
║                                             👤 You      ║
║                                                          ║
║  🤖 Concierge:                                          ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │ I can't advise on medication — that's one for    │   ║
║  │ a doctor or physio. What I can say is that       │   ║
║  │ persistent knee pain after running is worth      │   ║
║  │ getting checked out, especially before it        │   ║
║  │ becomes a bigger problem. In the meantime, you   │   ║
║  │ could try lower-impact activities — cycling or   │   ║
║  │ swimming — to keep moving without the strain.    │   ║
║  └──────────────────────────────────────────────────┘   ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

---

## 5. Sequence Diagrams

### 5.1 Reactive Flow (User Sends a Message)

```
User              Telegram API       Bot (long poll)      Brain            DB              Claude API
 │                     │                  │                 │                │                  │
 │  Send message       │                  │                 │                │                  │
 │────────────────────>│                  │                 │                │                  │
 │                     │  Deliver update  │                 │                │                  │
 │                     │─────────────────>│                 │                │                  │
 │                     │                  │  save inbound   │                │                  │
 │                     │                  │────────────────────────────────>│                  │
 │                     │                  │                 │                │                  │
 │                     │                  │  handle_message │                │                  │
 │                     │                  │────────────────>│                │                  │
 │                     │                  │                 │  load context  │                  │
 │                     │                  │                 │───────────────>│                  │
 │                     │                  │                 │  user profile  │                  │
 │                     │                  │                 │<───────────────│                  │
 │                     │                  │                 │  recent msgs   │                  │
 │                     │                  │                 │<───────────────│                  │
 │                     │                  │                 │  device data   │                  │
 │                     │                  │                 │<───────────────│                  │
 │                     │                  │                 │  summaries     │                  │
 │                     │                  │                 │<───────────────│                  │
 │                     │                  │                 │  meals         │                  │
 │                     │                  │                 │<───────────────│                  │
 │                     │                  │                 │                │                  │
 │                     │                  │                 │  assemble prompt (persona +      │
 │                     │                  │                 │  context + user message)          │
 │                     │                  │                 │                │                  │
 │                     │                  │                 │  generate response                │
 │                     │                  │                 │─────────────────────────────────>│
 │                     │                  │                 │                │    response text │
 │                     │                  │                 │<─────────────────────────────────│
 │                     │                  │                 │                │                  │
 │                     │                  │                 │  safety filter │                  │
 │                     │                  │                 │  (pass/block)  │                  │
 │                     │                  │                 │                │                  │
 │                     │                  │                 │  extract data  │                  │
 │                     │                  │                 │  (optional LLM)│                  │
 │                     │                  │                 │                │                  │
 │                     │                  │  response text  │                │                  │
 │                     │                  │<────────────────│                │                  │
 │                     │                  │                 │                │                  │
 │                     │                  │  save outbound + extracted data │                  │
 │                     │                  │────────────────────────────────>│                  │
 │                     │                  │  update engagement state        │                  │
 │                     │                  │────────────────────────────────>│                  │
 │                     │                  │                 │                │                  │
 │                     │  Send message    │                 │                │                  │
 │                     │<─────────────────│                 │                │                  │
 │  Receive response   │                  │                 │                │                  │
 │<────────────────────│                  │                 │                │                  │
```

### 5.2 Proactive Flow (Morning Check-In)

```
Cron               morning_checkin.py    Brain            DB              Claude API       Telegram API      User
 │                       │                 │                │                  │                │              │
 │  trigger (8:00 AM)   │                 │                │                  │                │              │
 │──────────────────────>│                 │                │                  │                │              │
 │                       │                 │                │                  │                │              │
 │                       │  for each user: │                │                  │                │              │
 │                       │                 │                │                  │                │              │
 │                       │  check governor │                │                  │                │              │
 │                       │────────────────────────────────>│                  │                │              │
 │                       │  can_send? ─────────────────────│                  │                │              │
 │                       │  (check mode, caps, timing)     │                  │                │              │
 │                       │<────────────────────────────────│                  │                │              │
 │                       │                 │                │                  │                │              │
 │                       │  if YES:        │                │                  │                │              │
 │                       │  generate_morning_checkin        │                  │                │              │
 │                       │────────────────>│                │                  │                │              │
 │                       │                 │  load context  │                  │                │              │
 │                       │                 │  (same as      │                  │                │              │
 │                       │                 │   reactive     │                  │                │              │
 │                       │                 │   flow)        │                  │                │              │
 │                       │                 │                │                  │                │              │
 │                       │                 │  + load last night's sleep (Oura)│                │              │
 │                       │                 │  + load today's Body Battery     │                │              │
 │                       │                 │  + load weight trend             │                │              │
 │                       │                 │───────────────>│                  │                │              │
 │                       │                 │  device data   │                  │                │              │
 │                       │                 │<───────────────│                  │                │              │
 │                       │                 │                │                  │                │              │
 │                       │                 │  assemble prompt                  │                │              │
 │                       │                 │  (persona + context +             │                │              │
 │                       │                 │   "generate morning check-in")    │                │              │
 │                       │                 │                │                  │                │              │
 │                       │                 │  call LLM      │                  │                │              │
 │                       │                 │─────────────────────────────────>│                │              │
 │                       │                 │                │   check-in text │                │              │
 │                       │                 │<─────────────────────────────────│                │              │
 │                       │                 │                │                  │                │              │
 │                       │                 │  safety filter │                  │                │              │
 │                       │                 │  frequency gov │                  │                │              │
 │                       │                 │                │                  │                │              │
 │                       │  message text   │                │                  │                │              │
 │                       │<────────────────│                │                  │                │              │
 │                       │                 │                │                  │                │              │
 │                       │  save to DB     │                │                  │                │              │
 │                       │────────────────────────────────>│                  │                │              │
 │                       │  update engagement state        │                  │                │              │
 │                       │────────────────────────────────>│                  │                │              │
 │                       │                 │                │                  │                │              │
 │                       │  send via Telegram              │                  │                │              │
 │                       │─────────────────────────────────────────────────────────────────────>│              │
 │                       │                 │                │                  │                │  deliver     │
 │                       │                 │                │                  │                │─────────────>│
 │                       │                 │                │                  │                │              │
 │                       │                 │                │                  │                │              │
 │                       │                 │                │                  │     User reads │              │
 │                       │                 │                │                  │     and replies │              │
 │                       │                 │                │                  │     (→ reactive│flow)         │
```

### 5.3 Data Sync Flow

```
Cron               sync_all.py        oura_sync.py     Oura API          DB
 │                     │                   │                │                │
 │  trigger (every 4h) │                   │                │                │
 │────────────────────>│                   │                │                │
 │                     │                   │                │                │
 │                     │  sync_oura()      │                │                │
 │                     │──────────────────>│                │                │
 │                     │                   │  GET /sleep    │                │
 │                     │                   │───────────────>│                │
 │                     │                   │  sleep data    │                │
 │                     │                   │<───────────────│                │
 │                     │                   │  GET /readiness│                │
 │                     │                   │───────────────>│                │
 │                     │                   │  readiness data│                │
 │                     │                   │<───────────────│                │
 │                     │                   │                │                │
 │                     │                   │  normalize + save               │
 │                     │                   │───────────────────────────────>│
 │                     │                   │                │                │
 │                     │  {oura: 2 sleep, 2 readiness}     │                │
 │                     │<──────────────────│                │                │
 │                     │                   │                │                │
 │                     │  (repeat for garmin, strava, renpho)               │
 │                     │                   │                │                │
 │                     │  log summary      │                │                │
 │                     │  "oura: 2 sleep, 2 readiness |                    │
 │                     │   garmin: 3 activities, 1 sleep |                  │
 │                     │   strava: 2 activities |                           │
 │                     │   renpho: 1 weight"                                │
```

### 5.4 Daily Summary Flow

```
Cron               daily_summary.py    Summarizer         DB              Claude API
 │                     │                   │                │                  │
 │  trigger (11:30 PM) │                   │                │                  │
 │────────────────────>│                   │                │                  │
 │                     │                   │                │                  │
 │                     │  for each user:   │                │                  │
 │                     │  generate_summary │                │                  │
 │                     │──────────────────>│                │                  │
 │                     │                   │  load today's  │                  │
 │                     │                   │  messages      │                  │
 │                     │                   │───────────────>│                  │
 │                     │                   │  load today's  │                  │
 │                     │                   │  device data   │                  │
 │                     │                   │───────────────>│                  │
 │                     │                   │                │                  │
 │                     │                   │  prompt: "Summarize this day"    │
 │                     │                   │  (messages + device data)        │
 │                     │                   │─────────────────────────────────>│
 │                     │                   │                │                  │
 │                     │                   │  {summary: "...", structured: {}}│
 │                     │                   │<─────────────────────────────────│
 │                     │                   │                │                  │
 │                     │                   │  save to daily_summaries         │
 │                     │                   │───────────────>│                  │
 │                     │                   │                │                  │
 │                     │  done             │                │                  │
 │                     │<──────────────────│                │                  │
```

---

## 6. Message Volume — What a Typical Day Looks Like

```
DAILY OUTBOUND MESSAGES (max 4):

Typical active day:
  1. Morning check-in                 8:00 AM     (scheduled)
  2. Post-workout nudge               7:15 PM     (triggered by Garmin data)
  3. Evening check-in                 9:00 PM     (scheduled)
  = 3 messages

Typical rest day:
  1. Morning check-in                 8:00 AM     (scheduled)
  2. Evening check-in                 9:00 PM     (scheduled)
  = 2 messages

Busy day (user doesn't reply to morning):
  1. Morning check-in                 8:00 AM     (scheduled)
  = 1 message (evening skipped because morning unanswered)

Drift day (no workout in 4 days):
  1. Morning check-in                 8:00 AM     (scheduled)
  2. Drift nudge                     10:00 AM     (triggered)
  3. Evening check-in                 9:00 PM     (scheduled)
  = 3 messages

Quiet mode (user silent 2+ days):
  1. Single low-pressure message     10:00 AM     (scheduled)
  = 1 message

Sunday:
  1. Morning check-in                 8:00 AM     (scheduled)
  2. Weekly reflection                8:00 PM     (replaces evening check-in)
  = 2 messages
```

**The user also sends messages** (replies + unsolicited) — the concierge always responds, but those responses don't count against the outbound cap.

---

## 7. What the System Knows (Data Sources Summary)

```
┌─────────────────────────────────────────────────────────────────┐
│                     CONCIERGE'S AWARENESS                        │
├─────────────────────┬───────────────────────────────────────────┤
│ FROM OURA RING      │ Sleep: duration, stages, efficiency       │
│                     │ Readiness: score, contributors             │
│                     │ HRV: overnight average                     │
│                     │ Activity: steps, calories                  │
│                     │ Temperature trend                          │
├─────────────────────┼───────────────────────────────────────────┤
│ FROM GARMIN 945     │ Activities: type, duration, HR, pace       │
│                     │ Training effect & training status           │
│                     │ Body Battery: level, charged, drained      │
│                     │ Stress: average daily stress                │
│                     │ Steps & distance                            │
│                     │ Resting heart rate                          │
├─────────────────────┼───────────────────────────────────────────┤
│ FROM RENPHO SCALE   │ Weight                                     │
│                     │ Body fat %                                  │
│                     │ Muscle mass                                 │
│                     │ BMI                                         │
├─────────────────────┼───────────────────────────────────────────┤
│ FROM STRAVA         │ Activities with social context              │
│                     │ Detailed GPS/route data                     │
│                     │ Activity descriptions                       │
├─────────────────────┼───────────────────────────────────────────┤
│ FROM CONVERSATION   │ Meals (what the user eats)                 │
│                     │ Energy / mood (how they feel)               │
│                     │ Plans & intentions (what they'll do)        │
│                     │ Challenges (what's hard right now)          │
│                     │ Context (work stress, travel, life events)  │
├─────────────────────┼───────────────────────────────────────────┤
│ LEARNED OVER TIME   │ Meal repertoire (favorite meals + tags)    │
│                     │ Workout patterns (frequency, types, times)  │
│                     │ Sleep patterns (typical bedtime, quality)    │
│                     │ Drift triggers (what causes lapses)         │
│                     │ Communication preferences (tone, frequency) │
│                     │ Motivation style (progress vs. routine)     │
└─────────────────────┴───────────────────────────────────────────┘
```
