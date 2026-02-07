# SPEC-016: ADT Help & Principles Page

**Status:** APPROVED
**Priority:** MEDIUM
**Owner:** Frontend_Engineer + Systems_Architect
**Created:** 2026-02-05
**References:** ADT Whitepaper (Sheridan, 2026), SPEC-003, SPEC-014, SPEC-015
**Location:** `adt_panel/about.html` (current), migrates to ADT Operational Center `/about` (SPEC-015)

---

## 1. Purpose

The ADT Help Page is the **public-facing explanation** of the ADT Framework as implemented in OceanPulse. It serves two audiences:

1. **External stakeholders** (Paul Sheridan, regulators, reviewers) -- understand what ADT is and how it's being proven in practice
2. **New team members / collaborating agents** -- understand the governance rules they operate under

The page must reflect the **full current state** of the ADT implementation: what exists, what's being integrated, and what's planned. It is a living document that evolves with the framework.

---

## 2. Content Structure

### 2.1 Section: What is ADT?

**Status: EXISTS** (update needed)

- Author: Paul Sheridan, Director, Advanced Digital Transformation (ADT)
- The problem (from whitepaper): "Digital transformation initiatives frequently fail not due to lack of technology, but because governance is applied after systems are operational."
- Core thesis: "ADT shifts governance upstream, embedding it into process creation so that compliance, accountability and auditability are properties of execution rather than downstream enforcement."
- UN governance principles: Direction, Performance, Accountability, Transparency, Legitimacy
- The Issues Taxonomy: reference Appendix A from the whitepaper -- the systemic scale of problems ADT addresses (Governance & Strategic Alignment, Process & Project Management, Technical & Systems Engineering, Risk & Compliance, People & Culture, Operational & Resource Management)
- Link to or summary of the ADT Whitepaper

### 2.2 Section: The Four Pillars

**Status: EXISTS** (update and expand)

Present the four key ADT components from the whitepaper:

| Pillar | What It Does | OceanPulse Implementation | Status |
|--------|-------------|--------------------------|--------|
| **SDD** (Specification-Driven Development) | No spec = no legitimate execution | `_cortex/specs/`, SPEC-000 through SPEC-016 | OPERATIONAL |
| **DTTP** (Digital Transformation Transfer Protocol) | Structural enforcement of spec-authorised actions | SPEC-014 + SPEC-015: privilege-separated Flask gateway | IN DEVELOPMENT |
| **Digital Black Box** | Immutable, auditable record of all actions | `events.jsonl`, SHA-256 hash chain, Safe Logger v3.0 | OPERATIONAL |
| **IoE** (Internet of Events) | Cross-system event capture and response | ADS event logging, narrative workflows | PARTIAL |

Each pillar gets its own expandable card with:
- Whitepaper definition (quoted)
- OceanPulse implementation details
- Current status (Operational / In Development / Planned)
- Visual indicator (green/amber/grey)

### 2.3 Section: The Authoritative Data Source (ADS)

**Status: EXISTS** (update needed)

- Single source of truth: `events.jsonl`
- Append-only: history is never modified
- "If an action is not recorded, it is not recognised as having occurred"
- Current stats: total events, agents, date range
- Link to ADS Timeline view in the panel

### 2.4 Section: Integrity Chain

**Status: EXISTS** (minor update)

- SHA-256 hash linking: every event contains hash of previous event
- Tamper detection: any modification breaks the chain
- Genesis block: the first event's prev_hash is all zeros
- Safe Logger v3.0: atomic locking (fcntl), schema validation, hash computation
- Real incident: chain break at line 114, detected and repaired (2026-02-05)

### 2.5 Section: Specification-Driven Development (SDD)

**Status: EXISTS as "Glossary entry"** (expand to full section)

- "No Spec, No Code" -- the fundamental rule
- Spec lifecycle: DRAFT → Human Approval → APPROVED → Active → Completed
- Spec tree: how specs relate (SPEC-000 → SPEC-004 → SPEC-005 through SPEC-012)
- Role of Systems_Architect: writes specs, does not implement
- Role of Human: approves specs, ultimate authority
- Real incident: Systems_Architect violation of Article II Section 2.1 (implemented before approval, caught by human, 2026-02-05)

### 2.6 Section: DTTP -- Structural Enforcement

**Status: NEW** (does not exist in current page)

- The three enforcement levels:
  - Level 1: Behavioural (prompt instructions) -- proven insufficient
  - Level 2: Hook-based (pre-action scripts) -- bypassable via Bash
  - Level 3: Privilege-separated (OS permissions + network rules) -- the target
- Three-user model: human / agent / dttp
- How it works: agents request actions via API, DTTP validates and executes
- No self-governance: DTTP enforces rules, doesn't define them
- Status: SPEC-014 approved, SPEC-015 designed, implementation in progress

### 2.7 Section: The ADT Operational Center

**Status: NEW**

- The ADT Framework incarnated as software
- Separate from the project it governs (court ≠ business)
- Flask application: human web UI + agent API + DTTP engine
- Public mirror: oceanpulse.pt as read-only governance display
- Multi-project capable: could govern any project
- Status: SPEC-015 designed, pending approval

### 2.8 Section: Roles & Jurisdiction

**Status: EXISTS as "Glossary"** (expand to full section)

- The Hivemind model: specialised roles with bounded jurisdiction
- Role table with jurisdiction paths
- Two agents: CLAUDE (Claude Code) and GEMINI (Gemini CLI)
- The Overseer: chronicler, ADS compiler, transparency guardian
- Jurisdiction enforcement: currently hook-based, migrating to DTTP (OS-level)

### 2.9 Section: Narrative Workflows

**Status: EXISTS** (keep as-is, minor updates)

- Causal chains: Intent → Action → Obstacle → Resolution
- How events are grouped into storylines
- Example workflow from real project history

### 2.10 Section: Real Incidents (Proving Ground Evidence)

**Status: NEW**

This is critical for the proving ground mission. Document real incidents that prove (or challenge) ADT:

| Date | Incident | ADT Response | What It Proved |
|------|----------|-------------|----------------|
| 2026-02-01 | ADS data loss (accidental overwrite) | Ledger Protocol implemented, Safe Logger v3.0 | Need for structural protection of ADS |
| 2026-02-03 | Pi 5 undervoltage, Arduino brownout | Escalation chain → human physical intervention | Escalation protocol works across physical/digital boundary |
| 2026-02-05 | ADS integrity chain broken at line 114 | Safe Logger v3.0 with atomic locking, chain healed | Hash chain detects tampering/corruption |
| 2026-02-05 | Architect violated SDD (implemented unapproved spec) | Human caught violation, logged to ADS | Behavioural compliance insufficient -- need DTTP |

### 2.11 Section: Glossary

**Status: EXISTS** (expand)

Updated glossary covering all ADT terms:
- ADS, SDD, DTTP, IoE, Digital Black Box
- Spec, Jurisdiction, Escalation, Lock Protocol
- Hash Chain, Integrity Violation, Safe Logger
- Fail-Closed, Privilege Separation, Shadow Mode
- Overseer, Chronicler, Hivemind

### 2.12 Section: Roadmap

**Status: NEW**

Visual timeline of ADT implementation progress:

```
COMPLETED                    IN PROGRESS              PLANNED
─────────                    ───────────              ───────
ADS Ledger ✓                 DTTP Engine              ADT Operational Center
SHA-256 Chain ✓              Privilege Separation     Multi-Project Support
Safe Logger v3.0 ✓           Credential Isolation     IoE Cross-System Events
SDD Enforcement ✓                                     Full Invocation Chaining
Enforcement Hooks ✓                                   Enterprise DTTP Network
ADT Static Panel ✓
Narrative Workflows ✓
```

---

## 3. Design Requirements

### 3.1 Visual Style

- Maintain current dark theme (#0d1117 background, #e6edf3 text)
- Use Bootstrap 5 cards with accordions for expandable sections
- Status indicators: green (operational), amber (in development), grey (planned)
- Whitepaper quotes in styled blockquotes
- Incident timeline with visual markers

### 3.2 Navigation

- Sticky sidebar or top nav with section links (for long page)
- "Back to Panel" link
- "Back to Dashboard" link (when ADT Operational Center exists)

### 3.3 Living Document Indicators

- Each section shows its status: CURRENT / NEEDS UPDATE / NEW
- Last updated timestamp
- Version number (v3.0 after this update)

---

## 4. Migration Path

### Phase 1 (Now): Update `adt_panel/about.html`

Update the existing static page with all new content. Deploy to oceanpulse.pt via FTP. This works under the current system.

### Phase 2 (After SPEC-015): Migrate to ADT Operational Center

The about page becomes `/about` in the Flask app. The static version on oceanpulse.pt continues as the public mirror copy.

---

## 5. Success Criteria

- [ ] All 12 sections present and accurate
- [ ] Whitepaper principles mapped to OceanPulse implementation
- [ ] Status indicators (operational/in-development/planned) are correct
- [ ] Real incidents documented with ADT response and lesson
- [ ] Glossary covers all ADT terms used in the project
- [ ] Page is accessible and readable for non-technical stakeholders
- [ ] Paul Sheridan can read this page and recognise his framework in action

---

## 6. Amendments

This spec may be amended as the ADT implementation evolves. All amendments logged to ADS with `spec_ref: SPEC-016`.

---

*"Transparency: Stakeholders operate from a single, verifiable source of truth."*
*-- ADT Framework (Sheridan, 2026)*
