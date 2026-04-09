from adt_core.ads.logger import ADSLogger
from adt_core.ads.schema import ADSEventSchema
import datetime
import uuid
import os

logger = ADSLogger("_cortex/ads/events.jsonl")
session_id = f"sess_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:4]}"

event = {
    "event_id": ADSEventSchema.generate_id("session_start"),
    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    "agent": "GEMINI",
    "role": "Systems_Architect",
    "action_type": "session_start",
    "description": "Systems Architect session started. Focusing on SPEC-042 Swarm Governance and architectural alignment for v0.4.0.",
    "spec_ref": "SPEC-038",
    "authorized": True,
    "tier": 3,
    "session_id": session_id
}
logger.log(event)
print(f"Logged session_start: {event["event_id"]} (Session: {session_id})")
