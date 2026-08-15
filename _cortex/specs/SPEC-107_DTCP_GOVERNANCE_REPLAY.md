# SPEC-107: DTCP Governance Replay (Demo Simulator)

**Status:** APPROVED
**Author:** Systems_Architect
**Created:** 2026-08-14
**Tier:** Operational
**Depends On:** SPEC-105 (Worker Namespace Sandbox), SPEC-106 (DTCP Monitor)
**Scope:** Framework-level utility that can target any child project.

**Intent:** Provide a fast, real-behavior driver that fires N DTCP `/request`
calls against a target child project's DTCP so the DTCP Monitor panel shows
the traffic volume a properly-instrumented forge/build lifecycle would have
produced. Used for demo videos and screenshots where the panel needs to
reflect the framework's actual enforcement capacity rather than the sparse
handful of requests from a single build.

**Triggering Event:** Operator request 2026-08-14 during SPEC-100 build:
"how many dtcp request the solar system project should have if it would be
properly using dtcp? i need a spec for that project that will as fast as
possible simulate those dtcp requests so i have the proper numbers on the
panel for the video". The DTCP Monitor tiles were showing only 2 requests
(from a single earlier smoke test) even though a fully-governed lifecycle for
solar_system would have produced ~500-700 requests across its vision forge,
6 feature-spec builds, and 2 SPEC-100 attempts. Without a replay tool the
operator cannot capture panel screenshots that reflect the framework's real
enforcement scale.

**Success Condition:** Running `_cortex/ops/dtcp_replay.py --count N` produces:
1. Exactly N POST `/request` calls against the target child DTCP.
2. Each request routed through the real `adt_core.sandbox.reconciler` code
   path (no synthetic ADS injection).
3. The DTCP Monitor `Total Requests` tile increases by N; `Allowed` and
   `Denied` tiles reflect DTCP's real decisions.
4. Every request is recorded as a `worker_write_denied_by_dtcp` or
   `worker_reconciliation_complete` event in the target project's ADS.

---

## 1. Anti-Goals

- **Not** injecting synthetic ADS events. Numbers must be earned through the
  real reconciler -> DTCP path. If the DTCP is down, counters stay flat.
- **Not** modifying files under the real target project tree. All writes are
  performed inside a scratch workspace; the reconciler diffs against the real
  project so the outcome is deterministic and non-destructive.
- **Not** shipping to production. Guarded by `--i-know-this-is-a-demo` flag.

## 2. Files

- `_cortex/ops/dtcp_replay.py` -- driver (new, ~150 lines).
- `_cortex/specs/SPEC-107_DTCP_GOVERNANCE_REPLAY.md` -- this spec.

## 3. Invocation

```
python3 _cortex/ops/dtcp_replay.py \
    --project-root /home/human/Projects/solar_system_1786569181 \
    --dtcp-url http://localhost:5006 \
    --count 600 \
    --deny-ratio 0.05 \
    --burst 50 \
    --i-know-this-is-a-demo
```

Each `--burst` batch creates one synthetic worker: it writes `burst` files
into a temp workspace, then calls `reconcile_overlay()` with the project's
DTCP URL. The reconciler POSTs each file's `/request`, DTCP returns
allow/deny, and the summary event `worker_reconciliation_complete` fires.

## 4. Acceptance Criteria

**AC-1:** `curl /api/governance/sandbox/status` before running reports
`enforcement_active: true`. After running with `--count 600`, the DTCP Monitor
for the target project shows `Total Requests >= 600` within one auto-refresh
cycle (5s).

**AC-2:** ADS delta on `<project_root>/_cortex/ads/events.jsonl` grows by
`ceil(600/burst)` reconciliation-complete events plus per-file denial events
proportional to `deny-ratio`.

**AC-3:** `git status` under the real target project shows no changes as a
result of the replay -- the synthetic workspace stays isolated.

## 5. Reads From

- SPEC-105 §4 (reconciler contract)
- SPEC-106 (DTCP Monitor panel data source)
- `adt_core/sandbox/reconciler.py::reconcile_overlay`
- AI_PROTOCOL §1.3 (DTCP compliance)

## 6. Non-Goals

- Not covering load-test scenarios (concurrent worker floods).
- Not exercising DTCP jurisdiction rules exhaustively -- just enough
  allow/deny mix to make the panel numbers realistic.
