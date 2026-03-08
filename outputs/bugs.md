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
