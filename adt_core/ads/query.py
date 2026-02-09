import json
from typing import List, Dict, Any, Optional

class ADSQuery:
    """Tools for querying and filtering ADS events."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def get_all_events(self) -> List[Dict[str, Any]]:
        """Returns all events from the ADS file."""
        events = []
        try:
            with open(self.file_path, "r") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        except FileNotFoundError:
            pass
        return events

    def filter_events(self, 
                      agent: Optional[str] = None, 
                      role: Optional[str] = None, 
                      action_type: Optional[str] = None,
                      spec_ref: Optional[str] = None) -> List[Dict[str, Any]]:
        """Filters events based on provided criteria."""
        all_events = self.get_all_events()
        filtered = []
        for event in all_events:
            if agent and event.get("agent") != agent:
                continue
            if role and event.get("role") != role:
                continue
            if action_type and event.get("action_type") != action_type:
                continue
            if spec_ref and event.get("spec_ref") != spec_ref:
                continue
            filtered.append(event)
        return filtered

    def get_last_event(self) -> Optional[Dict[str, Any]]:
        """Returns the most recent event."""
        events = self.get_all_events()
        return events[-1] if events else None
