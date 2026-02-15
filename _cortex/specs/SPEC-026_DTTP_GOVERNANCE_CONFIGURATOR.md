# SPEC-026: DTTP Governance Configurator

**Status:** COMPLETED
**Priority:** HIGH
**Owner:** Systems_Architect (spec), Backend_Engineer + Frontend_Engineer (implementation)
**Created:** 2026-02-13
**References:** SPEC-014 (DTTP), SPEC-015 (Operational Center), SPEC-020 (Self-Governance)

---

## 1. Purpose

Give the human operator a visual interface in the ADT Panel to define and lock in DTTP governance rules: what each role can do, where they can do it, and under which specs. Currently these rules live in two raw JSON files (`config/jurisdictions.json` and `config/specs.json`) that are Tier 1 sovereign paths -- editable only by humans. This spec turns that raw JSON into a proper governance control panel.

> "The human defines the rules. The machine enforces them."

---

## 2. Problem

- Role permissions are scattered across two JSON files with no validation UI
- A human must hand-edit JSON to change what Backend_Engineer can touch
- There is no visual overview of "who can do what where"
- Misconfigured jurisdictions cause silent DTTP denials (see REQ-005, REQ-009)
- No way to quickly lock down a role or revoke permissions
- Paul (or any collaborator) cannot configure governance without understanding the JSON schema

---

## 3. Architecture

### 3.1 New ADT Panel Page: "Governance" (`/governance`)

A dedicated page in the Operational Center with three sections:

#### Section A: Role Manager

A card for each role showing its current configuration:

```
+------------------------------------------+
|  SYSTEMS ARCHITECT                  [Edit]|
|  ----------------------------------------|
|  Jurisdiction:                            |
|    _cortex/    docs/                      |
|                                           |
|  Allowed Actions:                         |
|    create (specs only)                    |
|                                           |
|  Active Specs: SPEC-017, SPEC-020         |
|  Status: LOCKED                    [Lock] |
+------------------------------------------+

+------------------------------------------+
|  BACKEND ENGINEER                   [Edit]|
|  ----------------------------------------|
|  Jurisdiction:                            |
|    adt_core/   adt_center/api/            |
|    adt_sdk/    tests/    config/          |
|                                           |
|  Allowed Actions:                         |
|    edit  patch  create  delete             |
|                                           |
|  Active Specs: SPEC-014..019, SPEC-021    |
|  Status: ACTIVE                    [Lock] |
+------------------------------------------+

+------------------------------------------+
|  FRONTEND ENGINEER                  [Edit]|
|  ----------------------------------------|
|  Jurisdiction:                            |
|    adt_center/templates/                  |
|    adt_center/static/                     |
|    adt-console/src/                       |
|                                           |
|  Allowed Actions:                         |
|    edit  patch  create                    |
|                                           |
|  Active Specs: SPEC-015, SPEC-016,        |
|                SPEC-021                   |
|  Status: ACTIVE                    [Lock] |
+------------------------------------------+

+------------------------------------------+
|  DEVOPS ENGINEER                    [Edit]|
|  ----------------------------------------|
|  Jurisdiction:                            |
|    ops/   .github/   adt-console/src-tauri|
|    setup.py   start.sh   console.sh       |
|                                           |
|  Allowed Actions:                         |
|    edit  patch  create  delete             |
|                                           |
|  Active Specs: SPEC-014, SPEC-021,        |
|                SPEC-022                   |
|  Status: ACTIVE                    [Lock] |
+------------------------------------------+

+------------------------------------------+
|  OVERSEER                           [Edit]|
|  ----------------------------------------|
|  Jurisdiction:                            |
|    _cortex/ads/                           |
|                                           |
|  Allowed Actions:                         |
|    read (audit only)                      |
|                                           |
|  Active Specs: SPEC-020                   |
|  Status: LOCKED                    [Lock] |
+------------------------------------------+
```

#### Section B: Jurisdiction Editor

When [Edit] is clicked on a role card, a modal opens:

- **Paths list:** Add/remove directory paths (with autocomplete from project tree)
- **Action types:** Checkbox grid (edit, patch, create, delete, read)
- **Spec bindings:** Which specs authorize this role (dropdown multi-select from existing specs)
- **Preview:** Before saving, show a diff of what changed
- **Save:** Writes to `config/jurisdictions.json` and relevant entries in `config/specs.json`

#### Section C: Enforcement Dashboard

Live view of DTTP enforcement state:

- **Enforcement mode:** Development / Production (toggle, reads from DTTP service)
- **Protected paths:** List of sovereign (Tier 1) and constitutional (Tier 2) paths
- **Recent denials:** Last 10 DTTP denials with role, path, reason
- **Rule conflicts:** Automatic detection of overlapping jurisdictions or missing spec bindings

---

## 4. Data Model

### 4.1 What Gets Written

All changes write to the two existing sovereign config files:

**`config/jurisdictions.json`** -- role-to-path mapping:
```json
{
  "jurisdictions": {
    "Systems_Architect": ["_cortex/", "docs/"],
    "Backend_Engineer": ["adt_core/", "adt_center/api/", ...],
    ...
  }
}
```

**`config/specs.json`** -- spec-to-role-action-path authorization:
```json
{
  "specs": {
    "SPEC-014": {
      "title": "...",
      "status": "approved",
      "roles": ["Backend_Engineer", "DevOps_Engineer"],
      "action_types": ["edit", "patch", "create", "delete"],
      "paths": ["adt_core/dttp/", "config/"]
    }
  }
}
```

### 4.2 Sovereign Path Protection

These files are Tier 1 sovereign paths (SPEC-020). The Governance Configurator is the **only** legitimate way to modify them besides break-glass. The API endpoints must:

1. Verify the request comes from the Panel (localhost or authenticated remote)
2. Log every change to ADS with `agent: HUMAN`, `action_type: governance_config_updated`
3. Include a before/after diff in the ADS event
4. Refuse changes from agent API calls -- governance configuration is human-only

### 4.3 Role Lock

A "locked" role cannot be modified through the UI without first unlocking it. This prevents accidental changes. Lock state is stored in a new field:

```json
{
  "jurisdictions": {
    "Systems_Architect": {
      "paths": ["_cortex/", "docs/"],
      "locked": true
    }
  }
}
```

**Note:** Locking is a UI safeguard only. The underlying DTTP enforcement does not change -- a locked role is still enforced the same way. The lock prevents accidental human edits to governance rules.

---

## 5. API Endpoints

All endpoints are **human-only** (reject requests with `X-Agent` header or non-localhost without auth token).

### 5.1 GET /api/governance/roles

Returns all roles with their current jurisdictions, action types, and spec bindings. Merges data from both config files into a unified view.

```json
{
  "roles": {
    "Systems_Architect": {
      "paths": ["_cortex/", "docs/"],
      "action_types": ["create"],
      "specs": ["SPEC-017", "SPEC-020"],
      "locked": true
    },
    ...
  }
}
```

### 5.2 PUT /api/governance/roles/<role_name>

Update a role's jurisdiction, action types, or lock state.

```json
{
  "paths": ["_cortex/", "docs/"],
  "action_types": ["create"],
  "locked": false
}
```

- Validates path format (must end with `/` for directories or be a specific file)
- Prevents removing all paths (role must have at least one jurisdiction)
- Logs change to ADS with full before/after diff
- Writes to `config/jurisdictions.json`

### 5.3 PUT /api/governance/specs/<spec_id>/roles

Update which roles are authorized under a spec and what actions they can perform.

```json
{
  "roles": ["Backend_Engineer"],
  "action_types": ["edit", "patch", "create"]
}
```

- Validates spec exists
- Logs change to ADS
- Writes to `config/specs.json`

### 5.4 GET /api/governance/enforcement

Returns current DTTP enforcement state: mode, protected paths, recent denials.

### 5.5 GET /api/governance/conflicts

Returns detected conflicts: overlapping jurisdictions, roles authorized in specs but missing from jurisdictions, etc.

---

## 6. Security Constraints

### 6.1 Human-Only Enforcement

This is the most security-critical feature in the framework. These config files control what every agent can do. Therefore:

1. **No agent may call these endpoints.** The API must reject requests that appear to come from automated agents.
2. **Localhost or authenticated only.** Remote access requires the ADT_ACCESS_TOKEN (SPEC-024).
3. **ADS audit trail.** Every governance change creates an ADS event with `agent: HUMAN` and full diff.
4. **Confirmation required.** Destructive changes (removing paths, revoking roles) require a confirmation step in the UI.
5. **Break-glass alignment.** Governance changes bypass the normal DTTP flow (since they modify DTTP's own config). This is acceptable because the human IS the ultimate authority. But it must be logged.

### 6.2 Validation Rules

- Cannot assign a path to a role if it conflicts with a sovereign path
- Cannot remove a role from a spec that has active (in-progress) tasks assigned to that role
- Cannot lock a role that has pending configuration changes
- Path format validation: no `..`, no absolute paths, must be project-relative

---

## 7. Implementation Tasks

| Task | Description | Assigned To |
|------|-------------|-------------|
| task_058 | GET /api/governance/roles -- unified role view from both config files | Backend_Engineer |
| task_059 | PUT /api/governance/roles/<role> -- update jurisdiction with ADS logging | Backend_Engineer |
| task_060 | PUT /api/governance/specs/<spec_id>/roles -- update spec role bindings | Backend_Engineer |
| task_061 | GET /api/governance/enforcement -- DTTP state + recent denials | Backend_Engineer |
| task_062 | GET /api/governance/conflicts -- jurisdiction conflict detection | Backend_Engineer |
| task_063 | Governance page template -- role cards, jurisdiction editor modal | Frontend_Engineer |
| task_064 | Enforcement dashboard section -- mode display, protected paths, denials | Frontend_Engineer |
| task_065 | Role lock/unlock UI with confirmation dialogs | Frontend_Engineer |
| task_066 | Navigation: add "Governance" link to ADT Panel nav bar | Frontend_Engineer |

---

## 8. Acceptance Criteria

- [ ] Human can see all 5 roles with their current jurisdictions at a glance
- [ ] Human can add/remove paths from a role's jurisdiction via the UI
- [ ] Human can change which action types a role is allowed to perform
- [ ] Human can lock a role to prevent accidental changes
- [ ] Every governance change is logged to ADS with before/after diff
- [ ] Agent API calls to governance endpoints are rejected
- [ ] Jurisdiction conflicts are detected and displayed
- [ ] Sovereign and constitutional paths are displayed but not editable (read-only display)
- [ ] UI works in both ADT Panel (browser) and embedded in Operator Console (iframe)

---

## 9. User Story

Paul opens the ADT Panel. He clicks "Governance" in the nav bar. He sees five role cards. He clicks [Edit] on Systems_Architect. He removes all paths except `_cortex/specs/` and `_cortex/docs/`. He unticks everything except "create". He clicks Save. The ADS logs the change. From this moment, the Systems Architect agent can only create files in `_cortex/specs/` and `_cortex/docs/` -- nothing else. The machine enforces what the human decided.

He clicks [Lock] on Systems_Architect. Now even he can't accidentally change it without unlocking first.

He does the same for every role. Backend gets code. Frontend gets UI. DevOps gets infrastructure. Overseer gets audit logs. The governance is locked in, visible, auditable.

---

*"Configuration is governance made visible."*

---

## 10. Task Lifecycle Management

### 10.1 Problem

`_cortex/tasks.json` is under Systems_Architect jurisdiction. Agents who complete work cannot update their own task status. Every completion requires the Architect to act as middleman. This creates a bottleneck and delays visibility into project progress.

### 10.2 Solution: Role-Scoped Task Status API

Agents can mark their **own assigned tasks** as complete via an API endpoint. The human retains full override authority: reject completions, reassign tasks, reopen for troubleshooting.

### 10.3 Agent Self-Service

#### PUT /api/tasks/<task_id>/status (Agent-Callable)

```json
{
  "status": "completed",
  "agent": "GEMINI",
  "role": "Frontend_Engineer",
  "evidence": "Implemented in governance.html, tested in browser"
}
```

**Rules:**
- Agent can only update tasks where `assigned_to` matches their role
- Agent can only set status to `completed` or `in_progress` (cannot set `pending` -- that's a human action)
- Cannot update tasks assigned to other roles
- Logged to ADS as `task_status_updated` with `agent` field set to the requesting agent

### 10.4 Human Override

The human has full authority over all tasks through the Panel UI:

#### PUT /api/tasks/<task_id>/override (Human-Only)

```json
{
  "action": "reject",
  "reason": "Governance page missing conflict detection section",
  "reassign_to": "Frontend_Engineer",
  "new_status": "in_progress"
}
```

**Actions available to human:**

| Action | What It Does |
|--------|-------------|
| `reject` | Unmark a task the agent claimed was complete. Sets status back to `in_progress`. Reason is mandatory. |
| `reassign` | Move task to a different role for troubleshooting. Original role notified via ADS event. |
| `reopen` | Set a completed task back to `pending`. Used when previously accepted work needs rework. |
| `approve` | Explicitly approve a completion (optional -- completion stands if not rejected). |

**All human overrides are logged to ADS with `agent: HUMAN`.**

### 10.5 Tasks Page UI Enhancement

The existing Tasks page (`/tasks`) gains:

- **"Mark Complete" button** on each task (visible to the assigned role's agent via API, visible to human always)
- **"Review" column** showing whether a completion has been human-reviewed or is pending review
- **Human action buttons:** Reject (with reason modal), Reassign (role dropdown), Reopen, Approve
- **Completion evidence:** When an agent marks complete, their evidence text is displayed
- **Status history:** Expandable row showing the full status change history for each task

### 10.6 Notification Flow

```
Agent marks task_063 "completed"
  --> ADS logs: task_status_updated (agent: GEMINI, role: Frontend_Engineer)
  --> Tasks page shows: task_063 = COMPLETED (pending human review)
  --> Human reviews in Panel
      --> APPROVE: ADS logs task_approved, task stays completed
      --> REJECT: ADS logs task_rejected with reason, status -> in_progress
          --> Next agent session sees the rejection reason and reworks
```

### 10.7 Implementation Tasks

| Task | Description | Assigned To |
|------|-------------|-------------|
| task_074 | PUT /api/tasks/<id>/status -- agent self-service task status update | Backend_Engineer |
| task_075 | PUT /api/tasks/<id>/override -- human reject/reassign/reopen/approve | Backend_Engineer |
| task_076 | Tasks page UI: Mark Complete button, Review column, Human action buttons | Frontend_Engineer |
| task_077 | ADS event types: task_status_updated, task_approved, task_rejected, task_reassigned | Backend_Engineer |

### 10.8 Acceptance Criteria

- [ ] Agent can mark their own assigned tasks as completed via API
- [ ] Agent cannot mark tasks assigned to other roles
- [ ] Human can reject a completion with a mandatory reason
- [ ] Human can reassign a task to a different role
- [ ] Human can reopen a previously completed task
- [ ] All task lifecycle events are logged to ADS
- [ ] Tasks page shows review status and human action buttons
- [ ] Rejection reason is visible to the agent in their next session
