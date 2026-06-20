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

    def write_to_worker(self, worker_session_id: str, content: str) -> Dict[str, Any]:
        """SPEC-053: Send text/commands to a worker's PTY."""
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/governance/sessions/{worker_session_id}/write"
        payload = {
            "agent": self.agent_name,
            "role": self.role,
            "session_id": self.session_id,
            "spec_id": "SPEC-053",
            "content": content
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def read_worker_output(self, worker_session_id: str, limit: int = 1000) -> Dict[str, Any]:
        """SPEC-053: Read current buffer from a worker's PTY."""
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/governance/sessions/{worker_session_id}/output?limit={limit}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def tail_worker_output(self, worker_session_id: str):
        """SPEC-053: Stream output from a worker's PTY (SSE)."""
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/governance/sessions/{worker_session_id}/stream"
        resp = requests.get(url, stream=True, timeout=None)
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith("data: "):
                    try:
                        yield json.loads(decoded[6:])
                    except:
                        yield decoded[6:]

    def steer(self, worker_session_id: str, instruction: str) -> Dict[str, Any]:
        """SPEC-053: Higher-level steering: write an instruction and log it."""
        self.log_event({
            "agent": self.agent_name,
            "role": self.role,
            "action_type": "human_steering",
            "description": f"Steering worker {worker_session_id}: {instruction}",
            "spec_ref": "SPEC-053",
            "session_id": self.session_id,
            "action_data": {
                "target_session_id": worker_session_id,
                "instruction": instruction
            }
        })
        return self.write_to_worker(worker_session_id, f"\n*** STEERING: {instruction} ***\n")

    def send_message(self, 
                     to_session: str, 
                     body: str, 
                     context: Optional[Dict[str, Any]] = None,
                     priority: str = "normal",
                     reply_to: Optional[str] = None) -> str:
        """SPEC-057: Send a structured message to another agent mailbox."""
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/governance/comms/send"
        payload = {
            "from_session": self.session_id,
            "from_agent": self.agent_name,
            "from_role": self.role,
            "to_session": to_session,
            "body": body,
            "context": context or {},
            "priority": priority,
            "reply_to": reply_to,
            "spec_ref": os.environ.get("ADT_SPEC_ID", "SPEC-057")
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        msg_id = resp.json()["id"]
        
        self.log_event({
            "agent": self.agent_name,
            "role": self.role,
            "action_type": "agent_message_sent",
            "description": f"Sent {priority} message {msg_id} to session {to_session}",
            "spec_ref": "SPEC-057",
            "session_id": self.session_id,
            "action_data": {
                "msg_id": msg_id,
                "to_session": to_session,
                "priority": priority
            }
        })
        return msg_id

    def broadcast(self, body: str, context: Optional[Dict[str, Any]] = None, priority: str = "normal") -> str:
        """SPEC-057: Broadcast a message to all active agents in the swarm."""
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/governance/comms/broadcast"
        payload = {
            "from_session": self.session_id,
            "from_agent": self.agent_name,
            "from_role": self.role,
            "body": body,
            "context": context or {},
            "priority": priority,
            "spec_ref": os.environ.get("ADT_SPEC_ID", "SPEC-057")
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        batch_id = resp.json()["batch_id"]
        
        self.log_event({
            "agent": self.agent_name,
            "role": self.role,
            "action_type": "agent_broadcast_sent",
            "description": f"Sent broadcast batch {batch_id} to swarm",
            "spec_ref": "SPEC-057",
            "session_id": self.session_id,
            "action_data": {
                "batch_id": batch_id,
                "priority": priority
            }
        })
        return batch_id

    def read_replies(self, msg_id: str) -> List[Dict[str, Any]]:
        """SPEC-057: Read all replies to a specific message."""
        inbox_path = f"_cortex/comms/agents/{self.session_id}/inbox"
        replies = []
        if os.path.exists(inbox_path):
            for f in os.listdir(inbox_path):
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(inbox_path, f), "r") as m:
                            msg = json.load(m)
                            if msg.get("reply_to") == msg_id:
                                replies.append(msg)
                    except:
                        pass
        return replies

    def wait_for_reply(self, msg_id: str, timeout: int = 60, poll_interval: int = 2) -> Optional[Dict[str, Any]]:
        """SPEC-057: Block until a reply is received for a message."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            replies = self.read_replies(msg_id)
            if replies:
                return replies[0]
            time.sleep(poll_interval)
        return None

    def report_ready(self, project: str) -> Dict[str, Any]:
        """SPEC-043: Signal build completion to the console."""
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/governance/forge/report_ready"
        payload = {
            "project": project,
            "agent": self.agent_name,
            "role": self.role,
            "session_id": self.session_id
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()

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
            agent_name=os.environ.get("ADT_AGENT", "antigravity"),
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

    def reply(self, original_msg: Dict[str, Any], body: str, context: Optional[Dict[str, Any]] = None) -> str:
        """SPEC-057: Reply to a received message."""
        panel_url = self._get_panel_url()
        url = f"{panel_url}/api/governance/comms/send"
        payload = {
            "from_session": self.session_id,
            "from_agent": self.agent_name,
            "from_role": self.role,
            "to_session": original_msg["from_session"],
            "body": body,
            "context": context or {},
            "priority": original_msg.get("priority", "normal"),
            "reply_to": original_msg["id"],
            "spec_ref": original_msg.get("spec_ref", "SPEC-057")
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        msg_id = resp.json()["id"]
        
        self.log_event({
            "agent": self.agent_name,
            "role": self.role,
            "action_type": "agent_reply_sent",
            "description": f"Replied to message {original_msg[id]} with {msg_id}",
            "spec_ref": "SPEC-057",
            "session_id": self.session_id,
            "action_data": {
                "reply_msg_id": msg_id,
                "original_msg_id": original_msg["id"]
            }
        })
        return msg_id

    def read_inbox(self) -> List[Dict[str, Any]]:
        """SPEC-057: Read all messages in the agent inbox."""
        inbox_path = f"_cortex/comms/agents/{self.session_id}/inbox"
        messages = []
        if os.path.exists(inbox_path):
            for f in os.listdir(inbox_path):
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(inbox_path, f), "r") as m:
                            messages.append(json.load(m))
                    except:
                        pass
        return sorted(messages, key=lambda x: x.get("ts", ""))