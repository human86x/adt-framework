# SPEC-117 — Reconciler Completion Verification Hardening

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE, 2026-08-29)
**Authority:** Operator verbal approval, 2026-08-29 (this session — "go b go" for draft, "4.1 is fine" for version target and continuation)
**Version target:** v0.4.1 (patch — trust fix + retroactive audit). v0.5.0 reserved for DTGP debut.
**Category:** Governance Infrastructure — **TRUST-CRITICAL**
**Relates to:** SPEC-055 (Build Orchestration Engine), SPEC-062 Amendment E (Build Worker Lifecycle), SPEC-102 (Task Preflight & No-Op Detection — DRAFT), commit 99b71f0 (rc88 — "reconciler-authoritative task completion + sandbox auth mounts")

**Intent:** Close the false-positive completion loophole in ADT's reconciler. Task completion MUST be backed by positive artifact evidence or an explicit preflight pass — never inferred from worker exit alone. Jurisdiction-denied writes MUST be a hard fail, not silently reconciled. Add a retroactive audit tool that walks every task ever marked complete via reconciler and re-checks artifact presence, reverting fake completions to `failed` with the audit event as authority. First target of the audit is ADT-framework itself.

**Triggering Event:** On 2026-08-29 the operator discovered that a governed project showed SPEC-043 through SPEC-048 as "completed" in the Console with **zero code produced** for five of six specs. Root cause, independently diagnosed by the operator's external agent and the Architect: Antigravity workers were dispatched at paths their DTCP jurisdiction denies → workers exited without writing → reconciler marked tasks "completed via reconciliation" regardless of whether files landed. The code path is `adt_center/api/build_executor.py:1979`, emitting `build_worker_completed_via_reconciler` for any worker exit, with no evidence gate. Introduced in commit 99b71f0 (rc88, "reconciler-authoritative task completion"). This is not a project-level bug — it is a systemic governance failure. The whole premise of ADT is that ADS events are trustworthy; when the reconciler manufactures completion evidence without underlying reality, every downstream signal (dashboards, master-plan status, "completed" percentages, forge decisions, delegation trust) is a lie.

**Success Condition:**
1. Reconciler REFUSES to mark a task `completed` unless either (a) artifact evidence exists inside the worker's execution window, or (b) SPEC-102 preflight explicitly passed and was recorded.
2. Any `dtcp_write_denied`, `path_denied`, or `jurisdiction_violation` ADS event with the worker's `session_id` inside its execution window forces the task to `failed` with `reason: jurisdiction_blocked` — non-overridable by reconciliation.
3. `build_worker_completed_via_reconciler` is NEVER emitted for zero-artifact-delta workers absent a preflight pass. Instead, `task_reconciliation_refused` is emitted with the specific refusal reason.
4. A retroactive audit tool exists (`_cortex/ops/audit_reconciled_completions.py`), has been run against ADT-framework's own `tasks.json` as its first target, and results are visible in the Console.
5. Failed re-audits emit `task_completion_reaudit_fail` and (with operator confirmation) revert the task to `failed` with the audit event as authority.
6. Console surfaces `reconciliation_refused` and `reaudit_failed` as distinct statuses, not folded into generic `failed`.

---

## 1. Overview

The reconciler was introduced (rc88) to solve a real problem: workers can complete tasks and exit before the orchestrator sees the completion event, leading to phantom `in_progress` states. The fix was correct in shape — let the reconciler resolve the state after the fact — but it granted the reconciler too much authority: **the ability to mark completion without evidence**. This spec re-imposes an evidence gate on that authority.

The failure mode is not confined to one project or one build. Any worker that fails silently (DTCP deny, sandbox error, timeout with no stderr, disk full, network glitch mid-checkout) hits the same reconciler path and gets marked complete. Every "completed" task authored via reconciler since rc88 landed is suspect until proven otherwise.

## 2. Scope

### In scope

- New pre-completion evidence check inside the reconciler code path (`adt_center/api/build_executor.py` around line 1927–1980).
- Jurisdiction-deny query against ADS keyed on worker session_id and execution window.
- Zero-delta refusal path with structured refusal reason.
- New ADS event types for refusal and re-audit outcomes.
- Snapshot of git HEAD and jurisdiction-path fingerprint at worker spawn (so evidence check has baseline).
- Retroactive audit tool with dry-run and --commit modes.
- First-run audit against ADT-framework's own `tasks.json`.
- Console UI additions to distinguish `reconciliation_refused` and `reaudit_failed` from generic `failed`.

### Out of scope

- **Preventing DTCP denies themselves.** Per-project jurisdiction configuration is that project's own governance concern (the operator's external agent is handling that for the affected project).
- **Recovering lost work.** Workers that were denied wrote nothing. There is nothing to recover — only to correctly mark as failed.
- **Retroactively producing missing code.** The audit reveals phantom completions; producing real code to satisfy their acceptance criteria is a subsequent per-project spec, not this one.
- **Rewriting the reconciler-authoritative model.** rc88's fundamental shape is preserved. Only the evidence gate is added.

## 3. Design

### 3.1 Positive-Evidence Completion Contract

Before emitting `build_worker_completed_via_reconciler` for a task, the reconciler MUST verify at least one of:

- **Artifact evidence.** For each entry in `task.acceptance_criteria.artifacts[]` (or, absent that field, for each modified file under the task's declared jurisdiction paths), the file exists on disk AND its mtime is inside the worker's `[spawned_at, exited_at + grace_period]` window (default grace 30 seconds).
- **Declared hash match.** If an entry specifies `sha256`, the file's current hash MUST match.
- **SPEC-102 preflight pass.** A `task_completed_by_preflight` ADS event exists for this task inside the worker's execution window.

If none of the above hold → refuse completion. Emit `task_reconciliation_refused` (see §3.4) and mark the task `failed` with `reason: no_artifact_evidence`.

Task's own declared acceptance criteria take precedence. When absent, the reconciler falls back to "any new/modified file inside the task's jurisdiction paths within the window" as the evidence surface. Both are cheap; both are grounded in file system reality, not in worker exit code.

### 3.2 Jurisdiction-Block Hard Fail

Independent of §3.1: query ADS at reconciliation time for events matching:

```
session_id == worker.session_id
AND action_type IN {dtcp_write_denied, path_denied, jurisdiction_violation, sovereign_path_violation}
AND ts BETWEEN worker.spawned_at AND worker.exited_at + grace
```

Non-empty result → immediate hard fail. Task moves to `failed` with `reason: jurisdiction_blocked`, `action_data.denied_events: [event_ids]`. This decision is **non-overridable** by any other reconciliation path — a worker that hit even one jurisdiction deny during its run is presumed unable to have completed its task, regardless of other signals.

Rationale: jurisdiction denies are almost never partial or recoverable. They indicate a config mismatch that must be surfaced to the operator, not swept under a "completed" claim. False positives are acceptable in the direction of over-reporting failure; false negatives (phantom completions) are not.

### 3.3 Empty-Delta Refusal

Where §3.1 falls back to the jurisdiction-path scan and finds zero new/modified files, and §3.2 finds no jurisdiction denies (i.e. worker exited cleanly with no writes and no denies) → this is a NO-OP case. Two sub-cases:

- **With preflight pass recorded** → `completed` via SPEC-102 path (already covered in §3.1).
- **Without preflight pass** → refuse completion. Emit `task_reconciliation_refused` with `reason: no_artifact_produced_no_preflight`. Task moves to `failed`. Operator can retry as a preflight-eligible no-op via SPEC-102's mechanism if that turns out to be the correct interpretation.

Rationale: a worker that produced nothing and had nothing denied might genuinely be a no-op, but that determination requires the preflight gate — the reconciler cannot infer it from silence alone.

### 3.4 New ADS Event Types

Add to `adt_core/ads/schema.py`:

```
RECONCILIATION_HARDENING_EVENTS = [
    "task_reconciliation_refused",      # {task_id, reason, worker_session_id, window_start, window_end, evidence_scan_summary}
    "task_completion_reaudit_pass",     # {task_id, artifacts_verified[], denies_in_window: 0}
    "task_completion_reaudit_fail",     # {task_id, reason, missing_artifacts[], denies_in_window[]}
    "task_completion_reaudit_reverted", # {task_id, previous_status, new_status: "failed", authority_event_id}
    "reconciler_evidence_check_passed", # {task_id, evidence_source: artifact|preflight|jurisdiction_scan}
]
```

`reason` values are structured: `no_artifact_evidence`, `no_artifact_produced_no_preflight`, `jurisdiction_blocked`, `artifact_hash_mismatch`.

### 3.5 Reconciler Code Changes

Concrete edits in `adt_center/api/build_executor.py`:

1. Around line 1927 (the reconciler comment block): add call to `_verify_completion_evidence(task, worker)` before the completion-emission path.
2. `_verify_completion_evidence()` implements the checks from §3.1, §3.2, §3.3, in that order (§3.2 first is faster and short-circuits jurisdiction failures).
3. On any refusal, emit `task_reconciliation_refused` and set task status to `failed`. Do NOT emit `build_worker_completed_via_reconciler`.
4. Add feature flag `reconciler_evidence_required` in adt-center config, **default `true`**. Emergency disable path exists but requires an SCR (Tier-2 escalation — this is a safety gate, disabling it is a governance decision).

### 3.6 Retroactive Audit Tool

Path: `_cortex/ops/audit_reconciled_completions.py`.

Behaviour:

- Walks `<project>/_cortex/tasks.json`. Selects every task with `status == "completed"` AND `completion_source == "reconciler"` (or equivalent marker from rc88's schema).
- For each, locates the worker's `build_worker_spawned` and `build_worker_completed`/`_via_reconciler` events in ADS to derive the execution window.
- Runs the same checks from §3.1, §3.2, §3.3 against the current filesystem — with the caveat that this is *retroactive*, so file mtimes may have drifted; use "file exists at expected path" as the primary check and note mtime-drift in the report rather than treating it as failure.
- Emits `task_completion_reaudit_pass` or `task_completion_reaudit_fail` per task with structured detail.
- Prints summary to stdout and writes a report to `_cortex/reports/reaudit_<ts>.md`.

Modes:

- **`--dry-run` (default).** Emits `_pass`/`_fail` audit events but does NOT modify task status. Report is advisory.
- **`--commit`.** Additionally reverts every `_fail` task from `completed` to `failed`, adds `reaudit_verdict: "reverted"` to the task record, emits `task_completion_reaudit_reverted` with the audit event as `authority_event_id`.
- **`--project <path>`.** Limits scope to a single project. Default is `.` (current directory).
- **`--since <YYYY-MM-DD>`.** Limits to tasks completed after a date. Useful for scoping to post-rc88.

First execution — required as part of this spec's rollout — runs against ADT-framework itself in dry-run, results reviewed by operator, then re-run with `--commit` if approved. This is Task-7 in the breakdown.

## 4. Task Breakdown

- task_1: Add `_verify_completion_evidence` to `adt_center/api/build_executor.py` implementing §3.1 (artifact + preflight). **Role:** Backend_Engineer.
- task_2: Add jurisdiction-deny ADS query per §3.2, wired into `_verify_completion_evidence` as the first short-circuit. **Role:** Backend_Engineer.
- task_3: Add empty-delta refusal path per §3.3 with `task_reconciliation_refused` emission. **Role:** Backend_Engineer.
- task_4: Register `RECONCILIATION_HARDENING_EVENTS` in `adt_core/ads/schema.py`. **Role:** Backend_Engineer + Systems_Architect (schema authority).
- task_5: Extend `build_worker_spawned` event to include `head_sha_at_spawn` and `jurisdiction_paths_fingerprint` if not already present (needed as baseline for evidence checks). Check first — SPEC-062 Amendment E may already cover this. **Role:** Backend_Engineer.
- task_6: Implement `_cortex/ops/audit_reconciled_completions.py` per §3.6 with dry-run and --commit modes. **Role:** Backend_Engineer.
- task_7: Run the audit against ADT-framework in dry-run. Publish `_cortex/reports/reaudit_<ts>.md`. Operator reviews. If approved, re-run with --commit. **Role:** DevOps_Engineer (execution), Systems_Architect (report review).
- task_8: Console UI updates to distinguish `reconciliation_refused` and `reaudit_failed` from generic `failed` — colour, icon, hover tooltip explaining the reason. **Role:** Frontend_Engineer.
- task_9: End-to-end verification. Spawn a fixture worker configured to write to a DTCP-denied path; confirm reconciler emits `task_reconciliation_refused` with `reason: jurisdiction_blocked` and task status is `failed`, NOT `completed`. Spawn a fixture worker with SPEC-102 preflight pass and zero writes; confirm task moves to `completed` via preflight path. **Role:** DevOps_Engineer.
- task_10: **Version bump to v0.4.1.** Runs only after task_7 --commit completes and task_9 passes. Updates `adt-console/src/version.txt` and `adt-console/src/build_time.txt`. Authors `_cortex/reports/release_notes_v0.4.1.md` whose headline is the audit verdict distribution ("N tasks reverted from completed to failed by SPEC-117 audit") plus the feature-flag summary. Git tag `v0.4.1` after merge. **Role:** DevOps_Engineer.

## 5. Acceptance Criteria

- After task_1–3 land, unit test: a mock task with a worker session whose ADS log includes a `dtcp_write_denied` in-window returns `Refused(jurisdiction_blocked)` from `_verify_completion_evidence`.
- Unit test: a mock task whose declared `acceptance_criteria.artifacts[]` includes `foo.py` where `foo.py` does not exist on disk returns `Refused(no_artifact_evidence)`.
- Unit test: a mock task with a `task_completed_by_preflight` event in the worker window returns `Accepted(preflight)`.
- Integration test (task_9): fixture worker denied on every write → task ends `failed`, ADS shows `task_reconciliation_refused` with the denied event IDs enumerated. No `build_worker_completed_via_reconciler` event for this task.
- `_cortex/ops/audit_reconciled_completions.py --dry-run` on ADT-framework produces `_cortex/reports/reaudit_<ts>.md` listing every reconciler-completed task and its verdict. Verdict distribution is publishable (e.g. "437 pass, 36 fail").
- With operator approval, `--commit` mode reverts all failed audits; `tasks.json` shows those tasks with `status: failed` and `reaudit_verdict: "reverted"`. Console reflects the new statuses on refresh.
- Console distinguishes `reconciliation_refused` (amber/warning) from `reaudit_failed` (red/error) from `failed` (grey/neutral).
- Feature flag `reconciler_evidence_required: true` is the default in shipped config; disable requires SCR.

## 6. Non-Goals

- Preventing DTCP denies from happening. Per-project `jurisdictions.json` correctness is the project's own governance concern.
- Reconstructing what a failed worker should have written. The audit surfaces the phantom; producing the real code is per-project follow-up work.
- Rewriting rc88's reconciler-authoritative model. Only adding the evidence gate.
- Preventing the operator from disabling the evidence gate for a legitimate use case — but disabling requires SCR, and the ADS event on disable is a Tier-1 audit trail.
- Multi-project audit orchestration. Audit runs one project at a time. Cross-project rollup is a future concern if needed.

## 7. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| **Audit reverts many legitimate completions**, because file mtimes drifted, artifacts were reorganised, or acceptance criteria don't match reality. | Dry-run default. Report is reviewed BEFORE any --commit. Operator can filter the audit set (e.g. `--since 2026-08-15`) to limit blast radius. Reverted tasks get `reaudit_verdict` field so a subsequent counter-audit or manual restoration is possible. |
| **Evidence check misses partial-write cases.** Worker wrote SOME files (passes evidence) but not all required by acceptance criteria. | This spec catches "wrote nothing" cases. Deeper partial-completion detection is SPEC-102 territory (proper acceptance-criteria checking, not just presence). Flagged as a follow-on. |
| **Reconciler slowdown from ADS query per completion**. | ADS query is bounded to the worker's session_id and time window (small dataset). Cache the query result for the batch reconciliation pass. Measure; if latency becomes an issue, index ADS by session_id. |
| **Evidence gate rejects a legitimate no-op**, breaking a build that was actually done via SPEC-102 preflight but the preflight event wasn't recorded due to earlier bug. | Refusal `reason: no_artifact_produced_no_preflight` is distinct and actionable. Operator can retroactively record the preflight and re-reconcile, OR mark the task complete manually with an SCR-authorised override. |
| **False sense of trust after audit.** Operator sees "437 pass, 36 fail" and assumes 437 are correct. But `_pass` here means "artifact evidence exists" — not "artifact is correct". | Report explicitly frames results as "evidence present" vs "evidence absent", not "correct" vs "incorrect". Correctness verification is deeper — SPEC-102 acceptance-criteria checking is the path to that. |
| **Feature flag left off across projects**, defeating the fix. | Default `true`. Disable is a Tier-2 SCR with mandatory justification. Every start-up logs the flag state as an ADS event so operators can spot drift. |
| **Reconciler evidence check itself has a bug**, refusing legitimate completions across the board. | Feature flag exists for emergency disable. E2E verification (task_9) covers both refusal and acceptance paths. Ship behind flag OFF for first 24 hours on ADT-framework only, then flip to on after audit results are in. |

## 8. Dependencies

- **SPEC-055** — Build Orchestration Engine. This spec modifies its reconciler.
- **SPEC-062 Amendment E** — Build Worker Lifecycle event types. The `build_worker_spawned` event structure is where §3.5 additions live.
- **SPEC-102 (DRAFT)** — Task Preflight & No-Op Detection. Provides the `task_completed_by_preflight` event this spec's evidence gate accepts. SPEC-102 does not need to ship for SPEC-117 to be useful; SPEC-117 falls back to "artifact-or-fail" if preflight is not deployed.
- **DTCP** — jurisdiction-deny events (`dtcp_write_denied`, `path_denied`, `jurisdiction_violation`, `sovereign_path_violation`) are the primary hard-fail signal.
- **`_cortex/tasks.json`** — task status writes require existing schema; may gain `reaudit_verdict` field (nullable, backwards-compatible).

## 9. Follow-On Work

- **Complete SPEC-102** — moves from DRAFT to APPROVED and ships. Reduces false refusals in the "genuine no-op" case.
- **Acceptance-criteria correctness verification.** SPEC-117 catches "wrote nothing"; a deeper spec catches "wrote something, but not the right thing". Likely SPEC-118 candidate.
- **Cross-project audit rollup.** A framework-level dashboard showing reaudit fail-rates across all governed projects, so patterns of phantom-completion are visible.
- **Reconciler observability dashboard.** Real-time surface showing "refused vs completed" reconciliations, per-project, per-day.

## 10. Rollout

Deliberately staged to restore trust incrementally without shocking the whole system.

1. **task_4 + task_5** — schema and spawn-time snapshot additions. No behaviour change. Ship.
2. **task_1 + task_2 + task_3** — reconciler hardening, behind feature flag `reconciler_evidence_required`. Default **ON**. Emergency disable via SCR. Ship.
3. **task_9** — verification with fixture workers exercises both refusal and acceptance paths. Ship.
4. **task_6** — audit tool. Ships in `--dry-run` capable form. Ship.
5. **task_7 (dry-run against ADT-framework)** — first audit. Report reviewed by operator with Architect. Publish verdict distribution.
6. **task_7 (--commit against ADT-framework)** — only if operator approves the dry-run results. This is the moment ADT's own ledger corrects itself.
7. **task_8** — Console UI distinctions. Ship. Enables operators to see refusals distinctly.
8. Per-project audits — each governed project runs the audit tool, produces its own report, decides on --commit. This is per-project governance, not framework-level.
9. **task_10 — Version bump to v0.4.1**, release notes published with audit verdict distribution as headline, git tag.
10. Update `MASTER_PLAN.md` to add SPEC-117 as ACTIVE and mark v0.4.1 milestone (via SCR — Tier 1).

---

*"An unverified completion is worse than a known failure. The lie corrupts every decision downstream."*
