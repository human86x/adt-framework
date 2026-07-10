import sys
import os

# Add the project root to sys.path to import adt_core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from adt_core.ads.integrity import ADSIntegrity

file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "events.jsonl"))
is_valid, errors = ADSIntegrity.verify_chain(file_path)

if is_valid:
    print("ADS Integrity: VERIFIED")
else:
    print("ADS Integrity: FAILED")
    for error in errors:
        print(f"  - {error}")
