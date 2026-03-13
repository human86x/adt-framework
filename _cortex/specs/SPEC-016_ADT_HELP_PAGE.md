# SPEC-016: ADT Help & Principles Page

**Status:** APPROVED
**Version:** 2.0
**Priority:** MEDIUM
**Owner:** Frontend_Engineer + Systems_Architect
**Created:** 2026-02-05
**Updated:** 2026-03-09
**References:** ADT Whitepaper (Sheridan, 2026), SPEC-015, SPEC-017, SPEC-038, SPEC-039
**Location:** `adt_center/templates/about.html` (Flask route: `/about`)

---

## 1. Purpose

The ADT Help Page is the **public-facing explanation** of the ADT Framework. It serves two audiences:

1. **External stakeholders** (regulators, reviewers, adopters) -- understand what ADT is and how it works
2. **New team members / collaborating agents** -- understand the governance rules they operate under

The page reflects the **full current state** of the ADT Framework as a standalone, self-governing system. It is a living document that evolves with the framework.

> **v2.0 Note:** This spec was rewritten to reflect the ADT Framework's migration from OceanPulse-specific to a standalone, project-agnostic governance system (completed under SPEC-017). All OceanPulse-specific language has been removed.

---

## 2. Content Structure

The page is organized into sections accessible via a sticky sidebar navigation. Each section displays a status badge (CURRENT / OPERATIONAL / EVOLVED).

### 2.1 Section: What is ADT?

**Status: IMPLEMENTED**

- Author: Paul Sheridan, Director, Advanced Digital Transformation (ADT)
- Core problem (from whitepaper): "Digital transformation initiatives frequently fail not due to a lack of technology, but because governance is introduced too late, applied inconsistently or not applied at all—leaving organisations to confront complex, fragmented challenges without a coherent framework for accountability, coordination and control."
- Core thesis: ADT shifts governance upstream, embedding it into process creation
- UN governance principles: Direction, Performance, Accountability, Transparency, Legitimacy
- The Issues Taxonomy: reference Appendix A from the whitepaper

### 2.2 Section: The Four Pillars (Evolved)

**Status: IMPLEMENTED**

The original four pillars have evolved into five pillars reflecting the framework's maturity:

| Pillar | What It Does | Implementation | Status |
|--------|-------------|----------------|--------|
| **Capability Governance** | Organisational context -- the "Why" | SPEC-038: intents.jsonl, capability_events.jsonl | OPERATIONAL |
| **DTTP** | Structural enforcement of spec-authorised actions | SPEC-014, SPEC-019, SPEC-036 (Sandbox) | OPERATIONAL |
| **Digital Black Box** | Immutable, hash-chained causal traceability | events.jsonl, SHA-256 Integrity Chain | OPERATIONAL |
| **Interactive Orchestration** | Bi-directional human-agent command center | SPEC-039: Operator Console, PTY Injection | OPERATIONAL |
| **SDD** | No spec = no legitimate execution | `_cortex/specs/`, SPEC lifecycle | OPERATIONAL |

Each pillar is presented as an expandable accordion card with implementation details.

### 2.3 Section: Capability Governance (SPEC-038)

**Status: IMPLEMENTED**

- Bridges organisational strategy and technical execution
- Intents: desired outcomes
- Events: triggering occurrences
- Maturity: real-time tracking across 7 stages
- Full causal chain: Intent -> Trigger -> Spec -> Task -> Action -> Verification

### 2.4 Section: Authoritative Data Source (ADS)

**Status: IMPLEMENTED**

- Single source of truth: `_cortex/ads/events.jsonl`
- Append-only: history is never modified
- "If an action is not recorded, it is not recognised as having occurred"
- Current stats: total events, agents, date range
- Link to ADS Timeline view in the Operational Center

### 2.5 Section: Integrity Chain

**Status: IMPLEMENTED**

- SHA-256 hash linking: every event contains hash of previous event
- Tamper detection: any modification breaks the chain
- Genesis block: first event's prev_hash is all zeros
- Safe Logger v3.0: atomic locking (fcntl), schema validation, hash computation

### 2.6 Section: Specification-Driven Development (SDD)

**Status: IMPLEMENTED**

- "No Spec, No Code" -- the fundamental rule
- Spec lifecycle: DRAFT -> Human Approval -> APPROVED -> Active -> COMPLETED
- Role of Systems_Architect: writes specs, does not implement
- Role of Human: approves specs, ultimate authority

### 2.7 Section: DTTP -- Structural Enforcement

**Status: IMPLEMENTED**

- Three enforcement levels:
  - Level 1: Behavioural (prompt instructions) -- proven insufficient
  - Level 2: Hook-based (pre-action scripts) -- bypassable via Bash
  - Level 3: Privilege-separated (OS permissions + network rules) -- the target
- Three-user model: human / agent / dttp
- How it works: agents request actions via API, DTTP validates and executes
- Agent Filesystem Sandbox (SPEC-036): bwrap/unshare isolation

### 2.8 Section: Interactive Orchestration (SPEC-039)

**Status: IMPLEMENTED**

- Governance Zoom: hierarchical visualization from Intent down to Task
- Human Steering: real-time prioritization and command injection via PTY
- Thinking Feedback: visual pulses synchronized with agent tool-calls
- ADS Pulse Synchronization: real-time event-to-UI mapping

### 2.9 Section: The ADT Operational Center

**Status: IMPLEMENTED**

- The ADT Framework incarnated as software
- Flask application: human web UI + agent API + DTTP engine
- Dashboard, ADS Timeline, Spec Registry, Task Board, DTTP Monitor, Governance Configurator
- Multi-project capable via External Project Governance (SPEC-031)

### 2.10 Section: External Project Governance

**Status: IMPLEMENTED**

- ADT can govern any project, not just itself
- Multi-project registry with independent `_cortex/` directories
- Project isolation: each project gets its own ADS, specs, tasks, and jurisdictions

### 2.11 Section: Sovereign Change Requests (SCR)

**Status: IMPLEMENTED**

- Sovereign paths contain the rules of the framework (AI_PROTOCOL.md, MASTER_PLAN.md, config/*.json)
- No agent can modify them directly
- DTTP blocks sovereign writes and auto-submits SCRs for human authorization
- Implementation: SPEC-033

### 2.12 Section: Shatterglass Protocol

**Status: IMPLEMENTED**

- Emergency override for critical situations
- Break-glass mechanism with full ADS audit trail
- Implementation: SPEC-027

### 2.13 Section: Roles & Jurisdiction

**Status: IMPLEMENTED**

- The Hivemind model: specialised roles with bounded jurisdiction
- Role table with jurisdiction paths:
  - Systems_Architect: `_cortex/`, `docs/`
  - Backend_Engineer: `adt_core/`, `adt_center/api/`, `adt_sdk/`
  - Frontend_Engineer: `adt_center/templates/`, `adt_center/static/`, `adt-console/src/`
  - DevOps_Engineer: `ops/`, `.github/`, `.claude/`, `adt-console/src-tauri/`
  - Overseer: `_cortex/ads/`, compliance audits
- Two agents: CLAUDE (Claude Code) and GEMINI (Gemini CLI)
- Jurisdiction enforcement: DTTP + hook-based (migrating to full OS-level)

### 2.14 Section: Real Incidents

**Status: IMPLEMENTED**

Document real incidents that prove (or challenge) ADT governance. Should be maintained as significant new incidents occur.

### 2.15 Section: Glossary

**Status: IMPLEMENTED**

Covers all ADT terms: ADS, SDD, DTTP, IoE, Digital Black Box, Spec, Jurisdiction, Escalation, Hash Chain, Integrity Violation, Safe Logger, Fail-Closed, Privilege Separation, Overseer, Chronicler, Hivemind, SCR, Shatterglass, Capability, Intent, Triggering Event.

### 2.16 Section: Roadmap

**Status: IMPLEMENTED**

Three-column layout showing:

**Completed:** ADS Ledger & Integrity Chain, DTTP Standalone Service, Operator Console (Tauri), External Project Governance, Sovereign Change Requests, Shatterglass Protocol, Capability Governance (SPEC-038), Interactive Orchestration (SPEC-039)

**In Progress:** Agent Sandbox (Namespace Level), Collaborative Bootstrap V2, Windows MSI Distribution

**Planned:** Enterprise DTTP Network, Advanced Visual Analytics, Sovereign DAO Integration

---

## 3. Design Requirements

### 3.1 Visual Style

- Dark theme consistent with Operational Center (`base.html` template)
- Bootstrap 5 cards with accordions for expandable sections
- Status badges: green (OPERATIONAL/CURRENT), amber (IN PROGRESS), grey (PLANNED)
- Whitepaper quotes in styled blockquotes with accent border

### 3.2 Navigation

- Sticky sidebar with section links (col-lg-3)
- Main content area (col-lg-9)
- Extends `base.html` with full Operational Center navigation

### 3.3 Living Document Indicators

- Each section shows its status badge
- Content updated as specs are completed or milestones reached

---

## 4. Success Criteria

- [x] All sections present and accurate
- [x] Whitepaper principles mapped to framework implementation
- [x] Status indicators reflect current reality
- [x] Page is accessible and readable for non-technical stakeholders
- [x] No OceanPulse-specific references remain
- [x] Integrated into Flask Operational Center at `/about`
- [ ] Real incidents section expanded beyond initial 4 incidents
- [ ] Glossary kept current with new terms from v0.4.0+ specs

---

## 5. Amendment History

| Date | Version | Change |
|------|---------|--------|
| 2026-02-05 | 1.0 | Initial spec (OceanPulse context) |
| 2026-03-09 | 2.0 | Full rewrite for standalone ADT Framework. Removed all OceanPulse references. Updated to reflect v0.4.0 milestone. Aligned with actual about.html implementation. Expanded from 12 to 16 sections. |

---

*"Transparency: Stakeholders operate from a single, verifiable source of truth."*
*-- ADT Framework (Sheridan, 2026)*
