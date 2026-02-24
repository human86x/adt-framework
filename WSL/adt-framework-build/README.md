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

## The Solution: Four Pillars

| Pillar | What It Does |
|--------|-------------|
| **SDD** (Specification-Driven Development) | No spec, no code. Every action must trace to an approved specification. |
| **DTTP** (Digital Transformation Transfer Protocol) | Structural enforcement via OS-level privilege separation. Agents cannot bypass rules. |
| **Digital Black Box** | Immutable, SHA-256 hash-chained audit trail. If it's not recorded, it didn't happen. |
| **IoE** (Internet of Events) | Cross-system event capture and causal chain tracking. |

## Architecture

```
┌─────────────────────────────────────┐
│         ADT Operational Center      │  ← Human Web UI
│         (Flask Application)         │
├─────────────────────────────────────┤
│              DTTP Engine            │  ← Structural Enforcement
│     (Privilege-Separated Gateway)   │
├──────────┬──────────┬───────────────┤
│ ADS      │ SDD      │ IoE           │  ← Core Modules
│ (Ledger) │ (Specs)  │ (Events)      │
├──────────┴──────────┴───────────────┤
│           Agent SDK                 │  ← Client Library
│   (Claude, Gemini, any agent)       │
└─────────────────────────────────────┘
```

## Three Enforcement Levels

| Level | Mechanism | Strength |
|-------|-----------|----------|
| Level 1 | Prompt instructions | Voluntary -- agents can ignore |
| Level 2 | Hook scripts | Bypassable via shell commands |
| **Level 3** | **OS privilege separation** | **Structural -- impossible to bypass** |

ADT targets Level 3: agents run as a restricted OS user, DTTP runs as a privileged user. Agents request actions through the DTTP API -- they cannot act directly.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/YOUR_ORG/adt-framework.git
cd adt-framework

# Install
pip install -e .

# Govern a project
adt init /path/to/your/project
```

*Full documentation: [docs/getting-started.md](docs/getting-started.md)*

## Proving Ground

ADT is being proven through [OceanPulse](https://oceanpulse.pt) -- an autonomous marine monitoring buoy governed entirely by the ADT Framework. Real incidents, real enforcement, real lessons.

## License

AGPL-3.0. See [LICENSE](LICENSE).

Commercial licensing available for enterprises requiring proprietary modifications or SLA support.

## Author

Paul Sheridan, Director, Advanced Digital Transformation (ADT)

Based on the ADT Whitepaper (Sheridan, 2026). See [docs/whitepaper.md](docs/whitepaper.md).
