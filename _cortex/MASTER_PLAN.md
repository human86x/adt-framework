# ADT Framework: Master Plan

**Phase:** 1 (Core Build)
**Status:** Active Development
**Task Tracking:** See `_cortex/tasks.json`
**Parent Spec:** SPEC-017 (from OceanPulse proving ground)

## Mission

Build the ADT Framework as a standalone, open-source governance system for AI agents.
OceanPulse is the first governed project (reference implementation).

## Current Objectives

1. **ADS Engine:** Extract and generalize Safe Logger from OceanPulse. (Status: PENDING)
2. **SDD Engine:** Spec lifecycle management. (Status: PENDING)
3. **DTTP Engine:** Privilege-separated enforcement gateway. (Status: PENDING)
4. **Operational Center:** Flask web app -- human UI + agent API. (Status: PENDING)
5. **Agent SDK:** Client library for AI agents. (Status: PENDING)

## Active Specifications

| Spec | Name | Status | Origin |
|------|------|--------|--------|
| SPEC-014 | DTTP Implementation (Level 3) | APPROVED | OceanPulse |
| SPEC-015 | ADT Operational Center | APPROVED | OceanPulse |
| SPEC-016 | ADT Help & Principles Page | APPROVED | OceanPulse |
| SPEC-017 | ADT Framework Repository | APPROVED | OceanPulse |

> Specs originated in OceanPulse `_cortex/specs/`. Copies maintained here for
> engineer reference. Canonical versions remain in OceanPulse until ADT
> becomes self-governing (SPEC-017 Phase 5).

## Role Assignments

* **Systems_Architect:** Specs, coordination, architectural decisions.
* **Backend_Engineer:** Flask app, API routes, DTTP engine, ADS engine.
* **Frontend_Engineer:** Operational Center UI, templates, Help page.
* **DevOps_Engineer:** DTTP privilege separation, Linux user setup, deployment.
* **Overseer:** ADS compliance, audit trail integrity.
