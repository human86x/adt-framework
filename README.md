# ADT Framework

**Advanced Digital Transformation — Governance for a Trustworthy AI Future**
◆ *Scaling intelligence, preserving human authority* ◆

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

---

## 1. What is ADT?

Advanced Digital Transformation (ADT) is a **governance-native framework** for AI-agent systems. Rather than wrapping AI in policies, prompts or after-the-fact monitoring, ADT builds human authority and systemic control directly into the architecture — through external orchestration, mechanical execution control, living standards and coherent multi-agent state.

> Governance *around* AI asks it to behave responsibly. Governance *within* the architecture controls what it is permitted to do.

The result is a system in which **the intelligence can change without changing the governance**. Whatever AI model or harness comes next — Claude, Antigravity, anything else — the specifications, standards, authorised system state and evidence of execution remain outside the model and under human authority.

As Paul Sheridan, Director of ADT, observes:

> *"Digital transformation initiatives frequently fail not due to a lack of technology, but because governance is introduced too late, applied inconsistently, or not applied at all — leaving organisations to confront complex, fragmented challenges without a coherent framework for accountability, coordination and control."*

Founded in 1980 as an information systems engineering consultancy, ADT has evolved with applied computer science toward a single aim: to maximise technology's benefits through engineering discipline, governance and responsible innovation.

---

## 2. Three Dimensions of Governance

ADT brings together three complementary dimensions. The **Five Outcomes** define WHAT effective governance should achieve. The **Seven Stages** define HOW human intent progresses to governed execution. The **Five Pillars** — jointly the **Capability Governance Architecture (CGA)** — provide the technical mechanisms that make the whole thing enforceable, traceable and auditable.

### 2.1 Five Outcomes

1. **Direction**
2. **Performance**
3. **Accountability**
4. **Transparency**
5. **Legitimacy**

These are not aspirations or post-hoc checks. They are properties the architecture must actively support. Where a governance approach leaves any of them materially unaddressed, the resulting agent system has a corresponding governance weakness.

### 2.2 Seven Stages

A continuous chain from human intent to autonomous delivery:

1. **Human intent** — an operator defines the desired outcome in natural language.
2. **Specification** — ADT translates intent into a governing specification.
3. **Standards alignment** — relevant standards, regulations and requirements are identified and presented for consideration and adoption.
4. **Decomposition** — approved intent is transformed into role-scoped specifications and executable tasks.
5. **Governed execution** — AI agents operate within defined roles, permissions and transfer-control boundaries.
6. **Traceability** — every action remains accountable and auditable, traceable back to approved intent and specifications.
7. **Autonomous delivery** — AI agents can design, build and operate systems without requiring humans to write the underlying code, while remaining subject to the specifications, permissions and controls established by the framework.

### 2.3 Five Pillars — Capability Governance Architecture (CGA)

The Five Pillars are the technical mechanisms through which the Seven-Stage governance model is enforced and evidenced in execution. Together they form the **Capability Governance Architecture (CGA)**.

- **Authoritative Data Source (ADS)** — the append-only, SHA-256-chained event ledger. Every significant state change and agent action is captured, creating an evidence trail through which outcomes can be traced back from execution, through specifications, to the approved intent.
- **Specification-Driven Development (SDD)** — a strict *"no spec, no code"* discipline. Every technical change must be covered by an approved specification before execution; agents cannot generate or modify code outside an authorised scope.
- **Digital Transformation Control Protocol (DTCP)** — a privilege-separated enforcement mechanism that validates agent actions against role jurisdiction, specification authorisation and tiered protections in real time. Unauthorised actions are **denied, not merely logged**.
- **Agent Isolation** — separates agents from protected systems through controlled execution environments and restricted resource access, preventing direct modification of protected files, systems or configurations and containing the effects of errors or unintended actions.
- **Standards Layer** — the principles, obligations and governance requirements adopted by the organisation. Incorporates external standards (OECD AI Principles, EU AI Act, ISO/IEC 42001, NIST AI-RMF, UNESCO AI Ethics, COBIT, ITIL), internal policies, and documented decisions explaining adoption, adaptation and rationale.

Together, these mechanisms form a coherent governance architecture in which **intent, specification, authority, execution and evidence remain connected**.

### 2.4 Configurable Roles

Work is organised around configurable, structurally enforced roles. Each project defines its own roles and jurisdictions to match its domain — a software project might use Engineers, Architects and DevOps; a publishing project might define Editors, Writers and Designers. What remains constant is the enforcement model: every role operates within a defined jurisdiction enforced by DTCP. An agent cannot act outside its boundaries, regardless of the domain.

The ADT Framework itself — which governs its own development — uses the following roles:

- **Systems Architect** — defines system design, specifications, and technical strategy.
- **Frontend Engineer** — designs and develops user interfaces and governance dashboards.
- **Backend Engineer** — builds and maintains the engines, APIs and enforcement pipelines.
- **DevOps Engineer** — manages deployment, automation and agent sandboxing.
- **Overseer** — governance monitoring and compliance validation.

---

## 3. Structural Enforcement

DTCP replaces honour-system prompts with **OS-level privilege separation**.

### 3.1 Three-User Privilege Model

- **HUMAN (`human`)** — full access; root of trust. Approves specs and configures the forge.
- **AGENT (`agent`)** — restricted OS user. Read-only project access. Must route all writes through the DTCP service.
- **DTCP (`dtcp`)** — privileged worker. Validates agent requests, executes authorised ones, and logs each atomically to the ADS.

### 3.2 Tiered Path Protections

- **Tier 1 — Sovereign (human-only):** Config, Constitution, Master Plan. Changes go through **Sovereign Change Requests (SCR)** requiring explicit human authorisation.
- **Tier 2 — Constitutional (elevated):** Core enforcement logic. Requires dedicated hardening spec.
- **Tier 3 — Operational (standard):** Application code and assets.

### 3.3 Multi-Project Isolation

- **Forge:** the ADT Framework itself. Tier 1/Tier 2 protections and Shatterglass emergency override.
- **Governed (External Projects):** tenant projects — web apps, embedded systems, publishing workflows. Operate at Tier 3 with isolated `_cortex/` directories and DTCP instances.

---

## 4. Command Line Interface (`adt`)

### 4.1 Quick Start

```bash
git clone https://github.com/human86x/adt-framework.git
cd adt-framework
./install.sh

# Initialise a project
adt init /path/to/your/project --detect
```

### 4.2 Core Commands

| Command | Description |
|---------|-------------|
| `adt init` | Scaffold governance in a new directory with auto-detection. |
| `adt projects list` | List all registered projects and their DTCP status. |
| `adt connect share` | Expose local instance via Cloudflare Tunnel for remote access. |
| `adt shatterglass` | Emergency privilege escalation for manual framework repair. |
| `adt tasks complete` | Mark a task as completed with evidence from CLI. |

---

## 5. Security & Defence in Depth

### 5.1 Agent Sandboxing

Agents are restricted via application-layer hook sandboxing and OS-level namespace isolation using `bwrap` (bubblewrap) to block unauthorised network egress and filesystem traversal. This is the operational instantiation of the **Agent Isolation** pillar.

### 5.2 The Shatterglass Protocol

A fail-safe for emergency maintenance. If DTCP itself breaks, the human can activate Shatterglass to temporarily bypass DTCP and repair the framework. The window is time-limited and every action within it is logged with elevated visibility.

---

## 6. Architecture

```
┌───────────────────────────────────────────┐
│           ADT Operator Console            │  ← Human Command Center
│          (Tauri Desktop / PTY)            │
└────────┬──────────────────────────┬───────┘
         │                          │
┌────────▼──────────────────────────▼───────┐
│           ADT Operational Center          │  ← Strategic Management
│            (Flask Web / API)              │
├───────────────────────────────────────────┤
│               DTCP Engine                 │  ← Structural Enforcement
│      (Privilege-Separated Gateway)        │
├──────────┬──────────┬──────────┬──────────┤
│ ADS      │ SDD      │ Agent    │ Standards│  ← Capability Governance
│ (Ledger) │ (Specs)  │ Isolation│ Layer    │     Architecture (CGA)
├──────────┴──────────┴──────────┴──────────┤
│                Agent SDK                  │  ← Client Library
│   (Claude, Antigravity, any harness)      │
└───────────────────────────────────────────┘
```

---

## 7. Open and Accessible

ADT is licensed under **AGPL-3.0**, making governed AI freely accessible to individuals and organisations of any size. The framework provides the governance foundation, technical architecture and reference implementations needed for transparent evaluation, collaborative development and responsible adoption.

The current release establishes an operational framework while inviting community engagement and feedback. Performance and optimisation will continue to evolve as the platform develops.

## 8. Proving Ground

ADT governs its own development — **recursive self-governance through structural enforcement**. Every commit, spec and task in this repository was mediated by ADT's own DTCP engine and logged to its own ADS.

ADT is also being proven through [OceanPulse](https://oceanpulse.pt) — an autonomous marine monitoring buoy governed as an external project under ADT's multi-project isolation model.

---

## 9. Industry 6.0

If continued research and large-scale deployment validate the architecture, ADT has the potential to become a foundational enabling technology for **Industry 6.0** — an industrial evolution defined not simply by autonomous intelligence, but by autonomous intelligence operating within transparent, accountable and human-governed boundaries.

| Era | Definition |
|-----|-----------|
| Industry 1.0 | Mechanisation through water and steam power. |
| Industry 2.0 | Electrification and mass production. |
| Industry 3.0 | Computing, electronics and automation. |
| Industry 4.0 | Connected digital systems, cyber-physical systems, IIoT. |
| Industry 5.0 | Human-centric, sustainable and resilient industry. |
| **Industry 6.0** | **Greater capability through governance embedded in autonomous systems.** |

Industry 6.0 begins when governance becomes embedded in increasingly autonomous systems, enabling greater capability while keeping their purpose and operation aligned with human values.

---

## License

AGPL-3.0. See [LICENSE](LICENSE).

## Author

Paul Sheridan, Director, Advanced Digital Transformation (ADT).
Based on the ADT Whitepaper (Sheridan, 2026). See [docs/adt.pdf](docs/adt.pdf).

For the authoritative framework description, see [`_cortex/docs/ADT_FRAMEWORK_OVERVIEW.md`](./_cortex/docs/ADT_FRAMEWORK_OVERVIEW.md).
