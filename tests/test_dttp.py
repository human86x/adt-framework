import os
import json
import pytest
from adt_core.ads.logger import ADSLogger
from adt_core.sdd.validator import SpecValidator
from adt_core.dttp.jurisdictions import JurisdictionManager
from adt_core.dttp.policy import PolicyEngine
from adt_core.dttp.actions import ActionHandler
from adt_core.dttp.gateway import DTTPGateway

@pytest.fixture
def dttp_setup(tmp_path):
    # Configs
    spec_path = tmp_path / "specs.json"
    spec_config = {
        "specs": {
            "SPEC-001": {
                "status": "approved", "roles": ["tester"], 
                "action_types": ["edit"], "paths": ["data/"]
            }
        }
    }
    spec_path.write_text(json.dumps(spec_config))
    
    juris_path = tmp_path / "juris.json"
    juris_config = {"jurisdictions": {"tester": ["data/"]}}
    juris_path.write_text(json.dumps(juris_config))
    
    ads_path = tmp_path / "events.jsonl"
    project_root = tmp_path / "project"
    project_root.mkdir()
    
    # Initialize
    logger = ADSLogger(str(ads_path))
    validator = SpecValidator(str(spec_path))
    jurisdictions = JurisdictionManager(str(juris_path))
    policy_engine = PolicyEngine(validator, jurisdictions)
    action_handler = ActionHandler(str(project_root))
    gateway = DTTPGateway(policy_engine, action_handler, logger)
    
    return gateway, project_root

def test_gateway_allowed(dttp_setup):
    gateway, project_root = dttp_setup
    resp = gateway.request(
        agent="GEMINI", role="tester", spec_id="SPEC-001",
        action="edit", params={"file": "data/test.txt", "content": "hi"},
        rationale="test"
    )
    assert resp["status"] == "allowed"
    assert os.path.exists(project_root / "data/test.txt")

def test_gateway_denied(dttp_setup):
    gateway, project_root = dttp_setup
    resp = gateway.request(
        agent="GEMINI", role="dev", spec_id="SPEC-001",
        action="edit", params={"file": "data/test.txt", "content": "hi"},
        rationale="test"
    )
    assert resp["status"] == "denied"