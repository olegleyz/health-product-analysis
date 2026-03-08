# Development Process — AI Engineering Team

**Project:** Personal Health Concierge
**Team:** 1 PM Agent + 4 Engineer Agents + Human Stakeholders (Product + Principal Eng)

---

## 1. Team Structure

### Roles

| Role | Who | Responsibility |
|------|-----|---------------|
| **PM Agent** | Claude Code session (orchestrator) | Assigns tasks, tracks progress, runs retros/demos, unblocks engineers, maintains backlog status |
| **Engineer 1 — Core** | Claude Code session (worktree) | DB, Bot, Brain, Onboarding |
| **Engineer 2 — Data** | Claude Code session (worktree) | All 4 data syncs, Sync Runner, Daily Summaries, Meals |
| **Engineer 3 — LLM/Behavior** | Claude Code session (worktree) | Claude client, Persona, Safety, Governor, Engagement, Nudges |
| **Engineer 4 — Flex** | Claude Code session (worktree) | Overflow from any track, integration tasks, cron, polish. Fills review gaps. |
| **Human Stakeholders** | Product Manager + Principal Engineer | Approve acceptance gates, attend demos/retros, provide feedback |

### Ownership Map

```
Engineer 1 (Core):     T-001, T-002, T-003, T-006, T-013
Engineer 2 (Data):     T-008, T-009, T-010, T-011, T-012, T-020, T-022, T-023
Engineer 3 (Behavior): T-004, T-005, T-007, T-016, T-017, T-014, T-015, T-018
Engineer 4 (Flex):     T-019, T-021, T-024, T-025, T-026, T-027, T-028, T-029
```

### Review Rotation

Each engineer reviews the work of one other (rotating):
```
Eng 1 reviews → Eng 2
Eng 2 reviews → Eng 3
Eng 3 reviews → Eng 4
Eng 4 reviews → Eng 1
```

The PM Agent rotates the review pairs every milestone to ensure cross-pollination.

---

## 2. Task Lifecycle

```
READY → ASSIGNED → IN_PROGRESS → IN_REVIEW → DONE
                        ↓              ↓
                    BLOCKED        CHANGES_REQUESTED → IN_PROGRESS
```

### Status Definitions

| Status | Meaning |
|--------|---------|
| `READY` | All dependencies DONE. Can be picked up. |
| `ASSIGNED` | PM has assigned to an engineer. Not yet started. |
| `IN_PROGRESS` | Engineer is actively implementing. |
| `IN_REVIEW` | PR/diff submitted. Reviewer is evaluating. |
| `CHANGES_REQUESTED` | Reviewer found issues. Engineer must address. |
| `DONE` | Code merged, all tests pass, reviewer approved. |
| `BLOCKED` | Waiting on dependencies or external input. |
| `BUG` | Defect found during acceptance. Needs fix. |

### Task Assignment Rules

1. PM Agent checks `engineering-backlog.md` for tasks where all dependencies are `DONE`
2. Assigns based on ownership map (see above)
3. If the primary owner is busy, assigns to Eng 4 (Flex) or whoever is free
4. Never assign more than 2 active tasks to one engineer (1 preferred)
5. When assigning, PM updates the task status in `engineering-backlog.md`

---

## 3. Implementation Standards

### Git & GitHub

**Repository:** The project lives in the current directory (`/Users/oleizerov/Documents/private/health`), which is a git repo. All work MUST be committed and pushed to the GitHub remote.

**Commit rules:**
- Every meaningful unit of work gets a commit. Don't accumulate large uncommitted changes.
- Commit messages: concise, imperative mood. Reference the task ID. Example: `T-002: implement SQLite database layer and access functions`
- All commits include: `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
- Never commit secrets (`.env`, credentials). `.gitignore` must exclude them.
- Stage specific files — avoid `git add -A` to prevent accidentally committing sensitive files.

**Branch Strategy:**

```
main                          ← stable, passes all tests
├── feat/T-001-scaffolding    ← one branch per task
├── feat/T-002-database
├── feat/T-004-llm-client     ← parallel branches OK when no conflicts
└── ...
```

- Branch naming: `feat/T-{number}-{short-name}`
- One branch per task. One PR per task.
- Merge to `main` only after review approval + all tests pass.
- No force pushes. No rebasing shared branches.
- **Push every branch to the remote** (`git push -u origin feat/T-XXX-name`) before requesting review.

**Push Policy:**
- Engineers push their feature branch to GitHub when moving to `IN_REVIEW`.
- After review approval, merge to `main` and push main: `git push origin main`.
- PM Agent verifies `main` is pushed after each wave completes.
- At acceptance gates, `main` on GitHub must reflect the full milestone.

**PR Workflow (if using GitHub PRs):**
- Engineer creates PR from feature branch → main.
- Reviewer reviews on the PR (or locally — either is fine).
- Merge via the PR (squash or merge commit — team's choice).
- If not using formal GitHub PRs (simpler flow): merge locally, push main. The branch + commits serve as the audit trail.

### Code Standards

1. **Python 3.11+**. Type hints on all public functions.
2. **No ORM** — raw SQL with parameterized queries (prevent injection).
3. **No classes unless needed** — prefer simple functions and dicts. This is a 2-user project.
4. **Config via `.env`** — never hardcode secrets. Use `config.py` for typed access.
5. **Logging** — use Python `logging` module, not print statements. Log to files under `logs/`.
6. **Error handling** — catch specific exceptions. Log errors. Never silently swallow. Never crash the bot.
7. **JSON fields** — store as JSON strings in SQLite, deserialize on read.
8. **Timestamps** — always ISO 8601 strings. Always include timezone or use UTC.
9. **No over-engineering** — no abstractions for 1 use case. No factories, registries, or plugin systems.

### Testing Standards

1. Every task has `Required tests` in the backlog — implement ALL of them.
2. Tests go in `tests/test_{module}.py`.
3. Use `pytest`. Mock external APIs (Garmin, Oura, Strava, Renpho, Claude, Telegram).
4. **All tests must pass before requesting review.**
5. Integration tests (requiring real credentials) are documented but not run in CI — run manually.
6. Test naming: `test_{behavior_being_tested}` — descriptive, not `test_1`.

### Definition of Done (per task)

A task is DONE when ALL of the following are true:
- [ ] All deliverables listed in the task exist and work
- [ ] All required tests pass (`pytest tests/test_{module}.py`)
- [ ] Full test suite still passes (`pytest`) — no regressions
- [ ] Code follows standards above
- [ ] All changes committed to the feature branch with descriptive message referencing task ID
- [ ] Feature branch pushed to GitHub remote
- [ ] PR reviewed and approved by assigned reviewer
- [ ] Branch merged to `main` and `main` pushed to GitHub
- [ ] Task status updated in `engineering-backlog.md`

---

## 4. Code Review Process

### What the Reviewer Checks

1. **Correctness:** Does the code do what the task requires?
2. **Tests:** Are all required tests present and meaningful (not just passing trivially)?
3. **Safety:** No hardcoded secrets, no SQL injection, no unvalidated input at boundaries.
4. **Standards:** Follows code standards (see above).
5. **Simplicity:** No over-engineering. Would a simpler approach work?
6. **Integration:** Does it break or conflict with existing code?
7. **Edge cases:** Does it handle missing data, empty responses, API errors?

### Review Workflow

1. Engineer finishes task → sets status to `IN_REVIEW`
2. Engineer writes a brief summary: what was built, key decisions, anything non-obvious
3. Reviewer reads the diff + runs `pytest`
4. Reviewer either:
   - **Approves** → Engineer merges to main, sets status `DONE`
   - **Requests changes** → Lists specific issues. Status → `CHANGES_REQUESTED`. Engineer fixes and re-submits.
5. Max 1 round of changes. If still not right, PM Agent mediates.

### Review SLA

- Reviews should start within 1 task-cycle (i.e., when the reviewer finishes their current task)
- Don't let reviews queue up. Reviews take priority over starting new tasks.

---

## 5. Wave Execution Plan

Tasks are executed in waves. Within a wave, all tasks can run in parallel. A wave completes when all its tasks are DONE.

### Milestone 1 Waves

| Wave | Tasks | Engineers | Duration Est |
|------|-------|-----------|-------------|
| W1 | T-001 (Scaffolding) | Eng 1 | Short |
| W2 | T-002 (DB) + T-004 (LLM Client) | Eng 1 + Eng 3 | Medium |
| W3 | T-003 (Bot) + T-005 (Persona) + T-008 (Oura) + T-009 (Garmin) + T-010 (Strava) + T-011 (Renpho) | All 4 engineers | Medium-Long |
| W4 | T-006 (Brain) + T-007 (Safety) + T-012 (Sync Runner) + T-016 (Governor) | All 4 engineers | Medium |
| W5 | T-013 (Onboarding) + T-017 (Engagement) | Eng 1 + Eng 3 | Medium |
| W6 | A-M1 (Acceptance Gate) | PM Agent + Human Stakeholders | — |

### Wave 3 Assignment Detail (Peak Parallelism)
```
Eng 1: T-003 (Telegram Bot)
Eng 2: T-008 (Oura) → T-009 (Garmin)     ← 2 similar tasks back-to-back
Eng 3: T-005 (Persona)
Eng 4: T-010 (Strava) → T-011 (Renpho)   ← 2 similar tasks back-to-back
```

### Milestone 2 Waves

| Wave | Tasks | Engineers |
|------|-------|-----------|
| W7 | T-014 (Morning) + T-015 (Evening) + T-017* (if not done) | Eng 3 + Eng 4 + Eng 1 |
| W8 | T-018 (Nudges) + T-019 (Cron) | Eng 3 + Eng 4 |
| W9 | A-M2 (Acceptance Gate) | PM + Stakeholders |

### Milestone 3 Waves

| Wave | Tasks | Engineers |
|------|-------|-----------|
| W10 | T-020 (Summaries) + T-023 (Meals) | Eng 2 + Eng 2/4 |
| W11 | T-021 (Prompt Builder) + T-022 (Compression) | Eng 4 + Eng 2 |
| W12 | T-024 (Nutrition) + T-025 (Weekly Reflection) | Eng 4 + Eng 4/3 |
| W13 | T-026 (Cron Update) → A-M3 (Acceptance) | Eng 4 → PM + Stakeholders |

### Milestone 4 Waves

| Wave | Tasks | Engineers |
|------|-------|-----------|
| W14 | T-027 (Bug Fixes) + T-028 (Tone Tuning) | All available |
| W15 | T-029 (Hardening) | Eng 1 + Eng 4 |
| W16 | A-MVP (Final Acceptance) | PM + All Stakeholders |

---

## 6. PM Agent Operating Procedures

### Starting a Wave

1. Read `engineering-backlog.md` — identify all tasks with status `READY`
2. Verify dependencies are truly `DONE` (not just marked — check tests pass on main)
3. Assign tasks per ownership map. Update status to `ASSIGNED`.
4. Brief each engineer agent with:
   - Task ID and description
   - Branch to create
   - Key context files to read
   - Any cross-task coordination notes (e.g., "T-003 and T-002 share the DB layer")
5. Launch engineer agents (in parallel where possible, using worktrees for isolation)

### During a Wave

1. Monitor for blockers — if an engineer is stuck, investigate and unblock
2. When a task moves to `IN_REVIEW`, notify the assigned reviewer
3. Track progress: which tasks are in progress, in review, done
4. If a task is taking too long, check if it should be split or if the engineer needs help

### Completing a Wave

1. All tasks in the wave are `DONE`
2. Run full test suite on `main`: `pytest`
3. Verify all feature branches are merged to `main`
4. Push `main` to GitHub: `git push origin main`
5. Verify push succeeded — `git status` should show "up to date with origin/main"
6. Update `engineering-backlog.md` with final statuses
7. Commit the backlog status update: `git commit` + `git push origin main`
8. If this wave completes a milestone → trigger acceptance gate

### Managing the Backlog

- The PM Agent is the ONLY one who updates task statuses in `engineering-backlog.md`
- Engineers report completion; PM verifies and updates
- New bugs found during acceptance → PM creates `BUG-XXX` entries appended to backlog
- PM maintains a running log at `outputs/project-log.md`

---

## 7. Acceptance Gates

Acceptance gates (A-M1, A-M2, A-M3, A-MVP) are the quality checkpoints between milestones.

### Gate Process

1. **PM Agent prepares the demo:**
   - Compiles a summary of what was built in the milestone
   - Runs through the acceptance criteria (listed in the backlog for each gate)
   - Documents results: what passed, what failed, what surprised
   - Creates `outputs/demo-M{N}.md` with the demo report

2. **Demo to stakeholders:**
   - PM presents the demo report
   - Walks through each acceptance criterion with evidence (test output, screenshots, DB queries)
   - Stakeholders ask questions, flag concerns

3. **Stakeholder decision:**
   - **PASS** → Milestone accepted. Proceed to next milestone.
   - **PASS WITH BUGS** → Milestone accepted. Bugs logged as `BUG-XXX` tasks, added to next milestone.
   - **FAIL** → Specific failures identified. PM creates fix tasks, re-runs gate after fixes.

4. **Retro (see below)**

---

## 8. Retrospectives

A retro happens after each acceptance gate (4 total across the project).

### Retro Format

**File:** `outputs/retro-M{N}.md`

#### Sections:

1. **What was delivered**
   - Tasks completed, features working
   - Metrics: tasks planned vs completed, bugs found, review rounds

2. **What went well**
   - Patterns that worked (e.g., "data sync tasks were well-specified, all 4 completed without rework")
   - Effective practices to keep

3. **What didn't go well**
   - Tasks that needed rework and why
   - Blockers encountered and how they were resolved
   - Quality issues caught in review
   - Integration problems between tasks

4. **What to change**
   - Specific process improvements for next milestone
   - Adjustments to task specs (too vague? too detailed? missing context?)
   - Changes to review process
   - Changes to team assignment or ownership

5. **Engineer-specific notes**
   - Per-engineer observations: what each agent struggled with, excelled at
   - Useful for calibrating future assignments

6. **Action items**
   - Concrete changes to implement before next milestone starts
   - Owner for each action item

### How Retro Insights Are Applied

- Process changes → update THIS document (`dev-process.md`)
- Task spec improvements → update `engineering-backlog.md` for remaining tasks
- Code standard changes → update CLAUDE.md
- The PM Agent reads the latest retro before starting each new milestone

---

## 9. Project Log

**File:** `outputs/project-log.md`

The PM Agent maintains a running project log with entries for significant events:

```markdown
## [Date] — Wave N Complete
- Tasks done: T-XXX, T-YYY
- Tests passing: X/Y
- Blockers: none
- Notes: ...

## [Date] — M1 Acceptance: PASS WITH BUGS
- BUG-001: Garmin session caching fails on re-auth
- BUG-002: Safety filter false positive on "take a walk"
- Proceeding to M2. Bugs added to M2 backlog.
```

This log is the single source of truth for project history. Engineers and stakeholders can read it to understand current state.

---

## 10. Communication Protocol

### Between PM and Engineers
- PM assigns task → provides task ID, branch name, key context
- Engineer completes task → reports: "T-XXX complete. All tests pass. PR ready for review."
- Engineer is blocked → reports: "T-XXX blocked on [reason]. Need [specific help]."
- PM resolves blocker or escalates to stakeholders

### Between Engineers (via PM)
- Engineers don't directly coordinate. PM mediates all cross-task dependencies.
- If Eng 1 needs something from Eng 2's work, PM ensures the dependency is merged to main first.
- Exception: during review, reviewer communicates directly with the engineer about the review.

### Between PM and Stakeholders
- **Demo reports** after each milestone
- **Retro reports** after each milestone
- **Blocker escalation** if PM can't resolve (e.g., unclear requirements, API access issues)
- **Status updates** via project log (stakeholders can read anytime)

---

## 11. Risk Management

| Risk | Mitigation |
|------|-----------|
| Garmin `garminconnect` library breaks (unofficial) | T-009 includes session caching + re-auth. If lib is dead, fallback to Garmin's export or manual entry. |
| Renpho API unavailable | T-011 has Garmin body comp fallback built in. |
| LLM costs spike | Sonnet for daily use. Extraction uses keyword heuristic first (T-006). Monitor in logs. |
| Task specs are wrong/incomplete | Engineer flags to PM. PM updates spec or creates a clarification sub-task. Don't guess. |
| Integration failures at acceptance | Wave structure ensures components integrate incrementally. A-M1 catches early. |
| An engineer agent produces low-quality code | Review process catches it. PM can reassign or pair if pattern persists. |

---

## 12. How to Start the Project

### For the PM Agent

When the user says "start implementation" or "run the project":

1. Read this document (`outputs/dev-process.md`) in full
2. Read `outputs/engineering-backlog.md` for current task statuses
3. Read `outputs/project-log.md` for history (if exists)
4. Read the latest `outputs/retro-M{N}.md` (if exists)
5. Identify the current wave (first wave with incomplete tasks)
6. Assign tasks and launch engineer agents
7. Monitor, review, and advance through waves
8. At milestone boundaries: run acceptance, demo, retro

### For Engineer Agents

When assigned a task:

1. Read this document — specifically Sections 3 (Standards) and 4 (Review)
2. Read the task description in `outputs/engineering-backlog.md`
3. Read ALL context files listed in the task
4. Read existing code in `health-concierge/` (if any) to understand current state
5. Create branch: `feat/T-{number}-{short-name}`
6. Implement deliverables
7. Write ALL required tests
8. Run `pytest` — all tests must pass (not just yours)
9. Report completion to PM with a brief summary

### For Human Stakeholders

- You will be called upon at acceptance gates (A-M1, A-M2, A-M3, A-MVP)
- Review demo reports in `outputs/demo-M{N}.md`
- Review retro reports in `outputs/retro-M{N}.md`
- Provide go/no-go decisions at gates
- Can read `outputs/project-log.md` anytime for current status
