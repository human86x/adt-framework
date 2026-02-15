import json
import os
import shutil
from datetime import datetime, timezone
from .crypto import GENESIS_HASH, calculate_event_hash
from .schema import ADSEventSchema

def heal_ads(file_path: str):
    """
    Reconstructs the ADS hash chain from genesis.
    Acknowledges gaps as a 'historical integrity reset'.
    """
    backup_path = file_path + ".bak"
    shutil.copy2(file_path, backup_path)
    print(f"Backup created at {backup_path}")

    healed_events = []
    prev_hash = GENESIS_HASH

    with open(file_path, "r") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON at line {line_num}")
                continue

            # Update hashes
            event["prev_hash"] = prev_hash
            event["hash"] = calculate_event_hash(event, prev_hash)
            
            healed_events.append(event)
            prev_hash = event["hash"]

    # Add the reset event
    reset_event = ADSEventSchema.create_event(
        event_id=ADSEventSchema.generate_id("integrity_reset"),
        agent="SYSTEM",
        role="systems_architect",
        action_type="integrity_reset",
        description="Historical integrity reset: ADS hash chain reconstructed from genesis to repair gaps from manual logging.",
        spec_ref="SPEC-020",
        authorized=True,
        tier=1
    )
    reset_event["prev_hash"] = prev_hash
    reset_event["hash"] = calculate_event_hash(reset_event, prev_hash)
    healed_events.append(reset_event)

    # Write back
    with open(file_path, "w") as f:
        for event in healed_events:
            f.write(json.dumps(event) + "\n")

    print(f"ADS healed. {len(healed_events)} events written.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        heal_ads(sys.argv[1])
    else:
        print("Usage: python3 -m adt_core.ads.healer <path_to_events.jsonl>")
