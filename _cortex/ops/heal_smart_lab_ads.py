import json
import os
import sys

# Add framework root to path
sys.path.append('/home/human/Projects/adt-framework')

from adt_core.ads.crypto import GENESIS_HASH, calculate_event_hash

def heal_ads(file_path):
    if not os.path.exists(file_path):
        print(f'File {file_path} not found.')
        return

    print(f'Healing {file_path}...')
    temp_path = file_path + '.heal'
    
    with open(file_path, 'r') as f_in, open(temp_path, 'w') as f_out:
        prev_hash = GENESIS_HASH
        line_count = 0
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            
            try:
                event = json.loads(line)
                # Keep original data but recalculate hashes
                event['prev_hash'] = prev_hash
                new_hash = calculate_event_hash(event, prev_hash)
                event['hash'] = new_hash
                
                f_out.write(json.dumps(event) + '\n')
                prev_hash = new_hash
                line_count += 1
            except Exception as e:
                print(f'Error processing line: {line[:50]}... Error: {e}')
                
    print(f'Processed {line_count} events.')
    backup_path = file_path + '.bak_corrupted'
    os.rename(file_path, backup_path)
    os.rename(temp_path, file_path)
    print(f'ADS Healed successfully. Original backed up to {backup_path}')

if __name__ == '__main__':
    heal_ads('/home/human/Projects/smart-lab/_cortex/ads/events.jsonl')