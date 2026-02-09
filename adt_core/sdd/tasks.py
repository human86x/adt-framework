import fcntl
import json
import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class TaskManager:
    """Manages the project task board."""

    def __init__(self, tasks_path: str, project_name: str = ""):
        self.tasks_path = tasks_path
        self.project_name = project_name or self._detect_project_name()

    def _detect_project_name(self) -> str:
        """Read project name from existing tasks file if present."""
        if os.path.exists(self.tasks_path):
            try:
                with open(self.tasks_path, "r") as f:
                    data = json.load(f)
                    return data.get("project", "unknown")
            except (json.JSONDecodeError, OSError):
                pass
        return "unknown"

    def _load_tasks(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.tasks_path):
            with open(self.tasks_path, "r") as f:
                try:
                    data = json.load(f)
                    return data.get("tasks", [])
                except json.JSONDecodeError:
                    logger.warning("Failed to parse tasks file: %s", self.tasks_path)
                    return []
        return []

    def _save_tasks(self, tasks: List[Dict[str, Any]]):
        with open(self.tasks_path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump({"project": self.project_name, "tasks": tasks}, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all tasks, optionally filtered by status."""
        tasks = self._load_tasks()
        if status:
            return [t for t in tasks if t.get("status") == status]
        return tasks

    def update_task_status(self, task_id: str, new_status: str) -> bool:
        """Updates the status of a specific task."""
        tasks = self._load_tasks()
        updated = False
        for task in tasks:
            if task.get("id") == task_id:
                task["status"] = new_status
                updated = True
                break
        
        if updated:
            self._save_tasks(tasks)
        return updated

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Returns details for a specific task."""
        tasks = self._load_tasks()
        for task in tasks:
            if task.get("id") == task_id:
                return task
        return None
