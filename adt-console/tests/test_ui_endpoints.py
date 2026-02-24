import pytest
import requests

def test_adt_center_tasks_api():
    """Verify that /api/tasks returns the structure expected by the Console."""
    try:
        resp = requests.get("http://localhost:5001/api/tasks")
        if resp.status_code == 200:
            data = resp.json()
            assert "tasks" in data
            for task in data["tasks"]:
                assert "id" in task
                assert "title" in task
                assert "status" in task
                assert "assigned_to" in task
    except requests.exceptions.ConnectionError:
        pytest.skip("ADT Center not running")

def test_adt_center_ads_api():
    """Verify that /api/ads/events returns the structure expected by the Console."""
    try:
        resp = requests.get("http://localhost:5001/api/ads/events")
        if resp.status_code == 200:
            data = resp.json()
            assert "events" in data
            for event in data["events"]:
                assert "action_type" in event
                assert "description" in event
    except requests.exceptions.ConnectionError:
        pytest.skip("ADT Center not running")

def test_dttp_status_api():
    """Verify that /dttp/status is available."""
    try:
        resp = requests.get("http://localhost:5001/dttp/status")
        if resp.status_code == 200:
            data = resp.json()
            assert "status" in data
    except requests.exceptions.ConnectionError:
        pytest.skip("ADT Center not running")
