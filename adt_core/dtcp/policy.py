import logging
import os
import json
from typing import Optional, Tuple, List

from adt_core.sdd.validator import SpecValidator
from .jurisdictions import JurisdictionManager

logger = logging.getLogger(__name__)


class PolicyEngine:
    """Fail-closed policy engine for DTCP."""

    def __init__(self, 
                 validator: SpecValidator, 
                 jurisdictions: JurisdictionManager,
                 task_manager: Optional[any] = None,
                 delegation_policy_path: Optional[str] = None,
                 ads_query: Optional[any] = None):
        self.validator = validator
        self.jurisdictions = jurisdictions
        self.task_manager = task_manager
        self.delegation_policy_path = delegation_policy_path
        self.ads_query = ads_query

    def validate_request(self,
                         role: str,
                         spec_id: str,
                         action_type: str,
                         path: Optional[str] = None,
                         session_id: Optional[str] = None,
                         params: Optional[dict] = None) -> Tuple[bool, str]:
        """
        Validates an action request against specs and jurisdictions.
        Returns (is_allowed, reason).
        """
        # Systems_Architect spec-creation exemption: SA can always create/edit
        # _cortex/specs/SPEC-*.md regardless of which active spec is set.
        # Prevents the bootstrap deadlock where writing a new spec requires
        # an already-existing spec to authorize the write. Jurisdiction is
        # still enforced (SA owns _cortex/).
        if (role == "Systems_Architect"
                and action_type in ("edit", "patch", "create")
                and path is not None
                and os.path.normpath(path).startswith(os.path.normpath("_cortex/specs"))):
            if self.jurisdictions.is_in_jurisdiction(role, path):
                return True, "Authorized: Systems_Architect spec-creation exemption"

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

    def validate_delegation(self,
                            parent_role: str,
                            child_role: str,
                            task_id: str,
                            spec_ref: str) -> Tuple[bool, str]:
        """
        Validates a delegation (swarm spawn) request.
        Rules:
        1. Role Matrix: child_role must be in delegation_policy[parent_role]
        2. Task Jurisdiction: task_id.assigned_to must match child_role (or be unset)
        3. Spec Authorization: spec_ref must authorize child_role (at least one action)
        """
        # 1. Role Matrix Check
        if not self.delegation_policy_path or not os.path.exists(self.delegation_policy_path):
            return False, "Delegation policy not found"

        try:
            with open(self.delegation_policy_path, 'r') as f:
                policy = json.load(f)
                matrix = policy.get("matrix", {})
                allowed_roles = matrix.get(parent_role, [])
                if child_role not in allowed_roles:
                    return False, f"Role {parent_role} is not authorized to delegate to {child_role}"
        except Exception as e:
            logger.error(f"Error loading delegation policy: {e}")
            return False, f"Error loading delegation policy: {e}"

        # 2. Task Jurisdiction Check
        if self.task_manager:
            task = self.task_manager.get_task(task_id)
            if not task:
                return False, f"Task {task_id} not found"
            
            assigned_to = task.get("assigned_to")
            if assigned_to and assigned_to != child_role:
                return False, f"Task {task_id} is assigned to {assigned_to}, not {child_role}"

        # 3. Spec Authorization Check
        if not self.validator.is_authorized_for_role(spec_ref, child_role):
            return False, f"Spec {spec_ref} does not authorize role {child_role}"

        return True, "Delegation authorized"
