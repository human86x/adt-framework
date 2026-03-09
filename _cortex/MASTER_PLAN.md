# ADT Framework: Master Plan

**Phase:** 2.1 (Collaborative Governance)
**Status:** Active Development
**Task Tracking:** See `_cortex/tasks.json`
**Parent Spec:** SPEC-017 (from OceanPulse proving ground)

## Mission

Build the ADT Framework as a standalone, open-source governance system for AI agents.
OceanPulse is the first governed project (reference implementation).
The framework governs its own development -- recursive self-improvement through governance.

## Phase 2.1: Capability & Context (SPEC-038)
**Status:** ACTIVE

*   **[COMPLETED] Intent Definition API:** Capability Change Intents can be registered and traced.
*   **[COMPLETED] Triggering Event Capture:** External organizational signals can be linked to intents.
*   **[COMPLETED] Causal Traceability Engine:** Trace intents through triggering events, ADS audit trails, and tasks.
*   **[COMPLETED] Operator Console Integration:** Hive Tracker displays active Intent/Event context (SPEC-038 visual link).
*   **[IN PROGRESS] Automated Maturity Tracking:** Real-time calculation of intent maturity based on code/ADS evidence.

## Phase 2.2: Interactive Orchestration (SPEC-039)
**Status:** ACTIVE

*   **[COMPLETED] human_steering event:** ADS support for manual steering actions.
*   **[COMPLETED] PTY Command Injection:** Console can send hints/priorities to active agents.
*   **[IN PROGRESS] Hierarchical Sidebar:** Tree view visualization (Intent -> Spec -> Task).
*   **[IN PROGRESS] Real-time Pulse:** UI visual feedback synchronized with ADS tool-call stream.

## Current Objectives (Core)

1. **ADS Engine:** Extract and generalize Safe Logger from OceanPulse. (Status: COMPLETED)
2. **SDD Engine:** Spec lifecycle management. (Status: COMPLETED)
3. **DTTP Engine:** Privilege-separated enforcement gateway. (Status: COMPLETED)
4. **Operational Center:** Flask web app -- human UI + agent API. (Status: COMPLETED)
5. **Agent SDK:** Client library for AI agents. (Status: COMPLETED)
6. **Phase 1 Hardening:** Security fixes, deduplication, config population. (Status: COMPLETED -- SPEC-018)
7. **DTTP Standalone Service:** Standalone HTTP service on :5002. (Status: COMPLETED -- SPEC-019)
8. **Self-Governance Integrity:** Tiered path protection, break-glass, anti-self-modification. (Status: COMPLETED -- SPEC-020)
9. **Operator Console:** Cross-platform Tauri desktop app -- human command center for multi-agent governance. (Status: ACTIVE -- SPEC-021)
10. **Collaborative Bootstrap:** One-command setup for remote collaborators. Send framework, receive specs. (Status: DRAFT -- SPEC-025)

## Active Specifications

| Spec | Name | Status | Origin |
|------|------|--------|--------|
| SPEC-014 | DTTP Implementation (Level 3) | APPROVED | OceanPulse |
| SPEC-015 | ADT Operational Center | APPROVED | OceanPulse |
| SPEC-016 | ADT Help & Principles Page | APPROVED | OceanPulse |
| SPEC-017 | ADT Framework Repository | APPROVED | OceanPulse |
| SPEC-018 | Phase 1 Hardening | APPROVED | ADT Framework |
| SPEC-019 | DTTP Standalone Service | APPROVED | ADT Framework (REQ-001) |
| SPEC-020 | Self-Governance Integrity | COMPLETED | ADT Framework |
| SPEC-021 | ADT Operator Console | ACTIVE | ADT Framework |
| SPEC-038 | Organizational Capability Governance | APPROVED | ADT Framework |
| SPEC-039 | Interactive Governance Orchestration | APPROVED | ADT Framework |

## Version Roadmap

| Version | Milestone |
|---------|-----------|
| v0.1.0 | Core engines (ADS, SDD, DTTP) |
| v0.2.0 | Operational Center + Agent SDK + Self-Governance |
| v0.3.0 | Operator Console + Collaborative Bootstrap |
| v0.4.0 | Capability Governance & Interactive Orchestration |

## Role Assignments

* **Systems_Architect:** Specs, coordination, architectural decisions.
* **Backend_Engineer:** Flask app, API routes, DTTP engine, ADS engine.
* **Frontend_Engineer:** Operational Center UI, templates, Help page.
* **DevOps_Engineer:** DTTP privilege separation, Linux user setup, deployment.
* **Overseer:** ADS compliance, audit trail integrity.
