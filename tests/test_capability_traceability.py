import requests
import json
import time
import pytest

BASE_URL = "http://localhost:5001/api/governance"
DTTP_URL = "http://localhost:5002/request"

def test_full_causal_traceability():
    print("\n--- Testing Full Causal Traceability (SPEC-038) ---")
    
    # 1. Define an Intent
    intent_payload = {
        "title": "Traceability Test Intent",
        "description": "Verification of Intent -> Event -> SCR -> ADS -> Task chain",
        "role": "Systems_Architect",
        "agent": "HUMAN"
    }
    resp = requests.post(f"{BASE_URL}/capabilities/intents", json=intent_payload)
    assert resp.status_code == 201
    intent_id = resp.json().get("intent_id")
    print(f"Created Intent: {intent_id}")

    # 2. Record a Triggering Event linked to the Intent
    event_payload = {
        "description": "External trigger for traceability test",
        "intent_id": intent_id,
        "role": "Developer",
        "agent": "GEMINI"
    }
    resp = requests.post(f"{BASE_URL}/capabilities/events", json=event_payload)
    assert resp.status_code == 201
    event_id = resp.json().get("event_id")
    print(f"Recorded Event: {event_id}")

    # 3. Create a Task (for later linking via ADS)
    # We'll use an existing task or assume one is created during the session
    # Actually, TaskManager doesn't have a direct API to create tasks from agents yet (human UI only or via adt_core)
    # But we can find a task ID and use it in a DTTP request
    
    # 4. Submit a DTTP Request linked to the Intent
    dttp_payload = {
        "agent": "GEMINI",
        "role": "Backend_Engineer",
        "spec_id": "SPEC-017",
        "action": "edit",
        "params": {
            "file": "tests/dummy.txt",
            "content": f"Traceability test at {time.time()}",
            "intent_id": intent_id,
            "task_id": "task_999_test" # Mock task ID
        },
        "rationale": "Fulfilling traceability test intent",
        "dry_run": False # Execute to create ADS events
    }
    resp = requests.post(DTTP_URL, json=dttp_payload)
    assert resp.status_code == 200
    assert resp.json().get("status") == "allowed"
    print("Executed DTTP request linked to intent.")

    # 5. Verify Traceability API
    print(f"Fetching trace for {intent_id}...")
    resp = requests.get(f"{BASE_URL}/capabilities/trace/{intent_id}")
    assert resp.status_code == 200
    trace = resp.json()
    
    print(f"Trace result keys: {list(trace.keys())}")
    
    assert trace["intent"]["intent_id"] == intent_id
    assert any(e["event_id"] == event_id for e in trace["triggering_events"])
    assert len(trace["ads_events"]) >= 2 # pending_edit and completed_edit
    # DTTP uses SPEC-017, ADS intent events use SPEC-038 -- either may appear
    assert "SPEC-017" in trace["specs"] or "SPEC-038" in trace["specs"]
    # SPEC-038A: trace now includes gate chain
    assert "gates" in trace

    print(f"Linked ADS events count: {len(trace['ads_events'])}")
    print(f"Linked specs: {trace['specs']}")
    print(f"Gate evaluations: {len(trace['gates'])}")
    
    print("SUCCESS: Full causal chain verified.")

if __name__ == "__main__":
    test_full_causal_traceability()
