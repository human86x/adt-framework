# SPEC-033: Sovereign Change Requests

**Author:** CLAUDE (Systems_Architect)
**Date:** 2026-02-20
**Status:** APPROVED
**Approved:** 2026-02-20 by Human
**Extends:** SPEC-020 (Self-Governance Integrity), SPEC-026 (Governance Configurator)
**References:** SPEC-015 (Operational Center), SPEC-032 (Console Project Launcher)

---

## 1. Problem Statement

When an agent needs to update a Tier 1 (sovereign) file -- `MASTER_PLAN.md`,
`config/specs.json`, `config/jurisdictions.json`, `config/dttp.json`, or
`AI_PROTOCOL.md` -- DTTP correctly blocks the write. But the workflow that follows
is broken:

**Current workflow (broken):**
1. Agent proposes a change to a sovereign path
2. DTTP denies with `sovereign_path_violation`
3. Agent says to the human: "Please copy-paste this into the file"
4. Human must manually edit the file in a terminal or text editor
5. No audit trail connecting the agent's proposal to the human's action

**This creates three problems:**

1. **Friction.** The human is reduced to a copy-paste operator. The governance
   system should make authorized actions easy, not create busywork.
2. **No traceability.** There is no ADS record linking the agent's original
   proposal to the human's manual edit. The governance audit trail has a gap.
3. **Error-prone.** Manual editing of JSON config files (`specs.json`,
   `jurisdictions.json`) risks syntax errors, wrong indentation, or partial
   application of changes.

### 1.1 The Principle

> "Sovereignty means the human decides, not that the human does the typing."

The human's role is authorization -- reviewing what an agent proposes and deciding
whether to approve it. The system should handle the mechanical application of
approved changes. This is the same principle as a pull request: the reviewer
approves, the system merges.

---

## 2. Proposed Solution

A **Sovereign Change Request (SCR)** system: agents submit proposed changes to
sovereign paths into a queue. The human reviews diffs in the ADT Panel and
clicks Authorize. The system applies the change and logs it to the ADS with
full provenance (who proposed, who authorized, what changed).

---

## 3. Architecture

### 3.1 SCR Queue

Pending change requests are stored in `_cortex/ops/sovereign_requests.json`:

```json
{
  "requests": [
    {
      "id": "scr_20260220_150000_001",
      "ts": "2026-02-20T15:00:00Z",
      "agent": "CLAUDE",
      "role": "Systems_Architect",
      "spec_ref": "SPEC-032",
      "target_path": "_cortex/MASTER_PLAN.md",
      "change_type": "patch",
      "description": "Add SPEC-032 to Master Plan objectives and spec table",
      "patch": {
        "old_string": "13. **External Project Governance:** ...",
        "new_string": "13. **External Project Governance:** ...\n14. **Console Project Launcher:** ..."
      },
      "status": "pending",
      "authorized_by": null,
      "authorized_at": null
    }
  ]
}
```

### 3.2 Change Types

| Type | Description | Payload |
|------|-------------|---------|
| `patch` | Replace a substring in the file | `old_string`, `new_string` |
| `append` | Add content to end of file | `content` |
| `json_merge` | Merge keys into a JSON file | `merge_data` (deep merge) |
| `full_replace` | Replace entire file contents | `content` (with before hash for safety) |

The `json_merge` type is critical for `config/specs.json` and
`config/jurisdictions.json` -- agents propose a JSON fragment to merge, not raw
text edits. This eliminates syntax errors.

Example: registering SPEC-032 in `specs.json`:
```json
{
  "change_type": "json_merge",
  "target_path": "config/specs.json",
  "merge_data": {
    "specs": {
      "SPEC-032": {
        "title": "Console Project Launcher",
        "status": "approved",
        "roles": ["Frontend_Engineer", "DevOps_Engineer"],
        "action_types": ["edit", "patch", "create"],
        "paths": ["adt-console/", "adt_center/templates/", "adt_center/api/"]
      }
    }
  }
}
```

### 3.3 Flow

```
Agent proposes change
  |
  v
DTTP denies (sovereign_path_violation)
  |
  v
Agent SDK auto-creates SCR
  (POST /api/governance/sovereign-requests)
  |
  v
SCR stored in queue
  |
  v
ADT Panel shows pending SCRs
  (badge count on Governance nav link)
  |
  v
Human reviews diff in Panel
  |
  +---> [Authorize] --> System applies change, logs to ADS
  |
  +---> [Reject] --> SCR marked rejected, agent notified via ADS
  |
  +---> [Edit & Authorize] --> Human modifies the proposal, then applies
```

### 3.4 Auto-Submit on Sovereign Denial

When the DTTP hook (`claude_pretool.py` / `gemini_pretool.py`) receives a
`sovereign_path_violation` denial, instead of just blocking the agent, it
should automatically submit an SCR:

1. Hook receives denial with reason `sovereign_path_violation`
2. Hook POSTs the proposed change to `POST /api/governance/sovereign-requests`
3. Hook returns denial to the agent with message:
   "Change submitted for human authorization. Check the ADT Panel."
4. Agent sees a clear message instead of a raw denial

This means the agent doesn't need to know about SCRs -- the hook handles it
transparently.

---

## 4. API Endpoints

### 4.1 POST /api/governance/sovereign-requests

Submit a new sovereign change request.

**Request:**
```json
{
  "agent": "CLAUDE",
  "role": "Systems_Architect",
  "spec_ref": "SPEC-032",
  "target_path": "_cortex/MASTER_PLAN.md",
  "change_type": "patch",
  "description": "Add SPEC-032 to Master Plan",
  "patch": { "old_string": "...", "new_string": "..." }
}
```

**Response:** `201 Created`
```json
{
  "status": "queued",
  "scr_id": "scr_20260220_150000_001",
  "message": "Change request submitted. Awaiting human authorization in ADT Panel."
}
```

### 4.2 GET /api/governance/sovereign-requests

List all SCRs. Optional `?status=pending` filter.

### 4.3 PUT /api/governance/sovereign-requests/<scr_id>

Human action: authorize, reject, or edit a request.

**Authorize:**
```json
{ "action": "authorize" }
```
System applies the change, marks SCR as authorized, logs to ADS.

**Reject:**
```json
{ "action": "reject", "reason": "Not needed at this time" }
```

**Edit & Authorize:**
```json
{
  "action": "authorize",
  "edited_patch": { "old_string": "...", "new_string": "..." }
}
```
Human modifies the proposed change before authorizing.

---

## 5. Panel UI

### 5.1 Governance Page Addition

Add a **"Pending Authorizations"** section at the top of the Governance page:

```
+---------------------------------------------------------------+
| PENDING AUTHORIZATIONS (2)                                     |
+---------------------------------------------------------------+
| SCR-001  _cortex/MASTER_PLAN.md               2 min ago       |
| "Add SPEC-032 to Master Plan"                                  |
| Proposed by: CLAUDE (Systems_Architect)                        |
|                                                                |
| --- Diff Preview ---                                           |
| - 13. **External Project Governance:** ...                     |
| + 13. **External Project Governance:** ...                     |
| + 14. **Console Project Launcher:** ...                        |
|                                                                |
| [Authorize]  [Edit & Authorize]  [Reject]                      |
+---------------------------------------------------------------+
| SCR-002  config/specs.json                    2 min ago        |
| "Register SPEC-032 in specs.json"                              |
| Proposed by: CLAUDE (Systems_Architect)                        |
|                                                                |
| --- JSON Merge Preview ---                                     |
| + "SPEC-032": {                                                |
| +   "title": "Console Project Launcher",                      |
| +   "status": "approved",                                     |
| +   ...                                                        |
| + }                                                            |
|                                                                |
| [Authorize]  [Edit & Authorize]  [Reject]                      |
+---------------------------------------------------------------+
```

### 5.2 Navigation Badge

The Governance nav link shows a badge with the count of pending SCRs:
`Governance (2)` -- red badge, same style as notification badges.

### 5.3 Console Notification

When an SCR is created, the Console status bar shows:
`Pending authorizations: 2 -- open ADT Panel (Ctrl+G)`

---

## 6. ADS Logging

Every SCR action is logged:

| Event | Agent | Description |
|-------|-------|-------------|
| `sovereign_change_proposed` | Agent | SCR submitted to queue |
| `sovereign_change_authorized` | HUMAN | Human approved, system applied |
| `sovereign_change_rejected` | HUMAN | Human rejected with reason |
| `sovereign_change_applied` | SYSTEM | File successfully written |

The `sovereign_change_authorized` and `sovereign_change_applied` events are
linked via `scr_id` field, creating a complete provenance chain:
agent proposed -> human authorized -> system applied.

---

## 7. File Jurisdiction

| File | Role |
|------|------|
| `adt_center/api/governance_routes.py` (modify) | Backend_Engineer |
| `adt_center/templates/governance.html` (modify) | Frontend_Engineer |
| `adt_sdk/hooks/claude_pretool.py` (modify) | Backend_Engineer |
| `adt_sdk/hooks/gemini_pretool.py` (modify) | Backend_Engineer |
| `_cortex/ops/sovereign_requests.json` (NEW, auto-created) | System |

---

## 8. Task Breakdown

### Phase A: Backend
1. Create SCR queue file management (read/write `_cortex/ops/sovereign_requests.json`)
2. POST /api/governance/sovereign-requests endpoint
3. GET /api/governance/sovereign-requests endpoint
4. PUT /api/governance/sovereign-requests/<id> (authorize/reject/edit)
5. Change application logic: patch, append, json_merge, full_replace
6. ADS logging for all SCR events

### Phase B: Hook Integration
7. Update claude_pretool.py: on sovereign denial, auto-submit SCR
8. Update gemini_pretool.py: same
9. Return informative message to agent ("submitted for authorization")

### Phase C: Panel UI
10. "Pending Authorizations" section on Governance page
11. Diff preview renderer (text diff + JSON merge preview)
12. Authorize / Reject / Edit & Authorize buttons
13. Navigation badge with pending count

### Phase D: Console Integration
14. Status bar notification for pending SCRs
15. Ctrl+G quick-jump to Governance page when SCRs pending

---

## 9. Acceptance Criteria

1. Agent editing a sovereign path triggers automatic SCR submission
2. SCR appears in ADT Panel Governance page within 2 seconds
3. Human can review diff/merge preview before authorizing
4. "Authorize" applies the change to the actual file
5. Full ADS provenance: proposed -> authorized -> applied
6. "Reject" notifies agent via ADS event
7. "Edit & Authorize" lets human modify before applying
8. json_merge type handles specs.json and jurisdictions.json without syntax risk
9. Agent receives clear message: "submitted for authorization" (not raw denial)
10. Navigation badge shows pending count
