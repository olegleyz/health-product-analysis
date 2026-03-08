# Personal Health Concierge

## Project Overview
A personal health concierge agent for 1-2 users. Proactively checks in via Telegram about workouts, nutrition, sleep, and recovery. Integrates real device data from Garmin Forerunner 945, Oura Ring, Renpho scales, and Strava. Not a scalable service — success = working for 2 people.

## Key Decisions
- **Scale:** Personal project for 1-2 users. No cloud infra. SQLite, cron, single Python process.
- **Channel:** Telegram (no 24-hour window constraint like WhatsApp)
- **Devices (day 1):** Garmin (`garminconnect` lib), Oura (official API v2), Renpho (reverse-engineered or Garmin fallback), Strava (`stravalib`)
- **LLM:** Claude API (Sonnet for daily use, configurable)
- **Nutrition:** In scope — concierge remembers meals, recommends from user's own repertoire
- **Architecture:** Unified "Concierge Brain" — single Python process with reactive (user messages) and proactive (cron-triggered) paths
- **Storage:** SQLite single file database
- **Deployment:** Mac, Raspberry Pi, or $5 VPS. Cron for scheduled tasks.

## Project Structure
```
agent-team-framework.md          # Reusable 10-agent product/eng workflow
outputs/
  01-vision.md                   # Vision document
  02-product-challenge.md        # Product challenge review
  03-prd.md                      # Product Requirements Document
  04-architecture.md             # Initial architecture
  05-architecture-challenge.md   # Architecture review
  06-final-architecture.md       # Final architecture spec (SQLite schema, components)
  07-implementation-plan.md      # 4-milestone implementation plan
  08-behavioral-science.md       # Tone, messaging, engagement psychology
  09-data-learning.md            # Learning, memory architecture, personalization
  10-safety-ethics.md            # Safety guardrails, medical boundaries, privacy
  spike-data-integration.md      # Data extraction spike (APIs, libraries, auth)
  mvp-experience.md              # MVP UX: mock-ups, sequence diagrams, day-in-the-life
  engineering-backlog.md          # 29 tasks + 4 acceptance gates for engineering agents
```

## Agent Team Framework
To run a new product idea through the 10-agent team:
1. User provides a product concept
2. Run agents 1-7 sequentially (each depends on previous output)
3. Run agents 8-10 in parallel (specialty agents)
4. Output goes to `outputs/` directory

## Engineering Backlog
- Located at `outputs/engineering-backlog.md`
- 29 tasks (T-001 through T-029) + 4 acceptance gates (A-M1, A-M2, A-M3, A-MVP)
- Tasks are ordered by dependency — pick next READY task, implement, verify, mark DONE
- Each task has: description, deliverables, definition of done with specific tests, verification steps
- Milestones: M1 (Foundation + Data), M2 (Proactive Concierge), M3 (Intelligence + Nutrition), M4 (Polish)

## Development Process
- **Full process document:** `outputs/dev-process.md` — READ THIS BEFORE STARTING ANY IMPLEMENTATION WORK
- **Team:** 1 PM Agent (orchestrator) + 4 Engineer Agents (worktrees) + Human Stakeholders
- **Task lifecycle:** READY → ASSIGNED → IN_PROGRESS → IN_REVIEW → DONE
- **Branches:** `feat/T-{number}-{short-name}`, one branch per task, merge to main after review
- **Reviews:** Rotating pairs. Reviews take priority over new tasks. Check correctness, tests, safety, simplicity.
- **Waves:** Tasks grouped by dependency into waves. All tasks in a wave can run in parallel.
- **Acceptance gates:** Demo report + stakeholder review + retro after each milestone
- **Project log:** `outputs/project-log.md` — PM maintains running status
- **Retros:** `outputs/retro-M{N}.md` — after each milestone acceptance
- **Demos:** `outputs/demo-M{N}.md` — evidence-based walkthrough of acceptance criteria

### Code Standards (Quick Reference)
- Python 3.11+, type hints on public functions
- No ORM — raw parameterized SQL. No classes unless needed.
- Config via `.env` + `config.py`. Never hardcode secrets.
- Use `logging` module, not print. Logs go to `logs/`.
- All timestamps ISO 8601. JSON fields as JSON strings in SQLite.
- Every task's required tests must ALL pass. Full suite must not regress.
- No over-engineering. No abstractions for single use cases.

### PM Agent Quick Start
1. Read `outputs/dev-process.md` in full
2. Read `outputs/engineering-backlog.md` for current statuses
3. Read `outputs/project-log.md` and latest `outputs/retro-M{N}.md` if they exist
4. Identify current wave, assign tasks, launch engineers, monitor, review, advance

### Engineer Agent Quick Start
1. Read `outputs/dev-process.md` Sections 3 (Standards) and 4 (Review)
2. Read your assigned task in `outputs/engineering-backlog.md` + all listed context files
3. Read existing code in `health-concierge/` to understand current state
4. Create branch `git checkout -b feat/T-{number}-{short-name}`
5. Implement, write ALL required tests, run `pytest` — everything must pass
6. Commit with message `T-{number}: {what was done}` (include Co-Authored-By trailer)
7. Push to GitHub: `git push -u origin feat/T-{number}-{short-name}`
8. Report completion to PM

### Git Rules
- All work MUST be committed and pushed to the GitHub remote in this repo
- Commit messages reference task ID: `T-002: implement SQLite database layer`
- All commits include `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
- Never commit `.env` or credentials. Stage specific files, not `git add -A`.
- PM pushes `main` after each wave completes and verifies it's up to date

## User Preferences
- Prefers concise, well-structured outputs
- Wants engineering tasks that agents can pick up independently
- Values clear definition of done with specific tests
- Wants mock interfaces and sequence diagrams for visibility
- Does not want over-engineered solutions — keep it simple for 2 users
