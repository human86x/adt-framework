# SPEC-078: Post-Forge Governance Repairs

**Status:** APPROVED (operator directive, 2026-08-03)
**Author:** Systems_Architect (CLAUDE)
**Date:** 2026-08-03
**Tier:** Operational (parts A, B, C) + Constitutional (part D — touches worker orchestration)
**Priority:** P0 for part D, P1 for parts A/B/C
**Discovered via:** ar_art_preview_1785764174 forge run (2026-08-03) — see REQs 118, 119, 120, 121
**Complements / Amends:** SPEC-067 (Forge Wizard), SPEC-021 (Operator Console), SPEC-049 (CAOP), SPEC-076-A

**Intent:** Fix four demo-visible governance failures surfaced by the SPEC-077 (AR Art Preview) forge run. The framework's central value proposition -- "governed AI produces reliable outcomes" -- is contradicted by each of these failures. This spec bundles them because they are discovered together, block the same demo, and want coordinated verification.

**Triggering Event:** 2026-08-03 forge of ar_art_preview_1785764174. Operator watched 40 minutes of silence after pressing Forge → Decompose; investigation revealed (a) the forge itself completed but produced a colliding spec tree, (b) decompose worker hit an expired agy OAuth token and silently timed out at 60s, (c) the Spec Map showed 89 framework specs mixed with the 6 project specs. All four defects individually would be non-blocking; together on-camera they invalidate the demo thesis.

**Success Condition:** After parts A–D land, re-running the SPEC-077 template produces (a) a clean spec tree with no SPEC-001 collision, (b) decompose that either succeeds or PAUSES with a visible operator prompt (never a silent timeout), (c) a Spec Map that shows exactly the project's specs. The 40-minute mystery becomes a 10-second modal.

---

## Part A — Reject duplicate spec_id at the API (REQ-118)

**Owner:** Backend_Engineer
**Jurisdiction:** `adt_center/api/governance_routes.py`
**Change:** `POST /api/specs` returns HTTP 409 when the requested `spec_id` collides with an existing file in the project's specs dir. Adds `allocation_source: client|server` to the `spec_created` ADS event.
**Details:** see REQ-118 in `_cortex/requests.md`.

## Part B — Forge Architect prompt reserves SPEC-001 for Vision (REQ-119)

**Owner:** Backend_Engineer
**Jurisdiction:** `adt_center/api/forge_prompts/architect.md`
**Change:** Add an explicit rule to Phase B: "Child specs MUST start numbering at SPEC-002. SPEC-001 is reserved for the Vision spec you filled in Phase A. NEVER POST `spec_id: SPEC-001` in Phase B. If unsure, pass null and let the server allocate."
**Details:** see REQ-119.

## Part C — Spec Map project scoping is unbreakable (REQ-120)

**Owner:** Frontend_Engineer (primary), Backend_Engineer (safety-belt fix)
**Jurisdiction:** `adt-console/src/js/spec_map.js`, `adt_center/app.py:get_project_paths`
**Change:**
1. Frontend: every `/api/specs*` fetch call in spec_map.js MUST pass `?project=${currentProject}` and the current project variable MUST never be undefined at fetch time. Known leak points: lines 42, 877, 1050, 1891-1892 (conditional).
2. Backend safety belt: `get_project_paths(name)` when `name` is passed but not in registry currently falls back to `FRAMEWORK_ROOT` silently — change to return an "empty" resource set (or 404) so any residual frontend leak is *visible* rather than silent.
**Details:** see REQ-120.

## Part D — Worker interactive prompts pause + notify, never silent timeout (REQ-121, P0)

**Owner:** DevOps_Engineer (primary, worker-spawn code), Backend_Engineer (API), Frontend_Engineer (Console modal)
**Jurisdiction:** `adt_sdk/`, `adt_center/api/`, `adt-console/src/`
**Change:** Introduce a worker output classifier that detects interactive-prompt signatures (OAuth URLs, `password:`, `[Y/n]`, TOTP, etc.). On match: SUSPEND the worker (SIGSTOP or hold-stdin), emit `worker_awaiting_operator_input` ADS event, expose via `GET /api/workers/awaiting_input`, surface a Console modal, RESUME on operator confirmation (SIGCONT + refreshed auth state). Fail-safe: no operator response in 24h → clean cancel with `worker_auth_abandoned`.
**Details:** see REQ-121.

**Why P0:** the ADT framework's whole value proposition is contradicted by a governed system that silently loses 40 operator-minutes to an expired token. This part alone justifies the spec's priority.

---

## Rollout

Parts A, B, C, D can be built in parallel by three separate role workers (Backend takes A+B, Frontend takes C-frontend, DevOps takes D + collaborates with Backend for API + Frontend for modal). Each part has its own acceptance test in its REQ.

## Cross-cutting acceptance

Re-run the ar_art_preview forge after all parts land:
- Vision + SPEC-002…SPEC-00N children, no SPEC-001 collision (A + B)
- Spec Map on the project shows exactly N specs, no framework bleed (C)
- If agy is de-authed, decompose PAUSES with a visible modal; operator re-auths, presses Resume, decompose completes (D)

## Verification event

On completion of all four parts, Systems_Architect logs `spec_078_verified` to ADS with a summary of the re-run outcome.
