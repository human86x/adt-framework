# ADT Framework

**Advanced Digital Transformation -- Governance-Native AI Agent Management**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

---

## What is ADT?

ADT (Advanced Digital Transformation) is a governance framework for AI agent systems. It shifts governance upstream -- embedding compliance, accountability, and auditability into the process of execution itself, rather than applying them after the fact.

> *"Digital transformation initiatives frequently fail not due to lack of technology, but because governance is applied after systems are operational."*
> -- ADT Whitepaper (Sheridan, 2026)

## The Problem

AI agents (Claude, Gemini, GPT, etc.) are increasingly used for real engineering work -- writing code, deploying systems, managing infrastructure. But:

- **Who authorises what an agent does?** Prompt instructions are voluntary. Agents can and do violate them.
- **Who audits what happened?** Without an immutable record, there is no accountability.
- **Who enforces the rules?** Behavioural compliance is insufficient. Structural enforcement is required.
- **What is the business purpose?** Technical changes often lack organizational context (the "Why").

## The Solution: Four Pillars (Evolved)

| Pillar | What It Does |
|--------|-------------|
| **Capability Governance** | Traceability from organizational **Intent** and **Triggering Events** to technical action. |
| **DTTP** (Transfer Protocol) | Structural enforcement via Level 3 OS-level privilege separation. |
| **Digital Black Box** (ADS) | Immutable, SHA-256 hash-chained audit trail of all intentions and actions. |
| **Interactive Orchestration** | Real-time human steering and hierarchical task visualization (Intent → Spec → Task). |

## Architecture

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

## Enforcement & Security

- **Level 3 Enforcement:** Agents run as restricted OS users. DTTP runs as a privileged user. Bypassing rules is structurally impossible.
- **Sovereign Change Requests (SCR):** High-risk framework changes require explicit human-in-the-loop authorization.
- **Shatterglass Protocol:** Time-limited, audited emergency maintenance mode.
- **Agent Sandboxing:** Filesystem and network isolation per session.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/human86x/adt-framework.git
cd adt-framework

# Install
./install.sh

# Govern a project
adt init /path/to/your/project
```

## Proving Ground

ADT is being proven through [OceanPulse](https://oceanpulse.pt) -- an autonomous marine monitoring buoy governed entirely by the ADT Framework. Real incidents, real enforcement, real lessons.

## License

AGPL-3.0. See [LICENSE](LICENSE).

## Author

Paul Sheridan, Director, Advanced Digital Transformation (ADT)

Based on the ADT Whitepaper (Sheridan, 2026). See [docs/whitepaper.md](docs/whitepaper.md).
