import json
import os
import sys

# Add project root to path so we can import adt_core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adt_core.ads.crypto import GENESIS_HASH, calculate_event_hash

def heal_ads(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} not found.")
        return

    print(f"Healing {file_path}...")
    temp_path = file_path + ".heal"
    
    with open(file_path, "r") as f_in, open(temp_path, "w") as f_out:
        prev_hash = GENESIS_HASH
        line_count = 0
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            
            try:
                event = json.loads(line)
                # Keep original data but recalculate hashes
                event["prev_hash"] = prev_hash
                new_hash = calculate_event_hash(event, prev_hash)
                event["hash"] = new_hash
                
                f_out.write(json.dumps(event) + "\n")
                prev_hash = new_hash
                line_count += 1
            except Exception as e:
                print(f"Error processing line: {line[:50]}... Error: {e}")
                
    print(f"Processed {line_count} events.")
    # Backup original and swap
    # Use different backup extension to avoid conflict with existing .pre-heal
    backup_path = file_path + ".healed_backup"
    os.rename(file_path, backup_path)
    os.rename(temp_path, file_path)
    print(f"ADS Healed successfully. Original backed up to {backup_path}")

if __name__ == "__main__":
    # Path relative to script in _cortex/
    ads_file = os.path.join(os.path.dirname(__file__), "ads", "events.jsonl")
    heal_ads(ads_file)
