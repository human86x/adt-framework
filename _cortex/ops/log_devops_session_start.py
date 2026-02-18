from adt_core.ads.logger import ADSLogger
import datetime
import uuid
import os

ads_path = os.path.join('_cortex', 'ads', 'events.jsonl')
logger = ADSLogger(ads_path)
event = {
    "event_id": f"evt_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:4]}",
    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
    "agent": "GEMINI",
    "role": "DevOps_Engineer",
    "action_type": "session_start",
    "description": "DevOps Engineer session started. Focus: Phase D of SPEC-031 - Console session creation with project picker and PTY env var setup.",
    "spec_ref": "SPEC-031",
    "authorized": True,
    "tier": 3
}
logger.log(event)
print(f"Logged event: {event['event_id']}")