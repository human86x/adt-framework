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

**APPROVED** — Added to SPEC-013 UI Refinements.

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

**OPEN** — Submitted via Frontend session.

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

**OPEN** — Submitted via Overseer session.
