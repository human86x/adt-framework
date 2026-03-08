# SPEC-035: Unified Status Management API

**Status:** APPROVED
**Approved:** 2026-02-25 by Human
**Author:** Systems_Architect (GEMINI)
**Date:** 2026-02-25
**Related Specs:** SPEC-026 (Governance Configurator), SPEC-028 (Hive Tracker Panel), SPEC-034 (Role-Aware Context Panel)

---

## 1. Problem Statement

Agents working under the ADT Framework currently face a "governance friction" when completing tasks or requests. Because `_cortex/tasks.json` and `_cortex/requests.md` are protected sovereign/architectural paths, agents cannot update them using standard file-editing tools (Write/Edit). 

To bypass this, agents frequently use `Bash` to write directly to these files, which bypasses the DTTP hook entirely and violates the principle of governed self-modification.

## 2. Solution

Implement a unified, role-authorized API for status management. This allows agents to report progress and completion through a governed channel without requiring broad write access to the `_cortex/` directory.

### 2.1 Task Status API (Refinement)

Ensure `PUT /api/tasks/<id>/status` is fully functional and supports:
- `status`: "completed" or "in_progress"
- `evidence`: (Optional) String describing what was done
- `agent`: Name of the agent
- `role`: Role of the agent (verified against `assigned_to` in task)

### 2.2 Request Status API (New)

Add `PUT /api/governance/requests/<id>/status` to `adt_center/api/governance_routes.py`:
- **Payload:** `{ "status": "COMPLETED" | "IN_PROGRESS", "role": "string", "agent": "string" }`
- **Logic:**
    1. Parse `_cortex/requests.md`.
    2. Find the entry for REQ-ID.
    3. Verify that the requesting `role` matches the `To:` field in the request (case-insensitive, handles @ prefix).
    4. Replace the `**Status:**` line or the line following `### Status`.
    5. Write the file back to disk.
    6. Log `request_status_updated` to ADS.

### 2.3 CLI Integration

Add commands to `adt_core/cli.py`:
- `adt tasks complete <id> [--evidence "message"]`
- `adt requests complete <id> [--status "COMPLETED"]`

These commands will use the `ADTClient` to call the respective API endpoints.

### 2.4 SDK Integration

Add methods to `adt_sdk/client.py`:
- `complete_task(task_id, evidence)`
- `complete_request(req_id, status)`

---

## 3. Implementation Details

### 3.1 Request Markdown Update Logic

The update logic should use regex to target the specific REQ block and its status field.
Example Regex for status update in `requests.md`:
Find: `(## REQ-001:.*?
.*?
### Status

\*\*)[A-Z _]+(\*\*)`
Replace with: `\1COMPLETED\2`

### 3.2 Authorization

Both endpoints must verify the `X-Role` header or payload `role` field.
- For Tasks: `task["assigned_to"] == role`
- For Requests: `request["to"] == role`

---

## 4. Tasks

- **task_135**: Backend_Engineer -- Implement `update_request_status` logic in `governance_routes.py`.
- **task_136**: Backend_Engineer -- Add `complete_task` and `complete_request` methods to `ADTClient` in `adt_sdk/client.py`.
- **task_137**: Backend_Engineer -- Add `tasks` and `requests` command groups to `adt_core/cli.py`.

---

## 5. Acceptance Criteria

1. Backend_Engineer agent can run `adt requests complete REQ-001` and see `requests.md` update without triggering a DTTP denial.
2. Agent cannot update a request addressed to a different role.
3. ADS logs show the status update with correct provenance.
4. Console Context Panel updates in real-time (via existing polling/watchers).
