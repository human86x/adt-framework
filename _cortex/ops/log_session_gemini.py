import json
import datetime
import os
from hashlib import sha256

ADS_PATH = "_cortex/ads/events.jsonl"

def get_last_event():
    if not os.path.exists(ADS_PATH):
        return None
    with open(ADS_PATH, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        while pos > 0:
            pos -= 1
            f.seek(pos)
            if f.read(1) == b"
":
                line = f.readline()
                if line.strip():
                    return json.loads(line)
        f.seek(0)
        line = f.readline()
        if line.strip():
            return json.loads(line)
    return None

last_event = get_last_event()
prev_hash = last_event["hash"] if last_event else "0" * 64

event = {
    "event_id": f"evt_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_001",
    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    "agent": "GEMINI",
    "role": "Frontend_Engineer",
    "action_type": "session_start",
    "description": "Frontend Engineer session started. Initializing work on REQ-023 (Shatterglass UI) and finalizing REQ-020/021 documentation.",
    "spec_ref": "SPEC-017",
    "authorized": True,
    "tier": 3,
    "prev_hash": prev_hash
}

event_json = json.dumps(event, sort_keys=True)
event["hash"] = sha256(event_json.encode()).hexdigest()

with open(ADS_PATH, "a") as f:
    f.write(json.dumps(event) + "
")
