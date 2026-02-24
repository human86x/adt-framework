from adt_core.ads.logger import ADSLogger
import datetime
import uuid
import os

# Ensure we are in the right directory
logger = ADSLogger('_cortex/ads/events.jsonl')
event = {
    "event_id": f"evt_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:3]}",
    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
    "agent": "GEMINI",
    "role": "Backend_Engineer",
    "action_type": "session_start",
    "description": "Backend Engineer session started. Initializing and reviewing completed tasks.",
    "spec_ref": "SPEC-017",
    "authorized": True,
    "tier": 3
}
logger.log(event)
print(f"Logged event: {event['event_id']}")
