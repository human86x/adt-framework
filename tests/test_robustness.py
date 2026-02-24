import os
import json
import pytest
import threading
from adt_core.ads.logger import ADSLogger
from adt_core.ads.schema import ADSEventSchema
from adt_core.ads.integrity import ADSIntegrity
from adt_core.ads.query import ADSQuery
from adt_core.sdd.validator import SpecValidator
from adt_core.dttp.jurisdictions import JurisdictionManager
from adt_core.dttp.policy import PolicyEngine
from adt_core.dttp.actions import ActionHandler
from adt_core.dttp.gateway import DTTPGateway

@pytest.fixture
def full_setup(tmp_path):
    # Configs
    spec_path = tmp_path / "specs.json"
    spec_config = {
        "specs": {
            "SPEC-001": {
                "status": "approved", "roles": ["tester"], 
                "action_types": ["edit", "patch"], "paths": ["data/"]
            },
            "SPEC-002": {
                "status": "approved", "roles": ["admin"],
                "action_types": ["edit"], "paths": ["adt_core/ads/logger.py"]
            }
        }
    }
    spec_path.write_text(json.dumps(spec_config))
    
    juris_path = tmp_path / "juris.json"
    juris_config = {
        "jurisdictions": {
            "tester": ["data/"],
            "admin": ["adt_core/"]
        }
    }
    juris_path.write_text(json.dumps(juris_config))
    
    ads_path = tmp_path / "events.jsonl"
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "data").mkdir()
    (project_root / "adt_core/ads").mkdir(parents=True)
    (project_root / "adt_core/ads/logger.py").write_text("# logger")
    
    # Initialize
    logger = ADSLogger(str(ads_path))
    query = ADSQuery(str(ads_path))
    validator = SpecValidator(str(spec_path))
    jurisdictions = JurisdictionManager(str(juris_path))
    policy_engine = PolicyEngine(validator, jurisdictions)
    action_handler = ActionHandler(str(project_root))
    gateway = DTTPGateway(policy_engine, action_handler, logger)
    
    return gateway, project_root, ads_path, query

def test_path_traversal_prevention(full_setup):
    gateway, project_root, _, _ = full_setup
    # Attempt to write outside project root
    resp = gateway.request(
        agent="GEMINI", role="tester", spec_id="SPEC-001",
        action="edit", params={"file": "../secret.txt", "content": "pwned"},
        rationale="malicious"
    )
    assert resp["status"] == "denied"
    assert not os.path.exists(project_root.parent / "secret.txt")

def test_jurisdiction_boundary(full_setup):
    gateway, _, _, _ = full_setup
    # tester has access to data/, not other_data/
    resp = gateway.request(
        agent="GEMINI", role="tester", spec_id="SPEC-001",
        action="edit", params={"file": "other_data/test.txt", "content": "hi"},
        rationale="boundary test"
    )
    assert resp["status"] == "denied"

def test_sovereign_path_rejection(full_setup):
    gateway, _, _, _ = full_setup
    # Attempt to modify a sovereign path
    resp = gateway.request(
        agent="GEMINI", role="admin", spec_id="SPEC-001",
        action="edit", params={"file": "config/specs.json", "content": "{}"},
        rationale="sovereign test"
    )
    assert resp["status"] == "denied"
    assert resp["reason"] == "sovereign_path_violation"

def test_tier2_authorization(full_setup):
    gateway, _, _, _ = full_setup
    # admin has project/ but logger.py is Tier 2. 
    # SPEC-002 explicitly lists logger.py, so it should be allowed WITH justification.
    
    # Fail: missing justification
    resp = gateway.request(
        agent="GEMINI", role="admin", spec_id="SPEC-002",
        action="edit", params={"file": "adt_core/ads/logger.py", "content": "# new logger"},
        rationale="tier 2 test"
    )
    assert resp["status"] == "denied"
    assert resp["reason"] == "tier2_authorization_required"
    
    # Success: with justification
    resp = gateway.request(
        agent="GEMINI", role="admin", spec_id="SPEC-002",
        action="edit", params={
            "file": "adt_core/ads/logger.py", 
            "content": "# new logger",
            "tier2_justification": "Necessary fix"
        },
        rationale="tier 2 test"
    )
    assert resp["status"] == "allowed"

def test_ads_concurrent_writes(full_setup):
    _, _, ads_path, _ = full_setup
    logger = ADSLogger(str(ads_path))
    
    def log_events(name, count):
        for i in range(count):
            event = ADSEventSchema.create_event(
                event_id=f"evt_{name}_{i}",
                agent="TEST", role="tester", action_type="test",
                description=f"Event {i} from {name}", spec_ref="SPEC-001"
            )
            logger.log(event)

    threads = []
    for i in range(5):
        t = threading.Thread(target=log_events, args=(f"T{i}", 20))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    is_valid, errors = ADSIntegrity.verify_chain(str(ads_path))
    assert is_valid
    assert not errors
    
    with open(ads_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 100

def test_active_sessions_counting(full_setup):
    _, _, _, query = full_setup
    logger = ADSLogger(query.file_path)
    
    def log_session(agent, action):
        event = ADSEventSchema.create_event(
            event_id=f"evt_{agent}_{action}_{uuid_hex()}",
            agent=agent, role="tester", action_type=f"session_{action}",
            description=f"{agent} session {action}", spec_ref="SPEC-001"
        )
        logger.log(event)
        
    import uuid
    def uuid_hex(): return uuid.uuid4().hex[:4]

    log_session("CLAUDE", "start")
    log_session("GEMINI", "start")
    assert query.get_active_sessions() == 2
    
    log_session("CLAUDE", "end")
    assert query.get_active_sessions() == 1
    
    log_session("GEMINI", "end")
    assert query.get_active_sessions() == 0
    
    # Multiple starts
    log_session("CLAUDE", "start")
    log_session("CLAUDE", "start") # Should still count as 1 if we match last event
    assert query.get_active_sessions() == 1
