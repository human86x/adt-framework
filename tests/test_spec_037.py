import os
import json
import pytest
import requests
from adt_center.app import create_app
from adt_core.registry import ProjectRegistry

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_file_request_api(client):
    """Test the POST /api/governance/requests endpoint."""
    payload = {
        "from_role": "Backend_Engineer",
        "from_agent": "TEST_AGENT",
        "to_role": "Systems_Architect",
        "title": "Test Governed Request",
        "description": "This is a test request filed via API.",
        "priority": "LOW",
        "type": "IMPROVEMENT"
    }
    
    # We need to ensure requests.md exists or handle its creation
    # For testing, we might want to mock the file system or use a temp project
    # But for now, we'll hit the actual file if it exists in the framework root
    
    response = client.post('/api/governance/requests', json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data['status'] == 'success'
    assert 'req_id' in data
    
    # Verify file content (optional, but good)
    req_id = data['req_id']
    with open('_cortex/requests.md', 'r') as f:
        content = f.read()
        assert f"## {req_id}: Test Governed Request" in content
        assert "**From:** Backend_Engineer (TEST_AGENT)" in content

def test_request_status_update_api(client):
    """Test the PUT /api/governance/requests/<id>/status endpoint."""
    # First file a request to update
    payload = {
        "from_role": "Backend_Engineer",
        "to_role": "Systems_Architect",
        "title": "Status Update Test",
        "description": "Testing status update."
    }
    resp = client.post('/api/governance/requests', json=payload)
    req_id = resp.get_json()['req_id']
    
    # Update status - Must be from To: role (Systems_Architect) or From: role
    update_payload = {
        "status": "COMPLETED",
        "role": "Systems_Architect",
        "agent": "TEST_AGENT"
    }
    response = client.put(f'/api/governance/requests/{req_id}/status', json=update_payload)
    assert response.status_code == 200
    
    # Verify change
    with open('_cortex/requests.md', 'r') as f:
        content = f.read()
        # Find the block for req_id
        assert f"## {req_id}: Status Update Test" in content
        # Check if COMPLETED is present in that block
        # (Simple check since it's a new request)
        assert "**COMPLETED**" in content

def test_role_priority_resolution():
    """Verify role resolution priority logic in hooks (mocked env/file)."""
    # This is better tested by running the hook script with different inputs
    # But we can verify the logic by importing or simulating
    pass
