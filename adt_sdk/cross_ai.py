import os
import json
import logging
import time
from typing import Dict, Any, Optional, List
import requests

from adt_sdk.client import ADTClient

logger = logging.getLogger(__name__)

class CrossAIOrchestrator(ADTClient):
    """Orchestrator side of the Cross-AI Orchestration Protocol (CAOP)."""

    def create_task(self, 
                    worker_role: str, 
                    worker_agent: str, 
                    title: str, 
                    instructions: str,
                    context: Optional[Dict[str, Any]] = None,
                    constraints: Optional[Dict[str, Any]] = None,
                    timeout_seconds: int = 600) -> str:
        """Create a CAOP task manifest."""
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/governance/cross_ai/task"
        payload = {
            "orchestrator_session_id": self.session_id,
            "worker_role": worker_role,
            "worker_agent": worker_agent,
            "title": title,
            "instructions": instructions,
            "context": context or {},
            "constraints": constraints or {},
            "timeout_seconds": timeout_seconds,
            "agent": self.agent_name,
            "role": self.role
        }
        
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        return data["task_id"]

    def spawn_worker(self, task_id: str, child_harness: Optional[str] = None) -> str:
        """Spawn a child session with ADT_TASK_ID injected."""
        panel_url = self._get_panel_url()
        task_resp = requests.get(f"{panel_url}/api/governance/cross_ai/task/{task_id}", timeout=10)
        task_resp.raise_for_status()
        manifest = task_resp.json()
        
        child_role = manifest["worker_role"]
        child_harness = child_harness or manifest["worker_agent"]
        
        url = f"{panel_url}/api/governance/sessions/spawn"
        payload = {
            "parent_session_id": self.session_id,
            "child_role": child_role,
            "child_harness": child_harness,
            "task_id": task_id,
            "spec_ref": "SPEC-049",
            "context_hint": f"CAOP Worker for {task_id}"
        }
        
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()["child_session_id"]

    def get_orchestration_status(self) -> Dict[str, Any]:
        """Get aggregate status of all workers spawned by this session."""
        if not self.session_id:
            raise ValueError("session_id is required for get_orchestration_status")
            
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/governance/cross_ai/orchestration/{self.session_id}/status"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def wait_for_all(self, task_ids: List[str], poll_interval: int = 5, timeout: int = 1800) -> Dict[str, Any]:
        """Block until all specified tasks are complete or failed."""
        start_time = time.time()
        while True:
            status = self.get_orchestration_status()
            tasks = {t["task_id"]: t for t in status["tasks"] if t["task_id"] in task_ids}
            
            all_done = True
            for tid in task_ids:
                if tid not in tasks or tasks[tid]["status"] not in ["complete", "failed"]:
                    all_done = False
                    break
            
            if all_done:
                self.log_event({
                    "agent": self.agent_name,
                    "role": self.role,
                    "action_type": "cross_ai_orchestration_complete",
                    "description": f"CAOP Orchestration complete for {len(task_ids)} tasks.",
                    "spec_ref": "SPEC-049",
                    "session_id": self.session_id,
                    "action_data": {
                        "task_ids": task_ids,
                        "results": [tasks[tid]["status"] for tid in task_ids]
                    }
                })
                return tasks
                
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Orchestration timed out after {timeout}s")
                
            time.sleep(poll_interval)

class CrossAIWorker(ADTClient):
    """Worker side of the Cross-AI Orchestration Protocol (CAOP)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_id = os.environ.get("ADT_TASK_ID")
        self.manifest = None

    @classmethod
    def from_env(cls):
        """Bootstrap worker from environment variables."""
        worker = cls(
            agent_name=os.environ.get("ADT_AGENT", "gemini"),
            role=os.environ.get("ADT_ROLE", "backend_engineer"),
            session_id=os.environ.get("ADT_SESSION_ID")
        )
        if worker.task_id:
            worker.fetch_manifest()
        return worker

    def fetch_manifest(self) -> Dict[str, Any]:
        """Retrieve task instructions and constraints."""
        if not self.task_id:
            raise ValueError("ADT_TASK_ID environment variable not set")
            
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/governance/cross_ai/task/{self.task_id}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        self.manifest = resp.json()
        return self.manifest

    def accept(self) -> None:
        """Signal task acceptance to ADS."""
        self.log_event({
            "agent": self.agent_name,
            "role": self.role,
            "action_type": "cross_ai_task_accepted",
            "description": f"CAOP Task {self.task_id} accepted.",
            "spec_ref": "SPEC-049",
            "session_id": self.session_id,
            "action_data": {"task_id": self.task_id}
        })

    def progress(self, pct: int, summary: str) -> None:
        """Update task progress."""
        self.log_event({
            "agent": self.agent_name,
            "role": self.role,
            "action_type": "cross_ai_progress_update",
            "description": f"CAOP Task {self.task_id} progress: {pct}% - {summary}",
            "spec_ref": "SPEC-049",
            "session_id": self.session_id,
            "action_data": {
                "task_id": self.task_id,
                "progress_pct": pct,
                "summary": summary
            }
        })

    def complete(self, result_summary: str, artifacts: Optional[List[str]] = None) -> None:
        """Finalize task with success."""
        self.log_event({
            "agent": self.agent_name,
            "role": self.role,
            "action_type": "cross_ai_task_complete",
            "description": f"CAOP Task {self.task_id} complete: {result_summary}",
            "spec_ref": "SPEC-049",
            "session_id": self.session_id,
            "action_data": {
                "task_id": self.task_id,
                "result_summary": result_summary,
                "artifacts": artifacts or []
            }
        })

    def abort(self, reason: str) -> None:
        """Finalize task with failure."""
        self.log_event({
            "agent": self.agent_name,
            "role": self.role,
            "action_type": "cross_ai_task_aborted",
            "description": f"CAOP Task {self.task_id} aborted: {reason}",
            "spec_ref": "SPEC-049",
            "session_id": self.session_id,
            "action_data": {
                "task_id": self.task_id,
                "reason": reason
            }
        })