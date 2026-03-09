import os
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


# --- SPEC-038A Taxonomies ---

INTENT_TYPES = [
    "Innovation", "Enhancement", "Maintenance",
    "Risk Mitigation", "Regulatory Compliance", "Operational Improvement",
]

MATURITY_LEVELS = ["Initial", "Developing", "Defined", "Managed", "Optimised"]

VALUE_CATEGORIES = [
    "Revenue", "Efficiency", "Risk Reduction",
    "Customer Experience", "Sustainability",
]

INTENT_STATUSES = [
    "Intent Defined", "Event Under Review", "Approved for Transformation",
    "Rejected", "In Transformation", "Operational", "Value Assessed",
    # Legacy compat
    "Active",
]

CAPABILITY_TYPES = ["Business", "Digital", "Operational", "Data", "Technology"]

RISK_LEVELS = ["Low", "Medium", "High", "Critical"]

EVENT_TYPES = [
    "Customer Signal", "Market Change", "Regulatory Trigger",
    "Innovation Hub Breakthrough", "Workforce Observation",
    "Technology Opportunity", "Risk Occurrence",
    "Business-Technical Ecosystem Shift", "Strategic Initiative",
    "Operational Insight",
]

EVENT_STATUSES = ["Captured", "Under Review", "Actioned", "Dismissed"]

GATE_DECISIONS = ["Proceed", "Refine", "Halt"]


def validate_intent(data: Dict[str, Any]) -> List[str]:
    """Validate intent data against SPEC-038A enriched schema. Returns list of errors."""
    errors = []
    if not data.get("title"):
        errors.append("title is required")
    if not data.get("description"):
        errors.append("description is required")
    if data.get("type") and data["type"] not in INTENT_TYPES:
        errors.append(f"type must be one of: {INTENT_TYPES}")
    if data.get("target_maturity") and data["target_maturity"] not in MATURITY_LEVELS:
        errors.append(f"target_maturity must be one of: {MATURITY_LEVELS}")
    if data.get("value_category") and data["value_category"] not in VALUE_CATEGORIES:
        errors.append(f"value_category must be one of: {VALUE_CATEGORIES}")
    if data.get("status") and data["status"] not in INTENT_STATUSES:
        errors.append(f"status must be one of: {INTENT_STATUSES}")
    cap = data.get("capability", {})
    if cap.get("type") and cap["type"] not in CAPABILITY_TYPES:
        errors.append(f"capability.type must be one of: {CAPABILITY_TYPES}")
    if cap.get("current_maturity") and cap["current_maturity"] not in MATURITY_LEVELS:
        errors.append(f"capability.current_maturity must be one of: {MATURITY_LEVELS}")
    risk = data.get("risk", {})
    if risk.get("level") and risk["level"] not in RISK_LEVELS:
        errors.append(f"risk.level must be one of: {RISK_LEVELS}")
    return errors


def validate_event(data: Dict[str, Any]) -> List[str]:
    """Validate triggering event data against SPEC-038A enriched schema. Returns list of errors."""
    errors = []
    if not data.get("description"):
        errors.append("description is required")
    if data.get("type") and data["type"] not in EVENT_TYPES:
        errors.append(f"type must be one of: {EVENT_TYPES}")
    if data.get("priority") and data["priority"] not in RISK_LEVELS:
        errors.append(f"priority must be one of: {RISK_LEVELS}")
    if data.get("status") and data["status"] not in EVENT_STATUSES:
        errors.append(f"status must be one of: {EVENT_STATUSES}")
    return errors


class CapabilityManager:
    """Manages storage and retrieval of Capability Change Intents and Triggering Events."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.capabilities_dir = os.path.join(project_root, "_cortex", "capabilities")
        self.intents_path = os.path.join(self.capabilities_dir, "intents.jsonl")
        self.events_path = os.path.join(self.capabilities_dir, "capability_events.jsonl")

        # Ensure directory exists
        os.makedirs(self.capabilities_dir, exist_ok=True)

    def _append_jsonl(self, file_path: str, data: Dict[str, Any]):
        """Helper to append a dict as a JSON line."""
        if "ts" not in data:
            data["ts"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with open(file_path, "a") as f:
            f.write(json.dumps(data) + "\n")

    def _read_jsonl(self, file_path: str) -> List[Dict[str, Any]]:
        """Helper to read all lines from a JSONL file."""
        if not os.path.exists(file_path):
            return []
        results = []
        with open(file_path, "r") as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        return results

    def _rewrite_jsonl(self, file_path: str, records: List[Dict[str, Any]]):
        """Rewrite a JSONL file with updated records."""
        with open(file_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

    def add_intent(self, intent_data: Dict[str, Any]) -> str:
        """Adds a new Capability Change Intent with SPEC-038A defaults."""
        if not intent_data.get("intent_id"):
            ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            intent_data["intent_id"] = f"INT-{ts_str}"

        # SPEC-038A: Default status to lifecycle start
        if not intent_data.get("status"):
            intent_data["status"] = "Intent Defined"
        if not intent_data.get("target_maturity"):
            intent_data["target_maturity"] = "Initial"
        # Default empty nested sections for backward compat
        intent_data.setdefault("org_context", {})
        intent_data.setdefault("capability", {})
        intent_data.setdefault("technical_ecosystem", {})
        intent_data.setdefault("risk", {})
        intent_data.setdefault("value", {})
        intent_data.setdefault("governance", {})

        self._append_jsonl(self.intents_path, intent_data)
        return intent_data["intent_id"]

    def add_event(self, event_data: Dict[str, Any]) -> str:
        """Adds a new Triggering Event with SPEC-038A defaults."""
        if not event_data.get("event_id"):
            ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            event_data["event_id"] = f"CEV-{ts_str}"

        event_data.setdefault("status", "Captured")
        event_data.setdefault("org_context", {})
        event_data.setdefault("technical_ecosystem", {})

        self._append_jsonl(self.events_path, event_data)
        return event_data["event_id"]

    def list_intents(self) -> List[Dict[str, Any]]:
        return self._read_jsonl(self.intents_path)

    def list_events(self) -> List[Dict[str, Any]]:
        return self._read_jsonl(self.events_path)

    def get_intent(self, intent_id: str) -> Optional[Dict[str, Any]]:
        for intent in self.list_intents():
            if intent.get("intent_id") == intent_id:
                return intent
        return None

    def update_intent(self, intent_id: str, updates: Dict[str, Any]) -> bool:
        """Update arbitrary fields on an intent."""
        intents = self.list_intents()
        found = False
        for intent in intents:
            if intent.get("intent_id") == intent_id:
                intent.update(updates)
                intent["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                found = True
                break
        if found:
            self._rewrite_jsonl(self.intents_path, intents)
        return found

    def update_intent_status(self, intent_id: str, status: str) -> bool:
        """Updates the status of an intent."""
        return self.update_intent(intent_id, {"status": status})

    def update_event_status(self, event_id: str, status: str) -> bool:
        """Updates the status of an event."""
        events = self.list_events()
        found = False
        for event in events:
            if event.get("event_id") == event_id:
                event["status"] = status
                event["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                found = True
                break
        if found:
            self._rewrite_jsonl(self.events_path, events)
        return found

    def get_summary(self) -> Dict[str, Any]:
        """Aggregate statistics for the /capabilities/summary endpoint."""
        intents = self.list_intents()
        by_status = {}
        by_type = {}
        by_value = {}
        by_risk = {}
        maturity_current = {}
        maturity_target = {}
        gate_progress = []

        gate_mgr = GateManager(self.project_root)

        for i in intents:
            status = i.get("status", "Intent Defined")
            by_status[status] = by_status.get(status, 0) + 1

            itype = i.get("type", "Unknown")
            by_type[itype] = by_type.get(itype, 0) + 1

            vcat = i.get("value_category", i.get("value", {}).get("category", "Unknown"))
            by_value[vcat] = by_value.get(vcat, 0) + 1

            rlevel = i.get("risk", {}).get("level", "Unknown")
            by_risk[rlevel] = by_risk.get(rlevel, 0) + 1

            cm = i.get("capability", {}).get("current_maturity", "Initial")
            maturity_current[cm] = maturity_current.get(cm, 0) + 1

            tm = i.get("target_maturity", "Initial")
            maturity_target[tm] = maturity_target.get(tm, 0) + 1

            current_gate = gate_mgr.get_current_gate(i["intent_id"])
            gate_progress.append(current_gate - 1)  # completed gates

        total = len(intents)
        avg_gate = sum(gate_progress) / total if total else 0

        return {
            "total_intents": total,
            "active_count": by_status.get("In Transformation", 0),
            "value_assessed_count": by_status.get("Value Assessed", 0),
            "avg_gate_progress": round(avg_gate, 1),
            "by_status": by_status,
            "by_type": by_type,
            "by_value_category": by_value,
            "by_risk_level": by_risk,
            "maturity_current": maturity_current,
            "maturity_target": maturity_target,
        }

    def get_trace(self, intent_id: str, query: Optional[Any] = None,
                  task_manager: Optional[Any] = None) -> Dict[str, Any]:
        """Returns the full causal chain for an intent, including gate evaluations."""
        intent = self.get_intent(intent_id)
        if not intent:
            return {"error": "Intent not found"}

        events = [e for e in self.list_events() if e.get("intent_id") == intent_id]

        # Gate chain
        gate_mgr = GateManager(self.project_root)
        gates = gate_mgr.get_gates(intent_id)

        ads_events = []
        if query:
            all_ads = query.get_all_events()
            for e in all_ads:
                if e.get("action_data", {}).get("intent_id") == intent_id:
                    ads_events.append(e)
                elif e.get("intent_id") == intent_id:
                    ads_events.append(e)

        linked_tasks = []
        if task_manager:
            all_tasks = task_manager.list_tasks()
            task_ids = set()
            for e in ads_events:
                tid = e.get("action_data", {}).get("task_id")
                if tid:
                    task_ids.add(tid)
            for t in all_tasks:
                if t["id"] in task_ids:
                    linked_tasks.append(t)

        linked_specs = list(set(e.get("spec_ref") for e in ads_events if e.get("spec_ref")))

        return {
            "intent": intent,
            "triggering_events": events,
            "gates": gates,
            "specs": linked_specs,
            "tasks": linked_tasks,
            "ads_events": ads_events,
        }


class GateManager:
    """Manages the 7-stage Capability Evolution Workflow (SPEC-038A)."""

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
        self.project_root = project_root
        self.gates_path = os.path.join(
            project_root, "_cortex", "capabilities", "gates.jsonl"
        )
        os.makedirs(os.path.dirname(self.gates_path), exist_ok=True)

    def _read_gates(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.gates_path):
            return []
        results = []
        with open(self.gates_path, "r") as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        return results

    def _get_last_gate_hash(self, intent_id: str) -> str:
        """Get the hash of the last gate record for this intent."""
        gates = self.get_gates(intent_id)
        if gates:
            return gates[-1].get("hash", "")
        return ""

    def _compute_hash(self, record: Dict[str, Any]) -> str:
        """Compute SHA-256 hash of the gate record (excluding the hash field itself)."""
        to_hash = {k: v for k, v in record.items() if k != "hash"}
        raw = json.dumps(to_hash, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get_gates(self, intent_id: str) -> List[Dict[str, Any]]:
        """Return all gate evaluations for an intent, ordered by gate_number then timestamp."""
        all_gates = self._read_gates()
        intent_gates = [g for g in all_gates if g.get("intent_id") == intent_id]
        intent_gates.sort(key=lambda g: (g.get("gate_number", 0), g.get("ts", "")))
        return intent_gates

    def get_current_gate(self, intent_id: str) -> int:
        """Return the next gate number to evaluate (last completed Proceed + 1)."""
        gates = self.get_gates(intent_id)
        max_proceeded = 0
        for g in gates:
            if g.get("decision") == "Proceed" and g.get("gate_number", 0) > max_proceeded:
                max_proceeded = g["gate_number"]
        return max_proceeded + 1

    def get_gate(self, intent_id: str, gate_number: int) -> Optional[Dict[str, Any]]:
        """Get the latest gate evaluation for a specific gate number."""
        gates = self.get_gates(intent_id)
        matching = [g for g in gates if g.get("gate_number") == gate_number]
        return matching[-1] if matching else None

    def evaluate_gate(self, intent_id: str, gate_number: int, evaluator: str,
                      decision_data: Dict[str, Any], desired_outcome: str,
                      actual_outcome: str, decision: str) -> Dict[str, Any]:
        """Record a gate evaluation. Enforces ordering and hash-chains."""
        if gate_number < 1 or gate_number > 7:
            return {"error": "gate_number must be 1-7"}
        if decision not in GATE_DECISIONS:
            return {"error": f"decision must be one of: {GATE_DECISIONS}"}

        # Enforce sequential ordering: can only evaluate current gate
        current = self.get_current_gate(intent_id)
        if gate_number > current:
            return {"error": f"Cannot evaluate gate {gate_number}; current gate is {current}"}

        prev_hash = self._get_last_gate_hash(intent_id)
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        gate_id = f"GATE-{intent_id}-{gate_number}"

        record = {
            "gate_id": gate_id,
            "intent_id": intent_id,
            "gate_number": gate_number,
            "gate_name": self.GATE_NAMES.get(gate_number, f"Gate {gate_number}"),
            "ts": ts,
            "evaluator": evaluator,
            "decision_data": decision_data,
            "desired_outcome": desired_outcome,
            "actual_outcome": actual_outcome,
            "decision": decision,
            "next_gate": gate_number + 1 if decision == "Proceed" and gate_number < 7 else None,
            "prev_gate_hash": prev_hash,
        }
        record["hash"] = self._compute_hash(record)

        with open(self.gates_path, "a") as f:
            f.write(json.dumps(record) + "\n")

        # Determine intent status transition
        new_status = None
        if decision == "Halt":
            new_status = "Rejected"
        elif decision == "Proceed" and gate_number in self.STATUS_TRANSITIONS:
            new_status = self.STATUS_TRANSITIONS[gate_number]

        return {
            "gate_id": gate_id,
            "gate_number": gate_number,
            "decision": decision,
            "hash": record["hash"],
            "new_status": new_status,
        }

    def verify_chain(self, intent_id: str) -> Dict[str, Any]:
        """Verify the hash chain integrity for an intent's gates."""
        gates = self.get_gates(intent_id)
        if not gates:
            return {"valid": True, "count": 0}

        for i, gate in enumerate(gates):
            expected_hash = self._compute_hash(gate)
            if gate.get("hash") != expected_hash:
                return {"valid": False, "broken_at": gate.get("gate_id"), "index": i}
            if i > 0 and gate.get("prev_gate_hash") != gates[i - 1].get("hash"):
                return {"valid": False, "broken_at": gate.get("gate_id"), "index": i,
                        "reason": "prev_gate_hash mismatch"}

        return {"valid": True, "count": len(gates)}
