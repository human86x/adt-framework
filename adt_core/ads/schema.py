import json
from datetime import datetime
from typing import Optional, Dict, Any

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

    @staticmethod
    def generate_id(action_type: str) -> str:
        """Generates a unique event ID based on type and timestamp."""
        ts_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        return f"evt_{ts_str}_{action_type[:10]}"

    @staticmethod
    def validate(event_data: Dict[str, Any]) -> bool:
        """Validates that all required fields are present in the event."""
        for field in ADSEventSchema.REQUIRED_FIELDS:
            if field not in event_data:
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
        **kwargs
    ) -> Dict[str, Any]:
        """Helper to create a standard event dictionary."""
        event = {
            "event_id": event_id,
            "ts": datetime.utcnow().isoformat() + "Z",
            "agent": agent,
            "role": role,
            "action_type": action_type,
            "description": description,
            "spec_ref": spec_ref,
            "authorized": authorized
        }
        event.update(kwargs)
        return event
