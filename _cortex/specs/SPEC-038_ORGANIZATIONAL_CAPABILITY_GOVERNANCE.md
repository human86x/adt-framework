# SPEC-038: Organizational Capability Governance

**Status:** APPROVED
**Author:** Systems_Architect (GEMINI)
**Date:** 2026-03-06
**Priority:** HIGH
**Related Specs:** SPEC-017 (Repository), SPEC-020 (Self-Governance), SPEC-033 (Sovereign Change Requests), SPEC-035 (Unified Status API)

---

## 1. Purpose

This specification integrates the "Capability Change Intent and Event Capture" framework into the ADT Framework. It bridges the gap between high-level organizational strategy (Intents) and technical execution (Agent Actions). By capturing the "Why" (Intent) and the "What Triggered It" (Event), we achieve full causal traceability across the business-technical ecosystem.

---

## 2. Problem

Currently, the ADT Framework is focused on **technical governance**:
- We know *who* changed a file (Role).
- We know *what* authorized it (Spec).
- We know *how* it was done (Task).
- **We do not know the business purpose (Intent) or the external trigger (Event) that necessitated the change.**

Without this context, the framework provides technical integrity but lacks organizational alignment.

---

## 3. Data Model

### 3.1 Capability Registry (`_cortex/capabilities/`)

We will introduce a new directory to store structured governance artifacts for capabilities.

#### `intents.jsonl` (Capability Change Intents)
Each entry captures a desired organizational outcome:
- `intent_id`: Unique identifier (e.g., INT-001)
- `type`: Innovation, Enhancement, Maintenance, Risk Mitigation, etc.
- `title`: Short descriptive name.
- `description`: The desired outcome.
- `target_maturity`: Initial, Developing, Defined, Managed, Optimized.
- `value_category`: Revenue, Efficiency, Risk Reduction, etc.

#### `capability_events.jsonl` (Triggering Events)
Observable occurrences that trigger evaluation:
- `event_id`: Unique identifier (e.g., CEV-001)
- `intent_id`: Optional link to a parent intent.
- `type`: Customer Signal, Market Change, Regulatory Trigger, etc.
- `priority`: Low, Medium, High, Critical.
- `org_context`: { unit, domain, process, owner }
- `technical_ecosystem`: { systems, data_sources, platform }

### 3.2 Extended ADS Events
The ADS schema (`adt_core/ads/schema.py`) will be extended with:
- `capability_intent_defined`
- `capability_event_captured`
- `capability_maturity_updated`

---
## 4. Integration Logic

### 4.1 Capability Evolution Workflow (7-Stage Gate)
The progression of a Capability Change Intent is governed by a structured workflow consisting of seven "Controlling Events":

1. **Validation & Classification:** Confirming the intent is valid and assigning priority.
2. **Concept Development:** Prototyping and defining the architectural concept.
3. **Strategic Feasibility:** Evaluating financial, operational, and technical viability.
4. **Governance & Quality Review:** Meeting standards for risk and compliance.
5. **Portfolio Planning:** Resource allocation and dependency mapping.
6. **Investment Decision:** Final board approval and budget allocation.
7. **Transformation Initiation:** Starting the program and defining KPIs.

### 4.2 Outcome Tracking
Each event in the workflow must capture:
- **Desired Outcome:** The intended state defined at the start of the gate.
- **Actual Outcome:** The recorded reality once the gate is processed.
- **Provenance:** The hash-chain link to the ADS event authorizing the transition.

### 4.3 Intent-Linked SCRs
...
The `Unified Status Management API` (SPEC-035) will be extended to track capability maturity progress.
- As tasks are completed, the Panel will calculate the "Realized Maturity" based on task evidence and intent alignment.

---

## 5. API Endpoints (Operational Center)

### 5.1 POST /api/governance/capabilities/intents
Captures a new Capability Change Intent.
- **Access:** Systems_Architect or Human only.
- **Action:** Writes to `_cortex/capabilities/intents.jsonl`.
- **Log:** `capability_intent_defined` event in ADS.

### 5.2 POST /api/governance/capabilities/events
Records a Triggering Event.
- **Access:** Any role (agents can capture events from telemetry).
- **Action:** Writes to `_cortex/capabilities/capability_events.jsonl`.
- **Log:** `capability_event_captured` event in ADS.

### 5.3 GET /api/governance/capabilities/trace/<intent_id>
Returns the full causal chain:
`Intent -> Triggering Events -> Authorized Specs -> Executed Tasks -> ADS Audit Trail`.

---

## 6. UI Requirements

### 6.1 ADT Panel (Main Web Interface)
A new **"Capabilities"** tab in the Operational Center will provide:
1. **Strategic Map:** Visualizes Intents and their current maturity status.
2. **Event Feed:** Real-time stream of captured organizational events.
3. **Traceability Explorer:** Drill-down from a business intent to the specific line of code that fulfilled it.
4. **Impact Dashboard:** Graphs showing Value Realization (e.g., "Risk Reduction" across multiple technical changes).

### 6.2 Operator Console (Desktop Side Panel)
The **Hive Tracker** (Right Panel) will be extended with a **"Capability Context"** section:
1. **Active Intent:** Displays the Intent ID and Title driving the current session.
2. **Maturity Progress:** A small progress bar showing the delta between current and target maturity for that intent.
3. **Trigger Event:** Shows the specific Event (e.g., CEV-001) that initiated this workflow.

---

## 7. Jurisdiction Updates

The `config/jurisdictions.json` will be updated:
- `Systems_Architect`: Full access to `_cortex/capabilities/`.
- `All Roles`: Append-only access to `capability_events.jsonl` (to report triggers).

---

## 8. Implementation Tasks

| Task | Description | Assigned To |
|------|-------------|-------------|
| task_163 | Create `_cortex/capabilities/` directory and initialize JSONL files. | Systems_Architect |
| task_164 | Extend `ADSEventSchema` with capability event types. | Backend_Engineer |
| task_165 | Implement `POST /api/governance/capabilities/intents` and `events`. | Backend_Engineer |
| task_166 | Update SCR model and DTTP Gateway to support `intent_id` linking. | Backend_Engineer |
| task_167 | Create "Capabilities" UI tab in ADT Panel with Traceability Explorer. | Frontend_Engineer |
| task_168 | Update `config/jurisdictions.json` and `specs.json` for new paths. | Systems_Architect |

---

## 9. Acceptance Criteria

- [ ] A Human or Architect can define an Intent (e.g., "Improve ECU Tuning Accuracy").
- [ ] An agent can record an Event (e.g., "ECU Log Drift Detected").
- [ ] An SCR can be linked to an Intent ID.
- [ ] The ADS shows a continuous hash-chain from Intent definition to code implementation.
- [ ] The ADT Panel visualizes the "Organisational Context" and "Capability Impact" sections from the source document.

---

*"Traceability from purpose to production."*
