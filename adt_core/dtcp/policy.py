import logging
import os
import json
from typing import Optional, Tuple, List

from adt_core.sdd.validator import SpecValidator
from .jurisdictions import JurisdictionManager

logger = logging.getLogger(__name__)

# FIND-2026-06-20-001 fix: role-jurisdiction-as-floor for unconditional paths.
# Some paths represent a role's structural responsibility per AI_PROTOCOL.md
# section 2 and must be writable without active-spec path authorization,
# regardless of which SPEC happens to be in flight. Each role's
# unconditional list is a subset of its declared jurisdiction; jurisdiction
# is still enforced (defense in depth), and Tier-1 sovereign / Tier-2
# constitutional protections in gateway.py run BEFORE policy.py and are
# unaffected by this exemption.
ROLE_UNCONDITIONAL_PATHS = {
    "Systems_Architect": [
        "_cortex/specs",
        "_cortex/reports",
        "_cortex/work_logs",
        "_cortex/standards",
        "_cortex/capabilities",
    ],
    "Overseer": [
        "_cortex/ads",
        "_cortex/reports",
        "_cortex/work_logs",
    ],
    "Backend_Engineer": [
        "_cortex/work_logs",
    ],
    "Frontend_Engineer": [
        "_cortex/work_logs",
    ],
    "DevOps_Engineer": [
        "_cortex/work_logs",
    ],
}



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
        # SPEC-053: PTY I/O Authorization
        if action_type == "pty_io":
            target_sid = params.get("session_id") if params else None
            return self.validate_pty_io(role, session_id, target_sid, spec_id)

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

        # FIND-2026-06-20-001 fix: role-unconditional-path exemption.
        # If the path lies within the role's unconditional path list AND
        # within the role's declared jurisdiction, permit without
        # requiring the active spec to enumerate the path. Tier-1
        # sovereign and Tier-2 constitutional protections are enforced
        # upstream in gateway.py and remain in effect.
        if (action_type in ("edit", "patch", "create")
                and path is not None
                and role in ROLE_UNCONDITIONAL_PATHS):
            normalized = os.path.normpath(path)
            for unconditional in ROLE_UNCONDITIONAL_PATHS[role]:
                unconditional_norm = os.path.normpath(unconditional)
                if normalized == unconditional_norm or normalized.startswith(unconditional_norm + os.sep):
                    if self.jurisdictions.is_in_jurisdiction(role, path):
                        return True, f"Authorized: {role} unconditional path ({unconditional})"
                    break

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

    def validate_pty_io(self,
                        caller_role: str,
                        caller_sid: Optional[str],
                        target_sid: Optional[str],
                        spec_id: str) -> Tuple[bool, str]:
        """
        SPEC-053 sec 4.4: Authorization for PTY interaction.
        """
        if not target_sid:
            return False, "PTY I/O requires session_id in params"

        # 1. High-level role exemption
        if caller_role in ("Systems_Architect", "Overseer"):
            return True, f"Authorized: {caller_role} can interact with any PTY"

        # 2. Self-interaction
        if caller_sid == target_sid:
            return True, "Authorized: Agent can interact with its own PTY"

        # 3. Spawner interaction (requires ads_query)
        if self.ads_query:
            target_details = self.ads_query.get_session_details(target_sid)
            if target_details and target_details.get("parent_session_id") == caller_sid:
                return True, f"Authorized: Session {caller_sid} is the spawner of {target_sid}"

        return False, f"Denied: Session {caller_sid} (role {caller_role}) is not authorized to interact with PTY {target_sid}"
