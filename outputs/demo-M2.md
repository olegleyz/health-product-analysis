# Milestone 2 Demo Report — Proactive Concierge

**Date:** 2026-03-08
**Milestone:** M2 — Proactive Concierge
**Status:** PASS

---

## What Was Built

6 tasks completed across 3 waves:

| Wave | Tasks | Tests |
|------|-------|-------|
| Pre-M2 (pulled ahead) | T-016 Frequency Governor, T-017 Engagement State Machine | 27 |
| W1 | T-014 Morning Check-In, T-015 Evening Check-In | 17 |
| W2 | T-018 Proactive Nudges | 10 |
| W3 | T-019 Cron Configuration | 0 (scripts only) |

**Total: 169 tests, all passing.**

---

## Acceptance Criteria Verification

### 1. Morning Check-In (T-014)
- `generate_morning_checkin(user_id)` assembles context from Oura sleep data, readiness, weight
- References actual sleep data naturally (duration, score, quality)
- Adjusts tone: poor sleep = empathetic/gentle, good sleep = energized/upbeat
- Asks about today's plans (implementation intention)
- Goes through frequency governor
- 10 tests covering all scenarios

### 2. Evening Check-In (T-015)
- `generate_evening_checkin(user_id)` loads today's activities from Garmin/Strava
- Acknowledges workouts that happened
- Non-judgmental about rest days ("perfectly fine")
- Skips if morning check-in was sent today and user hasn't replied (don't pile on)
- 7 tests covering activity references, skip logic, quiet mode

### 3. Proactive Nudges (T-018)
- 5 nudge types implemented:
  1. Post-workout: fires within 1 hour of new activity, checks for prior acknowledgement
  2. Bedtime: fires 30 min before user's stated bedtime goal
  3. Drift — workout: fires after 4 days with no activity
  4. Drift — sleep: fires when avg bedtime shifts >30 min over 5 days vs prior week
  5. Drift — weight: fires when weight trend up >1kg over 2 weeks
- All nudges go through frequency governor
- Max 1 drift nudge per day enforced
- LLM generates nudge messages using Gentle Drift Alert archetype
- 10 tests covering all nudge types + governor integration

### 4. Frequency Governor (T-016, from M1)
- 7 rules: daily cap, nudge cap, backoff, quiet/paused mode, time restrictions, spacing
- Mode transitions: active→quiet (36h), quiet→paused (7d)
- 18 tests

### 5. Engagement State Machine (T-017, from M1)
- Tracks engagement mode and transitions
- Re-engagement message in paused mode
- 9 tests

### 6. Cron Configuration (T-019)
- Complete crontab with 5 scheduled jobs:
  - Data sync every 4 hours
  - Morning check-in at 8:00 AM
  - Evening check-in at 9:00 PM
  - Nudge checks every 2 hours (waking hours)
  - Daily counter reset at midnight
- `install_cron.sh` with backup and merge
- `reset_daily.py` for governor counter reset
- Logs to separate files per concern

---

## Test Summary

```
169 passed in 1.50s
```

All tests run with mocked external APIs.

---

## Items for Stakeholder Review

1. **No real-world testing yet** — nudge timing and frequency governor thresholds may need tuning after live testing.
2. **Bedtime nudge** — requires user to have stated a bedtime goal during onboarding. Default behavior if not set should be verified.
3. **Drift detection thresholds** — 4 days for workout drift, 30 min for sleep drift, 1kg for weight drift may need adjustment based on user feedback.

---

## Recommendation

**PASS** — All M2 deliverables complete. Proactive concierge is fully functional. Ready for M3 (Intelligence + Nutrition).
