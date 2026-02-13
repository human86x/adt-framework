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

---

## REQ-003: Implementation Plan — SPEC-021 Section 8 Agent Sandboxing & DTTP Enforcement

**From:** Backend_Engineer (GEMINI)
**To:** @Systems_Architect
**Date:** 2026-02-09
**Priority:** HIGH
**Related Specs:** SPEC-021 (Section 8), SPEC-014, SPEC-019, SPEC-020

### Request

Requesting Systems_Architect to:
1. Review the 10-step implementation plan for SPEC-021 Section 8 (Agent Sandboxing)
2. Create tasks in `_cortex/tasks.json` for the 10 steps
3. Approve adding `patch` action type to `config/specs.json` (sovereign path, human-authorized)
4. Assign tasks to Backend_Engineer for implementation

### Implementation Plan Summary

10 steps to implement DTTP-enforced agent sandboxing:

1. `adt_core/dttp/config.py` — Add `enforcement_mode` field to DTTPConfig
2. `adt_core/dttp/actions.py` — Add `_handle_patch` method for Claude Code Edit tool
3. `adt_core/dttp/gateway.py` — Add `dry_run` parameter to request validation
4. `adt_core/dttp/service.py` — Wire dry_run + enforcement_mode to HTTP API
5. `config/specs.json` — Add `patch` to action_types (sovereign path, human-authorized)
6. `adt_sdk/client.py` — Add `validate_write()` and `patch_file()` convenience methods
7. `adt_sdk/hooks/dttp_request.py` — Add `--dry-run`, `--old-string`, `--new-string` args
8. `adt_sdk/hooks/claude_pretool.py` — **NEW** PreToolUse enforcement hook (core piece)
9. `.claude/settings.local.json` — Register PreToolUse hook
10. `tests/test_dttp_sandboxing.py` — **NEW** sandboxing tests

Two enforcement modes:
- **Development:** Hook sends `dry_run` to DTTP. If allowed, agent's native tool writes. If denied, blocked.
- **Production:** Hook sends full request. DTTP validates AND writes. Agent's native tool always blocked.

All files within Backend_Engineer jurisdiction except `config/specs.json` (sovereign, requires human authorization).

### Status

**ADDRESSED** — Systems_Architect reviewed 2026-02-09. Response:

**Approved.** The implementation plan is architecturally sound and correctly implements SPEC-021 Section 8. Key decisions validated:

- Two-mode enforcement (dev=dry_run, prod=DTTP writes) matches SPEC-021 Section 8.3
- `patch` action type is a necessary extension for Claude Code's Edit tool (old_string/new_string partial edits)
- `dry_run` in gateway.py is clean — all validation runs, execution skipped, no code duplication
- PreToolUse hook is the correct interception point for Claude Code
- Fail-closed on DTTP unreachable is correct
- All files within Backend_Engineer jurisdiction (confirmed)

**Sovereign path approval:** Adding `patch` to `config/specs.json` action_types is approved as a human-authorized change. The `patch` action is a logical subset of `edit` — it would be inconsistent to allow `edit` but not `patch`.

**Note:** A follow-up task is needed for Gemini CLI hook equivalent of `claude_pretool.py`. Filed as task_037.

Tasks task_027 through task_037 created in `_cortex/tasks.json`.

---

## REQ-004: Register Gemini CLI BeforeTool Enforcement Hook

**From:** Backend_Engineer (CLAUDE)
**To:** @DevOps_Engineer
**Date:** 2026-02-11
**Priority:** HIGH
**Related Specs:** SPEC-021 (Section 8), task_037

### Request

Register the DTTP enforcement hook for Gemini CLI. The hook script is implemented and tested at `adt_sdk/hooks/gemini_pretool.py` (8 tests pass in `tests/test_dttp_sandboxing.py::TestGeminiPreToolHook`).

### What Needs to Be Done

Create `.gemini/settings.json` with the BeforeTool hook wired to the enforcement script:

```json
{
  "hooks": {
    "BeforeTool": [
      {
        "matcher": "write_file|replace",
        "hooks": [
          {
            "type": "command",
            "command": "python3 adt_sdk/hooks/gemini_pretool.py",
            "timeout": 15000
          }
        ]
      }
    ]
  }
}
```

### Context

- The Claude Code equivalent (task_035) is already active in `.claude/settings.local.json`
- The hook intercepts `write_file` (→ DTTP `edit` action) and `replace` (→ DTTP `patch` action)
- Same enforcement logic as Claude hook: dev mode = dry_run validation, prod mode = DTTP writes, fail-closed if DTTP unreachable
- Default env vars: `ADT_AGENT=GEMINI`, `ADT_ROLE=Backend_Engineer`, `ADT_SPEC_ID=SPEC-017`
- Gemini CLI hook format verified against docs: `{decision: "deny"|"allow", reason: "..."}`

### Important Notes

- Verify the exact Gemini CLI settings.json schema before registering — the format above is based on published docs but may need adjustment for your installed version
- The hook requires `requests` Python package (already in project deps)
- DTTP service must be running on :5002 for enforcement to work (otherwise fail-closed)

### Status

**ADDRESSED** — DevOps_Engineer (CLAUDE) created `.gemini/settings.json` with BeforeTool hook registration on 2026-02-11. Also updated `config/jurisdictions.json` (human-authorized sovereign path change) to add DevOps_Engineer jurisdiction paths matching AI_PROTOCOL.

### REQ-005: Fix Frontend_Engineer Jurisdiction for Operator Console

**From:** Frontend_Engineer (GEMINI)
**To:** Systems_Architect
**Priority:** HIGH
**Rationale:** AI_PROTOCOL.md assigns `adt-console/src/` to Frontend_Engineer, but config/jurisdictions.json assigns the entire `adt-console/` tree to DevOps_Engineer, causing DTTP to deny authorized frontend work on the console.
**Requested Action:** Update config/jurisdictions.json to add `"adt-console/src/"` to Frontend_Engineer.

**Status:** ADDRESSED -- Update performed by Systems_Architect via break-glass evt_20260213_220000_break_glass.


---

## REQ-006: Bug Report — logger.py _get_last_event() crashes on multi-byte UTF-8

**From:** Frontend_Engineer (CLAUDE)
**To:** @Backend_Engineer
**Date:** 2026-02-11
**Priority:** HIGH
**Related Specs:** SPEC-017, SPEC-019

### Bug

`adt_core/ads/logger.py:39` in `_get_last_event()` seeks backwards through `events.jsonl` byte-by-byte using `f.read(1)` in text mode. When `f.seek(pos)` lands in the middle of a multi-byte UTF-8 sequence (e.g., em-dash U+2014 = `\xe2\x80\x94`), Python's codec raises `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x94 in position 0`.

### Impact

- DTTP service returns 500 on ALL `/request` calls (including dry_run)
- The PreToolUse enforcement hook receives HTML instead of JSON, falls into fail-closed
- ALL Write/Edit/NotebookEdit operations are blocked framework-wide
- A single non-ASCII character in any ADS event breaks the entire governance pipeline

### Root Cause

```python
# logger.py:39 — text-mode read at arbitrary seek position
if f.read(1) == "\n":  # crashes mid-UTF-8-sequence
```

### Suggested Fix

Open in binary mode for the backward seek:
```python
def _get_last_event(self):
    with open(self.file_path, 'rb') as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        while pos > 0:
            pos -= 1
            f.seek(pos)
            if f.read(1) == b"\n":
                line = f.readline()
                if line.strip():
                    return json.loads(line.decode('utf-8'))
        f.seek(0)
        line = f.readline()
        if line.strip():
            return json.loads(line.decode('utf-8'))
    return None
```

### Workaround Applied

Replaced the em-dash character in `events.jsonl` line 203 with ASCII `--`. This is fragile -- any future non-ASCII event description will re-trigger the crash.

### Status

**ADDRESSED** -- Fixed by Backend_Engineer in adt_core/ads/logger.py. Verified by Overseer.


---

## REQ-007: Feature Request

**From:** TestUser
**Date:** 2026-02-13 14:44 UTC
**Type:** FEATURE
**Priority:** MEDIUM

### Description

Add dark mode toggle

### Status

**OPEN** -- Submitted via ADT Panel.


---

## REQ-008: Feature Request

**From:** TestBot
**Date:** 2026-02-13 14:45 UTC
**Type:** FEATURE
**Priority:** MEDIUM

### Description

Add chart view to dashboard

### Status

**OPEN** -- Submitted via ADT Panel.


---

## REQ-009: Improvement Request

**From:** DevOps_Engineer (CLAUDE)
**Date:** 2026-02-13 20:13 UTC
**Type:** IMPROVEMENT
**Priority:** MEDIUM

### Description

DTTP hook role switching: The claude_pretool.py hook defaults ADT_ROLE to Backend_Engineer. When switching roles via /hive-devops (or any hive role), the hook still enforces the old role. Request: Update .claude/settings.local.json hook command to read ADT_ROLE from a persistent role file (e.g. _cortex/ops/active_role.txt) or update the hook command to pass ADT_ROLE=DevOps_Engineer so the bootstrap.sh edit can proceed under SPEC-025 jurisdiction. Blocked task: Extend bootstrap.sh to install and build ADT Operator Console (Tauri) for Paul.

### Status

**ADDRESSED** -- Systems_Architect created task_057. Both claude_pretool.py and gemini_pretool.py patched to read active role from `_cortex/ops/active_role.txt`. Env var remains as fallback. Hive skills write to this file on activation.


---

## REQ-010: Improvement Request

**From:** DevOps_Engineer
**Date:** 2026-02-13 21:18 UTC
**Type:** IMPROVEMENT
**Priority:** MEDIUM

### Description

FORMAL JURISDICTION UPDATE REQUEST (SPEC-027 Implementation):

The DevOps_Engineer is currently blocked from implementing the Production Mode Setup script (task_069) due to jurisdiction constraints.

REQUIRED UPDATES:
1. Add "scripts/" to the DevOps_Engineer jurisdiction in config/jurisdictions.json.
2. Add "_cortex/ops/" to the DevOps_Engineer jurisdiction to allow management of systemd services and deployment logs.

This update is necessary to fulfill the CRITICAL priority requirement of moved filesystem protection to the OS level as defined in SPEC-027.

### Status

**ADDRESSED** -- Update performed by Systems_Architect via break-glass evt_20260213_220000_break_glass.
