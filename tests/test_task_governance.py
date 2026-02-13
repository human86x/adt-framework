import pytest
import json
import os
from datetime import datetime
from adt_center.app import create_app

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
    })
    yield app

@pytest.fixture
def client(app):
    return app.test_client()

def test_get_tasks(client):
    response = client.get("/api/tasks")
    assert response.status_code == 200
    data = response.get_json()
    assert "tasks" in data
    assert isinstance(data["tasks"], list)

def test_update_task_status_agent(client, app):
    # Find a task assigned to Backend_Engineer
    tasks = app.task_manager.list_tasks(assigned_to="Backend_Engineer")
    if not tasks:
        pytest.skip("No tasks assigned to Backend_Engineer for testing")
    
    task = tasks[0]
    task_id = task["id"]
    
    # Try to mark as completed
    response = client.put(f"/api/tasks/{task_id}/status", json={
        "status": "completed",
        "agent": "GEMINI",
        "role": "Backend_Engineer",
        "evidence": "Test evidence for completion"
    })
    
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    
    # Verify task is updated in task manager
    updated_task = app.task_manager.get_task(task_id)
    assert updated_task["status"] == "completed"
    assert updated_task["review_status"] == "pending"
    assert updated_task["evidence"] == "Test evidence for completion"

def test_update_task_status_unauthorized_role(client, app):
    # Find a task NOT assigned to Frontend_Engineer
    tasks = app.task_manager.list_tasks()
    task = next(t for t in tasks if t.get("assigned_to") != "Frontend_Engineer")
    task_id = task["id"]
    
    # Try to mark as completed as Frontend_Engineer
    response = client.put(f"/api/tasks/{task_id}/status", json={
        "status": "completed",
        "agent": "GEMINI",
        "role": "Frontend_Engineer",
        "evidence": "I shouldn't be able to do this"
    })
    
    assert response.status_code == 403
    assert "is assigned to" in response.get_json()["error"]

def test_human_override_approve(client, app):
    tasks = app.task_manager.list_tasks(assigned_to="Backend_Engineer")
    task = tasks[0]
    task_id = task["id"]
    
    # First set to completed (agent action)
    client.put(f"/api/tasks/{task_id}/status", json={
        "status": "completed",
        "agent": "GEMINI",
        "role": "Backend_Engineer",
        "evidence": "Ready for approval"
    })
    
    # Then human approve
    response = client.put(f"/api/tasks/{task_id}/override", json={
        "action": "approve"
    })
    
    assert response.status_code == 200
    updated_task = app.task_manager.get_task(task_id)
    assert updated_task["status"] == "completed"
    assert updated_task["review_status"] == "approved"

def test_human_override_reject(client, app):
    tasks = app.task_manager.list_tasks(assigned_to="Backend_Engineer")
    task = tasks[0]
    task_id = task["id"]
    
    # First set to completed
    client.put(f"/api/tasks/{task_id}/status", json={
        "status": "completed",
        "agent": "GEMINI",
        "role": "Backend_Engineer",
        "evidence": "Testing rejection"
    })
    
    # Then human reject
    response = client.put(f"/api/tasks/{task_id}/override", json={
        "action": "reject",
        "reason": "Missing unit tests"
    })
    
    assert response.status_code == 200
    updated_task = app.task_manager.get_task(task_id)
    assert updated_task["status"] == "in_progress"
    assert updated_task["review_status"] == "rejected"
    assert updated_task["rejection_reason"] == "Missing unit tests"

def test_human_override_reject_missing_reason(client, app):
    tasks = app.task_manager.list_tasks()
    task_id = tasks[0]["id"]
    
    response = client.put(f"/api/tasks/{task_id}/override", json={
        "action": "reject"
    })
    
    assert response.status_code == 400
    assert "Reason is required" in response.get_json()["error"]
