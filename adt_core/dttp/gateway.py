import os
from typing import Dict, Any, Optional
from adt_core.ads.logger import ADSLogger
from adt_core.ads.schema import ADSEventSchema
from .policy import PolicyEngine
from .actions import ActionHandler

# SPEC-020: HARDCODED Protected Paths (Sovereign/Constitutional)
# These are compiled into the gateway logic and cannot be configured away.
SOVEREIGN_PATHS = [
    "config/specs.json",
    "config/jurisdictions.json",
    "config/dttp.json",
    "_cortex/AI_PROTOCOL.md",
    "_cortex/MASTER_PLAN.md",
]

# SPEC-031 Amendment A: Governance Lock applies to ALL projects
GOVERNANCE_LOCKED = SOVEREIGN_PATHS

CONSTITUTIONAL_PATHS = [
    "adt_core/dttp/gateway.py",
    "adt_core/dttp/policy.py",
    "adt_core/dttp/service.py",
    "adt_core/ads/logger.py",
    "adt_core/ads/integrity.py",
    "adt_core/ads/crypto.py",
]

class DTTPGateway:
    """The main validation and execution gateway for DTTP requests."""

    def __init__(self, 
                 policy_engine: PolicyEngine, 
                 action_handler: ActionHandler, 
                 logger: ADSLogger,
                 is_framework: bool = False):
        self.policy_engine = policy_engine
        self.action_handler = action_handler
        self.logger = logger
        self.is_framework = is_framework

    def request(self,
                agent: str,
                role: str,
                spec_id: str,
                action: str,
                params: Dict[str, Any],
                rationale: str,
                dry_run: bool = False) -> Dict[str, Any]:
        """
        Processes a DTTP request: validates, logs pre-action, executes, logs post-action.
        If dry_run=True, runs all validation but skips execution.
        """
        path = params.get("file") or params.get("path")
        normalized_path = os.path.normpath(path) if path else None

        # 0. Path Containment Check (SPEC-031 Amendment A)
        if path:
            try:
                # This ensures the path is within project_root
                self.action_handler._resolve_path(path)
            except PermissionError as e:
                event_id = ADSEventSchema.generate_id("containment_violation")
                self.logger.log(ADSEventSchema.create_event(
                    event_id=event_id, agent=agent, role=role, action_type="denied_containment",
                    description=f"DENIED: Path {path} escapes project root. Rationale: {rationale}",
                    spec_ref=spec_id, authorized=False, tier=1, escalation=True
                ))
                return {"status": "denied", "reason": "path_outside_project_root"}

        # 0b. Governance Lock Check (SPEC-031 Amendment A)
        if normalized_path in GOVERNANCE_LOCKED:
            if not self.is_framework:
                # Project's own agents CANNOT modify their own governance files
                event_id = ADSEventSchema.generate_id("gov_lock_violation")
                self.logger.log(ADSEventSchema.create_event(
                    event_id=event_id, agent=agent, role=role, action_type="governance_lock_violation",
                    description=f"DENIED: Agent attempted to modify governance-locked file {normalized_path}. Rationale: {rationale}",
                    spec_ref=spec_id, authorized=False, tier=1, escalation=True
                ))
                return {"status": "denied", "reason": "governance_file_protected"}

        # 1. Sovereign Path Check (Tier 1) - SPEC-020 Section 2.1
        # Skip for external projects (SPEC-031)
        if self.is_framework and normalized_path in SOVEREIGN_PATHS:
            event_id = ADSEventSchema.generate_id("sovereign_violation")
            self.logger.log(ADSEventSchema.create_event(
                event_id=event_id,
                agent=agent,
                role=role,
                action_type="sovereign_path_violation",
                description=f"DENIED: Attempt to modify sovereign path {normalized_path}. Rationale: {rationale}",
                spec_ref=spec_id,
                authorized=False,
                tier=1,
                escalation=True
            ))
            return {"status": "denied", "reason": "sovereign_path_violation"}

        # 2. Constitutional Path Check (Tier 2) - SPEC-020 Section 2.2
        tier = 3
        is_tier2 = False
        tier2_reason = None

        if self.is_framework and normalized_path in CONSTITUTIONAL_PATHS:
            is_tier2 = True
            tier2_reason = f"Tier 2 path {normalized_path}"
        
        # 2b. Action-based Tier Elevation (SPEC-023) - Framework ONLY (Amendment A)
        if self.is_framework:
            if action == "git_tag":
                is_tier2 = True
                tier2_reason = "git_tag is a Tier 2 action"
            elif action == "git_push" and params.get("branch") == "main":
                is_tier2 = True
                tier2_reason = "Pushing to main is a Tier 2 action"

        if is_tier2:
            tier = 2
            tier2_justification = params.get("tier2_justification")
            
            # For paths, require explicit file match in spec (no directory wildcards for Tier 2)
            if normalized_path in CONSTITUTIONAL_PATHS:
                authorized_paths = self.policy_engine.validator.get_authorized_paths(spec_id)
                explicit_match = any(normalized_path == os.path.normpath(ap) for ap in authorized_paths)
                if not explicit_match:
                    reason = "tier2_authorization_required"
                    event_id = ADSEventSchema.generate_id("tier2_denied")
                    self.logger.log(ADSEventSchema.create_event(
                        event_id=event_id,
                        agent=agent,
                        role=role,
                        action_type="tier2_denied",
                        description=f"DENIED: {tier2_reason} requires explicit spec listing. Rationale: {rationale}",
                        spec_ref=spec_id,
                        authorized=False,
                        tier=2,
                        escalation=True
                    ))
                    return {"status": "denied", "reason": reason}

            if not tier2_justification:
                reason = "tier2_authorization_required"
                event_id = ADSEventSchema.generate_id("tier2_denied")
                self.logger.log(ADSEventSchema.create_event(
                    event_id=event_id,
                    agent=agent,
                    role=role,
                    action_type="tier2_denied",
                    description=f"DENIED: {tier2_reason} requires tier2_justification. Rationale: {rationale}",
                    spec_ref=spec_id,
                    authorized=False,
                    tier=2,
                    escalation=True
                ))
                return {"status": "denied", "reason": reason}

        # 3. Standard Policy Validation
        allowed, reason = self.policy_engine.validate_request(role, spec_id, action, path)
        
        if not allowed:
            # Log denial
            event_id = ADSEventSchema.generate_id(f"denial_{action}")
            self.logger.log(ADSEventSchema.create_event(
                event_id=event_id,
                agent=agent,
                role=role,
                action_type=f"denied_{action}",
                description=f"DENIED: {reason}. Rationale provided: {rationale}",
                spec_ref=spec_id,
                authorized=False,
                tier=tier,
                escalation=True
            ))
            return {"status": "denied", "reason": reason}

        # 4. Dry-run: validation passed, skip execution
        if dry_run:
            dry_event_id = ADSEventSchema.generate_id(f"dry_run_{action}")
            self.logger.log(ADSEventSchema.create_event(
                event_id=dry_event_id,
                agent=agent,
                role=role,
                action_type=f"dry_run_validated_{action}",
                description=f"Dry-run validated {action} on {path}. Rationale: {rationale}",
                spec_ref=spec_id,
                authorized=True,
                tier=tier,
            ))
            return {"status": "allowed", "dry_run": True}

        # 5. Log Pre-action
        pre_event_id = ADSEventSchema.generate_id(f"pending_{action}")
        self.logger.log(ADSEventSchema.create_event(
            event_id=pre_event_id,
            agent=agent,
            role=role,
            action_type=f"pending_{action}" if tier == 3 else "tier2_authorized",
            description=f"Requesting {action} on {path}. Rationale: {rationale}",
            spec_ref=spec_id,
            authorized=True,
            tier=tier,
            status="pending"
        ))

        # 6. Execute
        result = self.action_handler.execute(action, params, agent=agent, role=role)

        # 7. Log Post-action
        post_event_id = ADSEventSchema.generate_id(f"completed_{action}")
        self.logger.log(ADSEventSchema.create_event(
            event_id=post_event_id,
            agent=agent,
            role=role,
            action_type=f"completed_{action}",
            description=f"Completed {action} on {path}. Result: {result.get('status')}",
            spec_ref=spec_id,
            authorized=True,
            tier=tier,
            execution_result=result
        ))

        return {"status": "allowed", "result": result}