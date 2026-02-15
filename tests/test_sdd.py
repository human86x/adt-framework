import os
import json
import pytest
from adt_core.sdd.registry import SpecRegistry
from adt_core.sdd.validator import SpecValidator
from adt_core.sdd.tasks import TaskManager

@pytest.fixture
def mock_specs(tmp_path):
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    spec_file = specs_dir / "SPEC-001_TEST.md"
    spec_file.write_text("# SPEC-001: Test Spec\n\n**Status:** APPROVED\n")
    return str(specs_dir)

def test_registry(mock_specs):
    registry = SpecRegistry(mock_specs)
    specs = registry.list_specs()
    assert len(specs) == 1
    assert specs[0]["id"] == "SPEC-001"
    assert specs[0]["status"] == "APPROVED"

def test_validator(tmp_path):
    config_path = tmp_path / "specs.json"
    config = {
        "specs": {
            "SPEC-001": {
                "status": "approved",
                "roles": ["tester"],
                "action_types": ["test_action"],
                "paths": ["test/"]
            }
        }
    }
    config_path.write_text(json.dumps(config))
    
    validator = SpecValidator(str(config_path))
    assert validator.is_authorized("SPEC-001", "tester", "test_action")
    assert not validator.is_authorized("SPEC-001", "dev", "test_action")

def test_task_manager(tmp_path):
    tasks_path = tmp_path / "tasks.json"
    data = {"tasks": [{"id": "t1", "title": "Test", "status": "pending"}]}
    tasks_path.write_text(json.dumps(data))
    
        tm = TaskManager(str(tasks_path))
    
        tasks = tm.list_tasks(status="pending")
    
        assert len(tasks) == 1
    
        
    
        tm.update_task("t1", {"status": "completed"})
    
        assert tm.get_task("t1")["status"] == "completed"
    
    