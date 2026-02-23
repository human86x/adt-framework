import logging
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)


class ADTClient:
    """Client library for AI agents to interact with the DTTP service."""

    def __init__(self,
                 dttp_url: str = "http://localhost:5002",
                 agent_name: str = "AGENT",
                 role: str = "backend_engineer"):
        self.dttp_url = dttp_url.rstrip("/")
        self.agent_name = agent_name
        self.role = role
        self.session_id: Optional[str] = None

    def set_session(self, session_id: str):
        self.session_id = session_id

    def request(self,
                spec_id: str,
                action: str,
                params: Dict[str, Any],
                rationale: str) -> Dict[str, Any]:
        """Submit a DTTP request directly to the DTTP service."""
        payload = {
            "agent": self.agent_name,
            "role": self.role,
            "spec_id": spec_id,
            "action": action,
            "params": params,
            "rationale": rationale,
        }
        if self.session_id:
            payload["session_id"] = self.session_id

        try:
            response = requests.post(f"{self.dttp_url}/request", json=payload, timeout=10)
            return response.json()
        except requests.ConnectionError:
            logger.error("DTTP service unreachable at %s", self.dttp_url)
            return {"status": "error", "message": f"DTTP service unreachable at {self.dttp_url}"}
        except requests.RequestException as e:
            logger.error("DTTP request failed: %s", e)
            return {"status": "error", "message": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """Get the DTTP service status."""
        try:
            response = requests.get(f"{self.dttp_url}/status", timeout=5)
            return response.json()
        except requests.RequestException as e:
            return {"status": "error", "message": str(e)}

    def get_policy(self) -> Dict[str, Any]:
        """Get the current loaded policy from DTTP."""
        try:
            response = requests.get(f"{self.dttp_url}/policy", timeout=5)
            return response.json()
        except requests.RequestException as e:
            return {"status": "error", "message": str(e)}

    def validate_write(self,
                       spec_id: str,
                       action: str,
                       params: Dict[str, Any],
                       rationale: str) -> Dict[str, Any]:
        """Dry-run validation: checks if a write would be allowed without executing it."""
        payload = {
            "agent": self.agent_name,
            "role": self.role,
            "spec_id": spec_id,
            "action": action,
            "params": params,
            "rationale": rationale,
            "dry_run": True,
        }
        if self.session_id:
            payload["session_id"] = self.session_id

        try:
            response = requests.post(f"{self.dttp_url}/request", json=payload, timeout=10)
            return response.json()
        except requests.ConnectionError:
            logger.error("DTTP service unreachable at %s", self.dttp_url)
            return {"status": "error", "message": f"DTTP service unreachable at {self.dttp_url}"}
        except requests.RequestException as e:
            logger.error("DTTP validate_write failed: %s", e)
            return {"status": "error", "message": str(e)}

    def patch_file(self,
                   spec_id: str,
                   file_path: str,
                   old_string: str,
                   new_string: str,
                   rationale: str) -> Dict[str, Any]:
        """Submit a patch action (partial file edit) through DTTP."""
        return self.request(
            spec_id=spec_id,
            action="patch",
            params={"file": file_path, "old_string": old_string, "new_string": new_string},
            rationale=rationale,
        )

    def log_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Log an arbitrary event to the ADS via the DTTP service."""
        try:
            response = requests.post(f"{self.dttp_url}/log", json=event, timeout=10)
            return response.json()
        except requests.RequestException as e:
            logger.error("DTTP log_event failed: %s", e)
            return {"status": "error", "message": str(e)}
