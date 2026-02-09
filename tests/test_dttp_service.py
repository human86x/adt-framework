"""Integration tests for the standalone DTTP service (SPEC-019)."""
import json
import os
import pytest

from adt_core.dttp.config import DTTPConfig
from adt_core.dttp.service import create_dttp_app


@pytest.fixture
def dttp_app(tmp_path):
    """Create a test DTTP service with proper config."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "data").mkdir()

    # ADS log
    ads_dir = project_root / "_cortex" / "ads"
    ads_dir.mkdir(parents=True)
    ads_path = ads_dir / "events.jsonl"
    ads_path.write_text("")

    # Specs config
    config_dir = project_root / "config"
    config_dir.mkdir()
    specs_config = config_dir / "specs.json"
    specs_config.write_text(json.dumps({
        "specs": {
            "SPEC-001": {
                "status": "approved",
                "roles": ["tester"],
                "action_types": ["edit", "create", "delete"],
                "paths": ["data/"]
            }
        }
    }))

    # Jurisdictions config
    juris_config = config_dir / "jurisdictions.json"
    juris_config.write_text(json.dumps({
        "jurisdictions": {
            "tester": ["data/"]
        }
    }))

    config = DTTPConfig(
        port=5002,
        mode="development",
        ads_path=str(ads_path),
        specs_config=str(specs_config),
        jurisdictions_config=str(juris_config),
        project_root=str(project_root),
        project_name="test-project",
    )

    app = create_dttp_app(config)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(dttp_app):
    return dttp_app.test_client()


def _valid_request(**overrides):
    """Build a valid DTTP request payload."""
    payload = {
        "agent": "TEST",
        "role": "tester",
        "spec_id": "SPEC-001",
        "action": "edit",
        "params": {"file": "data/test.txt", "content": "hello"},
        "rationale": "Testing DTTP service",
    }
    payload.update(overrides)
    return payload


# === POST /request ===

class TestDTTPRequest:
    def test_approved_request(self, client):
        resp = client.post("/request", json=_valid_request())
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "allowed"

    def test_denied_wrong_role(self, client):
        resp = client.post("/request", json=_valid_request(role="unauthorized"))
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["status"] == "denied"

    def test_denied_wrong_spec(self, client):
        resp = client.post("/request", json=_valid_request(spec_id="SPEC-999"))
        assert resp.status_code == 403

    def test_denied_wrong_action(self, client):
        resp = client.post("/request", json=_valid_request(action="deploy"))
        assert resp.status_code == 403

    def test_denied_wrong_jurisdiction(self, client):
        resp = client.post("/request", json=_valid_request(
            params={"file": "forbidden/secret.txt", "content": "nope"}
        ))
        assert resp.status_code == 403

    def test_missing_field(self, client):
        payload = _valid_request()
        del payload["rationale"]
        resp = client.post("/request", json=payload)
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "MISSING_FIELD"

    def test_empty_body(self, client):
        resp = client.post("/request", content_type="application/json", data="")
        assert resp.status_code == 400

    def test_invalid_params_type(self, client):
        resp = client.post("/request", json=_valid_request(params="not_a_dict"))
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_TYPE"

    def test_empty_rationale(self, client):
        resp = client.post("/request", json=_valid_request(rationale=""))
        assert resp.status_code == 400

    def test_file_actually_written(self, client, dttp_app):
        client.post("/request", json=_valid_request())
        project_root = dttp_app.config["DTTP"].project_root
        written_file = os.path.join(project_root, "data", "test.txt")
        assert os.path.exists(written_file)
        with open(written_file) as f:
            assert f.read() == "hello"

    def test_ads_events_logged(self, client, dttp_app):
        client.post("/request", json=_valid_request())
        ads_path = dttp_app.config["DTTP"].ads_path
        with open(ads_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        # Should have pre-action (pending) and post-action (completed) events
        assert len(events) >= 2
        action_types = [e["action_type"] for e in events]
        assert any("pending" in t for t in action_types)
        assert any("completed" in t for t in action_types)

    def test_denial_logged_to_ads(self, client, dttp_app):
        client.post("/request", json=_valid_request(role="unauthorized"))
        ads_path = dttp_app.config["DTTP"].ads_path
        with open(ads_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        denied_events = [e for e in events if not e.get("authorized", True)]
        assert len(denied_events) == 1
        assert denied_events[0].get("escalation") is True


# === GET /status ===

class TestDTTPStatus:
    def test_status_endpoint(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["service"] == "dttp"
        assert data["version"] == "0.1.0"
        assert data["mode"] == "development"
        assert data["project"] == "test-project"
        assert data["policy_loaded"] is True
        assert data["specs_count"] == 1
        assert data["jurisdictions_count"] == 1

    def test_status_tracks_requests(self, client):
        client.post("/request", json=_valid_request())
        client.post("/request", json=_valid_request(role="unauthorized"))
        resp = client.get("/status")
        data = resp.get_json()
        assert data["total_requests"] == 2
        assert data["total_denials"] == 1


# === GET /policy ===

class TestDTTPPolicy:
    def test_policy_endpoint(self, client):
        resp = client.get("/policy")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "SPEC-001" in data["specs"]
        assert "tester" in data["jurisdictions"]


# === Security: Path Traversal ===

class TestPathTraversal:
    def test_path_traversal_blocked(self, client):
        resp = client.post("/request", json=_valid_request(
            params={"file": "data/../../etc/passwd", "content": "pwned"}
        ))
        # Should be denied by jurisdiction or path traversal check
        assert resp.status_code in (200, 403)
        data = resp.get_json()
        if data["status"] == "allowed":
            # If policy allowed it, the action handler should have caught it
            assert data["result"]["status"] == "denied"

    def test_dotdot_traversal(self, client):
        resp = client.post("/request", json=_valid_request(
            params={"file": "../outside.txt", "content": "escape"}
        ))
        assert resp.status_code == 403  # Blocked by jurisdiction

    def test_absolute_path_blocked(self, client):
        resp = client.post("/request", json=_valid_request(
            params={"file": "/etc/passwd", "content": "nope"}
        ))
        assert resp.status_code == 403


# === Security: Jurisdiction Boundary ===

class TestJurisdictionBoundary:
    def test_path_prefix_attack(self, client):
        """data2/ should NOT match jurisdiction for data/"""
        resp = client.post("/request", json=_valid_request(
            params={"file": "data2/sneaky.txt", "content": "nope"}
        ))
        assert resp.status_code == 403
