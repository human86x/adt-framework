import requests
import json
import time

BASE_URL = "http://localhost:5001/api/governance"

def test_scr_with_intent():
    print("--- Testing SCR with Intent ID ---")
    
    # 1. Try with invalid intent_id
    payload = {
        "agent": "GEMINI",
        "role": "Backend_Engineer",
        "target_path": "config/specs.json",
        "change_type": "patch",
        "description": "Test SCR with invalid intent",
        "intent_id": "INT-INVALID-999",
        "patch": {"old_string": "foo", "new_string": "bar"}
    }
    
    print("Submitting SCR with INT-INVALID-999...")
    resp = requests.post(f"{BASE_URL}/sovereign-requests", json=payload)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    
    assert resp.status_code == 400
    assert "not found" in resp.json().get("error", "").lower()
    print("SUCCESS: Invalid intent_id rejected.")

    # 2. Get a valid intent_id from the system
    print("\nFetching valid intents...")
    resp = requests.get(f"{BASE_URL}/capabilities/intents")
    intents = resp.json().get("intents", [])
    if not intents:
        print("No intents found. Creating one...")
        intent_payload = {
            "title": "Test Intent for SCR",
            "description": "Testing SCR linking",
            "role": "Systems_Architect",
            "agent": "HUMAN"
        }
        resp = requests.post(f"{BASE_URL}/capabilities/intents", json=intent_payload)
        valid_intent_id = resp.json().get("intent_id")
    else:
        valid_intent_id = intents[0]["intent_id"]
    
    print(f"Using valid intent_id: {valid_intent_id}")

    # 3. Submit SCR with valid intent_id
    payload["intent_id"] = valid_intent_id
    payload["description"] = "Test SCR with valid intent"
    
    print(f"Submitting SCR with {valid_intent_id}...")
    resp = requests.post(f"{BASE_URL}/sovereign-requests", json=payload)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    
    assert resp.status_code == 201
    scr_id = resp.json().get("scr_id")
    print(f"SUCCESS: SCR {scr_id} queued with valid intent_id.")

    # 4. Verify SCR contains intent_id in list
    print("\nVerifying SCR data in list...")
    resp = requests.get(f"{BASE_URL}/sovereign-requests")
    scrs = resp.json().get("requests", [])
    scr = next((r for r in scrs if r["id"] == scr_id), None)
    
    assert scr is not None
    assert scr.get("intent_id") == valid_intent_id
    print("SUCCESS: intent_id persisted in SCR.")

def test_gateway_with_intent():
    print("\n--- Testing DTTP Gateway with Intent ID ---")
    DTTP_URL = "http://localhost:5002/request"
    
    # 1. Get a valid intent_id
    resp = requests.get(f"{BASE_URL}/capabilities/intents")
    valid_intent_id = resp.json().get("intents")[0]["intent_id"]

    # 2. Try edit with invalid intent_id (Tier 3 path for simplicity)
    payload = {
        "agent": "GEMINI",
        "role": "Backend_Engineer",
        "spec_id": "SPEC-017",
        "action": "edit",
        "params": {
            "file": "tests/dummy.txt",
            "content": "test content",
            "intent_id": "INT-INVALID-888"
        },
        "rationale": "Testing gateway intent validation",
        "dry_run": True
    }
    
    print("Submitting DTTP request with INT-INVALID-888...")
    resp = requests.post(DTTP_URL, json=payload)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    
    assert resp.json().get("status") == "denied"
    assert resp.json().get("reason") == "intent_not_found"
    print("SUCCESS: Gateway rejected invalid intent_id.")

    # 3. Try with valid intent_id
    payload["params"]["intent_id"] = valid_intent_id
    print(f"Submitting DTTP request with {valid_intent_id}...")
    resp = requests.post(DTTP_URL, json=payload)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    
    assert resp.json().get("status") == "allowed"
    print("SUCCESS: Gateway allowed valid intent_id.")

if __name__ == "__main__":
    try:
        test_scr_with_intent()
        test_gateway_with_intent()
        print("\nALL TESTS PASSED.")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
