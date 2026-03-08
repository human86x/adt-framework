import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class ADSEventSchema:
    """Schema definition and validation for ADS events."""

    REQUIRED_FIELDS = [
        "event_id",
        "ts",
        "agent",
        "role",
        "action_type",
        "description",
        "spec_ref",
        "authorized"
    ]

    # SPEC-026: Task Lifecycle Event Types
    TASK_EVENTS = [
        "task_status_updated",  # Agent self-service
        "task_approved",        # Human approval
        "task_rejected",        # Human rejection
        "task_reassigned",      # Human reassignment
        "task_reopened"         # Human reopen
    ]

    # SPEC-020 Amendment B: Canonical values for normalization
    CANONICAL_AGENTS = ["CLAUDE", "GEMINI", "HUMAN", "SYSTEM"]
    CANONICAL_ROLES: Optional[List[str]] = None  # Loaded at startup

    @staticmethod
    def normalize_agent(agent: str) -> str:
        """Normalize agent identifier to uppercase canonical form."""
        if not agent:
            return "UNKNOWN"
        for canonical in ADSEventSchema.CANONICAL_AGENTS:
            if agent.upper() == canonical:
                return canonical
        return agent.upper()

    @staticmethod
    def normalize_role(role: str) -> str:
        """Normalize role name to canonical casing from jurisdictions.json."""
        if not role:
            return "unknown"
        if ADSEventSchema.CANONICAL_ROLES is None:
            return role
        for canonical in ADSEventSchema.CANONICAL_ROLES:
            if role.lower() == canonical.lower():
                return canonical
        return role

    @staticmethod
    def generate_id(action_type: str) -> str:
        """Generates a unique event ID based on type and timestamp."""
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
        return f"evt_{ts_str}_{action_type[:10]}"

    @staticmethod
    def validate(event_data: Dict[str, Any]) -> bool:
        """Validates that all required fields are present in the event."""
        for field in ADSEventSchema.REQUIRED_FIELDS:
            if field not in event_data:
                return False
        
        # SPEC-020 Amendment B: Role normalization check (warning only)
        if ADSEventSchema.CANONICAL_ROLES:
            role = event_data.get("role", "")
            if role.lower() not in [r.lower() for r in ADSEventSchema.CANONICAL_ROLES]:
                logger.warning(f"ADS: Unknown role '{role}' not in canonical list")

        # Validate tier if present
        if "tier" in event_data:
            if event_data["tier"] not in [1, 2, 3]:
                return False

        # Validate timestamp format
        try:
            datetime.fromisoformat(event_data["ts"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return False
            
        return True

    @staticmethod
    def create_event(
        event_id: str,
        agent: str,
        role: str,
        action_type: str,
        description: str,
        spec_ref: str,
        authorized: bool = True,
        tier: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Helper to create a standard event dictionary."""
        event = {
            "event_id": event_id,
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "agent": ADSEventSchema.normalize_agent(agent),
            "role": ADSEventSchema.normalize_role(role),
            "action_type": action_type,
            "description": description,
            "spec_ref": spec_ref,
            "authorized": authorized
        }
        if tier is not None:
            event["tier"] = tier
        event.update(kwargs)
        return event
