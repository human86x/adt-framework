# SPEC-040: Capability Governance UI Integration

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE)
**Date:** 2026-03-08
**Priority:** HIGH
**Depends On:** SPEC-038, SPEC-038A, SPEC-021, SPEC-028, SPEC-034, SPEC-039
**Source Authority:** itgis.org/dcp010 -- "Capability Change Intent and Event Capture" & "Capability Evolution Workflow"
**Related Specs:** SPEC-015 (Operational Center), SPEC-035 (Unified Status API)

---

## 1. Purpose

Provide a comprehensive, end-to-end UI for the Capability Governance system across both the **ADT Panel** (Flask web interface) and the **ADT Operator Console** (Tauri desktop app). This spec covers:

1. **ADT Panel** -- Full-page Capabilities tab with intent management, stage-gate workflow visualization, traceability explorer, and impact dashboards.
2. **ADT Console** -- Right-sidebar integration showing active capability context, gate progress, and inline gate evaluation for the operator.

The UI must faithfully represent all 8 sections of the source "Capability Change Intent and Event Capture" form and the 7-stage "Capability Evolution Workflow" gate process.

---

## 2. Design Principles

1. **Source Fidelity** -- Every field from the source documents must be capturable through the UI. No silent omissions.
2. **Progressive Disclosure** -- Show summary views by default; let the user drill into detail. Don't overwhelm with all 8 sections at once.
3. **Dual Context** -- The Panel is for strategic oversight (portfolio view). The Console is for operational context (what am I working on right now?).
4. **Live Data** -- All views pull from the API endpoints defined in SPEC-038A. No static mock data in production.
5. **ADT Visual Language** -- Dark theme, ADT color palette, consistent with existing Panel and Console styling.

---

## 3. ADT Panel: Capabilities Tab (Full Redesign)

### 3.1 Layout Overview

The Capabilities page (`/capabilities`) is divided into four main zones:

```
+------------------------------------------------------------------+
| HEADER: "Organizational Capabilities"  [+ New Intent] [Refresh]  |
+------------------------------------------------------------------+
| LEFT COL (8)              | RIGHT COL (4)                        |
|                           |                                      |
| 3.2 Strategic Pipeline    | 3.5 Portfolio Summary                |
|   (Kanban board)          |   (stats + charts)                   |
|                           |                                      |
+---------------------------+--------------------------------------+
| LEFT COL (4)    | CENTER COL (4)     | RIGHT COL (4)             |
|                 |                    |                            |
| 3.3 Event Feed  | 3.4 Stage-Gate     | 3.6 Traceability          |
|   (timeline)    |   Visualiser       |   Explorer                |
|                 |   (funnel/stepper) |   (causal chain)          |
+-----------------+--------------------+----------------------------+
```

### 3.2 Strategic Pipeline (Kanban Board)

A horizontal Kanban board showing intents grouped by their lifecycle status. Each column represents a status from the 7-state lifecycle:

**Columns:**
1. Intent Defined
2. Event Under Review
3. Approved for Transformation
4. In Transformation
5. Operational
6. Value Assessed
7. Rejected (collapsed by default, expandable)

**Intent Card:**
Each card displays:
- **Title** (bold, truncated to 2 lines)
- **Type badge** (color-coded: Innovation=purple, Enhancement=blue, Maintenance=grey, Risk Mitigation=amber, Regulatory Compliance=red, Operational Improvement=green)
- **Maturity delta bar** -- horizontal bar showing current (filled) vs target (outline), e.g. `[===|-----]` Developing -> Managed
- **Value category icon** (Revenue=$, Efficiency=gear, Risk Reduction=shield, Customer Experience=heart, Sustainability=leaf)
- **Gate progress indicator** -- `Gate 4/7` with mini dots (filled=completed, hollow=pending, red=halted)
- **Owner** (from `org_context.owner`)
- **Risk badge** (colored dot: green/amber/red/black for Low/Medium/High/Critical)

**Card Click:** Opens the Intent Detail Drawer (3.7).

**Drag-and-Drop:** Disabled. Status transitions happen only through gate evaluations or explicit status change via the detail drawer. This enforces governance.

### 3.3 Event Feed (Timeline)

A vertical timeline of captured Triggering Events, most recent first.

**Each event shows:**
- **Timestamp** (relative, e.g. "2 hours ago")
- **Type icon** (mapped from 10-type taxonomy, each with a distinct icon)
- **Title** (from `description`, truncated)
- **Priority badge** (Low=grey, Medium=blue, High=amber, Critical=red pulsing)
- **Linked Intent** (clickable chip showing `INT-xxx` if linked)
- **Status** (Captured / Under Review / Actioned / Dismissed)

**Actions per event:**
- "Link to Intent" (dropdown of active intents)
- "Dismiss" (with reason)

**"+ Capture Event" button** at top opens the Event Capture Modal (3.8).

**Event Type Icons:**

| Type | Icon |
|------|------|
| Innovation Hub Breakthrough | lightbulb |
| Customer Signal | people |
| Workforce Observation | eye |
| Market Change | trending-up |
| Technology Opportunity | cpu |
| Risk Occurrence | exclamation-triangle |
| Regulatory Trigger | file-earmark-ruled |
| Business-Technical Ecosystem Shift | arrows-fullscreen |
| Strategic Initiative | flag |
| Operational Insight | clipboard-data |

### 3.4 Stage-Gate Visualiser

When an intent is selected (via card click or traceability explorer), this panel shows the 7-stage gate progression as a **vertical stepper**:

```
  [1] Validation & Classification          [COMPLETED - Proceed]
   |  Financial: Positive, Technical: Feasible
   |  "Intent validated, classified as Enhancement"
   v
  [2] Concept Development                  [COMPLETED - Proceed]
   |  Prototype: Yes, Concept: "ML-based tuning"
   |  "Concept prototype demonstrated successfully"
   v
  [3] Strategic Feasibility                 [COMPLETED - Proceed]
   |  All dimensions positive
   v
  [4] Governance & Quality Review           [CURRENT - Awaiting]
   |  [Evaluate Gate] button
   v
  [5] Portfolio Planning                    [LOCKED]
   v
  [6] Investment Decision                   [LOCKED]
   v
  [7] Transformation Initiation             [LOCKED]
```

**Gate States:**
- **COMPLETED (Proceed)** -- Green checkmark, decision summary shown, collapsible detail
- **COMPLETED (Refine)** -- Amber loop icon, shows re-evaluation history
- **COMPLETED (Halt)** -- Red X, shows rejection reason
- **CURRENT (Awaiting)** -- Blue pulsing dot, "Evaluate Gate" button visible
- **LOCKED** -- Grey lock icon, not yet reachable

**"Evaluate Gate" Button:**
Opens the Gate Evaluation Modal (3.9) pre-populated with the gate-specific fields from SPEC-038A section 3.2.

**Completed Gate Expansion:**
Clicking a completed gate expands to show:
- All decision_data fields with values
- Desired outcome vs Actual outcome (side-by-side)
- Evaluator name and timestamp
- ADS event link (clickable, opens ADS Timeline filtered to that event)
- Hash chain verification status (checkmark if valid)

### 3.5 Portfolio Summary

Aggregate dashboard showing:

**Stats Cards (top row):**
- Total Intents (number)
- Active (In Transformation) count
- Avg Gate Progress (e.g. "Gate 3.2 / 7")
- Value Realised (count of "Value Assessed" intents)

**Maturity Distribution Chart:**
Horizontal stacked bar chart showing how many intents are at each maturity level (current vs target overlay).

**Value Category Breakdown:**
Donut chart showing distribution of intents by value_category (Revenue, Efficiency, Risk Reduction, Customer Experience, Sustainability).

**Risk Heatmap:**
2x2 grid (Impact vs Likelihood) with intent count per cell, colored by density.

**Intent Type Distribution:**
Small bar chart showing counts per type (Innovation, Enhancement, etc.).

### 3.6 Traceability Explorer

When an intent is selected, shows the full causal chain as a directed graph / tree:

```
Intent: "Improve ECU Tuning Accuracy" (INT-001)
  |
  +-- Triggering Event: "ECU Log Drift Detected" (CEV-001)
  |
  +-- Gate Chain: [1]->[2]->[3]->[4 awaiting]
  |
  +-- Linked Specs:
  |     +-- SPEC-042: ECU ML Pipeline
  |     +-- SPEC-043: Dyno Integration
  |
  +-- Executed Tasks:
  |     +-- task_201: Build ML training pipeline [completed]
  |     +-- task_202: Dyno API connector [in_progress]
  |
  +-- ADS Audit Trail: (last 10 events)
        +-- evt_001: capability_intent_defined
        +-- evt_002: capability_gate_evaluated (Gate 1)
        +-- evt_003: task_status_updated (task_201)
        +-- ...
```

**Each node is clickable:**
- Specs link to the Specs tab filtered to that spec
- Tasks link to the Tasks tab filtered to that task
- ADS events link to the ADS Timeline filtered to that event
- Gates scroll the Stage-Gate Visualiser (3.4) to that gate

**Export:** "Export Trace" button generates a JSON file with the complete causal chain for audit purposes.

### 3.7 Intent Detail Drawer

A slide-out drawer (from right, 600px wide) that opens when clicking an intent card. Contains all 8 sections from the source document in an accordion layout:

**Accordion Sections:**

1. **Intent Definition** (always open)
   - Title, Type, Description, Date
   - Status badge with lifecycle stepper (mini horizontal)
   - "Change Status" dropdown (only valid transitions shown)

2. **Organisational Context**
   - Unit, Domain, Process, Owner (editable inline)

3. **Capability Impact**
   - Capability Name, Type, Current Maturity, Target Maturity
   - Visual maturity delta bar (large)
   - "Realised Maturity" calculated from completed task evidence

4. **Technical Ecosystem**
   - Systems (tag chips, addable), Data Sources (tag chips), Dependencies (tag chips), Platform

5. **Risk & Compliance**
   - Risk Level (dropdown), Regulatory Impact (text), Description (textarea)
   - Color-coded risk banner at top of section

6. **Value Realisation**
   - Expected Benefit (text), Success Metrics (textarea)
   - Post-transformation: Actual Benefit, Measured Metrics (editable after "Operational" status)

7. **Governance & Accountability**
   - Reporter, Accountable Executive, Review Board
   - Decision History (from gate evaluations, read-only timeline)

8. **Gate Progress**
   - Embedded mini Stage-Gate Visualiser (compact vertical stepper)
   - "Evaluate Next Gate" button

**Footer Actions:**
- Save Changes (PUT to `/api/governance/capabilities/intents/<id>`)
- Archive Intent
- Export Intent (JSON)

### 3.8 Event Capture Modal

Full-screen modal for capturing a new Triggering Event. Organized as a multi-step wizard:

**Step 1: Event Details**
- Event Type (dropdown, 10 types with icons)
- Priority (Low/Medium/High/Critical radio buttons)
- Description (textarea)
- Date Detected (date picker, defaults to today)

**Step 2: Organisational Context**
- Organisation Unit (text, with autocomplete from previous events)
- Business Domain (text, autocomplete)
- Process Impacted (text, autocomplete)
- Stakeholder Owner (text, autocomplete)

**Step 3: Technical Ecosystem**
- Systems Affected (tag input)
- Data Sources (tag input)
- Integration Dependencies (tag input)
- Technology Platform (text)

**Step 4: Link to Intent**
- Dropdown of active intents (with search)
- "Create New Intent" inline option
- Or "No linked intent" checkbox

**Step 5: Review & Submit**
- Read-only summary of all fields
- "Submit" button (POST to `/api/governance/capabilities/events`)

### 3.9 Gate Evaluation Modal

Modal for evaluating a specific gate. The form dynamically renders fields based on the gate number (per SPEC-038A sec 3.2):

**Header:**
- Gate number and name (e.g. "Gate 3 -- Strategic Feasibility Evaluation")
- Intent title and ID
- Current status

**Gate-Specific Fields:**
Rendered dynamically from the `GATE_FIELDS` definition. Each field type maps to an appropriate control:

| Gate | Field | Control Type |
|------|-------|-------------|
| 1 | classification | Select (6 intent types) |
| 1 | priority | Select (Low/Medium/High/Critical) |
| 1 | validator | Text input |
| 2 | concept_id | Text input |
| 2 | prototype_required | Toggle (Yes/No) |
| 2 | architecture_concept | Textarea |
| 2 | concept_owner | Text input |
| 3 | financial_feasibility | Select (Positive/Marginal/Negative) |
| 3 | operational_feasibility | Select (Feasible/Requires Change/Not Feasible) |
| 3 | technical_feasibility | Select (Feasible/Complex/Not Feasible) |
| 3 | strategic_alignment | Select (High/Moderate/Low) |
| 4 | architecture_review | Select (Approved/Conditional/Rejected) |
| 4 | risk_rating | Select (Low/Medium/High/Critical) |
| 4 | compliance_status | Select (Compliant/Review Required/Non-Compliant) |
| 4 | review_board | Text input |
| 5 | portfolio_priority | Select (Low/Medium/High/Strategic) |
| 5 | portfolio_manager | Text input |
| 5 | estimated_resources | Text input |
| 5 | target_delivery_window | Text input |
| 6 | investment_decision | Select (Approved/Deferred/Rejected/Further Investigation) |
| 6 | investment_board | Text input |
| 6 | decision_date | Date picker |
| 6 | approved_budget | Text input |
| 7 | program_id | Text input |
| 7 | program_manager | Text input |
| 7 | start_date | Date picker |
| 7 | delivery_organisation | Text input |

**Outcome Fields (all gates):**
- Desired Outcome (textarea, pre-populated with gate-specific guidance text from source doc)
- Actual Outcome (textarea, required)

**Decision:**
- Radio buttons: `Proceed` | `Refine` | `Halt`
- If "Halt": Rejection Reason (textarea, required)
- If "Refine": Refinement Notes (textarea, required)

**Footer:**
- "Submit Gate Evaluation" (POST to `/api/governance/capabilities/intents/<id>/gates`)
- Warning banner: "This action will be permanently recorded in the ADS audit trail."

---

## 4. ADT Console: Right Sidebar Integration

### 4.1 Context Panel Enhancement

The existing right sidebar (Hive Tracker) in the Operator Console gains a new **"Capability Context"** section, positioned between the session info and the orchestration tree.

#### Layout (within existing sidebar):

```
+----------------------------------+
| SESSION INFO (existing)          |
|   Role: Backend_Engineer         |
|   Agent: CLAUDE                  |
|   Uptime: 2h 14m                 |
+----------------------------------+
| CAPABILITY CONTEXT (NEW)         |  <-- New section
|   Intent: INT-001                |
|   "Improve ECU Tuning Accuracy"  |
|   Status: In Transformation      |
|   Gate: 5/7 [=====||]            |
|   Maturity: Developing -> Managed|
|   [|||====] 40%                  |
|   Trigger: CEV-001               |
|   "ECU Log Drift Detected"       |
|   Risk: [Medium]                 |
|   [View in Panel] [Evaluate Gate]|
+----------------------------------+
| ORCHESTRATION TREE (existing)    |
|   ...                            |
+----------------------------------+
| ADS EVENTS (existing)            |
|   ...                            |
+----------------------------------+
```

### 4.2 Capability Context Section Detail

**4.2.1 Active Intent Display**

Shows the intent driving the current session (determined by matching the active spec/task to an intent via the traceability chain):

- **Intent ID** (small, muted) + **Title** (bold, white, up to 2 lines)
- **Status badge** (color-coded pill matching the lifecycle state)
- **Gate progress bar** -- horizontal segmented bar with 7 segments:
  - Filled green = completed (Proceed)
  - Filled amber = completed (Refine, was re-evaluated)
  - Filled red = halted
  - Blue pulse = current gate
  - Grey = locked
  - Label: "Gate N/7"
- **Maturity delta bar** -- two-tone horizontal bar:
  - Filled portion = current maturity level (1-5 mapped to 0-100%)
  - Target marker = target maturity level
  - Percentage label = realized maturity (task completion weighted)

**4.2.2 Trigger Event**

Below the intent:
- **Event ID** (small, muted) + **Description** (truncated to 1 line)
- **Type icon** (from the 10-type icon set)
- **Priority badge** (same color scheme as Panel)

**4.2.3 Risk Indicator**

- Colored dot + text label (Low/Medium/High/Critical)
- If Critical: pulsing red animation

**4.2.4 Action Buttons**

- **"View in Panel"** -- Opens the ADT Panel Capabilities tab filtered to this intent (using the existing Panel iframe or external browser launch)
- **"Evaluate Gate"** -- Only shown if the current gate is awaiting evaluation AND the operator's role has gate evaluation permissions. Opens a compact in-console gate evaluation form (4.3).

### 4.3 Inline Gate Evaluation (Console)

A compact, single-panel form that replaces the Capability Context section temporarily when "Evaluate Gate" is clicked. Designed for quick evaluations without leaving the console.

**Layout:**

```
+----------------------------------+
| GATE 4: Governance & Quality     |
| Intent: "Improve ECU Tuning..."  |
+----------------------------------+
| Architecture Review:             |
| [Approved v]                     |
| Risk Rating:                     |
| [Medium v]                       |
| Compliance Status:               |
| [Compliant v]                    |
| Review Board:                    |
| [Technical Steering Cmte    ]    |
+----------------------------------+
| Desired Outcome:                 |
| "Confirm meets quality..."       |
| Actual Outcome:                  |
| [                            ]   |
+----------------------------------+
| Decision: (o)Proceed ()Refine    |
|           ()Halt                 |
+----------------------------------+
| [Cancel]          [Submit Gate]  |
+----------------------------------+
```

- Fields rendered dynamically per gate number (same mapping as Panel modal)
- "Desired Outcome" pre-populated (read-only guidance)
- On submit: POST to gate API, section reverts to Capability Context display with updated state
- ADS pulse feedback on successful submission

### 4.4 Capability-Aware Orchestration Tree

The existing orchestration tree (SPEC-039) groups tasks by Spec, then by Intent. This section extends it:

**Current hierarchy:**
```
Intent: INT-001 "Improve ECU Tuning"
  Spec: SPEC-042
    Task: task_201 [completed]
    Task: task_202 [in_progress]
  Spec: SPEC-043
    Task: task_203 [pending]
```

**Enhancement:**
- Add a **gate progress indicator** next to each Intent node (mini 7-dot bar)
- Add **maturity delta** next to each Intent node
- Add **value category icon** next to each Intent node
- Color the Intent node border by risk level
- When a task is completed, animate the maturity delta bar if it changes the realized maturity percentage

### 4.5 Status Bar Integration

The bottom status bar of the Console gains one new indicator:

```
[ADS: 1,247] [Sessions: 3] [Escalations: 0] [DTTP: OK] [Gate: 4/7] [Git: main] [14:32]
                                                         ^^^^^^^^^^
                                                         NEW
```

- **Gate indicator** shows the current gate progress for the active session's linked intent
- Format: `Gate: N/7` where N is the current gate number
- Color: green if progressing, amber if refined, red if halted, grey if no linked intent
- Click: scrolls the sidebar to the Capability Context section

### 4.6 Notifications

The Console's native notification system (via `send_notification` IPC) triggers for:

| Event | Notification |
|-------|-------------|
| Gate evaluated (any intent) | "Gate N passed for [Intent Title]" |
| Gate halted | "Gate N HALTED for [Intent Title] - [reason]" (urgent) |
| Intent status changed | "Intent [Title] is now [Status]" |
| New triggering event captured | "New event: [Description]" |
| Maturity target reached | "Intent [Title] has reached target maturity!" (celebration) |

---

## 5. ADT Panel: New Intent Creation Wizard (Full Redesign)

Replace the current simple modal with a multi-step wizard that captures all 8 sections:

### Step 1: Intent Definition
- Title (required)
- Type (6-option select)
- Description (textarea, required)
- Date (auto-filled, editable)

### Step 2: Organisational Context
- Organisation Unit
- Business Domain
- Process Impacted
- Stakeholder Owner
- All with autocomplete from previously entered values

### Step 3: Capability Impact
- Capability Name
- Capability Type (5-option select)
- Current Maturity (5-level select)
- Target Maturity (5-level select, must be >= current)
- Visual preview of maturity delta bar

### Step 4: Technical Ecosystem
- Systems Affected (tag input with suggestions)
- Data Sources (tag input)
- Integration Dependencies (tag input)
- Technology Platform

### Step 5: Risk & Compliance
- Risk Level (4-option select with color preview)
- Regulatory Impact (text)
- Risk Description (textarea)

### Step 6: Value Realisation
- Expected Benefit (text)
- Value Category (5-option select)
- Success Metrics (textarea)

### Step 7: Governance & Accountability
- Reporter (auto-filled from session role)
- Accountable Executive
- Review Board

### Step 8: Review & Submit
- Read-only summary card showing all sections
- Validation warnings (missing optional but recommended fields highlighted)
- "Define Intent" button
- Confirmation: "This will create an ADS audit record."

**Wizard Navigation:**
- Step indicators at top (numbered circles)
- "Back" / "Next" buttons
- Steps 2-7 are optional (can be skipped)
- Step 1 and 8 are required

---

## 6. Shared Component Library

To avoid duplication between Panel and Console, define reusable visual components:

### 6.1 Maturity Delta Bar
- Input: `current_maturity`, `target_maturity`, `realized_percentage`
- Renders: two-tone bar with marker
- Used in: Panel intent cards, Console capability context, Intent detail drawer

### 6.2 Gate Progress Bar
- Input: `gates[]` array of gate records
- Renders: 7-segment horizontal bar with state colors
- Used in: Panel intent cards, Panel stage-gate visualiser, Console capability context, Console status bar

### 6.3 Risk Badge
- Input: `level` (Low/Medium/High/Critical)
- Renders: colored dot + label
- Used in: Panel intent cards, Console capability context, Intent detail drawer

### 6.4 Type Badge
- Input: `type` (6 intent types)
- Renders: colored pill with text
- Used in: Panel intent cards, Intent detail drawer

### 6.5 Value Icon
- Input: `value_category`
- Renders: Bootstrap icon mapped to category
- Mapping: Revenue=currency-dollar, Efficiency=gear-wide-connected, Risk Reduction=shield-check, Customer Experience=heart, Sustainability=tree

### 6.6 Event Type Icon
- Input: `event_type` (10 types)
- Renders: Bootstrap icon mapped to type
- Mapping: defined in section 3.3

---

## 7. Data Flow

### 7.1 Panel Data Flow

```
capabilities.html
  |
  +-- capabilities.js
        |
        +-- GET /api/governance/capabilities/intents       -> Strategic Pipeline
        +-- GET /api/governance/capabilities/events         -> Event Feed
        +-- GET /api/governance/capabilities/summary        -> Portfolio Summary
        +-- GET /api/governance/capabilities/intents/<id>/gates -> Stage-Gate Visualiser
        +-- GET /api/governance/capabilities/trace/<id>     -> Traceability Explorer
        |
        +-- POST /api/governance/capabilities/intents       <- New Intent Wizard
        +-- POST /api/governance/capabilities/events        <- Event Capture Modal
        +-- POST /api/governance/capabilities/intents/<id>/gates <- Gate Evaluation Modal
        +-- PUT  /api/governance/capabilities/intents/<id>  <- Intent Detail Drawer edits
        +-- PUT  /api/governance/capabilities/intents/<id>/status <- Status transitions
```

### 7.2 Console Data Flow

```
context.js
  |
  +-- fetchCapabilityContext()
  |     GET /api/governance/capabilities/trace/active
  |     -> Determines linked intent from active spec/task
  |
  +-- fetchGateProgress(intent_id)
  |     GET /api/governance/capabilities/intents/<id>/gates
  |     -> Gate progress bar, inline evaluation availability
  |
  +-- submitGateEvaluation(intent_id, gate_data)
  |     POST /api/governance/capabilities/intents/<id>/gates
  |     -> Inline gate form submission
  |
  +-- Tauri event listeners:
        "capability-updated" -> Refresh capability context section
        "gate-evaluated"     -> Update gate progress + ADS pulse
```

### 7.3 Active Intent Resolution (Console)

The Console needs to determine which intent is relevant to the current session:

1. Get the active session's `spec_ref` (e.g. SPEC-042)
2. Query all intents and their traces
3. Find the intent whose trace includes `spec_ref`
4. If multiple: show the most recently active one
5. If none: show "No linked intent" with a "Link Intent" button

The `/api/governance/capabilities/trace/active` endpoint accepts `?spec_ref=SPEC-042` to perform this resolution server-side.

---

## 8. File Changes Required

### 8.1 ADT Panel (Frontend_Engineer jurisdiction)

| File | Change |
|------|--------|
| `adt_center/templates/capabilities.html` | Complete rewrite per section 3 |
| `adt_center/static/js/capabilities.js` | Complete rewrite: pipeline, events, gates, traceability |
| `adt_center/static/css/adt-panel.css` (or equivalent) | Add gate stepper, maturity bar, risk badge, kanban styles |

### 8.2 ADT Console (Frontend_Engineer jurisdiction)

| File | Change |
|------|--------|
| `adt-console/src/index.html` | Add capability context section to right sidebar (lines ~91-164) |
| `adt-console/src/js/context.js` | Add `fetchGateProgress()`, `submitGateEvaluation()`, `renderCapabilityContext()`, `renderInlineGateForm()` |
| `adt-console/src/css/console.css` | Add capability context styles, gate bar, maturity bar, inline form |

### 8.3 Backend (Backend_Engineer jurisdiction)

| File | Change |
|------|--------|
| `adt_center/api/governance_routes.py` | Add gate endpoints, summary endpoint, active trace resolution |

### 8.4 Tauri IPC (DevOps_Engineer jurisdiction)

| File | Change |
|------|--------|
| `adt-console/src-tauri/src/ipc.rs` | Add `capability-updated` and `gate-evaluated` event emissions from file watchers |

---

## 9. Implementation Tasks

| Task ID | Title | Assigned To | Priority |
|---------|-------|-------------|----------|
| task_184 | Redesign `capabilities.html` with Kanban pipeline, event feed, gate visualiser, traceability explorer | Frontend_Engineer | HIGH |
| task_185 | Rewrite `capabilities.js` with full API integration (intents, events, gates, traces) | Frontend_Engineer | HIGH |
| task_186 | Implement New Intent Creation Wizard (8-step) in Panel | Frontend_Engineer | HIGH |
| task_187 | Implement Event Capture Modal (5-step wizard) in Panel | Frontend_Engineer | HIGH |
| task_188 | Implement Gate Evaluation Modal with dynamic field rendering in Panel | Frontend_Engineer | HIGH |
| task_189 | Implement Intent Detail Drawer (8-section accordion) in Panel | Frontend_Engineer | MEDIUM |
| task_190 | Implement Portfolio Summary dashboard (charts) in Panel | Frontend_Engineer | MEDIUM |
| task_191 | Add Capability Context section to Console right sidebar | Frontend_Engineer | HIGH |
| task_192 | Add inline Gate Evaluation form to Console sidebar | Frontend_Engineer | MEDIUM |
| task_193 | Extend Console orchestration tree with intent/gate/maturity decorations | Frontend_Engineer | MEDIUM |
| task_194 | Add Gate progress indicator to Console status bar | Frontend_Engineer | LOW |
| task_195 | Add capability-related Tauri event emissions (file watchers) | DevOps_Engineer | MEDIUM |
| task_196 | Implement gate API endpoints and active trace resolution in `governance_routes.py` | Backend_Engineer | HIGH |
| task_197 | Add Panel CSS for gate stepper, maturity bars, kanban, risk badges | Frontend_Engineer | HIGH |
| task_198 | Add Console CSS for capability context, inline gate form | Frontend_Engineer | MEDIUM |
| task_199 | Implement native notifications for gate events via Tauri IPC | DevOps_Engineer | LOW |

---

## 10. Acceptance Criteria

### Panel
- [ ] Strategic Pipeline displays all intents as cards in a Kanban board grouped by lifecycle status.
- [ ] Intent cards show type badge, maturity delta bar, gate progress, value icon, risk badge, and owner.
- [ ] Event Feed displays all triggering events with type icons, priority badges, and linked intent chips.
- [ ] Stage-Gate Visualiser shows 7 gates as a vertical stepper with correct state rendering.
- [ ] Gate Evaluation Modal renders gate-specific fields dynamically and submits via API.
- [ ] Traceability Explorer shows the full causal chain (Intent -> Gates -> Events -> Specs -> Tasks -> ADS).
- [ ] Portfolio Summary shows aggregate statistics and charts.
- [ ] Intent Detail Drawer shows all 8 sections in accordion layout.
- [ ] New Intent Wizard captures all 8 sections across steps.

### Console
- [ ] Capability Context section shows active intent, gate progress, maturity delta, trigger event, and risk.
- [ ] Inline Gate Evaluation form renders correct fields and submits successfully.
- [ ] Orchestration tree shows gate progress and maturity delta per intent node.
- [ ] Status bar shows Gate: N/7 indicator.
- [ ] Native notifications fire for gate evaluations and status changes.

### Integration
- [ ] Panel and Console show consistent data from the same API endpoints.
- [ ] Gate evaluation in Console immediately reflects in Panel (and vice versa).
- [ ] All actions are logged to ADS with proper hash-chain integrity.

---

*"The interface is the governance -- if you can see it, you can trace it."*
