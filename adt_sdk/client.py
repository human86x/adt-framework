import logging
import os
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)


class ADTClient:
    """Client library for AI agents to interact with the DTCP service."""

    def __init__(self,
                 dtcp_url: Optional[str] = None,
                 agent_name: str = "AGENT",
                 role: str = "backend_engineer",
                 session_id: Optional[str] = None,
                 parent_session_id: Optional[str] = None):
        # SPEC-044 Phase B3: Support DTCP_URL with fallback to DTTP_URL
        self.dtcp_url = (dtcp_url or os.environ.get("DTCP_URL") or os.environ.get("DTTP_URL") or "http://localhost:5002").rstrip("/")
        self.agent_name = agent_name
        self.role = role
        self.session_id = session_id
        self.parent_session_id = parent_session_id

    def set_session(self, session_id: str):
        self.session_id = session_id

    def set_parent_session(self, parent_session_id: str):
        self.parent_session_id = parent_session_id

    def request(self,
                spec_id: str,
                action: str,
                params: Dict[str, Any],
                rationale: str) -> Dict[str, Any]:
        """Submit a DTCP request directly to the DTCP service."""
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
        if self.parent_session_id:
            payload["parent_session_id"] = self.parent_session_id

        try:
            response = requests.post(f"{self.dtcp_url}/request", json=payload, timeout=10)
            return response.json()
        except requests.ConnectionError:
            logger.error("DTCP service unreachable at %s", self.dtcp_url)
            return {"status": "error", "message": f"DTCP service unreachable at {self.dtcp_url}"}
        except requests.RequestException as e:
            logger.error("DTCP request failed: %s", e)
            return {"status": "error", "message": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """Get the DTCP service status."""
        try:
            response = requests.get(f"{self.dtcp_url}/status", timeout=5)
            return response.json()
        except requests.RequestException as e:
            return {"status": "error", "message": str(e)}

    def get_policy(self) -> Dict[str, Any]:
        """Get the current loaded policy from DTCP."""
        try:
            response = requests.get(f"{self.dtcp_url}/policy", timeout=5)
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
        if self.parent_session_id:
            payload["parent_session_id"] = self.parent_session_id

        try:
            response = requests.post(f"{self.dtcp_url}/request", json=payload, timeout=10)
            return response.json()
        except requests.ConnectionError:
            logger.error("DTCP service unreachable at %s", self.dtcp_url)
            return {"status": "error", "message": f"DTCP service unreachable at {self.dtcp_url}"}
        except requests.RequestException as e:
            logger.error("DTCP validate_write failed: %s", e)
            return {"status": "error", "message": str(e)}

    def patch_file(self,
                   spec_id: str,
                   file_path: str,
                   old_string: str,
                   new_string: str,
                   rationale: str) -> Dict[str, Any]:
        """Submit a patch action (partial file edit) through DTCP."""
        return self.request(
            spec_id=spec_id,
            action="patch",
            params={"file": file_path, "old_string": old_string, "new_string": new_string},
            rationale=rationale,
        )

    def log_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Log an arbitrary event to the ADS via the DTCP service."""
        try:
            response = requests.post(f"{self.dtcp_url}/log", json=event, timeout=10)
            return response.json()
        except requests.RequestException as e:
            logger.error("DTCP log_event failed: %s", e)
            return {"status": "error", "message": str(e)}

    def _get_panel_url(self) -> str:
        """Derive the ADT Panel URL from the DTCP URL.
        Defaults to port 5001 on the same host."""
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(self.dtcp_url)
        # Rebuild with port 5001
        netloc = parsed.hostname or "localhost"
        if parsed.port:
            netloc = f"{netloc}:5001"
        else:
            netloc = f"{netloc}:5001"
        
        return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)).rstrip("/")

    def complete_task(self, task_id: str, evidence: str = "") -> Dict[str, Any]:
        """Update task status to completed."""
        # Task API is on the ADT Panel (port 5001 by default)
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/tasks/{task_id}/status"
        payload = {
            "agent": self.agent_name,
            "role": self.role,
            "status": "completed",
            "evidence": evidence
        }
        try:
            response = requests.put(url, json=payload, timeout=10)
            return response.json()
        except requests.RequestException as e:
            return {"status": "error", "message": str(e)}

    def complete_request(self, req_id: str, status: str = "COMPLETED") -> Dict[str, Any]:
        """Update request status. Backward compatibility wrapper for update_request_status."""
        return self.update_request_status(req_id, status)

    def update_request_status(self, req_id: str, status: str = "COMPLETED") -> Dict[str, Any]:
        """Update request status via governed API."""
        # Request API is on the ADT Panel (port 5001 by default)
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/governance/requests/{req_id}/status"
        payload = {
            "agent": self.agent_name,
            "role": self.role,
            "status": status.upper()
        }
        try:
            response = requests.put(url, json=payload, timeout=10)
            return response.json()
        except requests.RequestException as e:
            return {"status": "error", "message": str(e)}

    def file_request(self, 
                     to_role: str, 
                     title: str, 
                     description: str,
                     priority: str = "MEDIUM",
                     req_type: str = "SPEC_REQUEST",
                     related_specs: Optional[list] = None) -> Dict[str, Any]:
        """File a cross-role request via the governed API."""
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/governance/requests"
        payload = {
            "from_role": self.role,
            "from_agent": self.agent_name,
            "to_role": to_role,
            "title": title,
            "description": description,
            "priority": priority,
            "type": req_type,
            "related_specs": related_specs or []
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            return response.json()
        except requests.RequestException as e:
            return {"status": "error", "message": str(e)}

    def git_commit(self, message: str, files: Optional[list] = None) -> Dict[str, Any]:
        """Submit a git commit action through DTTP."""
        return self.request(
            spec_id="SPEC-023",
            action="git_commit",
            params={"message": message, "files": files or ["."]},
            rationale=f"Governed commit: {message}"
        )

    def git_push(self, branch: str = "main", remote: str = "origin", tier2_justification: Optional[str] = None) -> Dict[str, Any]:
        """Submit a git push action through DTTP."""
        params = {"branch": branch, "remote": remote}
        if tier2_justification:
            params["tier2_justification"] = tier2_justification
        return self.request(
            spec_id="SPEC-023",
            action="git_push",
            params=params,
            rationale=f"Governed push to {remote}/{branch}"
        )
