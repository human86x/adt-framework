"""Integration tests for SPEC-027 Shatterglass Protocol."""
import json
import os
import subprocess
import sys
import time
import pytest
from unittest.mock import patch
from adt_core.cli import shatterglass_command

@pytest.fixture
def project_env(tmp_path):
    """Create a mock project environment for shatterglass tests."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    
    # Create required directories
    (project_root / "config").mkdir()
    (project_root / "_cortex" / "ads").mkdir(parents=True)
    (project_root / "adt_core").mkdir()
    
    # Create sovereign files
    sovereign_paths = [
        "config/specs.json",
        "config/jurisdictions.json",
        "config/dttp.json",
        "_cortex/AI_PROTOCOL.md",
        "_cortex/MASTER_PLAN.md"
    ]
    for p in sovereign_paths:
        f = project_root / p
        f.write_text("{}")
        os.chmod(f, 0o644)

    # ADS log
    ads_path = project_root / "_cortex" / "ads" / "events.jsonl"
    ads_path.write_text("")

    return project_root

def test_shatterglass_activate_success(project_env):
    """Shatterglass activate should chmod files and log to ADS."""
    # Mock CLI args
    class Args:
        subcommand = 'activate'
        reason = "Test activation"
        timeout = 15
        delay = None
        auto = False
        session = None

    with (
        patch('adt_core.cli.os.path.abspath', return_value=str(project_env)),
        patch('adt_core.cli.os.path.dirname', return_value=str(project_env / "adt_core")),
        patch('builtins.input', return_value='SHATTERGLASS'),
        patch('adt_core.cli.platform.system', return_value='Linux'),
        patch('adt_core.cli.subprocess.Popen') as mock_popen
    ):
        shatterglass_command(Args())
        
        # Verify permissions
        sovereign_paths = [
            "config/specs.json",
            "config/jurisdictions.json",
            "config/dttp.json",
            "_cortex/AI_PROTOCOL.md",
            "_cortex/MASTER_PLAN.md"
        ]
        for p in sovereign_paths:
            full_path = project_env / p
            assert (os.stat(full_path).st_mode & 0o777) == 0o664
            
        # Verify ADS log
        ads_path = project_env / "_cortex" / "ads" / "events.jsonl"
        with open(ads_path) as f:
            event = json.loads(f.readline())
            assert event["action_type"] == "shatterglass_activated"
            assert event["agent"] == "HUMAN"
            assert event["tier"] == 1
            assert "Test activation" in event["description"]
            
        # Verify watchdog started
        assert mock_popen.called

def test_shatterglass_activate_aborted(project_env):
    """Shatterglass activate should abort if confirmation is wrong."""
    class Args:
        subcommand = 'activate'
        reason = "Test"
        timeout = 15
        delay = None
        auto = False
        session = None

    with (
        patch('adt_core.cli.os.path.abspath', return_value=str(project_env)),
        patch('adt_core.cli.os.path.dirname', return_value=str(project_env / "adt_core")),
        patch('builtins.input', return_value='WRONG')
    ):
        shatterglass_command(Args())
        
        # Verify permissions NOT changed
        full_path = project_env / "config" / "specs.json"
        assert (os.stat(full_path).st_mode & 0o777) == 0o644

def test_shatterglass_deactivate(project_env):
    """Shatterglass deactivate should restore permissions and log to ADS."""
    # First activate (manually)
    full_path = project_env / "config" / "specs.json"
    os.chmod(full_path, 0o664)

    class Args:
        subcommand = 'deactivate'
        auto = False
        session = "sg_123"
        delay = None

    with (
        patch('adt_core.cli.os.path.abspath', return_value=str(project_env)),
        patch('adt_core.cli.os.path.dirname', return_value=str(project_env / "adt_core"))
    ):
        shatterglass_command(Args())
        
        # Verify permissions restored
        assert (os.stat(full_path).st_mode & 0o777) == 0o644
        
        # Verify ADS log
        ads_path = project_env / "_cortex" / "ads" / "events.jsonl"
        with open(ads_path) as f:
            event = json.loads(f.readline())
            assert event["action_type"] == "shatterglass_deactivated"
            assert event["agent"] == "HUMAN"

def test_shatterglass_auto_expiry(project_env):
    """Shatterglass deactivate --auto should log as auto-expired."""
    class Args:
        subcommand = 'deactivate'
        auto = True
        session = "sg_123"
        delay = None

    with (
        patch('adt_core.cli.os.path.abspath', return_value=str(project_env)),
        patch('adt_core.cli.os.path.dirname', return_value=str(project_env / "adt_core"))
    ):
        shatterglass_command(Args())
        
        # Verify ADS log
        ads_path = project_env / "_cortex" / "ads" / "events.jsonl"
        with open(ads_path) as f:
            event = json.loads(f.readline())
            assert event["action_type"] == "shatterglass_auto_expired"
            assert event["agent"] == "SYSTEM"
