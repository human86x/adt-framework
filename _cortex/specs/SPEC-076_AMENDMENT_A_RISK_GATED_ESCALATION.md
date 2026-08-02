# SPEC-076 Amendment A: Risk-Gated Initial Tier & Failure-Informed Escalation

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE)
**Created:** 2026-08-01
**Target Milestone:** v0.4.0
**Amends:** SPEC-076 (Effort-Tiered Model Selection & Human-Gated Escalation)
**Jurisdiction:** Backend_Engineer (`adt_center/api/build_executor.py`), Systems_Architect (`_cortex/build/scratchpad/`)

**Intent:** Fix three known weaknesses in SPEC-076's initial-tier + escalation loop: (a) every task starts at LOW even when it's obviously heavy, so LOW's 3.4% success rate wastes tokens on nearly every real task; (b) the escalation ladder truncates the failing worker's log between rungs, discarding useful state; (c) the escalated worker gets the same prompt with zero context about what the previous worker tried, so it often re-starts from scratch and overwrites partial-but-useful work. Amendment A picks a smarter initial tier from the existing risk score, preserves each failed attempt's log in a per-task scratchpad, and threads a `PREVIOUS ATTEMPT HISTORY` block into the escalated worker's prompt.

**Triggering Event:** 2026-08-01 operator observation while filming SPEC-003 of `habit_tracker_1785598706`: "the worker agents were doing a spec up to almost 100% then failed... marking the task red and moving onto next, then escalation alert appears and if you hover the mouse on the red failed task it would start to show the new agent's thoughts and eventually the task gets built and it marks green... was happening with each one of the tasks in 2 specs (the whole app)... if the first dumb agent always fails and the second one redoes everything from scratch, why might we need the dumber mode at all?"

**Success Condition:**
(a) For a task with heavy_keywords >= 1 or upstream_deps + wave_size >= 2 (score >= 2), the initial spawn uses `Gemini 3.5 Flash (Medium)`; for score >= 4 uses `Gemini 3.5 Flash (High)`. Verified via `task_risk_assessed` ADS event `chosen_via` field starting with `risk_medium_start` / `risk_high_start` / `sa_bumped_high`.
(b) When the escalation loop advances past attempt 1, `_cortex/build/scratchpad/<task_id>_attempt<N>_<model>.log` exists on disk with the failed worker's full output — nothing lost to truncation.
(c) A summary markdown at `_cortex/build/scratchpad/<task_id>_summary.md` accumulates one section per attempt with: model, outcome, files touched (mtime heuristic), narration lines observed, tool calls observed.
(d) On attempt >= 2, the escalated worker's agy `-p` prompt contains a `!!! PREVIOUS ATTEMPT HISTORY !!!` block (auto-prepended by `_inject_previous_attempts_context`); the block updates cleanly across further escalations rather than stacking.
(e) Systems_Architect role starts one tier above the numeric default at every gate (LOW→MEDIUM, MEDIUM→HIGH) because planning tasks are harder than execution.
(f) Operator env override `ADT_BUILD_MODEL_<ROLE>` still wins over the risk-derived tier, and this is recorded in `chosen_via` as `env_override_*`.

---

## 1. Problem

`build_executor.py:_pick_routing_for_task` currently starts every task at whatever the role's `ROLE_MODEL_DEFAULTS` says (all `None` — meaning "let agy pick the default"). It only upgrades to `RISK_HIGH_MODEL` when score >= 3. Escalation from failure is handled by `ESCALATION_LADDER` — a fixed sequence of rungs that respawns the worker with the next model.

Three observed weaknesses:

1. **LOW's 3.4% clean-completion rate for real code tasks** (documented in `SPEC-062-H`) means the ladder walks from a doomed rung 96% of the time. Every attempt burns tokens; the operator sees a "red task → escalation → recovery" cascade on nearly every build.
2. **Log truncation between rungs** (`build_executor.py:1202-1204`, `open(log_path, "wb").close()`) discards the failed worker's narration + tool trail. That's the information the operator sees when hovering a failed task node — losing it means MEDIUM restarts blind.
3. **Same prompt on retry** means the escalated worker has no idea another agent was here five minutes ago, why it failed, or which files were partially written. Result: MEDIUM often rewrites from scratch, overwriting whatever LOW got right.

## 2. Design

### 2.1 Risk-gated initial tier (`_pick_routing_for_task`)

Extend the existing scoring output to pick the *initial* model, not just the escalated model:

| Score | Tier | Model |
|---|---|---|
| < 2 | LOW | `Gemini 3.5 Flash (Low)` |
| 2 – 3 | MEDIUM | `Gemini 3.5 Flash (Medium)` |
| ≥ 4 | HIGH | `Gemini 3.5 Flash (High)` |

Systems_Architect gets one tier bump because planning/decomposition is harder than execution. Explicit task assignments (`assigned_harness`, `assigned_model`) still win. `ADT_BUILD_MODEL_<ROLE>` env override still wins over the risk-derived choice.

### 2.2 Attempt scratchpad (`_cortex/build/scratchpad/`)

Per-task directory containing:
- `<task_id>_attempt<N>_<model>.log` — verbatim copy of the failed worker's log
- `<task_id>_summary.md` — accumulating markdown log of attempts with structured fields

Written by `_save_attempt_snapshot(project_root, task_ids, attempt_num, model, log_path, outcome)` called **before** the log truncation in the escalation loop, so nothing is lost.

Summary schema per attempt:
```markdown
## Attempt N — model=`<model>` — outcome=`narrator_killed|stalled|silent_exit`
- log: `_cortex/build/scratchpad/task_XXX_attempt02_Gemini_3.5_Flash_Medium.log`
- files touched:
  - `src/render.js`
  - `index.html`
- narration observed:
  - I will read the file to understand the layout...
  - Now I will identify the render function...
- tool calls observed:
  - Reading file src/render.js
  - (that's it — no writes)
```

Files-touched detection is a filesystem walk filtered by mtime relative to log start (heuristic; skips `_cortex/`, `.git/`, `node_modules/`, `venv/`).

### 2.3 Failure-informed context injection

`_inject_previous_attempts_context(cmd, project_root, task_ids, attempt_num)` mutates the `agy -p PROMPT` arg in place before respawn. It prepends:

```
!!! PREVIOUS ATTEMPT HISTORY — READ FIRST !!!
This task has been attempted before. A prior worker (probably at a lower tier)
produced the summary below. Files it touched are already on disk — read them
before you overwrite. Do NOT restart from scratch: continue or fix what exists.

<<summary.md content, capped at 6000 chars>>

!!! END PREVIOUS ATTEMPT HISTORY !!!
```

On further escalations, the previous history block is stripped and replaced with the updated one — no stacking.

## 3. Acceptance Criteria

1. `curl -X POST /api/governance/specs/<id>/build?project=<p>` with a task that has `heavy_keywords >= 1` emits `task_risk_assessed` ADS event with `chosen_via = "risk_medium_start"` or higher — NOT `"default"`.
2. Force an escalation (e.g. prompt agy with an impossible instruction). After the first attempt fails, `ls _cortex/build/scratchpad/` shows both a `_attempt01_*.log` and a `_summary.md`.
3. On attempt 2's spawn, the worker's agy invocation includes `!!! PREVIOUS ATTEMPT HISTORY !!!` in the prompt (verifiable by grepping `/proc/<pid>/cmdline`).
4. Set `ADT_BUILD_MODEL_BACKEND_ENGINEER="Gemini 3.5 Flash (High)"` in env — subsequent Backend_Engineer spawns must use it and emit `chosen_via = "env_override_risk_*"`.
5. Regression: a heavy task (matched by `HEAVY_KEYWORDS`) that previously required 3 escalation rungs now completes on the first attempt at MEDIUM/HIGH.

## 4. Implementation Notes

- Backend patches ALREADY applied to `build_executor.py` in this session (see `git log --oneline`). Amendment A serves as the audit-trail spec for those changes.
- No frontend changes needed for the backend logic. Follow-up: the spec-map task-node log tail should switch to the latest attempt's log on escalation (currently caches the first spawn's log_path) — that's Amendment A follow-up material.
- Scratchpad directory is under `_cortex/build/scratchpad/`. Add `.gitignore` entry `_cortex/build/scratchpad/*.log` to avoid committing per-run logs; the summary markdowns are diff-friendly and can be kept.

## 5. Out of Scope / Follow-ups

- Frontend log-source switching on escalation (separate spec).
- HIGH-tier operator-approval modal (already in SPEC-076 scope).
- Scratchpad rotation / cleanup policy (task-graph completion should archive).
- Cross-task pattern mining (if 5 tasks all fail at LOW on "session_start events" pattern, auto-upgrade role's default tier).

---

*"Failure not observed is failure repeated."*
