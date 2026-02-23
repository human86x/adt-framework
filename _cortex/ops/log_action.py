from adt_core.ads.logger import ADSLogger
from adt_core.ads.schema import ADSEventSchema
import datetime
import uuid
import os

logger = ADSLogger('_cortex/ads/events.jsonl')

def log_action(action_type, description, spec_ref):
    event = {
        "event_id": f"evt_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:3]}",
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
        "agent": "GEMINI",
        "role": "Backend_Engineer",
        "action_type": action_type,
        "description": description,
        "spec_ref": spec_ref,
        "authorized": True,
        "tier": 3
    }
    logger.log(event)
    print(f"Logged event: {event['event_id']}")

log_action("completed_edit", "Phase 1 Hardening (SPEC-018 Phase C & D): Implemented Session Counting fix, comprehensive Python logging across core modules, API Input Validation, and expanded Robustness tests.", "SPEC-018")
log_action("session_end", "Backend Engineer session ended. Completed Phase 1 Hardening tasks for Robustness and Confidence.", "SPEC-017")
