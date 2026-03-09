# ADT Framework: Manual & Principles

**Advanced Digital Transformation -- Governance-Native AI Agent Management**

---

## 1. What is ADT?

ADT (Advanced Digital Transformation) shifts governance upstream, embedding it into process creation so that compliance, accountability, and auditability are properties of execution rather than downstream enforcement.

> "Digital transformation initiatives frequently fail not due to lack of technology, but because governance is applied after systems are operational."
> -- Paul Sheridan, Director, ADT

The framework aligns with UN governance principles: **Direction**, **Performance**, **Accountability**, **Transparency**, and **Legitimacy**.

---

## 2. The Four Pillars (Evolved)

| Pillar | Description | Implementation |
|--------|-------------|----------------|
| **Capability Governance** | Bridges the gap between strategy and execution. Captures high-level **Intents** and **Triggering Events** to provide the "Why" behind every change. | SPEC-038 |
| **DTTP Enforcement** | Structural enforcement of spec-authorised actions via OS-level privilege separation. Agents cannot bypass rules. | SPEC-014, SPEC-019 |
| **Digital Black Box** | Immutable, SHA-256 hash-chained ADS log providing a full **Causal Traceability** chain. | events.jsonl |
| **Interactive Orchestration** | Bi-directional command center for human-agent collaboration. Real-time steering and feedback. | SPEC-039 |

---

## 3. Core Concepts

### 3.1 Authoritative Data Source (ADS)
The ADS is the single source of truth: `events.jsonl`. It is append-only — history is never modified. If an action is not recorded in the ADS, it is not recognised as having occurred.

### 3.2 Integrity Chain
Every ADS event contains the SHA-256 hash of the previous event, forming an unbroken chain from genesis to present. Any modification to past events breaks the chain and is immediately detected.

### 3.3 Specification-Driven Development (SDD)
**"No Spec, No Code"** — the fundamental rule. Every action must trace to an approved specification. Only a human can approve a spec.

### 3.4 DTTP (Transfer Protocol)
Structural enforcement via the Digital Transformation Transfer Protocol. The framework uses a three-user model (Human / Agent / DTTP) to ensure agents can only modify files through the governed gateway.

---

## 4. Roles & Jurisdictions

Jurisdiction is structurally enforced. Attempting to act outside your role will result in a DTTP denial.

| Role | Focus | Jurisdiction |
|------|-------|--------------|
| **Systems_Architect** | Technical Strategy, Specs | `_cortex/`, specs, architecture |
| **Backend_Engineer** | Core Logic, API, Engines | `adt_core/`, `adt_center/app.py` |
| **Frontend_Engineer** | UI, Templates, Dashboards | `adt_center/templates/`, `static/` |
| **DevOps_Engineer** | Deployment, Security, PTY | `ops/`, Linux config, Tauri Rust |
| **Overseer** | Compliance, ADS Integrity | `_cortex/ads/`, audits |

---

## 5. Security Protocols

### 5.1 Sovereign Change Requests (SCR)
Sovereign paths (Constitution, Master Plan, Jurisdictions) are Tier 1 protected. No agent can modify them directly. Proposed changes are queued as SCRs for manual human authorization.

### 5.2 Shatterglass Protocol
A fail-safe mechanism for emergency maintenance. Allows a human to temporarily escalate OS privileges to repair the framework. Every session is time-limited and requires a mandatory audit.

### 5.3 Agent Sandboxing
Defense-in-depth isolation. Agents are restricted via application-layer sandboxing and OS-level namespaces (network/filesystem isolation).

---

## 6. Narrative Workflows
ADT events form a **causal chain**:
`Intent (Why) -> Event (Trigger) -> Spec (What) -> Task (How) -> Action (Execution) -> Verification (Outcome)`

By grouping events into storylines, the framework provides context to every technical change.

---

## 7. Roadmap (v0.4.0+)

*   **v0.4.0 (Active):** Capability Governance & Interactive Orchestration.
*   **v0.5.0 (Planned):** Enterprise DTTP (Distributed Enforcement), RBAC integration.
*   **v0.6.0 (Planned):** Advanced Visual Analytics & Impact Dashboards.
*   **v1.0.0:** Production Stable Release.

---

*"Governance is an intrinsic system property, not an external overlay."*
