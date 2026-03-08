# Spike: Health Data Integration — Programmatic Access

**Date:** 2026-03-07
**Goal:** Identify the easiest scripted path to pull personal health data from Garmin, Oura, Renpho, Apple Health, and Strava into a local pipeline on macOS. No manual steps, 1-2 user scale.

---

## 1. Garmin (Forerunner 945)

### Official API
- Garmin has a **Health API** and **Wellness API**, but they are restricted to approved partners/enterprises. Individual developers cannot get access without a business relationship. Not viable for personal use.

### Recommended: `garminconnect` (Python, unofficial)
- **PyPI:** `garminconnect` (formerly `python-garminconnect`)
- **How it works:** Screen-scrapes / reverse-engineers the Garmin Connect web session. Authenticates with your Garmin Connect username + password, then hits internal JSON endpoints.
- **Data available:** Activities, sleep, heart rate (daily + timestamped), steps, stress, body composition, training status, VO2max, and more.
- **Auth:** Username + password. Garmin uses SSO with CSRF tokens; the library handles the flow. MFA/2FA can be a blocker — if your account has it enabled, you may need to use a session token or OAuth workaround (the library has added support for handling this via TOTP or session reuse).
- **Session caching:** The library supports serializing the session (cookies/tokens) to disk so you don't re-auth on every run. This is important — Garmin will rate-limit or temporarily lock accounts that auth too frequently.
- **Install:** `pip install garminconnect`
- **Maturity:** Actively maintained, widely used in Home Assistant and personal projects. Breakage risk exists (Garmin can change internal APIs), but the maintainer is responsive.

### Gotchas
- Not an official API — can break without notice when Garmin changes endpoints.
- Rate limiting: Don't poll more than a few times per day. Once or twice daily is safe.
- MFA: If enabled on the Garmin account, requires extra handling (TOTP seed or session token persistence).
- Garmin Connect sometimes returns partial data if the watch hasn't synced yet.

### Verdict: **GREEN** — `garminconnect` is the clear path. Works well for personal cron-job use.

---

## 2. Oura Ring

### Official API (v2)
- **Oura has a proper public REST API (v2)** available to individual users.
- **Portal:** `cloud.ouraring.com/v2/docs` (Swagger docs available)
- **Auth:** Personal Access Token (PAT). Generate one at `cloud.ouraring.com/personal-access-tokens`. No OAuth dance needed for personal use — just an API key in the `Authorization: Bearer <token>` header.
- **Data available:** Daily sleep, daily readiness, daily activity, heart rate, sleep periods (detailed hypnogram), SpO2, ring temperature, workouts, tags.
- **Rate limits:** Generous for personal use (5000 requests/day for PAT).
- **Format:** JSON, well-documented.

### Python libraries
- **`oura-ring`** (PyPI: `oura-ring`): Lightweight wrapper around the v2 API. Active, clean interface.
- **`python-ouraring`**: Older, targeted v1 API (deprecated by Oura). Avoid.
- Alternatively, since the API is straightforward REST+JSON, you can just use `httpx` or `requests` directly with minimal code.

### Gotchas
- The v2 API sometimes lags behind the app by a few hours for sleep data (processing delay).
- Historical data access: You can query any date range for your own data — no restrictions.
- PATs don't expire unless you revoke them.

### Verdict: **GREEN** — Best developer experience of all five sources. Official API + PAT = trivial to script.

---

## 3. Renpho Scales

### Official API
- **None.** Renpho has no public API. The data lives in the Renpho cloud, accessible only through their mobile app.

### Reverse-engineered access
- **`renpho-api`** (GitHub): A community reverse-engineered Python client that logs into the Renpho cloud using your email/password and pulls weight + body composition data (weight, BMI, body fat %, muscle mass, bone mass, water %, etc.).
- **How it works:** Mimics the mobile app's HTTP calls to Renpho's backend servers. Auth is email + password, returns a session token.
- **PyPI:** Check for `renpho-api` or install from GitHub directly.
- **Stability:** Fragile — Renpho can change their backend at any time. The community library has had periods of breakage.

### Alternative paths
1. **Apple Health export** — Renpho syncs weight + body composition to Apple Health. If you go the Apple Health export route, you get Renpho data for free.
2. **Renpho CSV export** — The app has a manual CSV export feature, but it's not scriptable.
3. **Home Assistant integration** — There's a Renpho integration for HA that keeps the reverse-engineering maintained.

### Gotchas
- Renpho's servers are sometimes slow/unreliable.
- No rate limit documentation (since it's unofficial), but low-frequency polling (1x/day) should be fine.
- Account lockout risk is low but theoretically possible.

### Verdict: **YELLOW** — Reverse-engineered API exists but is fragile. Recommended fallback: pull Renpho data from Apple Health instead.

---

## 4. Apple Health

### Official export mechanism
- Apple Health has **no REST API and no direct programmatic access** from a Mac script.
- The standard approach is a **manual XML export** from the Health app on iPhone (Settings > Health > Export All Health Data). This produces a ZIP containing `export.xml` — a massive XML file with all records.

### Programmatic paths on macOS

#### Option A: Shortcuts + Automation (iPhone-side)
- Use **Apple Shortcuts** on the iPhone to query HealthKit and push data somewhere (e.g., write to iCloud Drive, POST to a local server, save to a file).
- Limitations: Shortcuts HealthKit access is limited — you can read samples but the automation options are clunky. Not reliable for a full pipeline.

#### Option B: Periodic XML export + parse on Mac
- Automate the export trigger via Shortcuts (there's a "Export Health Data" shortcut action), save the ZIP to iCloud Drive, then have a Mac-side script pick it up and parse it.
- **Python parsing:** The XML export is well-structured. Libraries:
  - **`apple-health-parser`** (PyPI): Parses the Apple Health XML export into pandas DataFrames.
  - **Manual parsing** with `lxml` or `xml.etree.ElementTree` — straightforward since the schema is simple (`Record` elements with type, value, date attributes).
- File size warning: The export XML can be 1-5+ GB for users with years of data. Use streaming/iterative XML parsing (`iterparse`), not DOM parsing.

#### Option C: HealthKit via Swift/Python bridge (iPhone app)
- Write a small iOS app or use Pythonista on iPhone to query HealthKit directly. Overkill for this use case.

#### Option D: Skip Apple Health entirely
- Since we have direct API access to Garmin, Oura, and Strava, and Renpho is the only source where Apple Health is the easiest extraction path — consider pulling from each source directly and only using Apple Health for Renpho data (or skip Apple Health altogether and use the Renpho reverse-engineered API).

### Gotchas
- Apple Health XML export is **not incremental** — it's a full dump every time. For daily automation, this is wasteful but workable.
- The export requires user interaction on the iPhone (even via Shortcuts, it prompts for confirmation). True zero-touch automation is difficult.
- Parsing is CPU/memory intensive for large exports.

### Verdict: **YELLOW** — Usable as a fallback for Renpho data, but not ideal as the primary integration path. Direct source APIs are better for Garmin, Oura, and Strava.

---

## 5. Strava

### Official API
- **Strava has a well-documented public API (v3).**
- **Docs:** `developers.strava.com`
- **Auth:** OAuth 2.0. For personal use, you create an app at `strava.com/settings/api`, which gives you a `client_id`, `client_secret`, and an initial `refresh_token`. After a one-time browser-based authorization, you can use the refresh token to get access tokens programmatically forever.
- **Data available:** Activities (detailed: GPS, HR, power, laps, splits), athlete profile, segments, routes. Activity streams (time-series data for HR, pace, cadence, etc.).
- **Rate limits:** 100 requests/15 min, 1000 requests/day. Fine for personal use.

### Python libraries
- **`stravalib`** (PyPI: `stravalib`): Mature, well-maintained, Pythonic wrapper around the Strava v3 API. Handles OAuth token refresh, pagination, and model objects. The standard choice.
- **`stravaio`** (PyPI: `stravaio`): Lighter alternative, stores data locally in a structured way. Less popular but functional.
- **Recommendation:** Use `stravalib`. It's the community standard.

### Auth bootstrap (one-time)
1. Register an app at `strava.com/settings/api`.
2. Visit the authorization URL in a browser, grant access.
3. Exchange the code for access + refresh tokens.
4. Store the refresh token. Your script uses it to auto-refresh access tokens on each run.

This one-time browser step is unavoidable but only happens once. After that, fully automated.

### Gotchas
- Strava's API gives you **your own data** freely, but detailed activity streams require one API call per activity.
- If you already get activities from Garmin (which syncs to Strava), you may have duplicate data. Decide which is the source of truth.
- Webhook support exists (Strava can push to you when new activities are uploaded), but for a personal cron job, polling is simpler.

### Verdict: **GREEN** — Official API + `stravalib` is solid and reliable.

---

## Summary Matrix

| Source | API Type | Auth | Python Library | Stability | Day-1 Ready |
|--------|----------|------|---------------|-----------|-------------|
| **Garmin** | Unofficial (reverse-eng) | Username/password | `garminconnect` | Medium (can break) | Yes |
| **Oura** | Official REST v2 | Personal Access Token | `oura-ring` or raw `requests` | High | Yes |
| **Renpho** | Unofficial (reverse-eng) | Username/password | `renpho-api` (GitHub) | Low (fragile) | Maybe |
| **Apple Health** | XML export (manual trigger) | None (local file) | `apple-health-parser` / `lxml` | High (format stable) | No (needs manual step) |
| **Strava** | Official REST v3 | OAuth 2.0 (one-time setup) | `stravalib` | High | Yes |

---

## Recommended Path of Least Resistance

### Day-1 Integration Plan

1. **Oura** — Start here. Create a PAT at `cloud.ouraring.com`, `pip install oura-ring`, and you're pulling sleep/readiness/activity data in 10 minutes. Zero friction.

2. **Strava** — Register an API app, do the one-time OAuth dance, `pip install stravalib`. After the initial token exchange, fully automated. 20 minutes setup.

3. **Garmin** — `pip install garminconnect`, authenticate with credentials. Consider disabling MFA on Garmin Connect or setting up TOTP-based auth in the script. Cache sessions to avoid repeated logins. 30 minutes setup.

4. **Renpho** — Two options:
   - **Option A (easier):** Use `renpho-api` from GitHub if it's currently working. Test it first.
   - **Option B (more reliable):** Set up a weekly Apple Health export via iPhone Shortcuts, save to iCloud Drive, parse the XML on your Mac with `lxml`. Only needed for weight/body-comp data.
   - **Option C (simplest):** If Garmin Connect has your Renpho data (some scales sync to Garmin), pull it via `garminconnect` — body composition is available through that API.

5. **Apple Health** — Skip as a primary source. Use it only as a fallback for Renpho data if the reverse-engineered API breaks.

### Architecture Sketch

```
[Cron / launchd on Mac — runs 1-2x daily]
    |
    ├── garmin_pull.py    → garminconnect → activities, sleep, HR, training
    ├── oura_pull.py      → oura REST v2  → sleep, readiness, activity, HRV
    ├── strava_pull.py    → stravalib     → detailed activities, streams
    ├── renpho_pull.py    → renpho-api    → weight, body composition
    |
    └── store locally (SQLite / CSV / JSON) → analysis / dashboards
```

### Key Dependencies (pip)

```
garminconnect
oura-ring
stravalib
requests
lxml          # only if parsing Apple Health XML
```

---

## Blockers and Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Garmin changes internal API | `garminconnect` breaks | Pin version, monitor GitHub issues, have Apple Health XML as backup |
| Garmin MFA enforcement | Auth flow breaks | Use TOTP seed in script, or cache long-lived sessions |
| Renpho API instability | Can't pull weight data | Fall back to Apple Health XML or Garmin (if synced) |
| Strava OAuth token expiry | Script stops working | `stravalib` handles refresh automatically if you persist the refresh token |
| Apple Health export is manual | Can't fully automate | Only use as fallback; primary sources have direct API access |
| Rate limiting (all sources) | Temporary blocks | Run 1-2x daily max, cache data locally, don't re-fetch what you already have |

---

## Data Overlap and Deduplication

Since multiple sources record similar metrics, decide on a source-of-truth hierarchy:

| Metric | Primary Source | Why |
|--------|---------------|-----|
| Sleep | **Oura** | Most detailed sleep staging, HRV, temperature |
| Resting HR / HRV | **Oura** (overnight), **Garmin** (24h) | Oura for nighttime, Garmin for daytime |
| Activities / Training | **Garmin** (raw) or **Strava** (if you want social/segment data) | Garmin has richer training metrics (Training Effect, VO2max estimate) |
| Weight / Body Comp | **Renpho** (direct) | Only source for this data |
| Readiness / Recovery | **Oura** | Garmin has "Body Battery" but Oura's readiness score is more holistic |
| Steps / Daily Activity | **Garmin** | Watch is worn all day; Oura captures less movement detail |

---

*This spike is based on the state of these libraries and APIs as of early 2025. Verify current status of unofficial libraries (`garminconnect`, `renpho-api`) before implementation — they can break and get fixed on short cycles. Check their GitHub repos for recent issues/commits.*
