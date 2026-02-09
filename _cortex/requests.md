# Cross-Role Requests

---

## REQ-001: Spec Request — Standalone DTTP Service Architecture

**From:** Backend_Engineer (CLAUDE)
**To:** @Systems_Architect
**Date:** 2026-02-07
**Priority:** HIGH
**Related Specs:** SPEC-014 (DTTP Implementation)

### Request

Requesting a new spec (or SPEC-014 amendment) to define DTTP as a **standalone service from day one**, rather than an in-process library extracted later.

### Problem with Current Approach

SPEC-014 describes a 5-phase rollout where DTTP starts as a library embedded in the Flask app, then gets extracted into a privilege-separated process at Phase 4. Gemini built it this way — `adt_core/dttp/` is wired directly into `adt_center/app.py` as an in-process call.

This creates two problems:

1. **Architecture drift.** Building DTTP as an in-process library means its interfaces, error handling, and execution model are designed for function calls, not IPC/HTTP. Extracting it later means rewriting those interfaces — not just moving files.

2. **Late integration risk.** The hardest part of privilege separation isn't the OS permissions — it's making the service work correctly as an independent process. Building it embedded and extracting later pushes that complexity to the end.

### Proposed Approach

Build DTTP as a **standalone service from the start**. Two modes, same codebase:

```
DEVELOPMENT MODE (now):
  - DTTP runs as a separate Flask/process on its own port (e.g., :5002)
  - Agents and the Operational Center talk to it over HTTP
  - Everyone runs as the same OS user (human) — no privilege separation
  - Engineers can freely edit DTTP code, configs, everything
  - Functionally identical to production, minus the access restrictions

PRODUCTION MODE (Phase 4+):
  - Same DTTP service, same code, same API
  - Runs under `dttp` OS user with elevated write permissions
  - Agents run under `agent` OS user with read-only + network restrictions
  - iptables / file permissions enforced
  - The ONLY difference: who runs the process and what OS permissions they have
```

### What the Spec Should Define

1. **DTTP Service API** — standalone HTTP endpoints (not Flask blueprint)
   - `POST /request` — the gateway (validate + execute + log)
   - `GET /status` — health check
   - `GET /policy` — current policy/jurisdiction state (read-only)
2. **Service configuration** — how DTTP finds specs, jurisdictions, ADS path, project root
3. **Operational Center integration** — how the dashboard talks to DTTP (HTTP client, not in-process)
4. **Agent SDK integration** — `ADTClient` talks to DTTP over HTTP instead of importing it
5. **Dev vs Production mode** — same code, different OS-level privileges only
6. **No phased extraction** — eliminate the "build embedded, extract later" pattern from SPEC-014

### Why This Is Better

- **What you build is what you ship.** No rewrite at Phase 4.
- **Development is unrestricted.** Engineers edit anything freely. The privilege separation is purely an ops concern at deployment time.
- **Testable end-to-end now.** We can test the full agent → DTTP → action → ADS flow over HTTP today, exactly as it will work in production.
- **Clean separation of concerns.** Operational Center = monitoring/UI. DTTP = enforcement. They're different services with different responsibilities.

### Status

**ADDRESSED** — Systems_Architect reviewed 2026-02-07. Response: **SPEC-019 drafted.**

The request is architecturally sound. SPEC-019 (DTTP Standalone Service Architecture) has been written to define DTTP as a standalone HTTP service from day one, superseding the phased extraction approach in SPEC-014. The spec preserves all existing domain logic (`gateway.py`, `policy.py`, `jurisdictions.py`, `actions.py`) unchanged and adds a thin HTTP wrapper (`service.py`).

SPEC-019 is in DRAFT status pending human approval. Implementation tasks (task_008 through task_013) are defined in the spec and will be added to `tasks.json` upon approval.

Additionally, SPEC-018 (Phase 1 Hardening) addresses the security issues (path traversal, path matching bypass) that must be fixed before SPEC-019 implementation begins.
