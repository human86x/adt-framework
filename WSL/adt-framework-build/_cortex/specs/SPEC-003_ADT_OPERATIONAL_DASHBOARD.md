# SPEC-003: ADT Operational Dashboard

**Author:** CLAUDE (Systems_Architect)
**Date:** 2026-01-30
**Revised:** 2026-02-09 (v3.0 - ADT Framework Rewrite)
**Status:** APPROVED
**Extends:** SPEC-015 (ADT Operational Center)

> **v3.0 Changes:** Complete rewrite for ADT Framework context. Removed all
> OceanPulse-specific references, examples, and roles. Updated file paths from
> `adt_panel/` to `adt_center/`. Retained Delegation Tree and Hierarchy View as
> unique contributions extending SPEC-015. Deployment target: oceanpulse.pt/adt-framework/

---

## 1. Problem Statement

The ADT Operational Center (SPEC-015) provides a Flask-based governance interface with dashboard, ADS timeline, spec registry, task board, and DTTP monitor. However, it lacks **operational depth** in two areas:

| SPEC-015 Provides | This Spec Adds |
|-------------------|----------------|
| Flat task board (3 columns) | **Delegation Tree** (authority flow visualization) |
| Spec list with status | **Hierarchy View** (phase-structured project view) |
| Basic task cards | **Enhanced Task Board** with delegation metadata |
| ADS event timeline | Task-to-spec traceability via delegation chains |

Users cannot currently see:
- **Who delegated what to whom** (authority chains)
- **Traceability from task back to authorizing spec**
- How work relates to phases and milestones
- Overall project progress structured by phase

---

## 2. Proposed Solution

Extend the ADT Operational Center with two new views and enhanced task metadata:

### 2.1 Task Board Enhancements

Extend the existing SPEC-015 task board with delegation metadata:

```
+---------------+---------------+---------------+
|    PENDING    |  IN PROGRESS  |   COMPLETED   |
+---------------+---------------+---------------+
| [Task 014]    | [Task 005]    | [Task 010]    |
| @Backend_Eng  | @Frontend_Eng | @Backend_Eng  |
| SPEC-020      | SPEC-016      | SPEC-019      |
+---------------+---------------+---------------+
| [Task 015]    |               | [Task 009]    |
| @Backend_Eng  |               | @Backend_Eng  |
| SPEC-020      |               | SPEC-018      |
+---------------+---------------+---------------+
```

**Task Card Shows:**
- Task title
- Assigned role (@Role)
- Linked spec (SPEC-XXX)
- Agent working on it (Claude/Gemini badge)
- Created date
- Priority indicator
- Delegated by (role + agent)

### 2.2 Hierarchy View (Project Structure)

Tree view showing project phases, specs, and tasks:

```
ADT Framework
+-- Phase 1: Core Engines
|   +-- SPEC-017: ADT Framework Repository
|   |   +-- [v] Build ADS Engine (task_001)
|   |   +-- [v] Build SDD Engine (task_002)
|   |   +-- [v] Build Agent SDK (task_006)
|   |   +-- [v] Write core module tests (task_007)
|   |
|   +-- SPEC-014: DTTP Implementation
|   |   +-- [v] Build DTTP Gateway (task_003)
|   |
|   +-- SPEC-015: ADT Operational Center
|   |   +-- [v] Build Operational Center Flask App (task_004)
|   |
|   +-- SPEC-016: ADT Help & Principles Page
|       +-- [ ] Build Help & Principles Page (task_005)
|
+-- Phase 1.5: Hardening + Service Extraction
|   +-- SPEC-018: Phase 1 Hardening
|   |   +-- [v] Phase A: Security fixes (task_008)
|   |   +-- [v] Phase B: Shared hash, config (task_009)
|   |
|   +-- SPEC-019: DTTP Standalone Service
|   |   +-- [v] Create standalone service (task_010)
|   |   +-- [v] Refactor Operational Center (task_011)
|   |   +-- [v] Update Agent SDK (task_012)
|   |   +-- [v] Integration tests (task_013)
|   |
|   +-- SPEC-020: Self-Governance Integrity
|       +-- [ ] Sovereign path check (task_014)
|       +-- [ ] Constitutional path check (task_015)
|       +-- [ ] ADS schema extension (task_016)
|       +-- [ ] Self-governance tests (task_017)
|       +-- [v] Overseer audit docs (task_018)
|
+-- Phase 2: Production Deployment (future)
```

**Indicators:**
- `[ ]` Pending
- `[>]` In Progress
- `[v]` Completed
- `[!]` Blocked/Escalated

### 2.3 Delegation Tree (Authority Flow Visualization)

An interactive tree showing **who delegated what to whom**, enabling full traceability from spec creation through task completion.

#### 2.3.1 Tree View (Primary)

Clickable tree showing delegation chains:

```
SPEC-020: Self-Governance Integrity
+-- Created by: Systems_Architect (CLAUDE)
    |
    +-- -> Backend_Engineer
    |   +-- task_014: Sovereign Path Check (pending)       [ ] PENDING
    |   +-- task_015: Constitutional Path Check (pending)  [ ] PENDING
    |   |   +-- blocked by: task_014
    |   +-- task_016: ADS Schema Extension (pending)       [ ] PENDING
    |   |   +-- blocked by: task_014
    |   +-- task_017: Self-Governance Tests (pending)      [ ] PENDING
    |       +-- blocked by: task_014, task_015, task_016
    |
    +-- -> Systems_Architect
        +-- task_018: Overseer Audit Docs (GEMINI)         [v] COMPLETED
```

**Tree Node Types:**
- **Spec Node:** Root of delegation chain, shows author
- **Role Node:** Who received delegation
- **Task Node:** Individual work item with status indicator
- **Subtask Node:** Further breakdown (if role sub-delegates)

**Status Indicators:**
- `[ ]` Pending
- `[>]` In Progress
- `[v]` Completed
- `[!]` Blocked/Escalated

**Interactions:**
- Click any node to expand/collapse children
- Click task to see full details + ADS event history
- Click role to see all tasks delegated to that role
- Trace upward to find authorizing spec and delegator

#### 2.3.2 Summary Matrix (Secondary)

Compact overview showing task counts per role x agent:

```
                    CLAUDE    GEMINI    UNASSIGNED
+------------------+---------+---------+-----------+
| Systems_Architect|    2    |    1    |     0     |
| Backend_Engineer |    5    |    7    |     4     |
| Frontend_Engineer|    1    |    0    |     0     |
| DevOps_Engineer  |    0    |    1    |     0     |
| Overseer         |    0    |    0    |     0     |
+------------------+---------+---------+-----------+
```

- Color-coded by workload (green/yellow/red)
- Click cell to filter Tree View by that role+agent
- Tooltip shows (completed/in_progress/pending) breakdown

---

## 3. Data Model

### 3.1 Task Schema Extension

Extend the existing `_cortex/tasks.json` with delegation tracking fields:

```json
{
  "id": "task_014",
  "title": "Add sovereign path check to gateway.py",
  "description": "Hardcode SOVEREIGN_PATHS list in gateway.py...",
  "status": "pending",
  "priority": "critical",
  "spec_ref": "SPEC-020",

  "delegation": {
    "delegated_by": {
      "role": "Systems_Architect",
      "agent": "CLAUDE"
    },
    "delegated_to": {
      "role": "Backend_Engineer",
      "agent": null
    },
    "delegated_at": "2026-02-07T13:04:52Z"
  },

  "created_by": "Systems_Architect",
  "created_at": "2026-02-07T13:04:52Z",
  "updated_at": null,
  "completed_at": null,
  "blocked_by": ["task_008"],
  "subtasks": []
}
```

**Delegation Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `delegation.delegated_by.role` | string | Role that assigned this task |
| `delegation.delegated_by.agent` | string | Agent (CLAUDE/GEMINI) that assigned |
| `delegation.delegated_to.role` | string | Role receiving the task |
| `delegation.delegated_to.agent` | string/null | Agent assigned (null = unassigned) |
| `delegation.delegated_at` | ISO8601 | When delegation occurred |
| `subtasks` | array | Nested tasks if role sub-delegates |

This enables:
- **Upward tracing:** From any task -> who delegated -> authorizing spec
- **Downward tracing:** From spec -> all delegated roles -> all tasks
- **Sub-delegation:** Roles can break down work and delegate further

### 3.2 Phases Configuration: `_cortex/phases.json`

```json
{
  "phases": [
    {
      "id": "1",
      "name": "Core Engines",
      "status": "completed",
      "specs": ["SPEC-014", "SPEC-015", "SPEC-016", "SPEC-017"]
    },
    {
      "id": "1.5",
      "name": "Hardening + Service Extraction",
      "status": "active",
      "specs": ["SPEC-018", "SPEC-019", "SPEC-020"]
    },
    {
      "id": "2",
      "name": "Production Deployment",
      "status": "planned",
      "specs": []
    }
  ]
}
```

### 3.3 ADS Integration

Task state changes are logged to `events.jsonl`:

```jsonl
{"action_type": "task_created", "action_data": {"task_id": "task_014", ...}}
{"action_type": "task_status_change", "action_data": {"task_id": "task_014", "from": "pending", "to": "in_progress"}}
{"action_type": "task_delegated", "action_data": {"task_id": "task_014", "role": "Backend_Engineer", "agent": "GEMINI"}}
```

---

## 4. UI Implementation

### 4.1 Navigation Integration

Add views to the existing Operational Center navigation (SPEC-015):

```
[Dashboard] [ADS Timeline] [Specs] [Tasks] [DTTP] [Hierarchy] [Delegation] [Help]
```

The Hierarchy and Delegation views are new additions. The existing Task Board view
gains delegation metadata on cards.

### 4.2 Task Board Enhancements (`adt_center/templates/tasks.html`)

- Extend task cards with delegation badge (delegated_by role + agent)
- Collapsible completed tasks grouped by assigned role
- Filter by: Role, Agent, Spec, Priority, Phase

### 4.3 Hierarchy View (`adt_center/templates/hierarchy.html`)

- Collapsible tree structure: Phase -> Spec -> Task
- Progress bar per spec (tasks completed / total)
- Progress bar per phase (specs completed / total)
- Click task to see details
- Data sourced from `_cortex/phases.json` + `_cortex/tasks.json`

### 4.4 Delegation View (`adt_center/templates/delegation.html`)

**Two-panel layout:**

#### Left Panel: Delegation Tree
- Collapsible tree rooted at specs
- Shows: Spec -> Delegator -> Role -> Tasks -> Subtasks
- Click to expand/collapse branches
- Status icons on task nodes
- Click task to show details in modal
- Breadcrumb trail showing current path

#### Right Panel: Summary Matrix
- Role x Agent count matrix
- Color-coded cells: green (<3), yellow (3-5), red (>5)
- Click cell to filter tree to that role+agent
- Tooltip shows (completed/in_progress/pending)

#### Interactions
- Tree node click -> expand/collapse
- Task click -> detail modal with ADS history
- Matrix cell click -> filter tree
- "Trace Authority" button -> highlights path to spec root

---

## 5. Implementation Jurisdiction

| Component | Responsible Role |
|-----------|------------------|
| `_cortex/tasks.json` schema extension | Systems_Architect (design) |
| `_cortex/phases.json` | Systems_Architect (create structure) |
| `adt_center/templates/hierarchy.html` | Frontend_Engineer |
| `adt_center/templates/delegation.html` | Frontend_Engineer |
| `adt_center/templates/tasks.html` updates | Frontend_Engineer |
| `adt_center/static/css/adt.css` updates | Frontend_Engineer |
| `adt_center/app.py` route additions | Backend_Engineer |
| Task CRUD operations | All roles (via ADS logging) |
| Static mirror deployment | Overseer (export to oceanpulse.pt/adt-framework/) |

---

## 6. ADT Compliance

This spec maintains ADT principles:

1. **Single Source of Truth:** Tasks stored in `_cortex/tasks.json`, changes logged to ADS
2. **Traceability:** Every task links to a spec_ref AND records full delegation chain
3. **Accountability:** Every task has `delegated_by` and `delegated_to` with role+agent
4. **Governance by Construction:** Task status changes require ADS events
5. **Authority Flow:** Delegation Tree enables visual tracing from any task back to authorizing spec and original delegator

---

## 7. Acceptance Criteria

### Data Model
- [ ] `_cortex/tasks.json` extended with delegation fields
- [ ] `_cortex/phases.json` created with current ADT Framework phases
- [ ] All existing tasks populated with `delegation` objects

### Hierarchy View
- [ ] Phase -> Spec -> Task tree renders correctly
- [ ] Progress bars show completion per spec and per phase
- [ ] Collapsible tree nodes
- [ ] Task click shows detail view

### Delegation Tree (Primary Focus)
- [ ] Tree view shows Spec -> Delegator -> Role -> Task hierarchy
- [ ] Nodes are expandable/collapsible
- [ ] Task nodes show status indicators
- [ ] Clicking task shows detail modal with ADS event history
- [ ] Subtasks display under parent tasks (sub-delegation)
- [ ] "Trace Authority" highlights path from task to spec root

### Summary Matrix
- [ ] Role x Agent matrix displays alongside tree
- [ ] Cells color-coded by workload (green/yellow/red)
- [ ] Clicking cell filters tree to that role+agent
- [ ] Tooltip shows (completed/in_progress/pending) breakdown

### ADT Compliance
- [ ] All task delegations logged to ADS with `action_type: task_delegated`
- [ ] Delegation changes create new ADS events (not edits)
- [ ] Static mirror deployed to oceanpulse.pt/adt-framework/

---

## 8. Relationship to Other Specs

| Spec | Relationship |
|------|-------------|
| SPEC-015 | **Parent.** This spec extends the Operational Center with new views. |
| SPEC-013 | **Related.** UI refinements (collapsible tasks, spec icons) apply here too. |
| SPEC-016 | **Sibling.** Help page is a separate SPEC-015 view, independent of this work. |
| SPEC-020 | **Consumer.** Self-governance tasks are the primary dataset for the Delegation Tree. |

---

## 9. Approval

**Human Approval Required:** YES

~~This spec changes the ADT governance tooling. Implementation should not proceed until human approves this design.~~

**APPROVED:** 2026-02-01 by Human
**REVISED:** 2026-02-09 v3.0 -- ADT Framework rewrite (pending re-approval)

---

*"Governance is an intrinsic system property, not an external overlay."*
*-- ADT Framework (Sheridan, 2026)*
