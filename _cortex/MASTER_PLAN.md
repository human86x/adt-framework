# ADT Framework: Master Plan

**Phase:** 1.5 (Hardening + Service Extraction)
**Status:** Active Development
**Task Tracking:** See `_cortex/tasks.json`
**Parent Spec:** SPEC-017 (from OceanPulse proving ground)

## Mission

Build the ADT Framework as a standalone, open-source governance system for AI agents.
OceanPulse is the first governed project (reference implementation).

## Current Objectives

1. **ADS Engine:** Extract and generalize Safe Logger from OceanPulse. (Status: COMPLETED)
2. **SDD Engine:** Spec lifecycle management. (Status: COMPLETED)
3. **DTTP Engine:** Privilege-separated enforcement gateway. (Status: COMPLETED)
4. **Operational Center:** Flask web app -- human UI + agent API. (Status: COMPLETED)
5. **Agent SDK:** Client library for AI agents. (Status: COMPLETED)
6. **Phase 1 Hardening:** Security fixes, deduplication, config population. (Status: COMPLETED — SPEC-018)
7. **DTTP Standalone Service:** Standalone HTTP service on :5002. (Status: COMPLETED — SPEC-019)
8. **Self-Governance Integrity:** Tiered path protection, break-glass, anti-self-modification. (Status: PENDING — SPEC-020)

## Active Specifications

| Spec | Name | Status | Origin |
|------|------|--------|--------|
| SPEC-014 | DTTP Implementation (Level 3) | APPROVED | OceanPulse |
| SPEC-015 | ADT Operational Center | APPROVED | OceanPulse |
| SPEC-016 | ADT Help & Principles Page | APPROVED | OceanPulse |
| SPEC-017 | ADT Framework Repository | APPROVED | OceanPulse |
| SPEC-018 | Phase 1 Hardening | APPROVED | ADT Framework |
| SPEC-019 | DTTP Standalone Service | APPROVED | ADT Framework (REQ-001) |
| SPEC-020 | Self-Governance Integrity | DRAFT | ADT Framework |

> Specs SPEC-014 through SPEC-017 originated in OceanPulse `_cortex/specs/`.
> Specs SPEC-018+ are native to the ADT Framework — the framework is now generating
> its own governance artifacts. Self-governance milestone reached.

## Implementation Order

```
SPEC-018 Phase A (Security)     ✓ DONE: path traversal, path matching
SPEC-018 Phase B (Architecture) ✓ DONE: shared hash, hardcoded names, configs
SPEC-019 (DTTP Service)         ✓ DONE: standalone service, refactored integrations
SPEC-020 (Self-Governance)      ← NEXT: tiered paths, break-glass, anti-self-mod
SPEC-018 Phase C (Robustness)   ← Caching, locking, logging, validation
SPEC-018 Phase D (Confidence)   ← Test coverage expansion
SPEC-016 (Help Page)            ← task_005, pending Frontend_Engineer
```

## Role Assignments

* **Systems_Architect:** Specs, coordination, architectural decisions.
* **Backend_Engineer:** Flask app, API routes, DTTP engine, ADS engine.
* **Frontend_Engineer:** Operational Center UI, templates, Help page.
* **DevOps_Engineer:** DTTP privilege separation, Linux user setup, deployment.
* **Overseer:** ADS compliance, audit trail integrity.
