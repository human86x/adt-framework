import os
import sys
import re
import json

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adt_center.api.governance_routes import _parse_requests

def test_parser():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    requests_path = os.path.join(root, "_cortex", "requests.md")
    
    if not os.path.exists(requests_path):
        print(f"Error: {requests_path} not found")
        return

    requests = _parse_requests(requests_path)
    print(f"Parsed {len(requests)} requests.")
    
    for req in requests:
        print(f"[{req['id']}] {req['title']} ({req['status']})")
        
    # Specifically check REQ-014
    req14 = next((r for r in requests if r['id'] == 'REQ-014'), None)
    if req14:
        print("\nREQ-014 Detail:")
        print(f"  Title: {req14['title']}")
        print(f"  Status: {req14['status']}")
        print(f"  Summary: {req14['summary']}")
    else:
        print("\nREQ-014 NOT FOUND!")

if __name__ == "__main__":
    test_parser()
