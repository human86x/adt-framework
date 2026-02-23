import json
import os
import datetime
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class ProjectRegistry:
    """Manages the project registry at ~/.adt/projects.json."""

    def __init__(self, registry_path: Optional[str] = None):
        if registry_path:
            self.registry_path = registry_path
        else:
            self.registry_path = os.path.expanduser("~/.adt/projects.json")
        
        self._ensure_registry_exists()

    def _ensure_registry_exists(self):
        """Creates the registry directory and file if they don't exist."""
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        if not os.path.exists(self.registry_path):
            self._save_registry({
                "projects": {},
                "next_dttp_port": 5003
            })
            # Self-register the framework as project zero
            self.register_project(
                name="adt-framework",
                path=os.getcwd(),
                port=5002,
                is_framework=True
            )

    def _load_registry(self) -> Dict[str, Any]:
        """Loads the registry from disk."""
        try:
            with open(self.registry_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Error loading registry from {self.registry_path}: {e}")
            return {"projects": {}, "next_dttp_port": 5003}

    def _save_registry(self, data: Dict[str, Any]):
        """Saves the registry to disk."""
        try:
            with open(self.registry_path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logger.error(f"Error saving registry to {self.registry_path}: {e}")

    def register_project(self, 
                         name: str, 
                         path: str, 
                         port: Optional[int] = None, 
                         is_framework: bool = False) -> Dict[str, Any]:
        """Registers a new project or updates an existing one."""
        data = self._load_registry()
        projects = data.get("projects", {})
        
        path = os.path.abspath(path)
        
        if not port:
            port = data.get("next_dttp_port", 5003)
            data["next_dttp_port"] = port + 1

        projects[name] = {
            "path": path,
            "dttp_port": port,
            "panel_port": 5001 if is_framework else None,
            "status": "active",
            "registered_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "is_framework": is_framework
        }
        
        data["projects"] = projects
        self._save_registry(data)
        return projects[name]

    def deregister_project(self, name: str) -> bool:
        """Removes a project from the registry."""
        data = self._load_registry()
        projects = data.get("projects", {})
        
        if name in projects:
            if projects[name].get("is_framework"):
                logger.warning(f"Attempted to deregister framework project: {name}")
                return False
            del projects[name]
            data["projects"] = projects
            self._save_registry(data)
            return True
        return False

    def get_project(self, name: str) -> Optional[Dict[str, Any]]:
        """Returns details for a specific project."""
        data = self._load_registry()
        return data.get("projects", {}).get(name)

    def find_project_by_path(self, path: str) -> Optional[str]:
        """Finds a project name by its root directory path."""
        data = self._load_registry()
        path = os.path.abspath(path)
        for name, config in data.get("projects", {}).items():
            if os.path.abspath(config.get("path")) == path:
                return name
        return None

    def list_projects(self) -> Dict[str, Any]:
        """Returns all registered projects."""
        data = self._load_registry()
        return data.get("projects", {})

    def next_available_port(self) -> int:
        """Returns the next available DTTP port."""
        data = self._load_registry()
        return data.get("next_dttp_port", 5003)

    @staticmethod
    def get_cortex_path(project_root: str) -> str:
        """Returns the absolute path to the project's _cortex directory."""
        return os.path.join(os.path.abspath(project_root), "_cortex")

    @staticmethod
    def get_config_path(project_root: str) -> str:
        """Returns the absolute path to the project's config directory."""
        return os.path.join(os.path.abspath(project_root), "config")
