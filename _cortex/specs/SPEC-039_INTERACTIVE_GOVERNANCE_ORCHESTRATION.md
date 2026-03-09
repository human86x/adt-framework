# SPEC-039: Interactive Governance Orchestration

**Status:** APPROVED
**Author:** Systems_Architect (GEMINI)
**Date:** 2026-03-07
**Priority:** HIGH
**Related Specs:** SPEC-021 (Operator Console), SPEC-034 (Context Panel), SPEC-038 (Capability Governance)

---

## 1. Purpose

This specification defines the evolution of the ADT Operator Console from a passive monitoring tool to an **active orchestration command center**. It enables bi-directional communication between the Human and the Agent, visualizes the strategic hierarchy (Intent → Spec → Task), and provides real-time "thinking" feedback to ensure technical actions remain aligned with organizational purpose.

---

## 2. Problem

- **One-way Visibility:** The Human can see what the Agent is doing (via terminal and ADS feed), but can only influence it through natural language prompts within the terminal. This is slow and error-prone.
- **Context Blindness:** The "Hive Tracker" is a flat list of tasks. It lacks the visual hierarchy defined in SPEC-038 (Capability Governance), making it hard to see the "Big Picture" at a glance.
- **Latency in Oversight:** The Human only knows the "result" of an action. There is no visual feedback for the agent's "thinking" or "tool-calling" phases until the action is completed or denied.

---

## 3. The "Governance Zoom" (Contextual Hierarchy)

### 3.1 Hierarchical Tree View
The Sidebar (Hive Tracker) will transition from a flat list to a nested tree:

```
[+] Intent: INT-005 - Improve ECU Latency
    [+] Spec: SPEC-031 - External Project Governance
        [-] Task: task_164 - Extend ADSEventSchema
            (Status: IN_PROGRESS - Agent Active Here)
        [ ] Task: task_165 - Implement Endpoints
```

### 3.2 Visual "Gear Shifting"
- **Focus Mode:** When an agent starts a task, the parent hierarchy (Intent and Spec) should expand automatically and "glow" to show the active context.
- **Breadcrumb Alignment:** The Console header will show the full strategic path: `Capability > Intent > Spec > Task`.

---

## 4. Interactive Task Injection (Click-to-Assign)

### 4.1 Command Injection Protocol
We will implement a mechanism for the **Tauri Rust backend** to inject commands into the agent session.

- **The Trigger:** Human clicks a "Play" or "Prioritize" button next to a task in the Sidebar.
- **The Action:** The Console sends an IPC message to the Rust PTY handler.
- **The Execution:** The PTY handler sends a "Control Message" to the agent.
  - *For Claude Code:* Inject a natural language hint into the PTY stream: `User hint: Focus on Task ID: <task_id> immediately.`
  - *For Gemini CLI:* Append the task ID to a `~/.adt/current_priority` file that the CLI watches.

### 4.2 Governance Logging
Every interactive injection must be logged as a `human_steering` event:
- `event_id`: `evt_...`
- `action_type`: `human_steering`
- `description`: `Human prioritized task <task_id> via Console UI.`
- `authorized`: `True` (Human-only action)

---

## 5. Real-Time "Thinking" Visualization

### 5.1 ADS-Driven Feedback Loop
The Sidebar will pulse or change color based on **Pending ADS Events**.

| ADS Action Type | Visual Effect in Sidebar |
|-----------------|-------------------------|
| `pending_read`  | The "Technical Ecosystem" section pulses blue. |
| `pending_edit`  | The "Active Task" card pulses amber. |
| `denied_...`    | The hierarchy level (e.g., Spec) pulses red. |
| `completed_...` | The task card flashes green and transitions to "Completed" list. |

### 5.2 Tool-to-File Mapping
If a `pending_edit` event specifies a file (e.g., `adt_core/ads/schema.py`), the UI should display a temporary "Working on: <filename>" badge next to the active task.

---

## 6. Implementation Tasks

| Task | Description | Assigned To |
|------|-------------|-------------|
| task_169 | Refactor `index.html` to support nested hierarchy in Hive Tracker. | Frontend_Engineer |
| task_170 | Implement `human_steering` event in ADS Schema. | Backend_Engineer |
| task_171 | Implement PTY "Command Injection" logic in `pty.rs` (Rust). | DevOps_Engineer |
| task_172 | Map real-time ADS event stream to UI state changes in `context.js`. | Frontend_Engineer |
| task_173 | Add "Prioritize" buttons to task list in Sidebar. | Frontend_Engineer |

---

## 7. Acceptance Criteria

- [ ] Human can see the full Intent → Spec → Task hierarchy in the side panel.
- [ ] Clicking a task in the Sidebar sends a prioritization hint to the active agent.
- [ ] Every manual prioritization is logged as `human_steering` in the ADS.
- [ ] The Sidebar visually reacts (pulses) when the agent calls a tool (detected via ADS events).
- [ ] The hierarchy "shifts focus" visually when the agent transitions between tasks.

---

*"Orchestration is the art of alignment."*
