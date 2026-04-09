import sys
import os
import uuid
import datetime

# Add project root to path for imports
sys.path.insert(0, os.path.abspath("."))

from adt_core.ads.logger import ADSLogger
from adt_core.ads.schema import ADSEventSchema

def log_session_start(role: str, agent: str, description: str, spec_ref: str):
    logger = ADSLogger("_cortex/ads/events.jsonl")
    session_id = f"sess_{datetime.datetime.now().strftime(\"%Y%m%d_%H%M%S\")}_{uuid.uuid4().hex[:4]}"
    
    event_id = ADSEventSchema.generate_id("session_start")
    event = ADSEventSchema.create_event(
        event_id=event_id,
        agent=agent,
        role=role,
        action_type="session_start",
        description=description,
        spec_ref=spec_ref,
        session_id=session_id,
        tier=3
    )
    
    logger.log(event)
    print(f"Logged session_start: {event_id} (Session: {session_id})")
    return session_id

if __name__ == "__main__":
    log_session_start(
        role="Systems_Architect",
        agent="GEMINI",
        description="Systems Architect session started. Focusing on SPEC-042 Swarm Governance and architectural alignment for v0.4.0.",
        spec_ref="SPEC-038"
    )