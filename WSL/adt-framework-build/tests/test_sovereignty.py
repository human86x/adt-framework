"""Integration tests for SPEC-020 Self-Governance Integrity."""
import json
import os
import pytest

from adt_core.dttp.config import DTTPConfig
from adt_core.dttp.service import create_dttp_app
from adt_core.ads.logger import ADSLogger
from adt_core.ads.schema import ADSEventSchema


@pytest.fixture
def dttp_app(tmp_path):
    """Create a test DTTP service with SPEC-020 configurations."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    
    # Create required directories
    (project_root / "config").mkdir()
    (project_root / "_cortex" / "ads").mkdir(parents=True)
    (project_root / "adt_core" / "dttp").mkdir(parents=True)
    (project_root / "data").mkdir()

    # ADS log
    ads_path = project_root / "_cortex" / "ads" / "events.jsonl"
    ads_path.write_text("")

    # Specs config (Sovereign path)
    specs_config = project_root / "config" / "specs.json"
    specs_config.write_text(json.dumps({
        "specs": {
            "SPEC-020": {
                "status": "approved",
                "roles": ["admin"],
                "action_types": ["edit"],
                "paths": ["config/specs.json", "adt_core/dttp/gateway.py"]
            },
            "SPEC-WILDCARD": {
                "status": "approved",
                "roles": ["admin"],
                "action_types": ["edit"],
                "paths": ["adt_core/dttp/"]
            },
            "SPEC-REGULAR": {
                "status": "approved",
                "roles": ["tester"],
                "action_types": ["edit"],
                "paths": ["data/"]
            }
        }
    }))

    # Jurisdictions config (Sovereign path)
    juris_config = project_root / "config" / "jurisdictions.json"
    juris_config.write_text(json.dumps({
        "jurisdictions": {
            "admin": ["config/", "adt_core/", "_cortex/"],
            "tester": ["data/"]
        }
    }))

    # DTTP config (Sovereign path)
    dttp_json = project_root / "config" / "dttp.json"
    dttp_json.write_text(json.dumps({}))

    config = DTTPConfig(
        port=5002,
        mode="development",
        ads_path=str(ads_path),
        specs_config=str(specs_config),
        jurisdictions_config=str(juris_config),
        project_root=str(project_root),
        project_name="sovereign-test",
    )

    app = create_dttp_app(config)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(dttp_app):
    return dttp_app.test_client()


def _req(role="admin", spec="SPEC-020", file="data/test.txt", **overrides):
    payload = {
        "agent": "TEST",
        "role": role,
        "spec_id": spec,
        "action": "edit",
        "params": {"file": file, "content": "test"},
        "rationale": "Sovereignty testing",
    }
    payload.update(overrides)
    return payload


class TestSovereignPaths:
    """Tier 1: Sovereign Path Rejection Tests."""

    @pytest.mark.parametrize("path", [
        "config/specs.json",
        "config/jurisdictions.json",
        "config/dttp.json",
        "_cortex/AI_PROTOCOL.md",
        "_cortex/MASTER_PLAN.md"
    ])
    def test_sovereign_path_rejection(self, client, path):
        """Tier 1 paths must be rejected regardless of role or spec."""
        resp = client.post("/request", json=_req(file=path))
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["reason"] == "sovereign_path_violation"

    def test_sovereign_denial_logging(self, client, dttp_app):
        """Tier 1 denials must be logged with tier 1 and escalation."""
        client.post("/request", json=_req(file="config/specs.json"))
        ads_path = dttp_app.config["DTTP"].ads_path
        with open(ads_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        
        denial = events[-1]
        assert denial["action_type"] == "sovereign_path_violation"
        assert denial["authorized"] is False
        assert denial["tier"] == 1
        assert denial["escalation"] is True


class TestConstitutionalPaths:
    """Tier 2: Constitutional Path Elevated Authorization Tests."""

    @pytest.mark.parametrize("path", [
        "adt_core/dttp/gateway.py",
        "adt_core/ads/logger.py"
    ])
    def test_tier2_denied_no_justification(self, client, path):
        """Tier 2 paths require tier2_justification."""
        resp = client.post("/request", json=_req(file=path))
        assert resp.status_code == 403
        assert resp.get_json()["reason"] == "tier2_authorization_required"

    def test_tier2_denied_wildcard(self, client):
        """Tier 2 paths require explicit file listing in spec, not wildcard."""
        payload = _req(
            spec="SPEC-WILDCARD", 
            file="adt_core/dttp/gateway.py",
            params={"file": "adt_core/dttp/gateway.py", "content": "test", "tier2_justification": "needed"}
        )
        resp = client.post("/request", json=payload)
        assert resp.status_code == 403
        assert resp.get_json()["reason"] == "tier2_authorization_required"

    def test_tier2_approved(self, client):
        """Tier 2 approved with explicit spec listing and justification."""
        payload = _req(
            spec="SPEC-020",
            file="adt_core/dttp/gateway.py",
            params={"file": "adt_core/dttp/gateway.py", "content": "test", "tier2_justification": "Updating gateway for SPEC-020"}
        )
        resp = client.post("/request", json=payload)
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "allowed"

    def test_tier2_logging(self, client, dttp_app):
        """Tier 2 approved requests log tier2_authorized and tier: 2."""
        payload = _req(
            spec="SPEC-020",
            file="adt_core/dttp/gateway.py",
            params={"file": "adt_core/dttp/gateway.py", "content": "test", "tier2_justification": "test"}
        )
        client.post("/request", json=payload)
        ads_path = dttp_app.config["DTTP"].ads_path
        with open(ads_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        
        # Look for the pending event which should be changed to tier2_authorized
        authorized_event = [e for e in events if e["action_type"] == "tier2_authorized"][0]
        assert authorized_event["tier"] == 2
        assert authorized_event["authorized"] is True


class TestBreakGlass:
    """Break-glass Procedure Tests."""

    def test_break_glass_logging(self, tmp_path):
        """The ADSLogger must support manual break-glass events from agent HUMAN."""
        ads_path = tmp_path / "break_glass.jsonl"
        logger = ADSLogger(str(ads_path))
        
        event = ADSEventSchema.create_event(
            event_id="evt_manual_break_glass",
            agent="HUMAN",
            role="sovereign",
            action_type="break_glass",
            description="Manual repair of corrupted gateway.py",
            spec_ref="SPEC-020",
            authorized=True,
            tier=1,
            reason="Total lockout due to policy bug"
        )
        
        logger.log(event)
        
        with open(ads_path) as f:
            logged = json.loads(f.readline())
        
        assert logged["agent"] == "HUMAN"
        assert logged["action_type"] == "break_glass"
        assert logged["tier"] == 1

    def test_invalid_tier_rejected(self, tmp_path):
        """The ADS schema must reject invalid tier values."""
        event = ADSEventSchema.create_event(
            event_id="evt_bad_tier",
            agent="TEST",
            role="tester",
            action_type="test",
            description="test",
            spec_ref="SPEC-001",
            tier=4  # Invalid
        )
        assert ADSEventSchema.validate(event) is False
