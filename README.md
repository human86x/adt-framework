# ADT Framework

**Advanced Digital Transformation -- Governance-Native AI Agent Management**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

---

## 1. What is ADT?

ADT (Advanced Digital Transformation) is a governance framework designed from the ground up for AI agent systems. It shifts governance upstream, embedding compliance, accountability, and auditability into the process of execution itself, rather than applying them after the fact as an overlay.

> "Digital transformation initiatives frequently fail not due to a lack of technology, but because governance is introduced too late, applied inconsistently or not applied at all—leaving organisations to confront complex, fragmented challenges without a coherent framework for accountability, coordination and control."
> -- Paul Sheridan, Director, ADT

### 1.1 The Problem
AI agents (Claude, Gemini, GPT, etc.) are increasingly used for real engineering work—writing code, deploying systems, managing infrastructure. However, traditional prompts and instructions rely on *behavioral compliance*. Agents can, and do, violate prompt instructions.

Without ADT:
- **Authorization** is voluntary.
- **Auditing** lacks a cryptographic, immutable record.
- **Enforcement** is circumventable.
- **Business Purpose** (the "Why") is disconnected from the technical action (the "How").

### 1.2 The Four Pillars (Evolved)
1. **Capability Governance:** Bridges the gap between strategy and execution. Captures high-level **Intents** and **Triggering Events** to provide causal traceability.
2. **DTTP Enforcement:** Structural enforcement of spec-authorized actions via OS-level privilege separation. Agents physically cannot bypass rules.
3. **Digital Black Box (ADS):** An immutable, SHA-256 hash-chained Authoritative Data Source (ADS) log providing a full causal traceability chain.
4. **Interactive Orchestration:** A bi-directional command center (Operator Console) for human-agent collaboration, real-time steering, and feedback.

---

## 2. Core Governance Mechanisms

### 2.1 Specification-Driven Development (SDD)
The fundamental rule of ADT is **"No Spec, No Code"**. Every technical change must trace to an approved specification. Only a human can approve a specification. If an agent attempts to act without an active, approved specification covering their role and target file, the action is blocked.

### 2.2 Authoritative Data Source (ADS) & Integrity Chain
The ADS (`events.jsonl`) is the single source of truth. It is an append-only log. Every ADS event contains a SHA-256 hash of the previous event, forming an unbroken, cryptographically verifiable chain. Any unauthorized modification to past events breaks the chain and is immediately flagged.

### 2.3 Tiered Path Protections
To prevent the framework from corrupting itself, all file paths are classified into three tiers:
- **Tier 1: Sovereign (Human-Only):** Config files, Constitution, and Master Plan. Proposal changes become **Sovereign Change Requests (SCR)** requiring explicit human authorization.
- **Tier 2: Constitutional (Elevated):** Core enforcement logic. Requires a dedicated hardening spec.
- **Tier 3: Operational (Standard):** Regular application code and assets.

---

## 3. Structural Enforcement (DTTP)

The Digital Transformation Transfer Protocol (DTTP) replaces honor-system prompts with **Level 3 OS-level privilege separation**.

### 3.1 Three-User Privilege Model
- **HUMAN (user `human`):** Full access. The root of trust. Approves specs and configures the forge.
- **AGENT (user `agent`):** Restricted user. Read-only access to the project. Network access (SSH/FTP) blocked. Must route all writes through the DTTP service.
- **DTTP (user `dttp`):** Privileged worker. Write access to the project. Validates agent requests, executes them, and logs them to the ADS atomically.

### 3.2 Multi-Project Isolation
- **Forge:** The ADT Framework itself. Possesses Tier 1/Tier 2 concepts and Shatterglass capabilities.
- **Governed (External Projects):** tenant projects (e.g., web apps). Operate strictly at Tier 3 with isolated `_cortex/` directories and DTTP instances.

---

## 4. ADT Command Line Interface (`adt`)

The framework includes a powerful CLI for managing governance and projects.

### 4.1 Quick Start
```bash
# Clone the repository
git clone https://github.com/human86x/adt-framework.git
cd adt-framework

# Install
./install.sh

# Initialize a project
adt init /path/to/your/project --detect
```

### 4.2 Core Commands
| Command | Description |
|---------|-------------|
| `adt init` | Scaffold governance in a new directory with auto-detection. |
| `adt projects list` | List all registered projects and their DTTP status. |
| `adt connect share` | Expose local instance via Cloudflare Tunnel for remote access. |
| `adt shatterglass` | Emergency privilege escalation for manual framework repair. |
| `adt tasks complete` | Mark a task as completed with evidence directly from CLI. |

---

## 5. Security & Defense in Depth

### 5.1 Agent Sandboxing
Agents are restricted via application-layer hook sandboxing and OS-level namespace isolation using `bwrap` (bubblewrap) to block unauthorized network egress and filesystem traversal.

### 5.2 The Shatterglass Protocol
A fail-safe mechanism for emergency maintenance. If DTTP breaks, the Human can activate Shatterglass to temporarily escalate OS privileges, bypass DTTP, and repair the framework. This mode is time-limited and mandates an audit.

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
│               DTTP Engine                 │  ← Structural Enforcement
│      (Privilege-Separated Gateway)        │
├──────────┬──────────┬──────────┬──────────┤
│ ADS      │ SDD      │ IoE      │ Intents  │  ← Core Modules
│ (Ledger) │ (Specs)  │ (Events) │ (Context)│
├──────────┴──────────┴──────────┴──────────┤
│                Agent SDK                  │  ← Client Library
│        (Claude, Gemini, any agent)        │
└───────────────────────────────────────────┘
```

---

## 7. Current Milestone: v0.4.0 (Capability & Orchestration)

- **Capability Governance (SPEC-038):** Strategic alignment through Intents and Triggering Events. Full traceability from business purpose to technical action.
- **Interactive Orchestration (SPEC-039):** Bi-directional human-agent communication. Real-time steering, task injection, and pulse feedback via the Operator Console.
- **Capability Governance UI (SPEC-040):** Redesigned Capabilities Tab and integrated Console Sidebar.

## 8. Proving Ground

ADT governs its own development -- recursive self-governance through structural enforcement. Every commit, spec, and task in this repository was mediated by ADT's own DTTP engine and logged to its own ADS.

ADT is also being proven through [OceanPulse](https://oceanpulse.pt) -- an autonomous marine monitoring buoy governed as an external project under ADT's multi-project isolation model.

## License
AGPL-3.0. See [LICENSE](LICENSE).

## Author
Paul Sheridan, Director, Advanced Digital Transformation (ADT)
Based on the ADT Whitepaper (Sheridan, 2026). See [docs/adt.pdf](docs/adt.pdf).
