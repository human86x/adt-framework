import logging
import os
from typing import Optional, Tuple

from adt_core.sdd.validator import SpecValidator
from .jurisdictions import JurisdictionManager

logger = logging.getLogger(__name__)


class PolicyEngine:
    """Fail-closed policy engine for DTTP."""

    def __init__(self, validator: SpecValidator, jurisdictions: JurisdictionManager):
        self.validator = validator
        self.jurisdictions = jurisdictions

    def validate_request(self,
                         role: str,
                         spec_id: str,
                         action_type: str,
                         path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Validates an action request against specs and jurisdictions.
        Returns (is_allowed, reason).
        """
        # 1. Check spec authorization
        if not self.validator.is_authorized(spec_id, role, action_type):
            return False, f"Spec {spec_id} does not authorize role {role} for action {action_type}"

        # 2. Check jurisdiction if path is provided
        if path:
            if not self.jurisdictions.is_in_jurisdiction(role, path):
                return False, f"Path {path} is outside the jurisdiction of role {role}"

            # 3. Check if path is authorized by the spec (with boundary matching)
            authorized_paths = self.validator.get_authorized_paths(spec_id)
            normalized = os.path.normpath(path)
            path_authorized = False
            for auth_path in authorized_paths:
                auth_norm = os.path.normpath(auth_path)
                if normalized == auth_norm or normalized.startswith(auth_norm + os.sep):
                    path_authorized = True
                    break

            if not path_authorized:
                return False, f"Path {path} is not authorized by spec {spec_id}"

        return True, "Authorized"
