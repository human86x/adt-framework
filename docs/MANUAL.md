# ADT Framework: Comprehensive Reference Manual

**Advanced Digital Transformation -- Governance-Native AI Agent Management**

---

## 1. Introduction & Philosophy

### 1.1 What is ADT?
ADT (Advanced Digital Transformation) is a governance framework designed from the ground up for AI agent systems. It shifts governance upstream, embedding compliance, accountability, and auditability into the process of execution itself, rather than applying them after the fact as an overlay.

> "Digital transformation initiatives frequently fail not due to lack of technology, but because governance is applied after systems are operational."
> -- Paul Sheridan, Director, ADT

### 1.2 The Problem with AI Agents
AI agents (Claude, Gemini, GPT, etc.) are increasingly used for real engineering work—writing code, deploying systems, managing infrastructure. However, traditional prompts and instructions rely on *behavioral compliance*. Agents can, and do, violate prompt instructions.

Without ADT:
- **Authorization** is voluntary.
- **Auditing** lacks a cryptographic, immutable record.
- **Enforcement** is circumventable.
- **Business Purpose** (the "Why") is disconnected from the technical action (the "How").

### 1.3 The Four Pillars (Evolved)
1. **Capability Governance:** Bridges the gap between strategy and execution. Captures high-level **Intents** and **Triggering Events** to provide causal traceability.
2. **DTTP Enforcement:** Structural enforcement of spec-authorized actions via OS-level privilege separation. Agents physically cannot bypass rules.
3. **Digital Black Box (ADS):** An immutable, SHA-256 hash-chained Authoritative Data Source (ADS) log providing a full causal traceability chain.
4. **Interactive Orchestration:** A bi-directional command center (Operator Console) for human-agent collaboration, real-time steering, and feedback.

---

## 2. Core Governance Mechanisms

### 2.1 Specification-Driven Development (SDD)
The fundamental rule of ADT is **"No Spec, No Code"**. Every technical change must trace to an approved specification. Only a human can approve a specification. If an agent attempts to act without an active, approved specification covering their role and target file, the action is blocked.

### 2.2 Authoritative Data Source (ADS) & Integrity Chain
The ADS (`events.jsonl`) is the single source of truth. It is an append-only log. If an action is not recorded in the ADS, it is not recognized as having occurred. Every ADS event contains a SHA-256 hash of the previous event. This forms an unbroken, cryptographically verifiable chain from genesis to present. Any unauthorized modification to past events breaks the chain and is immediately flagged by the **Overseer** role.

### 2.3 Tiered Path Protections
To prevent the framework from corrupting itself (e.g., an agent rewriting its own governance rules), all file paths are classified into three tiers:

- **Tier 1: Sovereign (Human-Only):** Config files (`jurisdictions.json`, `specs.json`), the Constitution (`AI_PROTOCOL.md`), and the Master Plan. These are never directly modifiable by agents. Any agent proposal here becomes a **Sovereign Change Request (SCR)** requiring explicit human UI authorization.
- **Tier 2: Constitutional (Elevated Authorization):** Core enforcement logic (`gateway.py`, `policy.py`). Modifying these requires a dedicated spec that explicitly lists the file and includes a `tier2_justification`.
- **Tier 3: Operational (Standard):** Regular application code, UI templates, tests. Governed by standard DTTP rules (spec approved, jurisdiction match).

---

## 3. Structural Enforcement (DTTP)

The Digital Transformation Transfer Protocol (DTTP) replaces honor-system prompts with **Level 3 OS-level privilege separation**.

### 3.1 Three-User Privilege Model
- **HUMAN (user `human`):** Full filesystem/network access. The root of trust. Approves specs and configures the forge. Launches agents as the restricted user.
- **AGENT (user `agent`):** Read-only access to the project. Network access (SSH/FTP) blocked by `iptables`. Cannot read credentials. Must route all writes through the DTTP service.
- **DTTP (user `dttp`):** Write access to the project. Owns credentials. Validates agent requests against specs/jurisdictions, executes them, and logs them to the ADS atomically. Fail-closed by default.

### 3.2 Multi-Project Isolation
The framework categorizes projects into two types:
- **Forge:** The ADT Framework itself. Possesses Tier 1/Tier 2 concepts, Sovereign Change Requests, and Shatterglass capabilities.
- **Governed (External Projects):** External tenant projects (e.g., web apps, APIs). These operate strictly at **Tier 3**. They have their own isolated `_cortex/` directories, their own DTTP instances on unique ports, and isolated ADS event streams.

---

## 4. Capability Governance & Stage Gates (SPEC-038)

ADT doesn't just track *what* changed; it tracks *why* it changed. All technical execution is traced back to a **Capability Change Intent**.

### 4.1 Triggering Events
Events are organizational occurrences that trigger evaluations:
- Innovation Hub Breakthrough
- Customer Signal
- Market Change
- Regulatory Trigger
- Risk Occurrence

### 4.2 The 7-Stage Evolution Workflow
Every Intent must pass through a 7-stage gate model before execution begins. Evaluated by human operators or steering committees:
1. **Validation & Classification**
2. **Concept Development / Prototyping**
3. **Strategic Feasibility Evaluation**
4. **Governance & Quality Review** (Triggers "Approved for Transformation")
5. **Portfolio Planning**
6. **Investment Decision**
7. **Transformation Initiation** (Triggers "In Transformation")

### 4.3 Maturity Scale
Capabilities are tracked along a 5-level maturity scale: `Initial` -> `Developing` -> `Defined` -> `Managed` -> `Optimised`.

---

## 5. Security & Defense in Depth

### 5.1 Agent Sandboxing
Defense-in-depth isolation ensures agents cannot execute arbitrary code outside their purview. This is achieved via application-layer hook sandboxing and OS-level namespace isolation using `bwrap` (bubblewrap) to block unauthorized network egress and filesystem traversal.

### 5.2 The Shatterglass Protocol
A fail-safe mechanism for emergency maintenance. If DTTP breaks and causes an enforcement deadlock, the Human can activate the Shatterglass Protocol to temporarily escalate OS privileges, bypass DTTP, and repair the framework. This mode is strictly time-limited and mandates an automatic Overseer audit upon completion.

### 5.3 Sovereign Change Requests (SCR)
If an agent detects a flaw in the governance model (e.g., a missing path in `jurisdictions.json`), they submit a `json_merge` or `patch` request via DTTP. DTTP detects the Tier 1 Sovereign path, blocks the write, and automatically generates an SCR in the ADT Operational Center for the Human to review and approve.

---

## 6. Roles & Jurisdictions

Jurisdictions dictate exactly which files and directories an agent is allowed to touch.

### 6.1 Forge Roles (Internal ADT Framework)
- **Systems_Architect:** Technical Strategy, Specs. Jurisdiction: `_cortex/`, specs, architecture.
- **Backend_Engineer:** Core Logic, API, Engines. Jurisdiction: `adt_core/`, `adt_center/app.py`.
- **Frontend_Engineer:** UI, Templates, Dashboards. Jurisdiction: `adt_center/templates/`, `static/`.
- **DevOps_Engineer:** Deployment, Security, PTY. Jurisdiction: `ops/`, Linux config, Tauri Rust.
- **Overseer:** Compliance, ADS Integrity. Jurisdiction: `_cortex/ads/`, audits.

### 6.2 Governed Project Roles
When running `adt init` on an external project, the framework auto-detects the project type (Python, Node, Rust, etc.) and suggests appropriate roles (e.g., `Backend_Developer`, `Frontend_Developer`) mapping to typical application structures.

---

## 7. Interactive Orchestration

The ADT Operator Console serves as a bi-directional command center.
- **Governance Zoom:** Hierarchical visualization from Organizational Intent down to Technical Task.
- **Human Steering:** Humans can inject `human_steering` events directly into the PTY stream of active agents, reprioritizing tasks or injecting context mid-execution.
- **Thinking Feedback:** The console UI pulses in real-time, synchronized with agent tool calls detected via the DTTP gateway.

---

## 8. Standard Workflow (`adt` CLI)

1. **Initialize a Project:**
   ```bash
   adt init /path/to/your/project --detect
   ```
   *Scaffolds the `_cortex` directory, auto-detects the tech stack, and sets up local DTTP config.*

2. **Start Services:**
   ```bash
   ./start.sh
   ```
   *Boots the ADT Operational Center (Web UI) and the DTTP Enforcement Gateways.*

3. **Launch the Console:**
   ```bash
   ./console.sh
   ```
   *Opens the Tauri-based ADT Operator Console for managing agent sessions.*

---

*"Governance is the process by which we ensure that the outcomes we create are the outcomes we intended."*
