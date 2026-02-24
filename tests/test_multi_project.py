import os
import json
import pytest
import shutil
import subprocess
import sys
from adt_core.registry import ProjectRegistry
from adt_core.cli import init_command

class Args:
    """Mock args for CLI commands."""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

@pytest.fixture
def temp_home(tmp_path):
    """Mock home directory for project registry."""
    home = tmp_path / "home"
    home.mkdir()
    return home

@pytest.fixture
def registry(temp_home):
    registry_path = temp_home / ".adt" / "projects.json"
    return ProjectRegistry(str(registry_path))

def test_registry_initialization(registry, temp_home):
    """Test that registry is initialized with the framework project."""
    projects = registry.list_projects()
    assert "adt-framework" in projects
    assert projects["adt-framework"]["is_framework"] is True
    assert projects["adt-framework"]["dttp_port"] == 5002

def test_adt_init_scaffold(tmp_path, temp_home):
    """Test SPEC-031 Phase A: adt init command creates the correct scaffold."""
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    
    registry_path = temp_home / ".adt" / "projects.json"
    # Mock ProjectRegistry to use temp_home in init_command
    import adt_core.cli
    original_registry = adt_core.cli.ProjectRegistry
    adt_core.cli.ProjectRegistry = lambda: ProjectRegistry(str(registry_path))
    
    try:
        args = Args(path=str(project_dir), name="my-project", detect=True, port=5005)
        init_command(args)
        
        # Verify directories
        assert (project_dir / "_cortex" / "ads").exists()
        assert (project_dir / "_cortex" / "specs").exists()
        assert (project_dir / "config").exists()
        
        # Verify config files
        assert (project_dir / "config" / "dttp.json").exists()
        with open(project_dir / "config" / "dttp.json") as f:
            dttp_cfg = json.load(f)
            assert dttp_cfg["name"] == "my-project"
            assert dttp_cfg["port"] == 5005
            
        assert (project_dir / "config" / "jurisdictions.json").exists()
        assert (project_dir / "config" / "specs.json").exists()
        
        # Verify registry entry
        reg = ProjectRegistry(str(registry_path))
        project = reg.get_project("my-project")
        assert project is not None
        assert project["dttp_port"] == 5005
        assert project["path"] == str(project_dir)
        
    finally:
        adt_core.cli.ProjectRegistry = original_registry

def test_port_auto_assignment(tmp_path, temp_home):
    """Test SPEC-031 Phase A: Port auto-assignment and collision detection."""
    registry_path = temp_home / ".adt" / "projects.json"
    reg = ProjectRegistry(str(registry_path))
    
    p1 = tmp_path / "p1"
    p1.mkdir()
    reg.register_project("p1", str(p1))
    
    p2 = tmp_path / "p2"
    p2.mkdir()
    reg.register_project("p2", str(p2))
    
    projects = reg.list_projects()
    assert projects["p1"]["dttp_port"] == 5003
    assert projects["p2"]["dttp_port"] == 5004
    assert reg.next_available_port() == 5005

def test_api_project_filtering(tmp_path, temp_home):
    """Test SPEC-031 Phase C: API ?project= filter."""
    from adt_center.app import create_app
    
    # Setup two projects
    p1_dir = tmp_path / "p1"
    p1_dir.mkdir()
    os.makedirs(p1_dir / "_cortex" / "ads")
    os.makedirs(p1_dir / "_cortex" / "specs")
    with open(p1_dir / "_cortex" / "tasks.json", "w") as f:
        json.dump({"project": "p1", "tasks": [{"id": "t1", "title": "Task P1"}]}, f)
        
    p2_dir = tmp_path / "p2"
    p2_dir.mkdir()
    os.makedirs(p2_dir / "_cortex" / "ads")
    os.makedirs(p2_dir / "_cortex" / "specs")
    with open(p2_dir / "_cortex" / "tasks.json", "w") as f:
        json.dump({"project": "p2", "tasks": [{"id": "t2", "title": "Task P2"}]}, f)

    registry_path = temp_home / ".adt" / "projects.json"
    reg = ProjectRegistry(str(registry_path))
    reg.register_project("p1", str(p1_dir))
    reg.register_project("p2", str(p2_dir))

    # Mock ProjectRegistry in app
    import adt_center.app
    original_PR = adt_center.app.ProjectRegistry
    adt_center.app.ProjectRegistry = lambda: ProjectRegistry(str(registry_path))

    try:
        app = create_app()
        client = app.test_client()
        
        # Test /api/tasks?project=p1
        resp = client.get("/api/tasks?project=p1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["id"] == "t1"
        
        # Test /api/tasks?project=p2
        resp = client.get("/api/tasks?project=p2")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["id"] == "t2"
        
    finally:
        adt_center.app.ProjectRegistry = original_PR

def test_dttp_isolation(tmp_path):
    """Test SPEC-031 Phase B: DTTP isolation (framework vs external)."""
    from adt_core.dttp.config import DTTPConfig
    from adt_core.dttp.gateway import DTTPGateway, SOVEREIGN_PATHS
    from adt_core.dttp.policy import PolicyEngine
    from adt_core.dttp.actions import ActionHandler
    from adt_core.ads.logger import ADSLogger
    from adt_core.sdd.validator import SpecValidator
    from unittest.mock import MagicMock

    # Setup temp ADS
    ads_path = tmp_path / "events.jsonl"
    ads_path.write_text("")
    logger = ADSLogger(str(ads_path))
    
    # Mock policy engine to allow everything
    policy_engine = MagicMock(spec=PolicyEngine)
    policy_engine.validate_request.return_value = (True, "Authorized")
    
    action_handler = MagicMock(spec=ActionHandler)
    action_handler.execute.return_value = {"status": "success", "result": "mocked"}
    
    # 1. Framework Gateway (should REJECT sovereign paths)
    fw_gateway = DTTPGateway(policy_engine, action_handler, logger, is_framework=True)
    resp = fw_gateway.request(
        agent="TEST", role="tester", spec_id="SPEC-001",
        action="edit", params={"file": SOVEREIGN_PATHS[0], "content": "bad"},
        rationale="trying to modify sovereign path"
    )
    assert resp["status"] == "denied"
    assert resp["reason"] == "sovereign_path_violation"
    
    # 2. External Project Gateway (should ALLOW sovereign paths - they aren't sovereign here)
    ext_gateway = DTTPGateway(policy_engine, action_handler, logger, is_framework=False)
    resp = ext_gateway.request(
        agent="TEST", role="tester", spec_id="SPEC-001",
        action="edit", params={"file": SOVEREIGN_PATHS[0], "content": "ok"},
        rationale="modifying config/specs.json in external project"
    )
    assert resp["status"] == "allowed"

def test_registry_deregister(registry, tmp_path):
    """Test removing a project from the registry."""
    p1 = tmp_path / "p1"
    p1.mkdir()
    registry.register_project("p1", str(p1))
    assert "p1" in registry.list_projects()
    
    success = registry.deregister_project("p1")
    assert success is True
    assert "p1" not in registry.list_projects()
    
    # Cannot deregister framework
    success = registry.deregister_project("adt-framework")
    assert success is False
    assert "adt-framework" in registry.list_projects()

def test_ads_isolation(tmp_path, temp_home):
    """Test that ADS events are isolated between projects."""
    from adt_center.app import create_app
    
    p1_dir = tmp_path / "p1"
    p1_dir.mkdir()
    os.makedirs(p1_dir / "_cortex" / "ads")
    p1_ads = p1_dir / "_cortex" / "ads" / "events.jsonl"
    p1_ads.write_text(json.dumps({"event_id": "e1", "description": "P1 Event"}) + "\n")
    
    p2_dir = tmp_path / "p2"
    p2_dir.mkdir()
    os.makedirs(p2_dir / "_cortex" / "ads")
    p2_ads = p2_dir / "_cortex" / "ads" / "events.jsonl"
    p2_ads.write_text(json.dumps({"event_id": "e2", "description": "P2 Event"}) + "\n")

    registry_path = temp_home / ".adt" / "projects.json"
    reg = ProjectRegistry(str(registry_path))
    reg.register_project("p1", str(p1_dir))
    reg.register_project("p2", str(p2_dir))

    import adt_center.app
    original_PR = adt_center.app.ProjectRegistry
    adt_center.app.ProjectRegistry = lambda: ProjectRegistry(str(registry_path))

    try:
        app = create_app()
        client = app.test_client()
        
        # P1 events
        resp = client.get("/api/ads/events?project=p1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["event_id"] == "e1"
        
        # P2 events
        resp = client.get("/api/ads/events?project=p2")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["event_id"] == "e2"
        
    finally:
        adt_center.app.ProjectRegistry = original_PR

def test_hook_url_resolution(tmp_path):
    """Test that hooks correctly resolve DTTP URL from project config."""
    from adt_sdk.hooks.claude_pretool import read_project_dttp_url
    
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    
    # Default fallback
    assert read_project_dttp_url(str(project_dir)) == "http://localhost:5002"
    
    # With config/dttp.json
    config_dir = project_dir / "config"
    config_dir.mkdir()
    (config_dir / "dttp.json").write_text(json.dumps({"port": 5006}))
    
    assert read_project_dttp_url(str(project_dir)) == "http://localhost:5006"

def test_api_specs_filtering(tmp_path, temp_home):
    """Test SPEC-031 Phase C: API ?project= filter for specs."""
    from adt_center.app import create_app
    
    p1_dir = tmp_path / "p1"
    p1_dir.mkdir()
    os.makedirs(p1_dir / "_cortex" / "specs")
    os.makedirs(p1_dir / "config")
    with open(p1_dir / "config" / "specs.json", "w") as f:
        json.dump({"specs": {"SPEC-P1": {"title": "Spec P1"}}}, f)
    with open(p1_dir / "_cortex" / "specs" / "SPEC-P1_TITLE.md", "w") as f:
        f.write("# SPEC-P1: Title")
        
    registry_path = temp_home / ".adt" / "projects.json"
    reg = ProjectRegistry(str(registry_path))
    reg.register_project("p1", str(p1_dir))

    import adt_center.app
    original_PR = adt_center.app.ProjectRegistry
    adt_center.app.ProjectRegistry = lambda: ProjectRegistry(str(registry_path))

    try:
        app = create_app()
        client = app.test_client()
        
        resp = client.get("/api/specs?project=p1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["specs"]) == 1
        assert data["specs"][0]["id"] == "SPEC-P1"
        
    finally:
        adt_center.app.ProjectRegistry = original_PR

def test_cli_projects_list(tmp_path, temp_home, capsys):
    """Test adt projects list command."""
    registry_path = temp_home / ".adt" / "projects.json"
    reg = ProjectRegistry(str(registry_path))
    p1 = tmp_path / "p1"
    p1.mkdir()
    reg.register_project("p1", str(p1), port=5005)

    import adt_core.cli
    original_registry = adt_core.cli.ProjectRegistry
    adt_core.cli.ProjectRegistry = lambda: ProjectRegistry(str(registry_path))
    
    try:
        args = Args(subcommand='list')
        adt_core.cli.projects_command(args)
        captured = capsys.readouterr()
        assert "p1" in captured.out
        assert "5005" in captured.out
    finally:
        adt_core.cli.ProjectRegistry = original_registry

def test_scaffold_detection_python(tmp_path, temp_home):
    """Test project type detection for Python."""
    project_dir = tmp_path / "py-project"
    project_dir.mkdir()
    (project_dir / "requirements.txt").write_text("flask")
    
    registry_path = temp_home / ".adt" / "projects.json"
    import adt_core.cli
    original_registry = adt_core.cli.ProjectRegistry
    adt_core.cli.ProjectRegistry = lambda: ProjectRegistry(str(registry_path))
    
    try:
        args = Args(path=str(project_dir), name="py-project", detect=True, port=5006)
        init_command(args)
        
        with open(project_dir / "config" / "jurisdictions.json") as f:
            jur = json.load(f)
            dev_paths = jur["jurisdictions"]["Developer"]["paths"]
            assert "requirements.txt" in dev_paths
            # setup.py might not be there if not present initially, but requirements.txt is a match
    finally:
        adt_core.cli.ProjectRegistry = original_registry

def test_scaffold_detection_nodejs(tmp_path, temp_home):
    """Test project type detection for Node.js."""
    project_dir = tmp_path / "node-project"
    project_dir.mkdir()
    (project_dir / "package.json").write_text('{"name": "test"}')
    
    registry_path = temp_home / ".adt" / "projects.json"
    import adt_core.cli
    original_registry = adt_core.cli.ProjectRegistry
    adt_core.cli.ProjectRegistry = lambda: ProjectRegistry(str(registry_path))
    
    try:
        args = Args(path=str(project_dir), name="node-project", detect=True, port=5007)
        init_command(args)
        
        with open(project_dir / "config" / "jurisdictions.json") as f:
            jur = json.load(f)
            dev_paths = jur["jurisdictions"]["Developer"]["paths"]
            assert "package.json" in dev_paths
            assert "public/" in dev_paths
    finally:
        adt_core.cli.ProjectRegistry = original_registry

def test_registry_find_by_path(registry, tmp_path):
    """Test finding project name by path."""
    p1 = tmp_path / "p1"
    p1.mkdir()
    registry.register_project("p1", str(p1))
    
    name = registry.find_project_by_path(str(p1))
    assert name == "p1"
    
    name = registry.find_project_by_path(str(tmp_path / "non-existent"))
    assert name is None

def test_api_governance_roles_filtering(tmp_path, temp_home):
    """Test SPEC-031 Phase C: API ?project= filter for roles."""
    from adt_center.app import create_app
    
    p1_dir = tmp_path / "p1"
    p1_dir.mkdir()
    os.makedirs(p1_dir / "config")
    with open(p1_dir / "config" / "jurisdictions.json", "w") as f:
        json.dump({"jurisdictions": {"P1_Role": {"paths": ["path/"], "action_types": ["edit"]}}}, f)
    with open(p1_dir / "config" / "specs.json", "w") as f:
        json.dump({"specs": {}}, f)
        
    registry_path = temp_home / ".adt" / "projects.json"
    reg = ProjectRegistry(str(registry_path))
    reg.register_project("p1", str(p1_dir))

    import adt_center.app
    original_PR = adt_center.app.ProjectRegistry
    adt_center.app.ProjectRegistry = lambda: ProjectRegistry(str(registry_path))

    try:
        app = create_app()
        client = app.test_client()
        
        resp = client.get("/api/governance/roles?project=p1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "P1_Role" in data["roles"]
        # In multi-project mode, Architect might still be there if it's in the default logic,
        # but P1_Role MUST be there.
        
    finally:
        adt_center.app.ProjectRegistry = original_PR

def test_adt_projects_status_cli(tmp_path, temp_home, capsys):
    """Test adt projects status command."""
    registry_path = temp_home / ".adt" / "projects.json"
    reg = ProjectRegistry(str(registry_path))
    p1 = tmp_path / "p1"
    p1.mkdir()
    reg.register_project("p1", str(p1), port=5005)
    
    os.makedirs(p1 / "_cortex" / "ads")
    (p1 / "_cortex" / "ads" / "events.jsonl").write_text("{}\n{}\n")

    import adt_core.cli
    original_registry = adt_core.cli.ProjectRegistry
    adt_core.cli.ProjectRegistry = lambda: ProjectRegistry(str(registry_path))
    
    try:
        args = Args(subcommand='status', name='p1')
        adt_core.cli.projects_command(args)
        captured = capsys.readouterr()
        assert "Project: p1" in captured.out
        assert "ADS:     2 events" in captured.out
    finally:
        adt_core.cli.ProjectRegistry = original_registry
