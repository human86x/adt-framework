# SPEC-037: Cross-Role Request Access & Per-Session Role Identity

**Author:** CLAUDE (Systems_Architect)
**Date:** 2026-02-25
**Status:** APPROVED
**Approved:** 2026-02-25 by Human
**Origin:** REQ-027 (DevOps_Engineer), REQ-025 (Backend_Engineer)
**References:** SPEC-020 (Self-Governance), SPEC-034 (Role-Aware Context Panel),
SPEC-035 (Unified Status Management API), SPEC-021 (Operator Console)

---

## 1. Problem Statement

### 1.1 Requests Filing Blocked by Jurisdiction

`_cortex/requests.md` is in the Overseer's jurisdiction only (`config/jurisdictions.json`
line 85). No other role -- Backend_Engineer, Frontend_Engineer, DevOps_Engineer,
Systems_Architect -- can write to it through DTTP. Every cross-role request filed
to date has required a Bash workaround to bypass DTTP entirely.

The cross-role request system is the ONLY mechanism agents have to communicate
needs across jurisdiction boundaries. Blocking agents from using it forces them
into ungoverned workarounds -- the exact anti-pattern the framework exists to prevent.

### 1.2 Role Identity is a Global Singleton

`_cortex/ops/active_role.txt` stores a single role string for the entire framework.
Multiple concurrent agent sessions (common in the Console) overwrite each other's
roles. The DTTP hook reads this file on every tool call, meaning:

- Agent A starts as Backend_Engineer, writes `Backend_Engineer` to the file
- Agent B starts as Frontend_Engineer, overwrites with `Frontend_Engineer`
- Agent A's next tool call is validated as Frontend_Engineer -- wrong jurisdiction

This breaks multi-agent governance entirely.

---

## 2. Solution: Request Filing API

### 2.1 New Endpoint: `POST /api/governance/requests`

Add to `adt_center/api/governance_routes.py`:

```
POST /api/governance/requests
Content-Type: application/json

{
  "from_role": "DevOps_Engineer",
  "from_agent": "CLAUDE",
  "to_role": "Systems_Architect",
  "priority": "HIGH",
  "type": "SPEC_REQUEST",
  "title": "Agent Filesystem Sandboxing",
  "description": "...",
  "related_specs": ["SPEC-031", "SPEC-027"]
}
```

**Response:** `201 Created` with the assigned REQ-ID.

**Logic:**
1. Validate required fields (`from_role`, `to_role`, `title`)
2. Generate next sequential REQ-ID by parsing existing entries in `requests.md`
3. Format the request as markdown matching the existing convention
4. Append to `_cortex/requests.md`
5. Log `request_filed` to ADS with full provenance
6. Return `{"req_id": "REQ-028", "status": "OPEN"}`

**Authorization:** Any role may call this endpoint. The DTTP hook must allow
`POST /api/governance/requests` without jurisdiction checks on `requests.md`,
because the API itself performs the write server-side.

### 2.2 Request Status Update (deferred to SPEC-035)

SPEC-035 Section 2.2 defines `PUT /api/governance/requests/<id>/status` for
updating request completion status. This spec defers to SPEC-035 for that
endpoint and adds one requirement:

- The `From:` role may also update status (not just the `To:` role), since the
  filing role may want to mark their own request as withdrawn or superseded.

SPEC-035 and SPEC-037 are complementary: SPEC-035 covers status updates for
existing tasks/requests, SPEC-037 covers filing new requests and fixing role
identity. Both should be approved together.

### 2.3 SDK Integration

Add to `adt_sdk/client.py`:

```python
def file_request(self, from_role, to_role, title, description,
                 priority="MEDIUM", req_type="IMPROVEMENT",
                 related_specs=None):
    """File a cross-role request via the governed API."""
    ...

def update_request_status(self, req_id, status, role, agent):
    """Update the status of a request addressed to this role."""
    ...
```

### 2.4 Hook Integration

Add to both `claude_pretool.py` and `gemini_pretool.py`:

When a tool call targets `_cortex/requests.md` and the action is `append`:
- Instead of blocking, redirect to `POST /api/governance/requests`
- Parse the markdown content being appended to extract structured fields
- Call the API endpoint
- Return success to the agent

This provides backward compatibility: agents that try to append to `requests.md`
directly are transparently redirected to the governed API.

---

## 3. Solution: Per-Session Role Identity

### 3.1 Deprecate `active_role.txt` for Multi-Session Use

`_cortex/ops/active_role.txt` remains as a **fallback for CLI usage only**
(single-agent, non-Console sessions). For Console-spawned sessions, role
identity must come from the session's environment.

### 3.2 Environment-Based Role Resolution

The PTY spawner already sets `ADT_ROLE` in the agent's environment (`pty.rs:294`).
The DTTP hooks already read `ADT_ROLE` as a fallback. The fix is to change the
**priority order** in the hooks:

**Current priority (broken for multi-session):**
1. `active_role.txt` (global singleton -- wins even when wrong)
2. `ADT_ROLE` environment variable
3. Hardcoded default

**New priority:**
1. `ADT_ROLE` environment variable (per-session, set by PTY spawner)
2. `active_role.txt` (fallback for CLI-only sessions)
3. Hardcoded default

### 3.3 Hook Changes

In `claude_pretool.py` (lines 197-215) and `gemini_pretool.py` (equivalent):

```python
# NEW priority: env var first, then file fallback
role = os.environ.get("ADT_ROLE")
if not role:
    role_file = os.path.join(project_dir, "_cortex/ops/active_role.txt")
    if os.path.exists(role_file):
        role = open(role_file).read().strip()
if not role:
    role = "Backend_Engineer"  # last resort default
```

### 3.4 Console Session Isolation

Each Console session already receives its own PTY with isolated environment
variables. No changes to `pty.rs` are needed -- it already sets `ADT_ROLE`
correctly. The fix is entirely in the hooks.

---

## 4. Implementation Tasks

| Task | Role | Description |
|------|------|-------------|
| task_152 | Backend_Engineer | Implement `POST /api/governance/requests` endpoint in `governance_routes.py` |
| task_153 | Backend_Engineer | Add `file_request()` and `update_request_status()` to `adt_sdk/client.py` |
| task_154 | Backend_Engineer | Fix role priority in `claude_pretool.py`: env var before `active_role.txt` |
| task_155 | Backend_Engineer | Fix role priority in `gemini_pretool.py`: env var before `active_role.txt` |
| task_156 | Backend_Engineer | Add hook redirect for `requests.md` append -> API endpoint |
| task_157 | Backend_Engineer | Write tests for request filing API and role resolution priority |

---

## 5. Acceptance Criteria

1. Any role can file a cross-role request via `POST /api/governance/requests`
   without triggering a DTTP denial
2. Requests filed via API appear in `_cortex/requests.md` with correct formatting
3. ADS logs show `request_filed` events with role/agent provenance
4. Two concurrent Console sessions with different roles operate with correct
   jurisdiction -- neither overwrites the other's identity
5. CLI sessions (outside Console) still work via `active_role.txt` fallback
6. `ADTClient.file_request()` works from agent code
