# SPEC-013: ADT Panel UI Refinements

**Status:** APPROVED
**Priority:** MEDIUM
**Owner:** Frontend_Engineer + Overseer
**Created:** 2026-02-05
**References:** SPEC-003 (ADT Dashboard)

---

## 1. Purpose
Define specific UI/UX enhancements for the ADT Oversight Panel to improve task management visibility, specification status tracking, and workflow narrative flow.

---

## 2. Functional Requirements

### 2.1 Collapsible Completed Tasks
- **Grouping:** Tasks in the "Completed" column of the Task Board MUST be grouped by `assigned_role`.
- **Collapsibility:** Each role group MUST be collapsible to reduce visual clutter.
- **Default State:** Groups should be collapsed by default if there are many roles, or expanded if few. (Standard: Collapsed to save space).

### 2.2 Spec Status Icons
- **Confirmed Specs:** Specifications with `Status: APPROVED` or verified in metadata MUST display a confirmation icon (e.g., `bi-patch-check-fill` in green).
- **Unconfirmed Specs:** Specifications with `Status: PENDING` or `DRAFT` MUST display a warning/info icon (e.g., `bi-question-circle` or `bi-clock-history`).
- **Location:** Icons should appear in the "Specification Coverage" list and the "Hierarchy" view.

### 2.3 Workflow Narrative Auto-Scroll
- **Behavior:** When the "Workflows" tab is active or newly populated, the container MUST automatically scroll to the bottom (the most recent events).
- **Context:** Ensures the "conclusion" of the current narrative is immediately visible to the user.

---

## 3. Implementation Plan

### 3.1 Frontend (panel.js)
- Refactor `renderTasks()` to implement role-based grouping for completed tasks using Bootstrap accordions or custom toggles.
- Enhance `updateSpecs()` and `renderHierarchy()` to detect status keywords in spec content and prepend appropriate icons.
- Add an IntersectionObserver or tab-change event listener to trigger `scrollToBottom()` on the `workflow-container`.

### 3.2 Styles (style.css)
- Add CSS for role-group headers in the task board.
- Ensure smooth scrolling for the workflow container.

---

## 4. Acceptance Criteria
- [ ] Completed tasks are neatly organized by role.
- [ ] SPEC-000 shows a green checkmark; SPEC-005 shows a pending icon.
- [ ] Opening the panel immediately shows the latest actions in the Workflow tab without manual scrolling.
