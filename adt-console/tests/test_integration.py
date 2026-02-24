import pytest
import requests
import json
import time

BASE_URL = "http://localhost:5001/api"

def test_governance_api_flow():
    """Verify the full governance configuration flow: GET -> PUT -> GET."""
    try:
        # 1. Get current roles
        resp = requests.get(f"{BASE_URL}/governance/roles")
        assert resp.status_code == 200
        data = resp.json()
        assert "roles" in data
        
        # 2. Update a role (Backend_Engineer)
        role = "Backend_Engineer"
        old_config = data["roles"][role]
        
        new_paths = list(old_config["paths"])
        if "tests/integration/" not in new_paths:
            new_paths.append("tests/integration/")
            
        payload = {
            "paths": new_paths,
            "action_types": old_config["action_types"],
            "locked": False
        }
        
        put_resp = requests.put(f"{BASE_URL}/governance/roles/{role}", json=payload)
        assert put_resp.status_code == 200
        
        # 3. Verify update
        verify_resp = requests.get(f"{BASE_URL}/governance/roles")
        new_data = verify_resp.json()
        assert "tests/integration/" in new_data["roles"][role]["paths"]
        
        # 4. Check ADS for the log
        ads_resp = requests.get("http://localhost:5001/api/ads/events")
        events = ads_resp.json()
        last_event = events[-1]
        assert last_event["action_type"] == "governance_config_updated"
        assert role in last_event["description"]
        
    except requests.exceptions.ConnectionError:
        pytest.skip("ADT Center not running")

def test_session_lifecycle_logging():
    """Verify that starting/ending sessions logs correctly to ADS."""
    try:
        agent = "TEST_AGENT"
        role = "Backend_Engineer"
        spec = "SPEC-021"
        
        # Start session
        start_payload = {
            "agent": agent,
            "role": role,
            "spec_id": spec,
            "session_id": "test_123"
        }
        resp = requests.post(f"{BASE_URL}/sessions/start", json=start_payload)
        assert resp.status_code == 200
        
        # Verify ADS
        ads_resp = requests.get("http://localhost:5001/api/ads/events")
        events = ads_resp.json()
        assert any(e["action_type"] == "session_start" and e["agent"] == agent for e in events)
        
        # End session
        requests.post(f"{BASE_URL}/sessions/end", json=start_payload)
        
        # Verify ADS
        ads_resp = requests.get("http://localhost:5001/api/ads/events")
        events = ads_resp.json()
        assert any(e["action_type"] == "session_end" and e["agent"] == agent for e in events)
        
    except requests.exceptions.ConnectionError:
        pytest.skip("ADT Center not running")

if __name__ == "__main__":
    import sys
    pytest.main([__file__])
