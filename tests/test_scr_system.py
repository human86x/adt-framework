import os
import json
import pytest
import requests
from datetime import datetime, timezone

# Constants for testing
PANEL_URL = "http://localhost:5001"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def test_scr_lifecycle():
    """Test the full lifecycle of a Sovereign Change Request."""
    # 1. Submit SCR
    target_path = "config/specs.json"
    description = "Integration test SCR"
    scr_payload = {
        "agent": "TEST_AGENT",
        "role": "Backend_Engineer",
        "target_path": target_path,
        "change_type": "json_merge",
        "description": description,
        "merge_data": {
            "specs": {
                "SPEC-TEST": {
                    "title": "Test Spec",
                    "status": "draft"
                }
            }
        }
    }
    
    resp = requests.post(f"{PANEL_URL}/api/governance/sovereign-requests", json=scr_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "scr_id" in data
    scr_id = data["scr_id"]
    
    # 2. Verify in list
    resp = requests.get(f"{PANEL_URL}/api/governance/sovereign-requests?status=pending")
    assert resp.status_code == 200
    scrs = resp.json().get("requests", [])
    assert any(s["id"] == scr_id for s in scrs)
    
    # 3. Authorize SCR
    resp = requests.put(f"{PANEL_URL}/api/governance/sovereign-requests/{scr_id}", 
                        json={"action": "authorize"})
    assert resp.status_code == 200
    assert resp.json()["new_status"] == "authorized"
    
    # 4. Verify file update
    specs_path = os.path.join(PROJECT_ROOT, "config", "specs.json")
    with open(specs_path, "r") as f:
        specs_data = json.load(f)
    assert "SPEC-TEST" in specs_data["specs"]
    
    # 5. Cleanup (manual revert for now)
    del specs_data["specs"]["SPEC-TEST"]
    with open(specs_path, "w") as f:
        json.dump(specs_data, f, indent=2)

def test_scr_rejection():
    """Test SCR rejection flow."""
    scr_payload = {
        "agent": "TEST_AGENT",
        "role": "Backend_Engineer",
        "target_path": "config/dttp.json",
        "change_type": "patch",
        "description": "Reject this",
        "patch": {"old_string": "foo", "new_string": "bar"}
    }
    
    resp = requests.post(f"{PANEL_URL}/api/governance/sovereign-requests", json=scr_payload)
    scr_id = resp.json()["scr_id"]
    
    resp = requests.put(f"{PANEL_URL}/api/governance/sovereign-requests/{scr_id}", 
                        json={"action": "reject", "reason": "Testing rejection"})
    assert resp.status_code == 200
    assert resp.json()["new_status"] == "rejected"

def test_scr_human_only():
    """Test that agents cannot authorize SCRs."""
    scr_payload = {
        "agent": "TEST_AGENT",
        "role": "Backend_Engineer",
        "target_path": "config/dttp.json",
        "change_type": "append",
        "content": "\n# test"
    }
    resp = requests.post(f"{PANEL_URL}/api/governance/sovereign-requests", json=scr_payload)
    scr_id = resp.json()["scr_id"]
    
    # Simulate agent call with X-Agent header
    resp = requests.put(f"{PANEL_URL}/api/governance/sovereign-requests/{scr_id}", 
                        json={"action": "authorize"},
                        headers={"X-Agent": "CLAUDE"})
    assert resp.status_code == 403
    assert "Only humans" in resp.json()["error"]

def test_scr_invalid_path():
    """Test that non-sovereign paths are rejected for SCR."""
    scr_payload = {
        "agent": "TEST_AGENT",
        "role": "Backend_Engineer",
        "target_path": "README.md", # Not sovereign
        "change_type": "append",
        "content": "test"
    }
    resp = requests.post(f"{PANEL_URL}/api/governance/sovereign-requests", json=scr_payload)
    assert resp.status_code == 400
    assert "not a sovereign path" in resp.json()["error"]
