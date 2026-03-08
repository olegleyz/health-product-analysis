# Bug Tracker

## How to Report a Bug

1. Add a new entry below using this template
2. Status: `OPEN` → `IN_PROGRESS` → `FIXED` → `VERIFIED`
3. After fixing, reference the commit hash

---

## BUG-001: LLM hallucinates wrong day of week during onboarding

**Status:** `OPEN`
**Severity:** Medium
**Found:** 2026-03-08 (onboarding)
**Component:** `src/onboarding.py`

**Description:**
During onboarding, the bot said "tomorrow is Wednesday" when today is Sunday. The LLM has no awareness of the current date/time.

**Root cause:**
Onboarding prompts in `_STEP_QUESTIONS` and `_EXTRACTION_PROMPTS` don't include the current date or day of week. The LLM guesses and gets it wrong.

**Fix:**
Add current date/time to the context passed to `call_llm()` in `handle_onboarding_message()`.

---

## BUG-002: LLM flips PM to AM during onboarding

**Status:** `OPEN`
**Severity:** Medium
**Found:** 2026-03-08 (onboarding)
**Component:** `src/onboarding.py`

**Description:**
User said "trail running on Wednesday 6:30pm". The bot repeated it back as "6:30 am".

**Root cause:**
Same as BUG-001 — the LLM is paraphrasing without reliable context. The extraction prompt for "routine" asks for a short summary, and the LLM garbles the time.

**Fix:**
1. Include the user's exact message in the completion summary context so the LLM doesn't need to recall from memory
2. Consider storing extracted times as structured data (e.g. `{"day": "wednesday", "time": "18:30", "activity": "trail running"}`)

---

## BUG-003: Strava sync crashes on SummaryActivity missing attributes

**Status:** `FIXED`
**Severity:** Medium
**Found:** 2026-03-08
**Component:** `src/sync/strava_sync.py`

**Description:**
Strava sync failed with `'SummaryActivity' object has no attribute 'calories'`.

**Root cause:**
`calories`, `description`, `average_heartrate`, `max_heartrate` are only on `DetailedActivity`, not `SummaryActivity` which is what `get_activities()` returns.

**Fix:**
Used `getattr()` with `None` default for those fields.

---

## BUG-004: Bot checks in on tomorrow's plans as if they're happening now

**Status:** `FIXED`
**Severity:** High
**Found:** 2026-03-08
**Component:** `src/brain.py`

**Description:**
After onboarding, the user discussed plans for tomorrow (morning workout, post-workout breakfast). When the user said "ok", the bot immediately started asking about the morning session and breakfast as if tomorrow had already arrived.

**Root cause:**
The reactive message handler in `brain.py` calls the LLM without any current date/time context. The LLM sees conversation about "tomorrow's plans" but has no way to know what "today" is, so it treats future plans as current and starts checking in on them immediately.

**Fix:**
Added current date/time (day of week, full date, time, UTC) to the system prompt in `handle_message()`. Added explicit instruction: "If the user discussed plans for tomorrow, do NOT check in on those plans until that day actually arrives."
