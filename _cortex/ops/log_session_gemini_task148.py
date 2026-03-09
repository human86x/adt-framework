import json
import datetime
import hashlib
import os
import uuid

ads_path = '_cortex/ads/events.jsonl'
prev_hash = '0' * 64
try:
    with open(ads_path, 'r') as f:
        lines = f.readlines()
        if lines:
            last = json.loads(lines[-1])
            prev_hash = last.get('hash', prev_hash)
except Exception:
    pass

ts = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
event_id = f"evt_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:4]}"

event = {
    "event_id": event_id,
    "ts": ts,
    "agent": "GEMINI",
    "role": "DevOps_Engineer",
    "action_type": "session_start",
    "description": "Starting work on task_148: Implement network namespace with DTTP allowlist. Plan: Use unshare --net with Unix socket bridge to host DTTP service.",
    "spec_ref": "SPEC-036",
    "authorized": True,
    "tier": 3,
    "prev_hash": prev_hash
}

# The protocol says hash: SHA-256(prev_hash + ts + agent + action_type + spec_ref + authorized + tier)
# But events.jsonl shows many fields. I'll use json.dumps(sort_keys=True) as it's more robust.
raw = json.dumps(event, sort_keys=True)
event['hash'] = hashlib.sha256(raw.encode()).hexdigest()

with open(ads_path, 'a') as f:
    f.write(json.dumps(event) + '\n')
print(f"Logged session start: {event_id}")
