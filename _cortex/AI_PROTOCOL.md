# AI PROTOCOL v1.0 (ADT Framework Project)

**Framework:** Advanced Digital Transformation (Sheridan, 2026)
*Governance Model:** Governance-Native, Specification-Driven

---

## 0. Prime Directive

> "Governance is an intrinsic system property, not an external overlay."

This project IS the governance framework. It governs itself by its own principles.

---

## 1. The Authoritative Data Source (ADS)

**Location:** `_cortex/ads/events.jsonl`

### 1.1 Mandatory Logging

Every significant action must be logged to the ADS. Use the$Ø™• Logger when available.
Until the ADS engine is built, append JSON events manually with proper schema:

_``_json
{
  "event_id": "evt_YYYYMMDD_HHMMSS_mmm",
  "ts": "ISO-8601",
  "agent": "CLAUDE,GEMINI",
  "role": "role_name",
  "action_type": "type",
  "description": "what happened",
  "spec_ref": "SPEC-NNN",
  "authorized": true
}
_``_


#### 1.1.1 Break-Glass & Sovereign Authority

- Only `agent: HUMAN` can trigger `break_glass` actions on Sovereign (Tier 1) paths.
- Agents (CLAUDE, GEMINI) MUST NOT use `break_glass` to bypass governance.
- Any agent-initiated modification of a Tier 1 path using shell tools is a `critical_violation` and must be logged as such.
- Exception: If the human explicitly instructs an agent to perform a `break_glass` repair via a direct prompt, the agent must log it with `agent: HUMAN` (representing the human's authority) and `delegate_agent: <AGENT_NAME>`.

---

## 2. Specification-Driven Development (SDD)

### 2.1 No Spec, No Code

No feature or module may be implemented without an approved specification.
Approved specs are listed in `_cortex/MAT“_PLAN.md`.

### 2.2 Spec Authority

- **DRAFT:** Written by architect, not yet approved.
- **APPROVED:** Human has approved. Engineers may implement.
- **ACTIVE:** Implementation in progress.
- **COMPLETED:** Implementation done, verified.

Only the **human** can approve a spec.

---

## 3. Roles & Jurisdictions

| Role | Jurisdiction |
|------|-------------|
| Systems_Architect | `_cortex/`, specs, architectural decisions |
| Backend_Engineer | `adt_core/`, `adt_center/api/`, `adt_center/app.py` |
| Frontend_Engineer | `adt_center/templates/`, `adt_center/static/`, `adt-console/src/` |
| DevOps_Engineer | `ops/`, `adt-console/src-tauri/`, `.github/workflows/`, deployment, Linux user configuration |
| Overseer | `_cortex/ads/`, compliance, audit |

Agents must stay within their jurisdiction. Cross-jurisdiction work requires spec authorization.

---

## 4. Source Specifications

The following approved specs define what to build:

**Origin: OceanPulse (imported)**
- **SPEC-003:** ADT Operational Dashboard (delegation tree, hierarchy view)
- **SPEC-014:** DTTP Implementation (Level 3 privilege separation)
- **SPEC-015:** ADT Operational Center (Flask app, human UI + agent API)
- **SPEC-016:** ADT Help & Principles Page
- **SPEC-017:** Repository structure and migration plan

**Origin: ADT Framework (self-governed)**
- **SPEC-018:** Phase 1 Hardening (security fixes, deduplication, config)
- **SPEC-019:** DTTP Standalone Service (HTTP service on :5002)
- **SPEC-020:** Self-Governance Integrity (tiered path protection, break-glass)
- **SPEC-021:** ADT Operator Console (cross-platform Tauri desktop app)

Full spec text available in `_cortex/specs/`.

---

## 5. Coordination

### 5.1 Task Tracking

Tasks are tracked in `_cortex/tasks.json`. Agents must:
1. Check for available tasks before starting work
2. Lock a task before working on it
3. Log completion to ADS

### 5.2 Work Logs

Each session appends to: `_cortex/work_logs/<YYYY-MM-DD>_<role>.md`

---

## 6. Continuous Synchronization

**Mandate:** "Non-negotiable submission to GitHub."

### 6.1 Auto-Sync Policy
- Every successful file modification (edit, create, delete, patch) performed by an agent MUST be immediately committed to git.
- The system MUST attempt to push the commit to the remote repository (`origin`).
- Commit messages must follow the format: `[ADT] <Action> <File>`
- Failure to push (network issues) does NOT revert the local change, but must be logged.

---

"*The framework governs itself by its own principles.*"
