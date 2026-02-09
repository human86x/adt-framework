from typing import Dict, Any, Optional
from adt_core.ads.logger import ADSLogger
from adt_core.ads.schema import ADSEventSchema
from .policy import PolicyEngine
from .actions import ActionHandler

class DTTPGateway:
    """The main validation and execution gateway for DTTP requests."""

    def __init__(self, 
                 policy_engine: PolicyEngine, 
                 action_handler: ActionHandler, 
                 logger: ADSLogger):
        self.policy_engine = policy_engine
        self.action_handler = action_handler
        self.logger = logger

    def request(self, 
                agent: str,
                role: str,
                spec_id: str,
                action: str,
                params: Dict[str, Any],
                rationale: str) -> Dict[str, Any]:
        """
        Processes a DTTP request: validates, logs pre-action, executes, logs post-action.
        """
        path = params.get("file") or params.get("path")
        
        # 1. Validate
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
                escalation=True
            ))
            return {"status": "denied", "reason": reason}

        # 2. Log Pre-action
        pre_event_id = ADSEventSchema.generate_id(f"pending_{action}")
        self.logger.log(ADSEventSchema.create_event(
            event_id=pre_event_id,
            agent=agent,
            role=role,
            action_type=f"pending_{action}",
            description=f"Requesting {action} on {path}. Rationale: {rationale}",
            spec_ref=spec_id,
            authorized=True,
            status="pending"
        ))

        # 3. Execute
        result = self.action_handler.execute(action, params)
        
        # 4. Log Post-action
        post_event_id = ADSEventSchema.generate_id(f"completed_{action}")
        self.logger.log(ADSEventSchema.create_event(
            event_id=post_event_id,
            agent=agent,
            role=role,
            action_type=f"completed_{action}",
            description=f"Completed {action} on {path}. Result: {result.get('status')}",
            spec_ref=spec_id,
            authorized=True,
            execution_result=result
        ))

        return {"status": "allowed", "result": result}
