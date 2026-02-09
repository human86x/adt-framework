import hashlib
import json
from typing import Dict, Any

GENESIS_HASH = "0" * 64


def calculate_event_hash(event: Dict[str, Any], prev_hash: str) -> str:
    """Calculates a SHA-256 hash of the event data chained to the previous hash."""
    event_copy = {k: v for k, v in event.items() if k != "hash"}
    event_json = json.dumps(event_copy, sort_keys=True)
    hasher = hashlib.sha256()
    hasher.update(prev_hash.encode("utf-8"))
    hasher.update(event_json.encode("utf-8"))
    return hasher.hexdigest()
