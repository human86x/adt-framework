"""
SPEC-043: Forge Protocol Orchestration.
Autonomous logic for the Systems_Architect to manage the "Wish to Launch" flow.
"""
import os
import json
import time
import logging
import requests
import subprocess
import re
from typing import List, Dict, Any, Optional

from adt_sdk.client import ADTClient
from adt_sdk.cross_ai import CrossAIOrchestrator

logger = logging.getLogger(__name__)

class ForgeOrchestrator:
    """
    Manages the autonomous orchestration loop for a forged project.
    """

    def __init__(self, project_dir: str, agent_name: str = "Architect_Forge"):
        self.project_dir = project_dir
        self.project_name = os.path.basename(project_dir)
        self.client = ADTClient(agent_name=agent_name, role="Systems_Architect")
        self.orchestrator = CrossAIOrchestrator(agent_name=agent_name, role="Systems_Architect")
        self.adc_url = os.environ.get('ADC_URL', 'http://localhost:5001')
        self.active_tasks = []

    def get_state(self) -> str:
        """
        Determines the current state of the project.
        """
        # Check if SPEC-001 exists
        specs_dir = os.path.join(self.project_dir, "_cortex", "specs")
        spec_001_file = None
        if os.path.exists(specs_dir):
            for f in os.listdir(specs_dir):
                if f.startswith("SPEC-001"):
                    spec_001_file = f
                    break
        
        if not spec_001_file:
            return "design"
        
        # Check SPEC-001 status
        try:
            resp = requests.get(f"{self.adc_url}/api/governance/specs/SPEC-001?project={self.project_name}")
            if resp.ok:
                spec_data = resp.json()
                status = spec_data.get("status", "draft").upper()
                if status == "APPROVED":
                    # Check tasks
                    tasks_resp = requests.get(f"{self.adc_url}/api/governance/tasks?project={self.project_name}")
                    if tasks_resp.ok:
                        tasks = tasks_resp.json().get("tasks", [])
                        if not tasks:
                            return "orchestration"
                        
                        all_done = all(t.get("status") == "completed" for t in tasks)
                        if all_done:
                            return "verification"
                        return "execution"
                return "awaiting_approval"
        except:
            pass
            
        return "unknown"

    def run_design_phase(self, intent_description: str):
        """
        Phase 1: Read Intent -> Generate Spec -> Submit SCR.
        """
        logger.info(f"Forge Phase 1: Designing {self.project_name}")
        
        # 1. Register Intent
        intent_payload = {
            "title": f"Forge Project: {self.project_name}",
            "description": intent_description,
            "project": self.project_name,
            "agent": self.client.agent_name,
            "role": "Systems_Architect"
        }
        resp = requests.post(f"{self.adc_url}/api/governance/capabilities/intents", json=intent_payload)
        resp.raise_for_status()
        intent_id = resp.json()["intent_id"]
        
        # 2. Draft SPEC-001 (Blueprint)
        blueprint_content = f"""# SPEC-001: {self.project_name} Blueprint

**Status:** DRAFT
**Intent:** {intent_id}
**Description:** {intent_description}

## 1. Objectives
- Implement the core functionality described in the intent.
- Ensure ADT governance compliance.

## 2. Architecture
- Backend: Python/Flask
- Frontend: HTML/JS (Standalone)

## 3. Task Breakdown
- task_001: Implementation of Backend API (Backend_Engineer)
- task_002: Implementation of Frontend UI (Frontend_Engineer)
"""
        
        # 3. Submit SPEC-001 via API (which handles file creation and ADS log)
        spec_payload = {
            "id": "SPEC-001",
            "title": f"{self.project_name} Blueprint",
            "status": "DRAFT",
            "content": blueprint_content,
            "project": self.project_name
        }
        resp = requests.post(f"{self.adc_url}/api/governance/specs", json=spec_payload)
        resp.raise_for_status()
        
        # 4. Propose SCR for SPEC-001 Approval (Mechanically)
        # Note: In a real system, the Architect agent would do this.
        scr_payload = {
            "agent": self.client.agent_name,
            "role": "Systems_Architect",
            "spec_ref": "SPEC-001",
            "target_path": "config/specs.json",
            "change_type": "json_merge",
            "description": "Approve SPEC-001 Blueprint",
            "project": self.project_name,
            "merge_data": {
                "specs": {
                    "SPEC-001": {
                        "title": f"{self.project_name} Blueprint",
                        "status": "approved",
                        "roles": ["Systems_Architect", "Backend_Engineer", "Frontend_Engineer"],
                        "paths": ["src/", "tests/", "_cortex/tasks.json"],
                        "action_types": ["edit", "patch", "create"]
                    }
                }
            }
        }
        resp = requests.post(f"{self.adc_url}/api/governance/sovereign-requests", json=scr_payload)
        resp.raise_for_status()
        
        logger.info(f"Forge Phase 1 Completed: SPEC-001 and SCR submitted.")

    def run_orchestration_phase(self):
        """
        Phase 2: Break down into tasks -> Spawn children.
        """
        logger.info(f"Forge Phase 2: Orchestrating {self.project_name}")
        
        # 1. Read SPEC-001 from API
        try:
            resp = requests.get(f"{self.adc_url}/api/governance/specs/SPEC-001?project={self.project_name}")
            resp.raise_for_status()
            spec_content = resp.json().get("content", "")
            
            # 2. Parse tasks from markdown (Section-aware extractor - REQ-080)
            tasks = []
            
            # Extract ## Task Breakdown or ## Tasks section
            task_section_match = re.search(r"## (?:Task Breakdown|Tasks)(.*?)(?:##|$)", spec_content, re.DOTALL | re.IGNORECASE)
            if task_section_match:
                task_section = task_section_match.group(1)
                task_lines = re.findall(r"- (task_\d+): (.*?) \((.*?)\)", task_section)
                for tid, title, role in task_lines:
                    tasks.append({
                        "id": tid,
                        "title": title,
                        "assigned_to": role,
                        "status": "pending",
                        "priority": "high",
                        "spec_ref": "SPEC-001"
                    })
            else:
                logger.warning("## Tasks section not found in SPEC-001.")
            
            if not tasks:
                logger.warning("No tasks found in SPEC-001. Using defaults.")
                tasks = [
                    {"id": "task_001", "title": "Backend API", "assigned_to": "Backend_Engineer"},
                    {"id": "task_002", "title": "Frontend UI", "assigned_to": "Frontend_Engineer"}
                ]

            # 3. Initialize tasks.json in project
            tasks_path = os.path.join(self.project_dir, "_cortex", "tasks.json")
            tasks_data = {"project": self.project_name, "tasks": tasks}
            with open(tasks_path, "w") as f:
                json.dump(tasks_data, f, indent=2)

            # 4. Spawn workers via CAOP (SPEC-049)
            for t in tasks:
                caop_tid = self.orchestrator.create_task(
                    worker_role=t["assigned_to"],
                    worker_agent=os.environ.get("FORGE_DEFAULT_AGENT", "antigravity"),
                    title=t["title"],
                    instructions=f"Implement {t['title']} as defined in SPEC-001 for {self.project_name}."
                )
                self.orchestrator.spawn_worker(caop_tid)
                self.active_tasks.append(caop_tid)
                logger.info(f"Spawned worker for {t['id']} (CAOP: {caop_tid})")

        except Exception as e:
            logger.error(f"Forge Phase 2 failed: {e}")
            
        logger.info(f"Forge Phase 2 Completed: Orchestration active.")

    def run_verification_phase(self):
        """
        Phase 3: Review work -> Run tests -> Mark project as Ready (REQ-079).
        """
        logger.info(f"Forge Phase 3: Verifying {self.project_name}")
        
        # 1. Run Pytest
        try:
            # We assume a standard pytest setup in the forged project
            result = subprocess.run(["pytest", "--json-report", "--json-report-file=report.json"], 
                                    cwd=self.project_dir, 
                                    capture_output=True, 
                                    text=True)
            
            if result.returncode == 0:
                logger.info(f"Verification SUCCESS for {self.project_name}")
                
                # 2. Verify each task (REQ-079)
                tasks_path = os.path.join(self.project_dir, "_cortex", "tasks.json")
                if os.path.exists(tasks_path):
                    with open(tasks_path, "r") as f:
                        tasks_data = json.load(f)
                        for t in tasks_data.get("tasks", []):
                            self.verify_task(t["id"], f"Verified via automated test suite passing in {self.project_name}.")

                # 3. Signal Ready via ADS
                self.client.log_event({
                    "agent": self.client.agent_name,
                    "role": "Systems_Architect",
                    "action_type": "project_ready",
                    "description": f"FORGE COMPLETE: Project {self.project_name} is verified and ready.",
                    "spec_ref": "SPEC-001",
                    "action_data": {"project": self.project_name, "test_output": result.stdout[:1000]}
                })
            else:
                logger.error(f"Verification FAILED for {self.project_name}")
                self.client.log_event({
                    "agent": self.client.agent_name,
                    "role": "Systems_Architect",
                    "action_type": "project_verification_failed",
                    "description": f"FORGE FAILED: Project {self.project_name} failed verification tests.",
                    "spec_ref": "SPEC-001",
                    "action_data": {"project": self.project_name, "error": result.stderr[:1000]}
                })

        except Exception as e:
            logger.error(f"Failed to run verification tests: {e}")
        
        logger.info(f"Forge Phase 3 Completed for {self.project_name}.")

    def verify_task(self, task_id: str, summary: str):
        """REQ-070: Verify a completed CAOP task."""
        self.client.log_event({
            "agent": self.client.agent_name,
            "role": "Systems_Architect",
            "action_type": "cross_ai_task_verified",
            "description": f"Verified task {task_id}: {summary}",
            "spec_ref": "SPEC-049",
            "action_data": {"task_id": task_id, "summary": summary}
        })

    def retask_worker(self, task_id: str, new_instructions: str):
        """REQ-070: Reject work and assign new instructions (CAOP)."""
        self.client.log_event({
            "agent": self.client.agent_name,
            "role": "Systems_Architect",
            "action_type": "cross_ai_task_retasked",
            "description": f"Retasking worker for {task_id}. New instructions: {new_instructions}",
            "spec_ref": "SPEC-049",
            "action_data": {"task_id": task_id, "new_instructions": new_instructions}
        })
        # Respawn worker with same task_id
        return self.orchestrator.spawn_worker(task_id)

    def reject_task(self, task_id: str, reason: str):
        """REQ-070: Permanent rejection of a CAOP task."""
        self.client.log_event({
            "agent": self.client.agent_name,
            "role": "Systems_Architect",
            "action_type": "cross_ai_task_rejected",
            "description": f"Rejected task {task_id}: {reason}",
            "spec_ref": "SPEC-049",
            "action_data": {"task_id": task_id, "reason": reason}
        })

    def wait_for_results(self, timeout: int = 1800) -> Dict[str, Any]:
        """
        Wait for all active tasks to complete.
        """
        if not self.active_tasks:
            return {}
            
        logger.info(f"Forge: Waiting for {len(self.active_tasks)} tasks to complete...")
        results = self.orchestrator.wait_for_all(self.active_tasks, timeout=timeout)
        
        for tid, res in results.items():
            logger.info(f"Task {tid} finished with status: {res['status']}")
            
        return results

    def run(self, poll_interval: int = 10):
        """REQ-081: Continuous execution loop for the orchestrator."""
        logger.info(f"Forge Orchestrator started for {self.project_name}. Polling every {poll_interval}s.")
        terminal_states = ["ready", "failed", "unknown"]
        
        while True:
            state = self.get_state()
            if state in terminal_states:
                logger.info(f"Forge loop reached terminal state: {state}")
                break
                
            changed = self.step()
            if not changed:
                time.sleep(poll_interval)

    def step(self) -> bool:
        """
        Run the next appropriate step in the loop.
        Returns True if a state transition occurred.
        """
        state = self.get_state()
        logger.info(f"Forge Step: Current state is '{state}'")
        
        if state == "design":
            # Intent is handled at init time in forge_project()
            return False
        elif state == "orchestration":
            self.run_orchestration_phase()
            return True
        elif state == "verification":
            self.run_verification_phase()
            return True
        elif state == "execution":
            # In execution, we just wait for agents. 
            # We could poll for results here and advance.
            results = self.wait_for_results(timeout=5)
            if results and all(r['status'] == 'complete' for r in results.values()):
                logger.info("All tasks completed. Advancing to verification.")
                return True
            return False
        elif state == "awaiting_approval":
            logger.info("Awaiting human approval of SPEC-001 SCR...")
            if self._check_approval():
                logger.info("Approval detected! Advancing to orchestration.")
                return True
            return False
            
        return False

    def _check_approval(self) -> bool:
        """REQ-081: Improved listener for forge_approval_received event."""
        try:
            # 1. Check for the specific event type (REQ-071)
            ads_url = f"{self.adc_url}/api/governance/ads/events?project={self.project_name}&type=forge_approval_received"
            resp = requests.get(ads_url)
            if resp.ok:
                events = resp.json().get("events", [])
                # If we see the approval event for SPEC-001, we are good
                for e in events:
                    if e.get("action_data", {}).get("scr_id"): # Simplified check
                        return True

            # 2. Fallback to authorized SCR check
            resp = requests.get(f"{self.adc_url}/api/governance/sovereign-requests?project={self.project_name}&status=authorized")
            if resp.ok:
                scrs = resp.json().get("requests", [])
                return any(s.get("spec_ref") == "SPEC-001" for s in scrs)
        except Exception as e:
            logger.error(f"Failed to check approval: {e}")
        return False
        
        return state

def forge_project(intent_description: str, project_name: Optional[str] = None) -> Dict[str, Any]:
    """
    High-level entry point to trigger the Forge process.
    """
    adc_url = os.environ.get('ADC_URL', 'http://localhost:5001')
    
    # 1. Resolve path (external projects directory)
    base_dir = os.path.join(os.getcwd(), "external_projects")
    os.makedirs(base_dir, exist_ok=True)
    
    if not project_name:
        project_name = f"forge_{int(time.time())}"
    
    project_path = os.path.join(base_dir, project_name)
    
    # 2. Call api/projects/init
    init_payload = {
        "path": project_path,
        "name": project_name
    }
    resp = requests.post(f"{adc_url}/api/projects/init", json=init_payload)
    resp.raise_for_status()
    
    # 3. Start DTTP for the project
    resp = requests.post(f"{adc_url}/api/projects/{project_name}/start")
    if not resp.ok:
        logger.error(f"Failed to start DTTP for {project_name}: {resp.text}")
    resp.raise_for_status()
    
    # 4. Instantiate Orchestrator and run Design Phase
    orchestrator = ForgeOrchestrator(project_path)
    orchestrator.run_design_phase(intent_description)
    
    return {
        "status": "success", 
        "project_name": project_name, 
        "project_path": project_path,
        "message": "Forge initiated. Architect is drafting SPEC-001."
    }
