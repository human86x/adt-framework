import json
import logging
import os
from typing import Dict, Any, List

logger = logging.getLogger(__name__) # Restart Trigger


class SpecValidator:
    """Validates if a spec authorizes an action for a given role."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self._last_mtime: float = 0.0
        self._reload_config()

    def _reload_config(self):
        """Load config from file, tracking mtime to detect changes."""
        if not os.path.exists(self.config_path):
            self._config = {}
            return
        try:
            mtime = os.path.getmtime(self.config_path)
            if mtime != self._last_mtime:
                with open(self.config_path, "r") as f:
                    self._config = json.load(f)
                self._last_mtime = mtime
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load spec config %s: %s", self.config_path, e)
            self._config = {}

    def is_authorized(self, spec_id: str, role: str, action_type: str) -> bool:
        """Checks if the role is authorized to perform the action under the spec."""
        self._reload_config()
        spec_info = self._config.get("specs", {}).get(spec_id)
        if not spec_info:
            return False

        if spec_info.get("status") not in ("approved", "active"):
            return False

        if role not in spec_info.get("roles", []):
            return False

        if action_type not in spec_info.get("action_types", []):
            return False

        return True

    def is_authorized_for_role(self, spec_id: str, role: str) -> bool:
        """Checks if the role is authorized under the spec (regardless of action)."""
        self._reload_config()
        spec_info = self._config.get("specs", {}).get(spec_id)
        if not spec_info:
            return False
        
        if spec_info.get("status") not in ("approved", "active"):
            return False
        
        return role in spec_info.get("roles", [])

    def get_authorized_paths(self, spec_id: str) -> List[str]:
        """Returns the list of paths authorized by the spec."""
        self._reload_config()
        spec_info = self._config.get("specs", {}).get(spec_id)
        if not spec_info:
            return []
        return spec_info.get("paths", [])


    def get_standards_refs(self, spec_id: str) -> List[str]:
        """SPEC-063: Returns the list of RationalisedRule ids the spec compliesWith.

        Returns an empty list for specs without `standards_refs` set.
        Used by transparency surface and (opt-in) MRR evaluation in DTCP.
        """
        self._reload_config()
        spec_info = self._config.get("specs", {}).get(spec_id)
        if not spec_info:
            return []
        return spec_info.get("standards_refs", []) or []

    def get_all_specs(self) -> Dict[str, Any]:
        """Returns all loaded specs (read-only)."""
        self._reload_config()
        return dict(self._config.get("specs", {}))
