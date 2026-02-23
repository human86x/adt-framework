import json
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)


class JurisdictionManager:
    """Manages role-to-path jurisdiction mappings."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._jurisdictions = {}
        self._last_mtime = 0.0
        self._reload()

    def _reload(self):
        """Load jurisdictions from config file, tracking mtime to detect changes."""
        if not os.path.exists(self.config_path):
            self._jurisdictions = {}
            return
        try:
            mtime = os.path.getmtime(self.config_path)
            if mtime != self._last_mtime:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                    self._jurisdictions = data.get("jurisdictions", {})
                self._last_mtime = mtime
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load jurisdictions config %s: %s", self.config_path, e)
            self._jurisdictions = {}

    def reload(self):
        """Manually force reload jurisdictions."""
        self._last_mtime = 0.0
        self._reload()

    def is_in_jurisdiction(self, role: str, path: str) -> bool:
        """Checks if a path is within a role's jurisdiction."""
        normalized = os.path.normpath(path)
        allowed_paths = self._jurisdictions.get(role, [])
        for allowed_path in allowed_paths:
            allowed_norm = os.path.normpath(allowed_path)
            if normalized == allowed_norm or normalized.startswith(allowed_norm + os.sep):
                return True
        return False

    def get_jurisdictions(self) -> Dict[str, List[str]]:
        """Returns the full jurisdiction map (read-only)."""
        self._reload()
        return dict(self._jurisdictions)
