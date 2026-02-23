"""SPEC-027 Task 128: Shatterglass OS-level enforcement tests.

These tests verify that OS-level file permissions are correctly enforced
when production mode is active (agent/dttp users exist).

Tests that require real OS users are skipped if those users don't exist.
Tests that can run with mock data always run.
"""
import json
import os
import pwd
import stat
import subprocess
import sys
import pytest
from unittest.mock import patch, MagicMock

# --- Helpers ---

def _user_exists(username):
    """Check if an OS user exists."""
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False

AGENT_EXISTS = _user_exists("agent")
DTTP_EXISTS = _user_exists("dttp")
PRODUCTION_MODE = AGENT_EXISTS and DTTP_EXISTS


def _make_path_traversable(project_env):
    """Ensure all parent dirs from project_env up to /tmp are world-executable."""
    path = project_env
    dirs_to_fix = []
    while str(path) != "/" and str(path) != "/tmp":
        dirs_to_fix.append(str(path))
        path = path.parent
    if dirs_to_fix:
        subprocess.run(["sudo", "chmod", "o+x"] + dirs_to_fix, check=True)

requires_production = pytest.mark.skipif(
    not PRODUCTION_MODE,
    reason="Requires agent/dttp OS users (run setup_shatterglass.sh first)"
)

# --- Fixtures ---

@pytest.fixture
def project_env(tmp_path):
    """Create a mock project environment with tiered files."""
    project = tmp_path / "testproject"
    project.mkdir()

    (project / "config").mkdir()
    (project / "_cortex" / "ads").mkdir(parents=True)
    (project / "_cortex" / "ops").mkdir(parents=True)
    (project / "_cortex" / "specs").mkdir(parents=True)
    (project / "adt_core" / "dttp").mkdir(parents=True)
    (project / "adt_core" / "ads").mkdir(parents=True)
    (project / "src").mkdir()

    # Tier 1: Sovereign
    tier1 = [
        "config/specs.json",
        "config/jurisdictions.json",
        "config/dttp.json",
        "_cortex/AI_PROTOCOL.md",
        "_cortex/MASTER_PLAN.md",
    ]
    for p in tier1:
        f = project / p
        f.write_text("{}")

    # Tier 2: Constitutional
    tier2 = [
        "adt_core/dttp/gateway.py",
        "adt_core/dttp/policy.py",
        "adt_core/dttp/service.py",
        "adt_core/ads/logger.py",
        "adt_core/ads/integrity.py",
        "adt_core/ads/crypto.py",
    ]
    for p in tier2:
        f = project / p
        f.write_text("# constitutional file")

    # Tier 3: Regular
    (project / "src" / "app.py").write_text("# regular file")
    (project / "README.md").write_text("# readme")

    # ADS log
    (project / "_cortex" / "ads" / "events.jsonl").write_text("")

    return project


# ============================================================================
# TEST CLASS 1: Production Mode Detection
# ============================================================================

class TestProductionModeDetection:
    """Test that production mode is correctly detected."""

    def test_is_production_mode_with_users(self):
        """_is_production_mode returns correct value based on OS users."""
        from adt_center.api.governance_routes import _is_production_mode
        if PRODUCTION_MODE:
            assert _is_production_mode() is True
        else:
            assert _is_production_mode() is False

    def test_is_production_mode_mocked_true(self):
        """_is_production_mode returns True with mocked pwd."""
        from adt_center.api.governance_routes import _is_production_mode

        mock_user = MagicMock()
        mock_user.pw_uid = 1001
        with patch("pwd.getpwnam", return_value=mock_user):
            assert _is_production_mode() is True

    def test_is_production_mode_mocked_false(self):
        """_is_production_mode returns False when agent user missing."""
        from adt_center.api.governance_routes import _is_production_mode

        def side_effect(name):
            if name == "agent":
                raise KeyError("agent")
            return MagicMock()

        with patch("pwd.getpwnam", side_effect=side_effect):
            assert _is_production_mode() is False


# ============================================================================
# TEST CLASS 2: PTY Spawner Production Mode (Rust logic, tested via structure)
# ============================================================================

class TestPtyProductionMode:
    """Test PTY spawner production mode detection logic."""

    def test_pty_rs_has_is_production_mode(self):
        """pty.rs contains is_production_mode function."""
        pty_path = os.path.join(
            os.path.dirname(__file__), "..",
            "adt-console", "src-tauri", "src", "pty.rs"
        )
        if os.path.exists(pty_path):
            with open(pty_path) as f:
                content = f.read()
            assert "fn is_production_mode()" in content
            assert "sudo" in content
            assert "agent_user" in content
        else:
            pytest.skip("pty.rs not found")

    def test_pty_rs_agent_user_field(self):
        """SessionInfo struct has agent_user field."""
        pty_path = os.path.join(
            os.path.dirname(__file__), "..",
            "adt-console", "src-tauri", "src", "pty.rs"
        )
        if os.path.exists(pty_path):
            with open(pty_path) as f:
                content = f.read()
            assert "pub agent_user: Option<String>" in content
        else:
            pytest.skip("pty.rs not found")


# ============================================================================
# TEST CLASS 3: OS-Level Permission Enforcement (requires real users)
# ============================================================================

class TestOSEnforcement:
    """Test that OS permissions actually prevent unauthorized writes."""

    @requires_production
    def test_agent_cannot_write_tier1(self, project_env):
        """Agent user cannot write to Tier 1 (sovereign) files."""
        specs_json = project_env / "config" / "specs.json"
        human_uid = os.getuid()
        human_gid = os.getgid()
        os.chown(specs_json, human_uid, human_gid)
        os.chmod(specs_json, 0o644)

        result = subprocess.run(
            ["sudo", "-u", "agent", "bash", "-c", f"echo 'x' >> {specs_json}"],
            capture_output=True, text=True
        )
        assert result.returncode != 0, "Agent should NOT be able to write Tier 1 files"

    @requires_production
    def test_agent_cannot_write_tier2(self, project_env):
        """Agent user cannot write to Tier 2 (constitutional) files."""
        gateway = project_env / "adt_core" / "dttp" / "gateway.py"
        # Need sudo for chown to dttp user
        subprocess.run(["sudo", "chown", "dttp:dttp", str(gateway)], check=True)
        subprocess.run(["sudo", "chmod", "644", str(gateway)], check=True)

        result = subprocess.run(
            ["sudo", "-u", "agent", "bash", "-c", f"echo 'x' >> {gateway}"],
            capture_output=True, text=True
        )
        assert result.returncode != 0, "Agent should NOT be able to write Tier 2 files"

    @requires_production
    def test_agent_can_write_tier3(self, project_env):
        """Agent user CAN write to Tier 3 (regular) files when in dttp group."""
        app_py = project_env / "src" / "app.py"
        # Make entire tree traversable by dttp group
        subprocess.run(["sudo", "chown", "-R", "dttp:dttp", str(project_env)], check=True)
        subprocess.run(["sudo", "chmod", "-R", "775", str(project_env)], check=True)
        subprocess.run(["sudo", "chmod", "664", str(app_py)], check=True)
        # Ensure entire path from /tmp down is traversable
        _make_path_traversable(project_env)

        result = subprocess.run(
            ["sudo", "-u", "agent", "bash", "-c", f"echo '# test' >> {app_py}"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Agent should be able to write Tier 3 files: {result.stderr}"

    @requires_production
    def test_dttp_can_write_tier2(self, project_env):
        """DTTP user CAN write to Tier 2 (constitutional) files."""
        gateway = project_env / "adt_core" / "dttp" / "gateway.py"
        # Make entire tree traversable by dttp user
        subprocess.run(["sudo", "chown", "-R", "dttp:dttp", str(project_env)], check=True)
        subprocess.run(["sudo", "chmod", "-R", "775", str(project_env)], check=True)
        subprocess.run(["sudo", "chmod", "644", str(gateway)], check=True)
        # Ensure entire path from /tmp down is traversable
        _make_path_traversable(project_env)

        result = subprocess.run(
            ["sudo", "-u", "dttp", "bash", "-c", f"echo '# dttp write' >> {gateway}"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"DTTP should be able to write Tier 2 files: {result.stderr}"


# ============================================================================
# TEST CLASS 4: Shatterglass Permission Application
# ============================================================================

class TestApplyShatterglassPermissions:
    """Test _apply_shatterglass_permissions sets correct ownership/modes."""

    def test_apply_permissions_sets_tier1_human_owned(self, project_env):
        """Tier 1 files should be human-owned 644 after applying permissions."""
        from adt_center.api.governance_routes import _apply_shatterglass_permissions

        current_uid = os.getuid()
        current_gid = os.getgid()
        mock_human = MagicMock()
        mock_human.pw_uid = current_uid
        mock_human.pw_gid = current_gid

        mock_dttp = MagicMock()
        mock_dttp.pw_uid = current_uid
        mock_dttp.pw_gid = current_gid

        mock_grp = MagicMock()
        mock_grp.gr_gid = current_gid

        def mock_getpwnam(name):
            if name == "dttp":
                return mock_dttp
            return mock_human

        with patch("pwd.getpwnam", side_effect=mock_getpwnam), \
             patch("grp.getgrnam", return_value=mock_grp), \
             patch.dict(os.environ, {"USER": os.environ.get("USER", "testuser")}):
            _apply_shatterglass_permissions(str(project_env))

        tier1_paths = [
            "config/specs.json",
            "config/jurisdictions.json",
            "config/dttp.json",
            "_cortex/AI_PROTOCOL.md",
            "_cortex/MASTER_PLAN.md",
        ]
        for p in tier1_paths:
            full = project_env / p
            mode = os.stat(full).st_mode & 0o777
            assert mode == 0o644, f"{p} should be 644, got {oct(mode)}"

    def test_apply_permissions_sets_tier3_group_writable(self, project_env):
        """Regular files should be dttp-owned 664 after applying permissions."""
        from adt_center.api.governance_routes import _apply_shatterglass_permissions

        current_uid = os.getuid()
        current_gid = os.getgid()
        mock_user = MagicMock()
        mock_user.pw_uid = current_uid
        mock_user.pw_gid = current_gid

        mock_grp = MagicMock()
        mock_grp.gr_gid = current_gid

        with patch("pwd.getpwnam", return_value=mock_user), \
             patch("grp.getgrnam", return_value=mock_grp), \
             patch.dict(os.environ, {"USER": os.environ.get("USER", "testuser")}):
            _apply_shatterglass_permissions(str(project_env))

        app_py = project_env / "src" / "app.py"
        mode = os.stat(app_py).st_mode & 0o777
        assert mode == 0o664, f"src/app.py should be 664, got {oct(mode)}"

    def test_apply_permissions_dirs_775(self, project_env):
        """Directories should be 775 after applying permissions."""
        from adt_center.api.governance_routes import _apply_shatterglass_permissions

        current_uid = os.getuid()
        current_gid = os.getgid()
        mock_user = MagicMock()
        mock_user.pw_uid = current_uid
        mock_user.pw_gid = current_gid

        mock_grp = MagicMock()
        mock_grp.gr_gid = current_gid

        with patch("pwd.getpwnam", return_value=mock_user), \
             patch("grp.getgrnam", return_value=mock_grp), \
             patch.dict(os.environ, {"USER": os.environ.get("USER", "testuser")}):
            _apply_shatterglass_permissions(str(project_env))

        src_dir = project_env / "src"
        mode = os.stat(src_dir).st_mode & 0o777
        assert mode == 0o775, f"src/ dir should be 775, got {oct(mode)}"


# ============================================================================
# TEST CLASS 5: Sudoers and Setup Script Validation
# ============================================================================

class TestSetupScript:
    """Test that setup_shatterglass.sh contains required configuration."""

    def test_setup_script_exists(self):
        """setup_shatterglass.sh exists."""
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "setup_shatterglass.sh"
        )
        assert os.path.exists(script_path)

    def test_setup_script_has_agent_spawning_rule(self):
        """Sudoers config includes human -> agent NOPASSWD rule."""
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "setup_shatterglass.sh"
        )
        with open(script_path) as f:
            content = f.read()
        assert "ALL=(agent) NOPASSWD: ALL" in content

    def test_setup_script_has_dttp_service_rule(self):
        """Sudoers config includes human -> dttp for DTTP service."""
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "setup_shatterglass.sh"
        )
        with open(script_path) as f:
            content = f.read()
        assert "ALL=(dttp) NOPASSWD:" in content
        assert "adt_core.dttp.service" in content

    def test_setup_script_has_agent_path_restriction(self):
        """Sudoers config restricts agent PATH."""
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "setup_shatterglass.sh"
        )
        with open(script_path) as f:
            content = f.read()
        assert "Defaults:agent secure_path=" in content

    def test_setup_script_validates_sudoers(self):
        """Setup script validates sudoers file with visudo."""
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "setup_shatterglass.sh"
        )
        with open(script_path) as f:
            content = f.read()
        assert "visudo -cf" in content


# ============================================================================
# TEST CLASS 6: Service Launch Integration
# ============================================================================

class TestServiceLaunch:
    """Test that start.sh and install.sh use sudo -u dttp in production."""

    def test_start_sh_has_production_mode(self):
        """start.sh detects production mode and uses sudo -u dttp."""
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "start.sh"
        )
        with open(script_path) as f:
            content = f.read()
        assert "PRODUCTION_MODE=" in content
        assert "sudo -u dttp" in content

    def test_install_sh_has_production_mode(self):
        """install.sh detects production mode and uses sudo -u dttp."""
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "install.sh"
        )
        with open(script_path) as f:
            content = f.read()
        assert "PROD_MODE=" in content
        assert "sudo -u dttp" in content

    def test_governance_routes_has_production_dttp(self):
        """governance_routes.py _start_project_dttp uses sudo -u dttp."""
        routes_path = os.path.join(
            os.path.dirname(__file__), "..",
            "adt_center", "api", "governance_routes.py"
        )
        with open(routes_path) as f:
            content = f.read()
        assert "sudo" in content
        assert "_is_production_mode" in content
