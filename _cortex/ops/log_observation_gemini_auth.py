import json
import datetime
import hashlib
import os
import uuid

ads_path = "_cortex/ads/events.jsonl"
prev_hash = "0" * 64
try:
    with open(ads_path, "r") as f:
        lines = f.readlines()
        if lines:
            last = json.loads(lines[-1])
            prev_hash = last.get("hash", prev_hash)
except Exception:
    pass

ts = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
event_id = f"evt_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:4]}"

event = {
    "event_id": event_id,
    "ts": ts,
    "agent": "GEMINI",
    "role": "DevOps_Engineer",
    "action_type": "observation",
    "description": "Observed Google OAuth 400 error in Gemini CLI. Recommended bypass: GEMINI_API_KEY via AI Studio. ADT environment sanitization may be a factor.",
    "spec_ref": "SPEC-017",
    "authorized": True,
    "tier": 3,
    "prev_hash": prev_hash
}

raw = json.dumps(event, sort_keys=True)
event["hash"] = hashlib.sha256(raw.encode()).hexdigest()

with open(ads_path, "a") as f:
    f.write(json.dumps(event) + "\n")
print(f"Logged observation: {event_id}")
