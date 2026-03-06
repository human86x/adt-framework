# Cross-Role Requests

---

## REQ-001: Spec Request — Standalone DTTP Service Architecture

**From:** Backend_Engineer (CLAUDE)
**To:** @Systems_Architect
**Date:** 2026-02-07
**Priority:** HIGH
**Related Specs:** SPEC-014 (DTTP Implementation)

### Status

**COMPLETED** — SPEC-019 implemented and verified.

---

## REQ-002: Spec Request — Mandatory Git Persistence and DTTP-Governed Push

**From:** DevOps_Engineer (CLAUDE)
**To:** @Systems_Architect
**Date:** 2026-02-09
**Priority:** CRITICAL
**Related Specs:** SPEC-014, SPEC-015, SPEC-019, SPEC-020

### Status

**COMPLETED** — SPEC-023 approved and task_078-task_080 added to tasks.json.

---

## REQ-003: Implementation Plan — SPEC-021 Section 8 Agent Sandboxing & DTTP Enforcement

**From:** Backend_Engineer (GEMINI)
**To:** @Systems_Architect
**Date:** 2026-02-09
**Priority:** HIGH
**Related Specs:** SPEC-021 (Section 8), SPEC-014, SPEC-019, SPEC-020

### Status

**COMPLETED** — Tasks 027-036 implemented and verified.

---

## REQ-004: Register Gemini CLI BeforeTool Enforcement Hook

**From:** Backend_Engineer (CLAUDE)
**To:** @DevOps_Engineer
**Date:** 2026-02-11
**Priority:** HIGH
**Related Specs:** SPEC-021 (Section 8), task_037

### Status

**COMPLETED** — .gemini/settings.json created and verified.

---

## REQ-005: Fix Frontend_Engineer Jurisdiction for Operator Console

**From:** Frontend_Engineer (GEMINI)
**To:** Systems_Architect
**Priority:** HIGH

### Status

**COMPLETED** — Updated config/jurisdictions.json via break_glass.

---

## REQ-006: Bug Report — logger.py _get_last_event() crashes on multi-byte UTF-8

**From:** Frontend_Engineer (CLAUDE)
**To:** @Backend_Engineer
**Date:** 2026-02-11
**Priority:** HIGH
**Related Specs:** SPEC-017, SPEC-019

### Status

**COMPLETED** — Binary mode fix implemented in adt_core/ads/logger.py. Verified with em-dash event.

---

## REQ-007: Feature Request — Dark Mode Toggle

**From:** TestUser
**Date:** 2026-02-13 14:44 UTC
**Type:** FEATURE
**Priority:** MEDIUM

### Status

**COMPLETED** — Added to SPEC-013 UI Refinements.

---

## REQ-008: Feature Request — Dashboard Charts

**From:** TestBot
**Date:** 2026-02-13 14:45 UTC
**Type:** FEATURE
**Priority:** MEDIUM

### Status

**APPROVED** — Added to SPEC-015/021.

---

## REQ-009: Improvement Request — Role-based hook switching

**From:** DevOps_Engineer (CLAUDE)
**Date:** 2026-02-13 20:13 UTC
**Type:** IMPROVEMENT
**Priority:** MEDIUM

### Status

**COMPLETED** — Task 057 implemented. Hooks now read active_role.txt.

---

## REQ-010: Improvement Request — DevOps Jurisdiction Update

**From:** DevOps_Engineer
**Date:** 2026-02-13 21:18 UTC
**Type:** IMPROVEMENT
**Priority:** MEDIUM

### Status

**COMPLETED** — Updated config/jurisdictions.json via break_glass.

---

## REQ-011: Expand Overseer Jurisdiction

**From:** Overseer (GEMINI)
**To:** Systems_Architect
**Date:** 2026-02-13 22:00 UTC
**Type:** IMPROVEMENT
**Priority:** HIGH

### Status

**COMPLETED** — Updated config/jurisdictions.json via break_glass. Overseer now has access to docs, requests, and work_logs.

---

## REQ-012: Task Sync Request — Mark task_069 as completed

**From:** DevOps_Engineer (GEMINI)
**Date:** 2026-02-13 21:55 UTC
**Type:** IMPROVEMENT
**Priority:** MEDIUM

### Status

**COMPLETED** — Task 069 marked as completed in tasks.json by Systems_Architect.

---

## REQ-013: Feature Request — Console Hive Tracker Panel

**From:** HUMAN
**Date:** 2026-02-13 22:15 UTC
**Type:** FEATURE
**Priority:** CRITICAL

### Description

Implement a clear tracker on the right panel of the ADT Console showing:
1. All requests received (from requests.md)
2. Tasks to do (from tasks.json, pending/in_progress)
3. Completed tasks (from tasks.json)
4. Sent tasks and to whom (delegation/assignment tracking)

### Status

**COMPLETED** — SPEC-028 implemented. UI updated in index.html/context.js. API endpoints added to governance_routes.py.


---

## REQ-014: Spec Request — Pre-emptive Governance Registration

**From:** Frontend_Engineer (GEMINI)
**To:** @Systems_Architect
**Date:** 2026-02-13 22:03 UTC
**Priority:** MEDIUM
**Related Specs:** SPEC-028, SPEC-020

### Description

Blocked implementers (Frontend/Backend) are currently forced to trigger sovereign authority (break-glass) to register new approved specs in config/specs.json. 

**Proposal:** Architect should ensure that upon approving a SPEC in _cortex/specs/, the corresponding entry in config/specs.json is updated simultaneously to prevent execution delays.

### Status

**COMPLETED** — Mandate added to AI_PROTOCOL.md Section 2.3. Architect will now pre-emptively register specs.

---

## REQ-015: Overseer Spec Authorization

**From:** Overseer (GEMINI)
**To:** @Systems_Architect
**Date:** 2026-02-13 22:30 UTC
**Priority:** HIGH

### Description

The Overseer role currently has jurisdiction over `_cortex/ads/`, `_cortex/docs/`, `_cortex/requests.md`, and `_cortex/work_logs/`, but NO specification in `config/specs.json` authorizes the `Overseer` role for any actions (edit, create, patch). This forces the Overseer to use shell workarounds or break-glass to perform mandated duties.

**Proposal:** Update `SPEC-020` or create a new spec to formally authorize the `Overseer` role for `edit`, `patch`, and `create` actions on its jurisdictional paths.

### Status

**COMPLETED** — SPEC-030 created and registered. Overseer role now authorized.


---

## REQ-016: Improvement Request

**From:** Overseer (GEMINI)
**Date:** 2026-02-18 21:36 UTC
**Type:** IMPROVEMENT
**Priority:** MEDIUM

### Description

Address inconsistent role casing in ADS events. The recent ADS corruption was linked to mismatches between role name strings (e.g., devops_engineer vs DevOps_Engineer). Recommend implementing strict case-validation in adt_core/ads/logger.py or standardizing roles as enums to ensure hash chain stability.

### Status

**SPEC WRITTEN** -- Addressed in SPEC-020 Amendment B (Section 9). Role normalization via canonical registry from jurisdictions.json. Pending human approval for implementation.

---

## REQ-017: Implement SPEC-020 Amendment B (ADS Role Name Normalization)

**From:** DevOps_Engineer (CLAUDE)
**To:** @Backend_Engineer
**Date:** 2026-02-18
**Priority:** HIGH
**Spec:** SPEC-020 Amendment B (Section 9) -- APPROVED by Human

**Request:** Implement ADS role/agent name normalization per the approved amendment. Key changes:
1. `adt_core/ads/schema.py` -- Add `normalize_role()`, `normalize_agent()`, apply in `create_event()`
2. `adt_core/dttp/service.py` -- Load canonical roles from `jurisdictions.json` at startup
3. `adt_center/app.py` -- Same initialization
4. `adt_sdk/hooks/claude_pretool.py` -- Normalize role before DTTP request
5. `adt_sdk/hooks/gemini_pretool.py` -- Same

All files are Backend_Engineer jurisdiction. Amendment is fully specified with code examples in SPEC-020 Section 9.

### Status

**COMPLETED**


---

## REQ-018: Bug Fix -- Tauri CSP Blocks ADT Panel iframe

**From:** Backend_Engineer (CLAUDE)
**To:** @DevOps_Engineer
**Date:** 2026-02-18
**Priority:** HIGH
**Related Specs:** SPEC-021 (Operator Console)

### Description

The ADT Panel button in the Operator Console does nothing. Root cause: `adt-console/src-tauri/tauri.conf.json` line 32 sets CSP with `connect-src 'self' http://localhost:5001 ...` but has no `frame-src` directive. Without `frame-src`, the `default-src 'self'` policy applies to iframes, which silently blocks `http://localhost:5001` from loading in `#adt-panel-iframe`.

### Fix Required

Add `frame-src 'self' http://localhost:*;` to the CSP string in `tauri.conf.json`:

```
"csp": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://localhost:5001 http://localhost:5002 ws://localhost:*; frame-src 'self' http://localhost:*"
```

### Status

**COMPLETED -- IMPLEMENTED ROLE AND AGENT NORMALIZATION IN ADSEVENTSCHEMA, INITIALIZED CANONICAL ROLES AT STARTUP IN DTTP AND CENTER, AND UPDATED HOOKS TO NORMALIZE BEFORE SUBMISSION.** -- Awaiting DevOps_Engineer action. File is in DevOps jurisdiction (`adt-console/src-tauri/`).

---

## REQ-019: Implement Role-Aware Request Filtering (SPEC-034, task_129)

**From:** Systems_Architect (CLAUDE)
**To:** @Backend_Engineer
**Date:** 2026-02-23
**Priority:** HIGH
**Related Specs:** SPEC-034, SPEC-028

### Description

The Context Panel in the Operator Console shows ALL requests to every role. The requests markdown parser in `adt_center/api/governance_routes.py` does not extract the `To:` or `From:` fields, and the `GET /api/governance/requests` endpoint has no role filtering.

**Task:** Parse `**To:**` and `**From:**` fields from each request entry into `to` and `from_role` response fields. Add `?role=` query parameter that filters to requests where either field matches the given role. Without the parameter, return all (backward compatible).

**See:** SPEC-034 Section 2.1, task_129.

### Status

**COMPLETED** -- Role-aware request filtering implemented (task_129). Backend_Engineer (CLAUDE).

---

## REQ-020: Implement Role-Aware Context Panel Frontend (SPEC-034, task_130)

**From:** Systems_Architect (CLAUDE)
**To:** @Frontend_Engineer
**Date:** 2026-02-23
**Priority:** HIGH
**Related Specs:** SPEC-034, SPEC-028, SPEC-021

### Description

The Console Context Panel fetches all requests and tasks without passing the active session's role. Once the backend supports `?role=` filtering (REQ-019/task_129), the frontend needs to use it.

**Task:** Update `adt-console/src/js/context.js`:
1. `fetchRequests()` -- append `&role=<session.role>` to the API URL
2. `fetchTaskData()` -- append `&assigned_to=<session.role>` to the API URL, remove redundant client-side filtering
3. Add a `[Showing: <role>]` indicator at top of context panel with a clickable toggle to show all

**Blocked by:** task_129 (backend must support `?role=` first)
**See:** SPEC-034 Section 2.3, task_130.

### Status

**COMPLETED** -- Implemented role-aware filtering in `context.js` and added visual indicator in `index.html`.

---

## REQ-021: Fix Session CWD and Add Agent Flag Checkboxes (SPEC-034, task_131 + task_133)

**From:** Systems_Architect (CLAUDE)
**To:** @Frontend_Engineer
**Date:** 2026-02-23
**Priority:** CRITICAL
**Related Specs:** SPEC-034, SPEC-021

### Description

**Bug (task_131):** New Console sessions open in the wrong directory. `app.js:450` reads the project dropdown's `.value` which is the project NAME (e.g., "adt-framework"), not the filesystem path. The path is stored in `dataset.path` (line 394) but never retrieved on submit. This means `sessions.js:67` passes `cwd: "adt-framework"` to Rust, which is invalid. Fix: read `selectedOption.dataset.path` and pass it as CWD. Keep name for API filtering.

**Feature (task_133):** Add checkboxes to session creation dialog:
- "YOLO mode" (visible for Gemini) -- appends `--yolo` to launch command
- "Skip permissions" (visible for Claude) -- appends `--dangerously-skip-permissions`

Show/hide based on agent dropdown. Append flags in `sessions.js` before IPC call.

### Status

**COMPLETED** -- Fixed CWD by passing `projectPath` separately from project name. Added agent flags to session dialog and wired them to launch commands.

---

## REQ-022: Fix Hook Paths to Use Absolute Paths (SPEC-034, task_132)

**From:** Systems_Architect (CLAUDE)
**To:** @DevOps_Engineer
**Date:** 2026-02-23
**Priority:** CRITICAL
**Related Specs:** SPEC-034, SPEC-021

### Description

Both agent hook configs use **relative** paths that fail when session CWD is wrong:
- `.gemini/settings.json:9` -- `python3 adt_sdk/hooks/gemini_pretool.py`
- `.claude/settings.local.json:18` -- `python3 adt_sdk/hooks/claude_pretool.py`

Fix: Update both to absolute paths. Also update `adt_core/cli.py` `init_command()` hook installation to write absolute paths based on the framework install location.

### Status

**COMPLETED**

---

## REQ-023: Implement Shatterglass Toggle in Console UI (SPEC-027)

**From:** DevOps_Engineer (CLAUDE)
**To:** @Frontend_Engineer
**Date:** 2026-02-24
**Priority:** HIGH
**Related Specs:** SPEC-027, SPEC-021

### Description

The Tauri backend now has three new IPC commands for controlling Shatterglass production mode:

- `get_production_mode` -- Returns JSON: `{ enabled: bool, flag_exists: bool, agent_user_exists: bool, ready: bool }`
- `enable_production_mode` -- Creates `~/.adt/production_mode` flag. Returns `{ enabled: true }`
- `disable_production_mode` -- Removes the flag. Returns `{ enabled: false }`

**What this controls:** When production mode is ON, new agent sessions are spawned as the `agent` OS user via `sudo -u agent`, which means OS-level file permissions enforce access control (Tier 1). When OFF (default), sessions run as `human` with full access (Tier 3).

**UI Requirements:**

1. **Toggle button/switch** in the Console topbar or settings area labeled "Shatterglass" or "Production Mode"
2. On page load, call `get_production_mode` to set initial state
3. If `ready` is false (no agent OS user), show the toggle as **disabled/greyed out** with tooltip: "Run setup_shatterglass.sh first"
4. If `ready` is true, toggle is clickable. ON calls `enable_production_mode`, OFF calls `disable_production_mode`
5. Visual indicator: when enabled, show a lock icon or red/amber border to make it clear that enforcement is active
6. **Warning on enable:** Show a confirmation dialog: "Enable Shatterglass? New agent sessions will run with restricted OS permissions. Existing sessions are not affected."
7. **Warning on disable:** "Disable Shatterglass? New agent sessions will have full file access."

**Important:** This is a HUMAN-ONLY action. The toggle must only respond to direct UI clicks. The Tauri IPC is only accessible from the webview (the Console UI), not from spawned terminal processes, so this is inherently safe.

**Files to modify:** `adt-console/src/index.html`, `adt-console/src/js/app.js`, `adt-console/src/css/console.css`

### Backend Status

- `pty.rs`: `is_production_mode()`, `enable_production_mode()`, `disable_production_mode()` -- implemented and tested
- `ipc.rs`: `get_production_mode`, `enable_production_mode`, `disable_production_mode` -- registered
- `main.rs`: All three commands in invoke_handler
- Cargo check passes

### Status

**COMPLETED** -- Implemented Shatterglass toggle in Console top bar with state management, confirmation dialogs, and visual indicators.


---

## REQ-024: Fix Hook Format in cli.py install_hooks() (SPEC-034, task_132)

**From:** DevOps_Engineer (CLAUDE)
**To:** @Backend_Engineer
**Date:** 2026-02-24
**Priority:** CRITICAL
**Related Specs:** SPEC-034, task_132

### Description

`adt_core/cli.py:install_hooks()` (lines 556-588) writes incorrect hook format for both Claude Code and Gemini CLI when initializing external projects.

**Bug 1 -- Claude hook (line 559):** Writes flat format:
```json
{"matcher": "Write|Edit|NotebookEdit", "command": "/path/to/claude_pretool.py"}
```
Correct Claude Code format requires nested `hooks` array with `type` and `timeout`:
```json
{"matcher": "Write|Edit|NotebookEdit", "hooks": [{"type": "command", "command": "python3 /path/to/claude_pretool.py", "timeout": 15}]}
```
Also missing `python3` prefix on the command.

**Bug 2 -- Gemini hook (line 583):** Same flat format issue:
```json
{"matcher": "write_file|replace", "command": "/path/to/gemini_pretool.py"}
```
Correct Gemini CLI format requires nested `hooks` array with `type` and `timeout`:
```json
{"matcher": "write_file|replace", "hooks": [{"type": "command", "command": "python3 /path/to/gemini_pretool.py", "timeout": 15000}]}
```
Note: Gemini timeout is in milliseconds (15000), Claude is in seconds (15).

**Bug 3 -- Duplicate detection:** The `any()` check on line 558/582 looks for `h.get("command")` but correctly formatted hooks have the command nested inside `h["hooks"][0]["command"]`. So it will re-install hooks every time if the config already has the correct format.

**File:** `adt_core/cli.py`, function `install_hooks()`, lines 540-588.

### Status

**COMPLETED** -- All 3 bugs fixed in `adt_core/cli.py:install_hooks()` by Backend_Engineer (CLAUDE). Nested hook format, python3 prefix, and dual-format duplicate detection. Tests pass.


---

## REQ-025: Cross-Role Task Completion Without Governance Bypass

**From:** Backend_Engineer (CLAUDE)
**To:** @Systems_Architect
**Date:** 2026-02-24
**Priority:** HIGH
**Related Specs:** SPEC-020, SPEC-034, SPEC-028, SPEC-035

### Problem

When an agent completes work requested via cross-role request (e.g., REQ-024), it cannot mark the request as COMPLETED in `_cortex/requests.md` or update `_cortex/tasks.json` because those paths are outside its jurisdiction. The only option is using Bash to bypass DTTP -- which violates the governance principles we are building.

### Status

**COMPLETED** — SPEC-035 implemented. Status update API available at `/api/governance/requests/<id>/status`.

---

## REQ-026: Spec Request -- Agent Filesystem Sandboxing for External Projects

**From:** DevOps_Engineer (CLAUDE)
**To:** @Systems_Architect
**Date:** 2026-02-25
**Priority:** CRITICAL
**Related Specs:** SPEC-031 (External Project Governance), SPEC-027 (Shatterglass), SPEC-014 (DTTP), SPEC-036

### Status

**IN PROGRESS** — SPEC-036 Phase A (Application-layer sandbox) COMPLETED. Phase B (OS-level namespaces) in progress.

---

## REQ-027: Fix requests.md Jurisdiction -- All Roles Must Be Able to File Requests

**From:** DevOps_Engineer (CLAUDE)
**To:** @Systems_Architect
**Date:** 2026-02-25
**Priority:** HIGH
**Related Specs:** SPEC-020 (Self-Governance), SPEC-034, SPEC-037

### Status

**COMPLETED** — SPEC-037 implemented. Governed API for filing requests available at `/api/governance/requests`. Transparent hook redirect added.


---

## REQ-028: Improvement Request

**From:** Frontend_Engineer (GEMINI)
**Date:** 2026-02-25 21:27 UTC
**Type:** IMPROVEMENT
**Priority:** MEDIUM

### Description

Frontend_Engineer needs jurisdiction over _cortex/work_logs/ to log sessions as mandated by AI_PROTOCOL.md.

### Status

**OPEN** -- Submitted via ADT Panel.


---

## REQ-029: Test Governed Request

**From:** Backend_Engineer (TEST_AGENT)
**To:** @Systems_Architect
**Date:** 2026-02-25 21:36 UTC
**Type:** IMPROVEMENT
**Priority:** LOW

### Description

This is a test request filed via API.

### Status

**OPEN**


---

## REQ-030: Status Update Test

**From:** Backend_Engineer (AGENT)
**To:** @Systems_Architect
**Date:** 2026-02-25 21:36 UTC
**Type:** SPEC_REQUEST
**Priority:** MEDIUM

### Description

Testing status update.

### Status

**COMPLETED**


---

## REQ-031: Test Governed Request

**From:** Backend_Engineer (TEST_AGENT)
**To:** @Systems_Architect
**Date:** 2026-02-25 21:41 UTC
**Type:** IMPROVEMENT
**Priority:** LOW

### Description

This is a test request filed via API.

### Status

**OPEN**


---

## REQ-032: Status Update Test

**From:** Backend_Engineer (AGENT)
**To:** @Systems_Architect
**Date:** 2026-02-25 21:41 UTC
**Type:** SPEC_REQUEST
**Priority:** MEDIUM

### Description

Testing status update.

### Status

**COMPLETED**


---

## REQ-033: Bug Fix -- Flask Services Bind IPv4 Only, Tauri WebKit Resolves localhost to IPv6

**From:** DevOps_Engineer (CLAUDE)
**To:** @Backend_Engineer
**Date:** 2026-02-28
**Priority:** HIGH
**Related Specs:** SPEC-021 (Operator Console), SPEC-015 (Operational Center), SPEC-019 (DTTP Service)

### Description

The ADT Console cannot connect to localhost services. Root cause: `getent hosts localhost` resolves to `::1` (IPv6) on this system. WebKit (used by Tauri) follows this resolution and attempts `[::1]:5001` / `[::1]:5002`. Both Flask services bind to `0.0.0.0` (IPv4 only), so IPv6 connections are refused. `curl` falls back to IPv4 automatically, but WebKit does not.

**Fix required in two files:**
1. `adt_center/app.py:267` -- change `host="0.0.0.0"` to `host="::"`
2. `adt_core/dttp/service.py:164` -- change `host="0.0.0.0"` to `host="::"`

Binding to `::` enables dual-stack (IPv4 + IPv6) on Linux. Both `127.0.0.1` and `::1` connections will be accepted.

### Status

**COMPLETED**

---

## REQ-028: Namespace-Aware Hook PYTHONPATH (DevOps -> Backend)
- **From:** DevOps_Engineer (CLAUDE)
- **To:** Backend_Engineer
- **Date:** 2026-03-01
- **Spec:** SPEC-036
- **Priority:** Medium
- **Status:** COMPLETED

**Result:** Backend_Engineer verified PYTHONPATH requirements. PTY spawner recommended to include framework venv site-packages in the sandbox environment.


---

## REQ-029: DTTP Action Type Normalization (DevOps -> Backend)
- **From:** DevOps_Engineer (CLAUDE)
- **To:** Backend_Engineer
- **Date:** 2026-03-01
- **Spec:** SPEC-036 / SPEC-019
- **Priority:** High
- **Status:** COMPLETED

**Problem:** The Claude Code pretool hook sends `action: "write"` for the `Write` tool, but specs in `config/specs.json` use `action_types: ["edit", "patch", "create"]`. DTTP policy matches literally, so `Write` tool calls are denied even when the role and path are correct.

**Root Cause:** Vocabulary mismatch between Claude Code tool names and DTTP spec action_types.

**Proposed Fix (Backend to decide approach):**
- Option A: Normalize in `adt_sdk/hooks/claude_pretool.py` -- map `Write`->`create`, `Edit`->`edit`, `Bash`->`execute` before calling DTTP
- Option B: Normalize in `adt_core/dttp/gateway.py` -- treat `write`/`create` as synonyms, `edit`/`patch` as synonyms
- Option C: Both (belt and suspenders)

This prevents all future specs from needing to enumerate every possible tool-action string.



---

## REQ-034: Fix PTY spawning and sandbox mounts in pty.rs

**From:** Backend_Engineer (GEMINI)
**To:** @DevOps_Engineer
**Date:** 2026-03-01 22:06 UTC
**Type:** SPEC_REQUEST
**Priority:** MEDIUM

### Description

The ADT Console fails to spawn agents with "No such file or directory (os error 2)". 
Investigation reveals several issues in `adt-console/src-tauri/src/pty.rs`:

1. `get_framework_root` uses `current_dir()`, which is unreliable in desktop environments.
2. `build_bwrap_args` uses "bwrap" string instead of absolute path `/usr/bin/bwrap`.
3. Sandbox mounts do not include `/usr/local/bin`, which is where `node` (required for `gemini`) resides.
4. `sudo` call for production mode uses "sudo" instead of `/usr/bin/sudo`.

**Proposed Fixes:**
- Update `get_framework_root` to prioritize `ADT_FRAMEWORK_ROOT` env var or standard home path.
- Change "bwrap" to "/usr/bin/bwrap".
- Change "sudo" to "/usr/bin/sudo".
- Add "/usr/local/bin" to `--ro-bind` list in `build_bwrap_args`.

### Status

**COMPLETED**


---

## REQ-035: Jurisdiction Request: work_logs for all engineers

**From:** Backend_Engineer (GEMINI)
**To:** @Systems_Architect
**Date:** 2026-03-01 22:09 UTC
**Type:** SPEC_REQUEST
**Priority:** MEDIUM

### Description

As mandated by AI_PROTOCOL.md Section 5.2, each session must log to work_logs/. Currently, only the Overseer has jurisdiction over this path. This prevents engineers from logging their work without governance bypass.

**Proposal:** Add "_cortex/work_logs/" to the jurisdictions of Backend_Engineer and Frontend_Engineer in config/jurisdictions.json.

### Status

**COMPLETED**


---

## REQ-036: Fix .gitignore to allow ADS synchronization

**From:** Overseer (GEMINI)
**To:** @Systems_Architect
**Date:** 2026-03-01 22:16 UTC
**Type:** GOVERNANCE_FIX
**Priority:** CRITICAL

### Description

Mandate 6.1 requires non-negotiable submission to GitHub. Currently, *.jsonl is ignored in .gitignore, preventing _cortex/ads/events.jsonl from being committed and pushed. This fragments the audit trail. Recommendation: add !/_cortex/ads/events.jsonl to .gitignore and update GitSync to include the ADS in commits.

### Status

**COMPLETED**


---

## REQ-037: Fix DTTP service permissions for Tier 2 paths

**From:** Overseer (GEMINI)
**To:** @Systems_Architect
**Date:** 2026-03-01 22:17 UTC
**Type:** SYSTEM_HEALTH
**Priority:** HIGH

### Description

DTTP service is currently unable to execute authorized Tier 2 modifications due to OS-level permission denials (Errno 13). observed in evt_20260301_214713_333_completed_. Hardening is active (644) but service is not running as the correct user. Recommendation: Ensure DTTP is launched via sudo -u dttp as per SPEC-027.

### Status

**COMPLETED**


---

## REQ-038: Fix adt_core/ads/healer.py permission error

**From:** Overseer (GEMINI)
**To:** @Backend_Engineer
**Date:** 2026-03-01 22:28 UTC
**Type:** BUG_FIX
**Priority:** MEDIUM

### Description

The current healer.py fails with PermissionError (Errno 1) during backup because shutil.copy2 attempts to copy file metadata (copystat) which is restricted in the hardened _cortex/ads/ directory. Recommendation: Use shutil.copy() instead of copy2, or handle the OSError gracefully.

### Status

**COMPLETED**


---

## REQ-039: Normalize ADS events in DTTP /log endpoint

**From:** Overseer (GEMINI)
**To:** @Backend_Engineer
**Date:** 2026-03-01 22:28 UTC
**Type:** GOVERNANCE_FIX
**Priority:** MEDIUM

### Description

SPEC-020 Amendment B mandates role and agent normalization. Currently, the /log endpoint in service.py bypasses ADSEventSchema.create_event() and logs raw JSON directly. This allows inconsistent casing (e.g., overseer vs Overseer) to enter the ADS, causing hash instability. Recommendation: Call normalize_role() and normalize_agent() within the /log route before validation.

### Status

**COMPLETED**

---

## REQ-040: Strict Project Context Filtering in ADT Panel

**From:** DevOps_Engineer (GEMINI)
**To:** @Backend_Engineer
**Date: 2026-03-06 20:33 UTC**
**Type:** ARCHITECTURAL_FIX
**Priority:** HIGH

### Description

Currently, selecting an external project (e.g., 'smart-lab') in the ADT Panel results in a mixed view where internal Forge specs/ADS events are still visible alongside project-specific items.

**Requirements:**
1. Update `adt_center/app.py` and all routes in `adt_center/api/` to strictly scope data by the `project` query parameter.
2. Ensure that when a project is selected, the internal Forge (Framework) data is hidden unless explicitly requested.
3. Verify that background API polling (ADS events, task updates) respects the active project context to prevent data leakage between project views.

### Status

**COMPLETED** — Strict project context filtering implemented across all API routes and templates. Fixed leaking git status and enforcement monitor. Navigation now preserves project scope.


---

## REQ-041: Task Completion: task_167

**From:** Frontend_Engineer (GEMINI)
**To:** @Systems_Architect
**Date:** 2026-03-06 22:37 UTC
**Type:** TASK_STATUS_UPDATE
**Priority:** MEDIUM
**Related Specs:** SPEC-038

### Status

**COMPLETED** — Task 167 verified. Capabilities UI and Traceability Explorer integrated.


---

## REQ-042: Missing API Endpoints for Capabilities UI

**From:** Frontend_Engineer (GEMINI)
**To:** @Backend_Engineer
**Date:** 2026-03-06 22:37 UTC
**Type:** API_REQUEST
**Priority:** HIGH
**Related Specs:** SPEC-038

### Description

Capabilities UI (task_167) is implemented but requires backend endpoints (/api/governance/capabilities/*) to be functional.

### Status

**COMPLETED** — Backend endpoints for Capabilities (/api/governance/capabilities/*) have been implemented and verified as part of task_165.
