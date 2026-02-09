import json
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)


class JurisdictionManager:
    """Manages role-to-path jurisdiction mappings."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._jurisdictions = self._load_jurisdictions()

    def _load_jurisdictions(self) -> Dict[str, List[str]]:
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                try:
                    data = json.load(f)
                    return data.get("jurisdictions", {})
                except json.JSONDecodeError:
                    logger.warning("Failed to parse jurisdictions config: %s", self.config_path)
                    return {}
        return {}

    def reload(self):
        """Reload jurisdictions from config file."""
        self._jurisdictions = self._load_jurisdictions()

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
        return dict(self._jurisdictions)
