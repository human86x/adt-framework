"""Tests for DTTP sandboxing features: dry_run, patch action, enforcement_mode,
and Claude Code PreToolUse hook (SPEC-021 Section 8)."""
import json
import os
import py_compile
import pytest

from adt_core.dttp.config import DTTPConfig
from adt_core.dttp.service import create_dttp_app


@pytest.fixture
def dttp_app(tmp_path):
    """Create a test DTTP service with patch-capable config."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "data").mkdir()

    # ADS log
    ads_dir = project_root / "_cortex" / "ads"
    ads_dir.mkdir(parents=True)
    ads_path = ads_dir / "events.jsonl"
    ads_path.write_text("")

    # Specs config (includes patch action type)
    config_dir = project_root / "config"
    config_dir.mkdir()
    specs_config = config_dir / "specs.json"
    specs_config.write_text(json.dumps({
        "specs": {
            "SPEC-001": {
                "status": "approved",
                "roles": ["tester"],
                "action_types": ["edit", "patch", "create", "delete"],
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
        enforcement_mode="development",
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
        "rationale": "Testing sandboxing",
    }
    payload.update(overrides)
    return payload


# === Dry Run ===

class TestDryRun:
    def test_dry_run_allowed_does_not_write(self, client, dttp_app):
        """dry_run=True should validate but NOT write the file."""
        resp = client.post("/request", json=_valid_request(dry_run=True))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "allowed"
        assert data["dry_run"] is True

        # File must NOT exist
        project_root = dttp_app.config["DTTP"].project_root
        written_file = os.path.join(project_root, "data", "test.txt")
        assert not os.path.exists(written_file)

    def test_dry_run_denied_blocks(self, client):
        """dry_run=True with wrong role should still deny."""
        resp = client.post("/request", json=_valid_request(
            role="unauthorized", dry_run=True
        ))
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["status"] == "denied"

    def test_dry_run_logged_to_ads(self, client, dttp_app):
        """dry_run should log a dry_run_validated event to ADS."""
        client.post("/request", json=_valid_request(dry_run=True))
        ads_path = dttp_app.config["DTTP"].ads_path
        with open(ads_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        dry_events = [e for e in events if "dry_run" in e.get("action_type", "")]
        assert len(dry_events) == 1
        assert dry_events[0]["authorized"] is True

    def test_dry_run_default_false_backward_compat(self, client, dttp_app):
        """Without dry_run field, request should execute normally (backward compat)."""
        resp = client.post("/request", json=_valid_request())
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "allowed"
        assert "dry_run" not in data  # Normal response has 'result', not 'dry_run'
        assert "result" in data

        # File SHOULD exist
        project_root = dttp_app.config["DTTP"].project_root
        written_file = os.path.join(project_root, "data", "test.txt")
        assert os.path.exists(written_file)


# === Patch Action ===

class TestPatchAction:
    def test_patch_success(self, client, dttp_app):
        """Patch should replace old_string with new_string."""
        project_root = dttp_app.config["DTTP"].project_root
        target = os.path.join(project_root, "data", "patch_test.txt")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            f.write("Hello World")

        resp = client.post("/request", json=_valid_request(
            action="patch",
            params={"file": "data/patch_test.txt", "old_string": "World", "new_string": "ADT"}
        ))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "allowed"
        assert data["result"]["result"] == "file_patched"

        with open(target) as f:
            assert f.read() == "Hello ADT"

    def test_patch_old_string_not_found(self, client, dttp_app):
        """Patch should error if old_string not in file."""
        project_root = dttp_app.config["DTTP"].project_root
        target = os.path.join(project_root, "data", "patch_nf.txt")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            f.write("Some content")

        resp = client.post("/request", json=_valid_request(
            action="patch",
            params={"file": "data/patch_nf.txt", "old_string": "MISSING", "new_string": "replacement"}
        ))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["result"]["status"] == "error"
        assert "not found" in data["result"]["message"]

    def test_patch_ambiguous_match(self, client, dttp_app):
        """Patch should error if old_string matches more than once."""
        project_root = dttp_app.config["DTTP"].project_root
        target = os.path.join(project_root, "data", "patch_amb.txt")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            f.write("foo bar foo baz foo")

        resp = client.post("/request", json=_valid_request(
            action="patch",
            params={"file": "data/patch_amb.txt", "old_string": "foo", "new_string": "qux"}
        ))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["result"]["status"] == "error"
        assert "ambiguous" in data["result"]["message"]

    def test_patch_file_not_found(self, client):
        """Patch should error if target file doesn't exist."""
        resp = client.post("/request", json=_valid_request(
            action="patch",
            params={"file": "data/nonexistent.txt", "old_string": "a", "new_string": "b"}
        ))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["result"]["status"] == "error"
        assert "not found" in data["result"]["message"].lower()


# === Enforcement Mode ===

class TestEnforcementMode:
    def test_enforcement_mode_in_status(self, client):
        """GET /status should include enforcement_mode."""
        resp = client.get("/status")
        data = resp.get_json()
        assert "enforcement_mode" in data
        assert data["enforcement_mode"] == "development"

    def test_enforcement_mode_from_env(self, tmp_path, monkeypatch):
        """enforcement_mode should read from DTTP_ENFORCEMENT_MODE env var."""
        monkeypatch.setenv("DTTP_ENFORCEMENT_MODE", "production")
        config = DTTPConfig.from_env()
        assert config.enforcement_mode == "production"

    def test_enforcement_mode_default(self):
        """enforcement_mode should default to 'development'."""
        config = DTTPConfig()
        assert config.enforcement_mode == "development"

    def test_enforcement_mode_from_project_root(self, tmp_path):
        """from_project_root should set enforcement_mode to development."""
        config = DTTPConfig.from_project_root(str(tmp_path))
        assert config.enforcement_mode == "development"


# === Claude PreToolUse Hook ===

class TestClaudePreToolHook:
    def test_hook_is_valid_python(self):
        """The claude_pretool.py hook must be syntactically valid Python."""
        hook_path = os.path.join(
            os.path.dirname(__file__), "..", "adt_sdk", "hooks", "claude_pretool.py"
        )
        hook_path = os.path.abspath(hook_path)
        assert os.path.exists(hook_path), f"Hook not found: {hook_path}"
        py_compile.compile(hook_path, doraise=True)

    def test_non_write_tools_pass_through(self):
        """The hook should only intercept Write, Edit, NotebookEdit."""
        import importlib.util
        hook_path = os.path.join(
            os.path.dirname(__file__), "..", "adt_sdk", "hooks", "claude_pretool.py"
        )
        hook_path = os.path.abspath(hook_path)
        spec = importlib.util.spec_from_file_location("claude_pretool", hook_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert "Write" in mod.INTERCEPTED_TOOLS
        assert "Edit" in mod.INTERCEPTED_TOOLS
        assert "NotebookEdit" in mod.INTERCEPTED_TOOLS
        assert "Read" not in mod.INTERCEPTED_TOOLS
        assert "Bash" not in mod.INTERCEPTED_TOOLS
        assert "Glob" not in mod.INTERCEPTED_TOOLS

    def test_path_resolution(self):
        """to_project_relative should correctly convert absolute to relative."""
        import importlib.util
        hook_path = os.path.join(
            os.path.dirname(__file__), "..", "adt_sdk", "hooks", "claude_pretool.py"
        )
        hook_path = os.path.abspath(hook_path)
        spec = importlib.util.spec_from_file_location("claude_pretool", hook_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod.to_project_relative("/home/user/project/src/foo.py", "/home/user/project") == "src/foo.py"
        assert mod.to_project_relative("/home/user/project", "/home/user/project") == "."
        # Outside project returns as-is
        result = mod.to_project_relative("/etc/passwd", "/home/user/project")
        assert result == "/etc/passwd"

    def test_build_dttp_params_write(self):
        """Write tool should map to 'edit' action."""
        import importlib.util
        hook_path = os.path.join(
            os.path.dirname(__file__), "..", "adt_sdk", "hooks", "claude_pretool.py"
        )
        hook_path = os.path.abspath(hook_path)
        spec = importlib.util.spec_from_file_location("claude_pretool", hook_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        action, params = mod.build_dttp_params("Write", {"content": "hello"}, "src/file.py")
        assert action == "edit"
        assert params["file"] == "src/file.py"
        assert params["content"] == "hello"

    def test_build_dttp_params_edit(self):
        """Edit tool should map to 'patch' action."""
        import importlib.util
        hook_path = os.path.join(
            os.path.dirname(__file__), "..", "adt_sdk", "hooks", "claude_pretool.py"
        )
        hook_path = os.path.abspath(hook_path)
        spec = importlib.util.spec_from_file_location("claude_pretool", hook_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        action, params = mod.build_dttp_params("Edit", {
            "old_string": "old", "new_string": "new"
        }, "src/file.py")
        assert action == "patch"
        assert params["old_string"] == "old"
        assert params["new_string"] == "new"


# === Gemini CLI BeforeTool Hook ===

def _load_gemini_hook():
    """Helper to load the gemini_pretool module."""
    import importlib.util
    hook_path = os.path.join(
        os.path.dirname(__file__), "..", "adt_sdk", "hooks", "gemini_pretool.py"
    )
    hook_path = os.path.abspath(hook_path)
    spec = importlib.util.spec_from_file_location("gemini_pretool", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, hook_path


class TestGeminiPreToolHook:
    def test_hook_is_valid_python(self):
        """The gemini_pretool.py hook must be syntactically valid Python."""
        hook_path = os.path.join(
            os.path.dirname(__file__), "..", "adt_sdk", "hooks", "gemini_pretool.py"
        )
        hook_path = os.path.abspath(hook_path)
        assert os.path.exists(hook_path), f"Hook not found: {hook_path}"
        py_compile.compile(hook_path, doraise=True)

    def test_intercepted_tools(self):
        """The hook should only intercept write_file and replace."""
        mod, _ = _load_gemini_hook()
        assert "write_file" in mod.INTERCEPTED_TOOLS
        assert "replace" in mod.INTERCEPTED_TOOLS
        assert "read_file" not in mod.INTERCEPTED_TOOLS
        assert "run_shell_command" not in mod.INTERCEPTED_TOOLS
        assert "grep_search" not in mod.INTERCEPTED_TOOLS

    def test_path_resolution(self):
        """to_project_relative should correctly convert absolute to relative."""
        mod, _ = _load_gemini_hook()
        assert mod.to_project_relative("/home/user/project/src/foo.py", "/home/user/project") == "src/foo.py"
        assert mod.to_project_relative("/home/user/project", "/home/user/project") == "."
        result = mod.to_project_relative("/etc/passwd", "/home/user/project")
        assert result == "/etc/passwd"

    def test_build_dttp_params_write_file(self):
        """write_file tool should map to 'edit' action."""
        mod, _ = _load_gemini_hook()
        action, params = mod.build_dttp_params("write_file", {"content": "hello"}, "src/file.py")
        assert action == "edit"
        assert params["file"] == "src/file.py"
        assert params["content"] == "hello"

    def test_build_dttp_params_replace(self):
        """replace tool should map to 'patch' action."""
        mod, _ = _load_gemini_hook()
        action, params = mod.build_dttp_params("replace", {
            "old_string": "old", "new_string": "new"
        }, "src/file.py")
        assert action == "patch"
        assert params["old_string"] == "old"
        assert params["new_string"] == "new"

    def test_deny_format(self):
        """Gemini deny decision should use Gemini CLI format (not Claude format)."""
        mod, _ = _load_gemini_hook()
        result = mod.make_deny("test reason")
        assert result["decision"] == "deny"
        assert result["reason"] == "test reason"
        # Must NOT use Claude's hookSpecificOutput format
        assert "hookSpecificOutput" not in result

    def test_allow_format(self):
        """Gemini allow decision should use Gemini CLI format."""
        mod, _ = _load_gemini_hook()
        result = mod.make_allow("test reason")
        assert result["decision"] == "allow"
        assert "hookSpecificOutput" not in result

    def test_default_agent_is_gemini(self):
        """Default agent should be GEMINI, not CLAUDE."""
        mod, _ = _load_gemini_hook()
        # Verify the source code contains GEMINI as default
        import inspect
        source = inspect.getsource(mod.main)
        assert '"GEMINI"' in source
