# SPEC-038 Amendment A: Capability Data Model Enrichment & Stage-Gate Engine

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE)
**Date:** 2026-03-08
**Priority:** HIGH
**Amends:** SPEC-038 (Organizational Capability Governance)
**Source Authority:** itgis.org/dcp010 -- "Capability Change Intent and Event Capture" & "Capability Evolution Workflow"
**Related Specs:** SPEC-017, SPEC-020, SPEC-033, SPEC-035, SPEC-040

---

## 1. Purpose

SPEC-038 established the conceptual architecture for organizational capability governance within ADT. This amendment addresses gaps identified against the authoritative source documents:

1. **Data Model Enrichment** -- The intent and event schemas are missing organizational context, capability impact, risk/compliance, value realization, and governance accountability fields.
2. **Stage-Gate Engine** -- The 7-stage Capability Evolution Workflow exists only in spec text; there is no executable gate model, progression tracking, or per-gate decision capture.
3. **Status Lifecycle** -- The current single-state `Active` default does not reflect the full 7-state lifecycle from the source.

---

## 2. Data Model Changes

### 2.1 Enriched Intent Schema (`intents.jsonl`)

Each line in `_cortex/capabilities/intents.jsonl` MUST contain the following fields. Fields marked `[NEW]` are additions to the original SPEC-038 model.

```jsonc
{
  // --- Existing (SPEC-038) ---
  "intent_id": "INT-20260308_143000",
  "ts": "2026-03-08T14:30:00Z",
  "title": "Improve ECU Tuning Accuracy",
  "description": "Desired organisational outcome...",
  "type": "Enhancement",                  // See 2.1.1
  "target_maturity": "Managed",           // See 2.1.2
  "value_category": "Efficiency",         // See 2.1.3
  "status": "Intent Defined",             // See 2.1.4 [CHANGED]

  // --- NEW: Organisational Context (Source Doc Section 3) ---
  "org_context": {
    "unit": "Engineering Division",
    "domain": "Vehicle Systems",
    "process": "ECU Calibration",
    "owner": "Jane Smith"
  },

  // --- NEW: Capability Impact (Source Doc Section 4) ---
  "capability": {
    "name": "ECU Parameter Optimization",
    "type": "Digital",                     // See 2.1.5
    "current_maturity": "Developing"
  },

  // --- NEW: Technical Ecosystem (Source Doc Section 5) ---
  "technical_ecosystem": {
    "systems": ["ECU Logger", "Tuning Bench"],
    "data_sources": ["CAN Bus", "Dyno Logs"],
    "integration_dependencies": ["OBD-II API"],
    "platform": "Linux Embedded"
  },

  // --- NEW: Risk and Compliance (Source Doc Section 6) ---
  "risk": {
    "level": "Medium",                     // Low | Medium | High | Critical
    "regulatory_impact": "EU Stage VI",
    "description": "Incorrect tuning could cause emissions failure."
  },

  // --- NEW: Value Realisation (Source Doc Section 7) ---
  "value": {
    "expected_benefit": "15% reduction in calibration time",
    "success_metrics": "Calibration cycle time < 2 hours, first-pass yield > 95%"
  },

  // --- NEW: Governance & Accountability (Source Doc Section 8) ---
  "governance": {
    "reporter": "Backend_Engineer",
    "accountable_executive": "CTO",
    "review_board": "Technical Steering Committee"
  }
}
```

#### 2.1.1 Intent Type (Extended)

Source doc lists 6 types. Current implementation has 4. Add the missing two:

| Value | Status |
|-------|--------|
| Innovation | Existing |
| Enhancement | Existing |
| Maintenance | Existing |
| Risk Mitigation | Existing |
| Regulatory Compliance | **NEW** |
| Operational Improvement | **NEW** |

#### 2.1.2 Maturity Scale (Standardised)

Five-level scale: `Initial` | `Developing` | `Defined` | `Managed` | `Optimised`

Note: Source uses British spelling "Optimised". Implementation currently uses "Optimized". **Standardise to "Optimised"** to match the source authority.

#### 2.1.3 Value Category (Extended)

| Value | Status |
|-------|--------|
| Revenue | Existing |
| Efficiency | Existing |
| Risk Reduction | Existing |
| Customer Experience | **NEW** |
| Sustainability | **NEW** |

#### 2.1.4 Status Lifecycle (Replaced)

The source document Section 8 defines a 7-state lifecycle. Replace the simple `Active` default:

```
Intent Defined --> Event Under Review --> Approved for Transformation
    --> In Transformation --> Operational --> Value Assessed
    \--> Rejected (terminal)
```

| Status | Description |
|--------|-------------|
| `Intent Defined` | Initial capture. Default for new intents. |
| `Event Under Review` | Triggering event received, under evaluation. |
| `Approved for Transformation` | Passed governance gates, cleared for execution. |
| `Rejected` | Terminal. Did not pass a gate. |
| `In Transformation` | Active implementation/delivery in progress. |
| `Operational` | Deployed and running in production. |
| `Value Assessed` | Post-implementation value review completed. Terminal. |

#### 2.1.5 Capability Type (New)

| Value | Description |
|-------|-------------|
| Business | Business process capabilities |
| Digital | Software/digital capabilities |
| Operational | Day-to-day operational capabilities |
| Data | Data management and analytics capabilities |
| Technology | Infrastructure and platform capabilities |

### 2.2 Enriched Event Schema (`capability_events.jsonl`)

Triggering events gain organizational and technical context:

```jsonc
{
  // --- Existing (SPEC-038) ---
  "event_id": "CEV-20260308_150000",
  "ts": "2026-03-08T15:00:00Z",
  "intent_id": "INT-20260308_143000",
  "type": "Technology Opportunity",       // See 2.2.1
  "priority": "High",
  "description": "New ML model available for ECU parameter prediction.",

  // --- NEW: Organisational Context ---
  "org_context": {
    "unit": "Engineering Division",
    "domain": "Vehicle Systems",
    "process": "ECU Calibration",
    "owner": "Jane Smith"
  },

  // --- NEW: Technical Ecosystem ---
  "technical_ecosystem": {
    "systems": ["ML Pipeline"],
    "data_sources": ["Training Dataset v3"],
    "platform": "Python/TensorFlow"
  },

  // --- NEW: Status ---
  "status": "Captured"                   // Captured | Under Review | Actioned | Dismissed
}
```

#### 2.2.1 Event Type Taxonomy (Extended to 10)

| Value | Status |
|-------|--------|
| Customer Signal | Existing |
| Market Change | Existing |
| Regulatory Trigger | Existing |
| Innovation Hub Breakthrough | **NEW** |
| Workforce Observation | **NEW** |
| Technology Opportunity | **NEW** |
| Risk Occurrence | **NEW** |
| Business-Technical Ecosystem Shift | **NEW** |
| Strategic Initiative | **NEW** |
| Operational Insight | **NEW** |

---

## 3. Stage-Gate Engine

### 3.1 Gate Model

The 7-stage Capability Evolution Workflow from the source document is implemented as a structured progression model. Each gate is a **Controlling Event** that evaluates whether the intent should proceed.

#### Gate Registry (`_cortex/capabilities/gates.jsonl`)

New JSONL file. Each line records a gate evaluation for a specific intent:

```jsonc
{
  "gate_id": "GATE-INT001-3",
  "intent_id": "INT-20260308_143000",
  "gate_number": 3,
  "gate_name": "Strategic Feasibility Evaluation",
  "ts": "2026-03-08T16:00:00Z",
  "evaluator": "Systems_Architect",

  // --- Decision Fields (gate-specific) ---
  "decision_data": {
    "financial_feasibility": "Positive",
    "operational_feasibility": "Feasible",
    "technical_feasibility": "Feasible",
    "strategic_alignment": "High"
  },

  // --- Outcome Tracking ---
  "desired_outcome": "Confirm financial and technical viability for ECU ML integration.",
  "actual_outcome": "All three feasibility dimensions positive. Strategic alignment high.",

  // --- Progression ---
  "decision": "Proceed",                  // Proceed | Refine | Halt
  "next_gate": 4,                         // null if Halt
  "ads_event_id": "evt_20260308_160000_gate_eval",

  // --- Hash chain ---
  "prev_gate_hash": "abc123...",
  "hash": "def456..."
}
```

#### 3.2 Gate Definitions

Each gate has a fixed schema for its `decision_data` fields:

| Gate | Name | Decision Fields |
|------|------|----------------|
| 1 | Validation & Classification | `classification` (Innovation/Enhancement/...), `priority` (Low-Critical), `validator` (name) |
| 2 | Concept Development | `concept_id`, `prototype_required` (Yes/No), `architecture_concept` (text), `concept_owner` (name) |
| 3 | Strategic Feasibility | `financial_feasibility`, `operational_feasibility`, `technical_feasibility`, `strategic_alignment` |
| 4 | Governance & Quality Review | `architecture_review` (Approved/Conditional/Rejected), `risk_rating` (Low-Critical), `compliance_status` (Compliant/Review Required/Non-Compliant), `review_board` |
| 5 | Portfolio Planning | `portfolio_priority` (Low/Medium/High/Strategic), `portfolio_manager`, `estimated_resources`, `target_delivery_window` |
| 6 | Investment Decision | `investment_decision` (Approved/Deferred/Rejected/Further Investigation), `investment_board`, `decision_date`, `approved_budget` |
| 7 | Transformation Initiation | `program_id`, `program_manager`, `start_date`, `delivery_organisation` |

#### 3.3 Gate Progression Rules

1. Gates MUST be evaluated in order (1 through 7). No skipping.
2. A gate with `decision: "Halt"` sets intent status to `Rejected`.
3. A gate with `decision: "Refine"` keeps the intent at its current gate for re-evaluation.
4. A gate with `decision: "Proceed"` advances to `next_gate`.
5. Completing Gate 1 sets intent status to `Event Under Review`.
6. Completing Gate 4 (with Proceed) sets intent status to `Approved for Transformation`.
7. Completing Gate 7 sets intent status to `In Transformation`.
8. Every gate evaluation MUST log an ADS event (`capability_gate_evaluated`).
9. Each gate record is hash-chained to the previous gate record for that intent, providing an independent integrity chain per intent.

#### 3.4 Gate-Intent Status Mapping

| Gate Completed | Intent Status Transition |
|---------------|------------------------|
| Gate 1 (Proceed) | `Intent Defined` --> `Event Under Review` |
| Gate 2 (Proceed) | No change |
| Gate 3 (Proceed) | No change |
| Gate 4 (Proceed) | `Event Under Review` --> `Approved for Transformation` |
| Gate 5 (Proceed) | No change |
| Gate 6 (Proceed) | No change |
| Gate 7 (Proceed) | `Approved for Transformation` --> `In Transformation` |
| Any gate (Halt) | Current --> `Rejected` |
| Post-delivery | `In Transformation` --> `Operational` (manual) |
| Value review | `Operational` --> `Value Assessed` (manual) |

---

## 4. New ADS Event Types

Add to `ADSEventSchema.CAPABILITY_EVENTS`:

```python
CAPABILITY_EVENTS = [
    "capability_intent_defined",       # Existing
    "capability_event_captured",       # Existing
    "capability_maturity_updated",     # Existing
    "capability_gate_evaluated",       # NEW: Gate decision recorded
    "capability_intent_status_changed",# NEW: Status lifecycle transition
    "capability_gate_refined",         # NEW: Gate sent back for re-evaluation
]
```

---

## 5. API Endpoints

### 5.1 New Endpoints

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| GET | `/api/governance/capabilities/intents/<id>/gates` | List all gate evaluations for an intent | Any |
| POST | `/api/governance/capabilities/intents/<id>/gates` | Submit a gate evaluation | Systems_Architect, Human |
| GET | `/api/governance/capabilities/intents/<id>/gates/<gate_number>` | Get specific gate result | Any |
| PUT | `/api/governance/capabilities/intents/<id>/status` | Transition intent status | Systems_Architect, Human |
| GET | `/api/governance/capabilities/summary` | Aggregate stats (intents by status, avg maturity delta, value categories) | Any |
| GET | `/api/governance/capabilities/intents/<id>/maturity-delta` | Current vs target maturity with completion % | Any |

### 5.2 Modified Endpoints

| Method | Path | Change |
|--------|------|--------|
| POST | `/api/governance/capabilities/intents` | Accept enriched schema (sec 2.1). Validate new required fields. |
| POST | `/api/governance/capabilities/events` | Accept enriched schema (sec 2.2). Validate event type taxonomy. |
| GET | `/api/governance/capabilities/trace/<id>` | Include gate evaluations in causal chain. |

---

## 6. Implementation Changes to `capability.py`

### 6.1 Schema Validation

Add a `validate_intent()` method that checks:
- Required fields: `title`, `description`, `type`, `target_maturity`
- `type` is in the 6-value taxonomy
- `target_maturity` is in the 5-level scale
- `status` is in the 7-state lifecycle (default `Intent Defined`)
- If `capability` is provided, validate `capability.type` against the 5-type taxonomy
- If `risk` is provided, validate `risk.level` against Low/Medium/High/Critical

### 6.2 Gate Manager

Add a `GateManager` class (or extend `CapabilityManager`):

```python
class GateManager:
    """Manages the 7-stage Capability Evolution Workflow."""

    GATE_NAMES = {
        1: "Validation & Classification",
        2: "Concept Development / Prototyping",
        3: "Strategic Feasibility Evaluation",
        4: "Governance & Quality Review",
        5: "Portfolio Planning",
        6: "Investment Decision",
        7: "Transformation Initiation",
    }

    GATE_FIELDS = {
        1: ["classification", "priority", "validator"],
        2: ["concept_id", "prototype_required", "architecture_concept", "concept_owner"],
        3: ["financial_feasibility", "operational_feasibility", "technical_feasibility", "strategic_alignment"],
        4: ["architecture_review", "risk_rating", "compliance_status", "review_board"],
        5: ["portfolio_priority", "portfolio_manager", "estimated_resources", "target_delivery_window"],
        6: ["investment_decision", "investment_board", "decision_date", "approved_budget"],
        7: ["program_id", "program_manager", "start_date", "delivery_organisation"],
    }

    STATUS_TRANSITIONS = {
        1: "Event Under Review",
        4: "Approved for Transformation",
        7: "In Transformation",
    }

    def __init__(self, project_root: str):
        self.gates_path = os.path.join(
            project_root, "_cortex", "capabilities", "gates.jsonl"
        )

    def evaluate_gate(self, intent_id, gate_number, evaluator,
                      decision_data, desired_outcome, actual_outcome,
                      decision):
        """Record a gate evaluation. Enforces ordering and hash-chains."""
        ...

    def get_gates(self, intent_id):
        """Return all gate evaluations for an intent, ordered."""
        ...

    def get_current_gate(self, intent_id):
        """Return the next gate number to evaluate (last completed + 1)."""
        ...
```

### 6.3 Backward Compatibility

- Existing intents without the new fields remain valid (read path tolerates missing fields).
- `add_intent()` applies defaults: `status="Intent Defined"`, empty nested dicts.
- Migration: No data migration needed. New fields are additive.

---

## 7. Implementation Tasks

| Task ID | Title | Assigned To | Priority |
|---------|-------|-------------|----------|
| task_174 | Enrich intent schema validation in `capability.py` | Backend_Engineer | HIGH |
| task_175 | Enrich event schema validation in `capability.py` | Backend_Engineer | HIGH |
| task_176 | Implement `GateManager` class with hash-chained gate records | Backend_Engineer | HIGH |
| task_177 | Add new capability ADS event types to `schema.py` | Backend_Engineer | HIGH |
| task_178 | Implement gate API endpoints in `governance_routes.py` | Backend_Engineer | HIGH |
| task_179 | Update `POST /intents` and `POST /events` for enriched schemas | Backend_Engineer | MEDIUM |
| task_180 | Update `GET /trace/<id>` to include gate chain in causal trace | Backend_Engineer | MEDIUM |
| task_181 | Implement `/capabilities/summary` aggregate endpoint | Backend_Engineer | MEDIUM |
| task_182 | Add `gates.jsonl` initialisation to project scaffold | Backend_Engineer | LOW |
| task_183 | Update `config/jurisdictions.json` for gate access control | Systems_Architect | LOW |

---

## 8. Acceptance Criteria

- [ ] A new intent captures all 8 sections from the source document.
- [ ] The 7-stage gate workflow executes: each gate captures its specific decision fields, desired/actual outcomes, and hash-chains to the previous gate.
- [ ] Gate progression enforces ordering (no skipping gates).
- [ ] Gate decisions automatically transition intent status per the mapping in 3.4.
- [ ] The causal trace endpoint returns: Intent --> Gates --> Events --> Specs --> Tasks --> ADS chain.
- [ ] Existing intents without new fields continue to load without errors.
- [ ] All gate evaluations are logged to ADS with `capability_gate_evaluated`.

---

*"From purpose through gates to production -- every decision recorded, every outcome measured."*
