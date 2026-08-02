# SPEC-076: Effort-Tiered Model Selection & Human-Gated Escalation

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE)
**Created:** 2026-07-27
**Target Milestone:** v0.4.0
**Jurisdiction:** Backend_Engineer (`adt_center/api/build_executor.py`, `adt_center/api/governance_routes.py`), Frontend_Engineer (`adt-console/src/js/launcher.js`, `adt-console/src/js/spec_map.js`), Systems_Architect (`config/model_tiers.json`)
**Depends On:** SPEC-045 (SCR Authorization Hardening), SPEC-062 (Spec Map), SPEC-067 (Forge Wizard)
**Complements:** SPEC-075 (LLM-Backed Intent Classification)

**Intent:** Prevent silent token/quota evaporation by making model effort tiers a first-class governance concept. Workers default to the cheapest tier that plausibly does the job. Auto-escalation is allowed up to MEDIUM. Any escalation to HIGH (or Pro / Opus / Sonnet models known to be expensive per-token) is a **break-glass action** that requires explicit operator approval via a Console prompt — no worker may unilaterally burn HIGH-tier tokens.

**Triggering Event:** 2026-07-27 UTC operator report during a Forge attempt: `Gemini 3.1 Pro (High)` quota exhausted, reset in 2h10m. The Forge worker defaulted to `Gemini 3.1 Pro (High)` (`governance_routes.py:417,689`) with no operator visibility into cost, and no fallback. Operator observation: "on this mode tokens evaporate instantly." The ADT framework governs jurisdiction, sovereignty, and data — but does not govern its own compute-budget discipline. This spec closes that gap.

**Success Condition:**
(a) Every worker spawn (forge, decompose, build, standards ingest, intent classifier, watchdog) selects a model whose `effort_tier` is `LOW` by default, `MEDIUM` if the caller sets `effort=medium`, and `HIGH` only if a matching SCR-lite authorization record exists for the run_id.
(b) When a worker's initial LOW attempt fails (via existing escalation triggers — `worker_escalation_step`, narrator kills), the executor automatically retries at MEDIUM without operator prompt, and logs `worker_effort_escalated LOW→MEDIUM` to ADS.
(c) If MEDIUM also fails and the escalation logic wants to try HIGH, the executor **blocks** and emits a `worker_high_effort_requested` event with `{run_id, spec_id, task_id, reason, estimated_tokens_burned_so_far}`. The Console renders a prominent modal: "Escalate to HIGH? [Approve for this task] [Approve for this session] [Deny — mark task failed]". No HIGH-tier model may be invoked without one of those approvals logged as `worker_high_effort_authorized` in ADS.
(d) The effort-tier registry lives at `config/model_tiers.json` (Tier-1 sovereign) and defines which model names map to LOW/MEDIUM/HIGH. Edits require SCR.
(e) All model-selection events emit to ADS with `{worker_role, model, effort_tier, provenance: "default|escalation|operator_override", authorizer: null | operator_session_id}`. Overseer can audit the full cost history.
(f) A `GET /api/governance/effort/budget?since=<ts>` endpoint returns cumulative LOW/MEDIUM/HIGH invocations, per role, per project — visible in the Console's Task Detail panel as running counters.

---

## 1. Problem

Current forge/build/decompose flows hardcode model names:

```
governance_routes.py:417  forge_model = os.environ.get("ADT_FORGE_MODEL", "Gemini 3.1 Pro (High)")
governance_routes.py:689  forge_model = os.environ.get("ADT_FORGE_MODEL", "Gemini 3.1 Pro (High)")
governance_routes.py:3623 --model "Gemini 3.5 Flash (High)"   (decompose)
```

Three consequences:

1. **Quota surprise.** Operator hits the top-tier quota ceiling with no warning. Reset takes hours. Blocking forge is a poor operator experience.
2. **Cost opacity.** No ADS record of how many HIGH-tier invocations were made in a session. Impossible to answer "why was our token spend $X this week?"
3. **Silent escalation.** The existing `worker_escalation_step` logic (in `build_executor.py`) already retries with different models on failure — but without any tier-aware policy. A failing task can silently burn through the entire Pro-tier daily quota.

The ADT framework's whole point is **structural enforcement of governance**. Compute-budget is a legitimate governance concern the framework should own.

---

## 2. Architecture

### 2.1 Effort-tier registry (`config/model_tiers.json`) — Tier-1 sovereign

```json
{
  "$schema": "adt://schemas/model_tiers/v1",
  "tiers": {
    "LOW": {
      "models": [
        "Gemini 3.6 Flash (Low)",
        "Gemini 3.5 Flash (Low)",
        "gemini-3.1-pro-low"
      ],
      "default_for_roles": ["Backend_Engineer", "Frontend_Engineer", "DevOps_Engineer"],
      "human_approval_required": false
    },
    "MEDIUM": {
      "models": [
        "Gemini 3.6 Flash (Medium)",
        "Gemini 3.5 Flash (Medium)"
      ],
      "default_for_roles": ["Systems_Architect"],
      "human_approval_required": false,
      "auto_escalate_from": "LOW"
    },
    "HIGH": {
      "models": [
        "Gemini 3.6 Flash (High)",
        "Gemini 3.1 Pro (High)",
        "claude-sonnet-4-6",
        "claude-opus-4-6-thinking"
      ],
      "default_for_roles": [],
      "human_approval_required": true,
      "auto_escalate_from": null,
      "approval_ttl_seconds": 3600,
      "approval_scope_options": ["single_task", "single_session", "global_burst_1h"]
    }
  }
}
```

### 2.2 Executor changes (`build_executor.py`)

Introduce `effort_tier` as the primary parameter, not model name:

```python
def select_model(worker_role: str, effort_tier: str = "LOW") -> str:
    """Return the model name for the given tier, checking operator overrides."""
```

Escalation logic pattern:

```
attempt 1: LOW  → run, capture outcome
if outcome == pass: done
if outcome in {fast_fail, narrator_kill, tool_error}:
    ADS: worker_effort_escalated {from: LOW, to: MEDIUM}
    attempt 2: MEDIUM → run
    if outcome == pass: done
    if outcome fails:
        emit ADS: worker_high_effort_requested {...}
        block worker; wait up to N minutes for operator response
        if approved via operator_action  → attempt 3 at HIGH
        if denied or timeout             → ADS: worker_all_escalations_exhausted
```

### 2.3 Approval endpoint (`/api/governance/effort/approve`)

`POST` body:
```json
{ "run_id": "...", "spec_id": "...", "task_id": "...", "scope": "single_task", "operator_note": "optional" }
```

Records `worker_high_effort_authorized` in ADS with a TTL (default 3600 s). Worker's escalation-blocked thread wakes and proceeds at HIGH.

### 2.4 Denial endpoint (`/api/governance/effort/deny`)

`POST` body: `{ "run_id": ..., "reason": "..." }`. Marks task failed with `authorization_denied`.

### 2.5 Console UI (Frontend)

New modal `#effort-escalation-modal` — appears when the ADS stream (Tauri event bus) receives `worker_high_effort_requested`. Contents:

```
⚠ Worker requests HIGH-tier model

Spec:    SPEC-072
Task:    task_478 (Define classifier prompt template)
Role:    Systems_Architect
Reason:  MEDIUM attempt failed with "narrator_killed" after 2 retries.

Tokens burned so far this session: 1.2M (est. cost $2.40)
Model that would be used:          Gemini 3.1 Pro (High)

[Approve for THIS task]  [Approve for THIS session]  [Deny — fail task]
```

Operator's choice fires the approve/deny endpoint. Modal closes. Worker resumes or fails.

### 2.6 Budget endpoint

`GET /api/governance/effort/budget?since=<iso_ts>&project=<name>`:

```json
{
  "since": "2026-07-27T00:00:00Z",
  "totals": {"LOW": 87, "MEDIUM": 12, "HIGH": 3},
  "by_role": {
    "Backend_Engineer": {"LOW": 45, "MEDIUM": 6, "HIGH": 0},
    "Systems_Architect": {"LOW": 12, "MEDIUM": 4, "HIGH": 3}
  },
  "estimated_cost_usd": 4.20
}
```

Rendered as a small strip in the Task Detail panel.

---

## 3. Migration & Backward Compatibility

1. Existing `ADT_FORGE_MODEL` env var still honored — but only if it resolves to LOW or MEDIUM tier. HIGH-tier env var value emits a startup warning and downgrades to MEDIUM.
2. Existing `worker_escalation_step` events remain — augmented with new `effort_tier` field.
3. First-boot behaviour: if `config/model_tiers.json` is absent, framework defaults to LOW for everything except Systems_Architect (MEDIUM) — same defaults as the JSON above.

---

## 4. Acceptance Criteria

1. Forge on a fresh project with no env overrides uses `Gemini 3.6 Flash (Low)` for the initial attempt.
2. If the initial LOW forge worker fails (test: prompt the worker with an impossible constraint), executor auto-retries at MEDIUM without operator input. ADS shows `worker_effort_escalated {from: LOW, to: MEDIUM}`.
3. If MEDIUM also fails, the Forge Complete screen does NOT auto-transition. Instead, an `effort-escalation-modal` appears in the Console with the three-button choice.
4. Clicking `[Deny]` marks the task failed; ADS logs `worker_high_effort_denied`. Clicking `[Approve for this task]` runs the retry at HIGH; ADS logs `worker_high_effort_authorized` with scope=single_task.
5. `GET /api/governance/effort/budget?since=2026-07-27T00:00:00Z` returns non-zero counts after a session of usage.
6. Editing `config/model_tiers.json` without an SCR is denied by DTCP.
7. Regression test: attempting to invoke `Gemini 3.1 Pro (High)` from any executor without a live `worker_high_effort_authorized` for that run_id raises `EffortEscalationDenied` and emits `unauthorized_high_effort_attempt` to ADS.

---

## 5. Implementation Sequencing

1. **SA** — write `config/model_tiers.json` (this spec's Section 2.1 verbatim); register via SCR.
2. **BE #1** — `select_model(role, tier)` helper + refactor forge/decompose/build to call it. Ship with tier=LOW default. No escalation yet.
3. **BE #2** — add auto-escalate LOW→MEDIUM logic. ADS `worker_effort_escalated` events.
4. **BE #3** — add HIGH-tier gate: approval/denial endpoints + block-wait pattern.
5. **FE #1** — effort-escalation-modal + Tauri ADS listener wiring. Approve/Deny buttons hit endpoints.
6. **BE #4** — `/api/governance/effort/budget` endpoint + Task Detail strip renderer.
7. **Overseer** — one-time audit of first 20 real forges; verify no HIGH-tier invocation went ungated.

Sequenced so operators get relief (LOW default) at step 2 — before the modal work is even done.

---

## 6. Out of Scope / Follow-ups

- Per-operator budgets (personal daily caps).
- Cost-based auto-halt (e.g. "stop everything if session spend > $10").
- Model-quality-per-task heuristics (e.g. code tasks prefer Claude Sonnet).
- Federated quota across multiple operator accounts.

---

*"An unbounded escalation is an unbounded bill."*
