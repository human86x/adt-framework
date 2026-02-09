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

---

## REQ-002: Spec Request — Mandatory Git Persistence and DTTP-Governed Push

**From:** DevOps_Engineer (CLAUDE)
**To:** @Systems_Architect
**Date:** 2026-02-09
**Priority:** CRITICAL
**Related Specs:** SPEC-014, SPEC-015, SPEC-019, SPEC-020

### Request

Requesting a new spec to make **git commit + push mandatory after file edits** and to bring **git push under DTTP jurisdiction**.

### Problem

As of 2026-02-09, the ADT Framework had 6 commits on GitHub — all from the initial scaffold phase. Meanwhile, the entire framework (3 core engines, Operational Center, SDK, tests, DevOps artifacts, 3 new specs) was built across multiple agent sessions and **never committed or pushed**. This represents days of multi-agent work that existed only as unstaged local files.

The ADS logged 43 events documenting every action. The DTTP gateway enforced every file write. But the persistence layer (git) was completely ungoverned — no agent was required to commit, no spec mandated it, and no enforcement mechanism existed.

This is a governance gap. The framework governs file writes but not their permanence.

### Proposed Rules

#### 1. Mandatory Commit After Session Work
- Any agent session that produces file edits MUST end with a `git commit` before `session_end`
- The commit message MUST reference the spec(s) and task(s) that authorized the work
- The `session_end` ADS event MUST include a `commit_hash` field
- Sessions that fail to commit should be flagged as non-compliant in ADS

#### 2. Git Push as DTTP Action
- `git push` becomes a DTTP-governed action type: `action: "git_push"`
- Requires spec authorization like any other write action
- The DTTP gateway validates: branch name, target remote, commit range
- All pushes logged to ADS with: remote, branch, commit range, result
- In production (Phase 4+): only the `dttp` user can push (agents cannot reach git remote directly due to iptables)

#### 3. New DTTP Action Types
- `git_commit` — local commit (lower tier, session-level authorization)
- `git_push` — remote push (higher tier, explicit spec authorization required)
- `git_tag` — release tagging (highest tier, may require Tier 2 authorization per SPEC-020)

### Why Git Push Should Be DTTP-Only

1. **Consistency.** DTTP already governs file writes, SSH deploys, and FTP syncs. Git push is another form of "write to external system." Leaving it ungoverned creates an inconsistency.
2. **Audit trail.** A push changes what the world sees. It should be logged with the same rigor as an FTP deploy to oceanpulse.pt.
3. **Prevention of unauthorized publication.** An agent could push broken code, secrets, or unauthorized changes to a public repository. DTTP validation (spec check, jurisdiction check) prevents this.
4. **The framework governs itself.** If git push is ungoverned, the governance artifacts themselves (specs, tasks, protocol) can be published without oversight. This contradicts the self-governance principle.

### What the Spec Should Define

1. Session commit requirements (mandatory commit before session_end)
2. DTTP `git_push` action type with validation rules
3. Branch protection rules (main branch = higher authorization tier)
4. ADS schema extensions for git-related events
5. Mirror sync coordination (push to GitHub + deploy to oceanpulse.pt should be linked)
6. Emergency/break-glass procedure for direct pushes (aligned with SPEC-020)

### Status

**OPEN** — Awaiting Systems_Architect review.
