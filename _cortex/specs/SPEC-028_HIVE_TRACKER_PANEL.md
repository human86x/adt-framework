# SPEC-028: Console Hive Tracker Panel

**Status:** APPROVED
**Priority:** CRITICAL
**Owner:** Systems_Architect (spec), Frontend_Engineer (implementation)
**Created:** 2026-02-13
**References:** SPEC-021 (Operator Console), REQ-011

---

## 1. Purpose

To provide the human operator with a unified, real-time "Command Context" within the ADT Console. Currently, the operator must switch between the Console (for work), the Panel (for tasks/specs), and markdown files (for requests) to understand the project state. This spec integrates all three into the Console's right sidebar.

> "A governor must see the whole board."

---

## 2. UI Layout: The "Hive Tracker" (Right Sidebar)

The right sidebar is divided into four main scrollable sections:

### 2.1 Section 1: Requests Feed
- **Source:** `_cortex/requests.md` (parsed via ADT Center API)
- **Content:** List of all requests with ID, Type, and Status.
- **Visuals:**
  - `REQ-001` [FEATURE] (COMPLETED)
  - `REQ-011` [FEATURE] (OPEN) - Highlighted if new or urgent.
- **Interactions:** Click to view full description and author.

### 2.2 Section 2: Tasks To-Do
- **Source:** `_cortex/tasks.json` (status: `pending` or `in_progress`)
- **Content:** List of tasks assigned to the **active role** or global tasks.
- **Visuals:**
  - `task_069` (HIGH) - Setup Shatterglass
  - `task_081` (CRITICAL) - Hive Tracker Panel
- **Interactions:** "Focus" button to set task as the primary session context.

### 2.3 Section 3: Completed Tasks
- **Source:** `_cortex/tasks.json` (status: `completed`)
- **Content:** Chronological list of recently finished work.
- **Visuals:**
  - [Check] `task_057` - Role switching fix
  - [Check] `task_044` - ADS Query optimization
- **Interactions:** View completion evidence.

### 2.4 Section 4: Delegation Tracker ("Sent Tasks")
- **Source:** `_cortex/tasks.json` + ADS Delegation Events
- **Content:** Who assigned what to whom.
- **Visuals:**
  - `task_081` -> Frontend_Engineer (Assigned by Architect)
  - `task_069` -> DevOps_Engineer (Assigned by Architect)
- **Interactions:** Track progress of delegated work.

---

## 3. Data Integration

### 3.1 ADT Center API Extensions
To support this panel, the ADT Center API (`adt_center/api/governance_routes.py`) must provide:
1. `GET /api/requests` - Parses `_cortex/requests.md` and returns a JSON list.
2. `GET /api/delegations` - Returns a mapping of task assignments and their history from ADS.

### 3.2 Real-time Updates
- The Console uses the existing file watcher (`SPEC-021 Section 9.2`) to detect changes to `requests.md` and `tasks.json`.
- Changes trigger an immediate refresh of the Tracker Panel.

---

## 4. Implementation Tasks

| Task | Description | Assigned To |
|------|-------------|-------------|
| task_081 | Implement Hive Tracker Panel UI in `adt-console/src/` | Frontend_Engineer |
| task_082 | `GET /api/requests` endpoint in `governance_routes.py` | Backend_Engineer |
| task_083 | `GET /api/delegations` endpoint in `governance_routes.py` | Backend_Engineer |
| task_084 | Wire file watchers to trigger Tracker Panel refresh | DevOps_Engineer |

---

## 5. Acceptance Criteria

- [ ] Right sidebar shows all 4 sections (Requests, To-Do, Completed, Delegations).
- [ ] Data is refreshed automatically when files change.
- [ ] Tasks are filtered by active role but allow viewing all.
- [ ] Delegation tracker correctly shows who assigned the task.
- [ ] Layout is consistent with ADT Dark theme.

---

*"The Hive Mind needs a shared memory. The Console provides the lens."*
