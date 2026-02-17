import json
import os
import logging
from typing import List, Dict, Any, Optional

# Cross-platform file locking
try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self, file_path: str, project_name: str = 'unknown'):
        self.file_path = file_path
        self.project_name = project_name
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w') as f:
                json.dump({'project': self.project_name, 'tasks': []}, f, indent=2)

    def list_tasks(self, status: Optional[str] = None, assigned_to: Optional[str] = None) -> List[Dict[str, Any]]:
        with open(self.file_path, 'r') as f:
            self._lock(f)
            try:
                data = json.load(f)
                tasks = data.get('tasks', [])
                if status:
                    tasks = [t for t in tasks if t.get('status') == status]
                if assigned_to:
                    tasks = [t for t in tasks if assigned_to in (t.get('assigned_to') or '')]
                return tasks
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Error reading tasks from {self.file_path}: {e}")
                return []
            finally:
                self._unlock(f)

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        with open(self.file_path, 'r+') as f:
            self._lock(f)
            try:
                data = json.load(f)
                tasks = data.get('tasks', [])
                found = False
                for task in tasks:
                    if task['id'] == task_id:
                        task.update(updates)
                        found = True
                        break
                if found:
                    f.seek(0)
                    json.dump(data, f, indent=2)
                    f.truncate()
                return found
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Error updating task {task_id} in {self.file_path}: {e}")
                return False
            finally:
                self._unlock(f)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        tasks = self.list_tasks()
        for task in tasks:
            if task['id'] == task_id:
                return task
        return None

    def _lock(self, f):
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_EX)
        elif msvcrt:
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(self, f):
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_UN)
        elif msvcrt:
            msvcrt.locking(f.fileno(), msvcrt.LK_ULOCK, 1)
