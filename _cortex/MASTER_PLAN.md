# ADT Framework: Master Plan

**Phase:** 2.0 (Collaborative Governance)
**Status:** Active Development
**Task Tracking:** See `_cortex/tasks.json`
**Parent Spec:** SPEC-017 (from OceanPulse proving ground)

## Mission

Build the ADT Framework as a standalone, open-source governance system for AI agents.
OceanPulse is the first governed project (reference implementation).
The framework governs its own development -- recursive self-improvement through governance.

## Current Objectives

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
11. **Governance Configurator:** Visual UI for human to configure DTTP roles, jurisdictions, and permissions. (Status: DRAFT -- SPEC-026)
12. **Shatterglass Protocol:** OS-level file permission enforcement with time-limited privilege escalation. (Status: APPROVED -- SPEC-027)

## Active Specifications

| Spec | Name | Status | Origin |
|------|------|--------|--------|
| SPEC-013 | ADT Panel UI Refinements | COMPLETED | ADT Framework |
| SPEC-014 | DTTP Implementation (Level 3) | APPROVED | OceanPulse |
| SPEC-015 | ADT Operational Center | APPROVED | OceanPulse |
| SPEC-016 | ADT Help & Principles Page | APPROVED | OceanPulse |
| SPEC-017 | ADT Framework Repository | APPROVED | OceanPulse |
| SPEC-018 | Phase 1 Hardening | APPROVED | ADT Framework |
| SPEC-019 | DTTP Standalone Service | APPROVED | ADT Framework (REQ-001) |
| SPEC-020 | Self-Governance Integrity | COMPLETED | ADT Framework |
| SPEC-021 | ADT Operator Console | ACTIVE | ADT Framework |
| SPEC-022 | Windows Ready Installer | DRAFT | ADT Framework |
| SPEC-023 | Git Governance | APPROVED | ADT Framework |
| SPEC-024 | ADT Connect (Remote Access) | DRAFT | ADT Framework |
| SPEC-025 | Collaborative Bootstrap | APPROVED | ADT Framework |
| SPEC-026 | DTTP Governance Configurator | COMPLETED | ADT Framework |
| SPEC-027 | Shatterglass Protocol | APPROVED | ADT Framework |
| SPEC-028 | Hive Tracker Panel | COMPLETED | ADT Framework |
| SPEC-029 | Single-File Installer | APPROVED | ADT Framework |

> Specs SPEC-014 through SPEC-017 originated in OceanPulse `_cortex/specs/`.
> Specs SPEC-018+ are native to the ADT Framework -- the framework is now generating
> its own governance artifacts. Self-governance milestone reached.

## Implementation Order

```
SPEC-018 Phase A (Security)       DONE: path traversal, path matching
SPEC-018 Phase B (Architecture)   DONE: shared hash, hardcoded names, configs
SPEC-019 (DTTP Service)           DONE: standalone service, refactored integrations
SPEC-020 (Self-Governance)        DONE: tiered paths, break-glass, anti-self-mod
SPEC-021 (Operator Console)       DONE: Phases A-E, Hive View, Panel embed, UI polish
SPEC-025 (Collaborative Bootstrap) <- bootstrap.sh DONE, API endpoints + UI pending
SPEC-018 Phase C (Robustness)     <- Caching, locking, logging, validation
SPEC-018 Phase D (Confidence)     <- Test coverage expansion
SPEC-024 (ADT Connect)            <- Remote access via Cloudflare tunnels
SPEC-026 (Governance Configurator) <- Visual DTTP rule configuration UI
SPEC-027 (Shatterglass Protocol)    <- OS-level enforcement, privilege escalation
SPEC-022 (Windows Installer)      <- Inno Setup bundled distribution
```

## Version Roadmap

| Version | Milestone |
|---------|-----------|
| v0.1.0 | Core engines (ADS, SDD, DTTP) |
| v0.2.0 | Operational Center + Agent SDK + Self-Governance |
| v0.3.0 | Operator Console + Collaborative Bootstrap |
| v0.4.0 | *Driven by collaborator feedback from v0.3* |

## Role Assignments

* **Systems_Architect:** Specs, coordination, architectural decisions.
* **Backend_Engineer:** Flask app, API routes, DTTP engine, ADS engine.
* **Frontend_Engineer:** Operational Center UI, templates, Help page.
* **DevOps_Engineer:** DTTP privilege separation, Linux user setup, deployment.
* **Overseer:** ADS compliance, audit trail integrity.
