import os
import sys
import json
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def test_delegations_logic():
    # Mock current_app
    current_app = MagicMock()
    
    # Mock ads_query
    current_app.ads_query.get_all_events.return_value = [
        {
            "ts": "2026-02-13T22:00:00Z",
            "role": "Systems_Architect",
            "action_type": "task_reassigned",
            "action_data": {"task_id": "task_001", "reassign_to": "Backend_Engineer"}
        }
    ]
    
    # Mock task_manager
    current_app.task_manager.list_tasks.return_value = [
        {
            "id": "task_005",
            "delegation": {
                "delegated_at": "2026-02-09T10:00:00Z",
                "delegated_by": {"role": "Systems_Architect", "agent": "CLAUDE"},
                "delegated_to": {"role": "Frontend_Engineer", "agent": "GEMINI"}
            }
        }
    ]
    
    # Logic from governance_routes.py
    events = current_app.ads_query.get_all_events()
    delegations = []
    
    for event in events:
        if event.get("action_type") in ["task_status_updated", "task_approved", "task_rejected", "task_reassigned", "task_reopened"]:
            delegations.append({
                "ts": event.get("ts"),
                "task_id": event.get("action_data", {}).get("task_id"),
                "from": event.get("role"),
                "to": event.get("action_data", {}).get("reassign_to") or event.get("role"),
                "action": event.get("action_type"),
                "agent": event.get("agent", "unknown")
            })
            
    tasks = current_app.task_manager.list_tasks()
    for task in tasks:
        if task.get("delegation"):
            d = task["delegation"]
            delegations.append({
                "ts": d.get("delegated_at"),
                "task_id": task["id"],
                "from": d.get("delegated_by", {}).get("role"),
                "to": d.get("delegated_to", {}).get("role"),
                "action": "task_delegated",
                "agent": d.get("delegated_by", {}).get("agent")
            })
            
    delegations.sort(key=lambda x: x.get("ts", ""), reverse=True)
    
    print(json.dumps(delegations, indent=2))
    assert len(delegations) == 2
    assert delegations[0]["task_id"] == "task_001"
    assert delegations[1]["task_id"] == "task_005"
    print("Test Passed!")

if __name__ == "__main__":
    test_delegations_logic()
