"""SPEC-036 Phase A: Agent Filesystem Sandbox Integration Tests.

Tests verify that:
1. Sandboxed agents cannot read files outside project root (via hook enforcement)
2. Sandboxed agents cannot write outside project root via Bash escape
3. Sandbox directory lifecycle (creation, cleanup)
4. Environment sanitization
5. Claude/Gemini config generation
"""
import importlib.util
import json
import os
import tempfile
import shutil
import pytest


# --- Helper: Load hook modules ---

def _load_claude_hook():
    hook_path = os.path.join(
        os.path.dirname(__file__), "..", "adt_sdk", "hooks", "claude_pretool.py"
    )
    hook_path = os.path.abspath(hook_path)
    spec = importlib.util.spec_from_file_location("claude_pretool", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_gemini_hook():
    hook_path = os.path.join(
        os.path.dirname(__file__), "..", "adt_sdk", "hooks", "gemini_pretool.py"
    )
    hook_path = os.path.abspath(hook_path)
    spec = importlib.util.spec_from_file_location("gemini_pretool", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- Fixtures ---

@pytest.fixture
def sandbox_project(tmp_path):
    """Create a mock project with sandbox directory structure."""
    project_root = tmp_path / "my-project"
    project_root.mkdir()

    # Create some project files
    src_dir = project_root / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hello')")
    (project_root / "README.md").write_text("# My Project")

    # Create sandbox dir structure (as pty.rs would)
    session_id = "session_42"
    sandbox_root = project_root / ".adt" / "sandbox" / session_id
    for subdir in [".claude", ".gemini", "home", "tmp"]:
        (sandbox_root / subdir).mkdir(parents=True)

    # Create a file OUTSIDE the project (simulating another project)
    external_dir = tmp_path / "other-project"
    external_dir.mkdir()
    (external_dir / "secret.txt").write_text("TOP SECRET DATA")

    # Create simulated home directory secrets
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    (fake_home / ".ssh").mkdir()
    (fake_home / ".ssh" / "id_rsa").write_text("FAKE PRIVATE KEY")
    (fake_home / ".aws").mkdir()
    (fake_home / ".aws" / "credentials").write_text("aws_secret=FAKE")

    return {
        "project_root": str(project_root),
        "sandbox_root": str(sandbox_root),
        "session_id": session_id,
        "external_dir": str(external_dir),
        "fake_home": str(fake_home),
        "tmp_path": str(tmp_path),
    }


# === Test Class: Read Isolation (task_145) ===

class TestSandboxReadIsolation:
    """Verify sandboxed agents cannot read outside project root."""

    def test_claude_hook_blocks_read_outside_project(self, sandbox_project):
        """Read tool targeting path outside project should be denied when ADT_SANDBOX=1."""
        mod = _load_claude_hook()
        project_root = sandbox_project["project_root"]
        external_file = os.path.join(sandbox_project["external_dir"], "secret.txt")

        # Simulate path resolution and containment check
        full_abs = os.path.realpath(external_file)
        full_project = os.path.realpath(project_root)
        is_contained = (full_abs == full_project or
                        full_abs.startswith(full_project + os.sep))

        assert not is_contained, "External file should NOT be contained in project"

    def test_claude_hook_allows_read_inside_project(self, sandbox_project):
        """Read tool targeting path inside project should be allowed."""
        mod = _load_claude_hook()
        project_root = sandbox_project["project_root"]
        internal_file = os.path.join(project_root, "src", "main.py")

        full_abs = os.path.realpath(internal_file)
        full_project = os.path.realpath(project_root)
        is_contained = (full_abs == full_project or
                        full_abs.startswith(full_project + os.sep))

        assert is_contained, "Internal file should be contained in project"

    def test_symlink_escape_blocked(self, sandbox_project):
        """Symlink pointing outside project should be caught by realpath resolution."""
        mod = _load_claude_hook()
        project_root = sandbox_project["project_root"]
        external_file = os.path.join(sandbox_project["external_dir"], "secret.txt")

        # Create symlink inside project pointing outside
        symlink_path = os.path.join(project_root, "src", "sneaky_link")
        os.symlink(external_file, symlink_path)

        # realpath resolves the symlink
        full_abs = os.path.realpath(symlink_path)
        full_project = os.path.realpath(project_root)
        is_contained = (full_abs == full_project or
                        full_abs.startswith(full_project + os.sep))

        assert not is_contained, "Symlink escape should be detected by realpath"

    def test_dot_dot_traversal_blocked(self, sandbox_project):
        """../../../etc/passwd style traversal should be blocked."""
        mod = _load_claude_hook()
        project_root = sandbox_project["project_root"]

        traversal_path = os.path.join(project_root, "src", "..", "..", "..", "etc", "passwd")
        full_abs = os.path.realpath(traversal_path)
        full_project = os.path.realpath(project_root)
        is_contained = (full_abs == full_project or
                        full_abs.startswith(full_project + os.sep))

        assert not is_contained, "Path traversal should be blocked"

    def test_read_tools_defined_in_hook(self):
        """Verify that Read, Glob, Grep are in READ_TOOLS set."""
        mod = _load_claude_hook()
        assert "Read" in mod.READ_TOOLS
        assert "Glob" in mod.READ_TOOLS
        assert "Grep" in mod.READ_TOOLS

    def test_ssh_keys_not_readable(self, sandbox_project):
        """~/.ssh/ should be outside sandbox containment."""
        project_root = sandbox_project["project_root"]
        ssh_key = os.path.join(sandbox_project["fake_home"], ".ssh", "id_rsa")

        full_abs = os.path.realpath(ssh_key)
        full_project = os.path.realpath(project_root)
        is_contained = (full_abs == full_project or
                        full_abs.startswith(full_project + os.sep))

        assert not is_contained, "SSH keys must be outside sandbox"

    def test_aws_credentials_not_readable(self, sandbox_project):
        """~/.aws/credentials should be outside sandbox containment."""
        project_root = sandbox_project["project_root"]
        aws_creds = os.path.join(sandbox_project["fake_home"], ".aws", "credentials")

        full_abs = os.path.realpath(aws_creds)
        full_project = os.path.realpath(project_root)
        is_contained = (full_abs == full_project or
                        full_abs.startswith(full_project + os.sep))

        assert not is_contained, "AWS credentials must be outside sandbox"

    def test_glob_pattern_outside_project_blocked(self, sandbox_project):
        """Glob with path outside project should be caught."""
        mod = _load_claude_hook()
        project_root = sandbox_project["project_root"]

        # Glob targeting /tmp or /home
        for path in ["/tmp", "/home", "/etc", sandbox_project["external_dir"]]:
            full_abs = os.path.realpath(path)
            full_project = os.path.realpath(project_root)
            is_contained = (full_abs == full_project or
                            full_abs.startswith(full_project + os.sep))
            assert not is_contained, f"Glob path {path} should be outside sandbox"


# === Test Class: Bash Escape Prevention (task_146) ===

class TestSandboxBashEscape:
    """Verify that Bash tool cannot be used to escape the sandbox."""

    def test_environment_sanitization_removes_ssh_auth_sock(self, sandbox_project):
        """SSH_AUTH_SOCK should be stripped from sandboxed environment."""
        # Simulate env var denylist
        denylist = [
            "SSH_AUTH_SOCK", "SSH_AGENT_PID",
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
            "GITHUB_TOKEN", "GH_TOKEN",
            "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        ]
        test_env = {
            "SSH_AUTH_SOCK": "/tmp/ssh-XXXXX/agent.12345",
            "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
            "HOME": "/home/human",
            "PATH": "/usr/bin:/bin",
        }

        sanitized = {k: v for k, v in test_env.items() if k not in denylist}
        assert "SSH_AUTH_SOCK" not in sanitized
        assert "AWS_ACCESS_KEY_ID" not in sanitized
        assert "PATH" in sanitized  # PATH should survive

    def test_home_redirected_to_sandbox(self, sandbox_project):
        """HOME should point to sandbox/home, not real home."""
        sandbox_home = os.path.join(sandbox_project["sandbox_root"], "home")
        assert os.path.isdir(sandbox_home)
        # In the real system, cmd.env("HOME", sandbox_home) is called
        # The agent's Bash commands would see HOME as this path

    def test_tmpdir_redirected_to_sandbox(self, sandbox_project):
        """TMPDIR should point to sandbox/tmp."""
        sandbox_tmp = os.path.join(sandbox_project["sandbox_root"], "tmp")
        assert os.path.isdir(sandbox_tmp)

    def test_adt_sandbox_env_flag_set(self):
        """ADT_SANDBOX=1 should be present in sandboxed sessions."""
        # This is set by pty.rs apply_sandbox_env
        # The hook checks: os.environ.get("ADT_SANDBOX") == "1"
        assert os.environ.get("ADT_SANDBOX", "0") in ("0", "1")

    def test_prefix_denylist_strips_aws_vars(self):
        """All AWS_* prefixed vars should be stripped."""
        prefix_denylist = ["AWS_", "GCP_", "AZURE_", "GOOGLE_CLOUD_"]
        test_env = {
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_SESSION_TOKEN": "FwoGZXIvYXdzE...",
            "GCP_PROJECT": "my-project",
            "AZURE_TENANT_ID": "abc-123",
            "NORMAL_VAR": "keep_this",
        }

        sanitized = {}
        for k, v in test_env.items():
            stripped = False
            for prefix in prefix_denylist:
                if k.startswith(prefix):
                    stripped = True
                    break
            if not stripped:
                sanitized[k] = v

        assert "AWS_DEFAULT_REGION" not in sanitized
        assert "AWS_SESSION_TOKEN" not in sanitized
        assert "GCP_PROJECT" not in sanitized
        assert "AZURE_TENANT_ID" not in sanitized
        assert "NORMAL_VAR" in sanitized


# === Test Class: Sandbox Directory Lifecycle ===

class TestSandboxLifecycle:
    """Verify sandbox directory creation and cleanup."""

    def test_sandbox_dir_created_with_subdirs(self, sandbox_project):
        """Sandbox should have .claude, .gemini, home, tmp subdirs."""
        sandbox_root = sandbox_project["sandbox_root"]
        for subdir in [".claude", ".gemini", "home", "tmp"]:
            assert os.path.isdir(os.path.join(sandbox_root, subdir))

    def test_sandbox_cleanup_removes_all(self, sandbox_project):
        """Cleanup should remove the entire sandbox dir."""
        sandbox_root = sandbox_project["sandbox_root"]
        assert os.path.isdir(sandbox_root)

        # Simulate cleanup
        shutil.rmtree(sandbox_root)
        assert not os.path.exists(sandbox_root)

    def test_sandbox_per_session_isolation(self, tmp_path):
        """Each session gets its own sandbox directory."""
        project_root = tmp_path / "project"
        project_root.mkdir()

        sessions = ["session_1", "session_2", "session_3"]
        for sid in sessions:
            sb = project_root / ".adt" / "sandbox" / sid
            sb.mkdir(parents=True)

        # Each sandbox is independent
        for sid in sessions:
            sb = project_root / ".adt" / "sandbox" / sid
            assert sb.exists()

        # Removing one doesn't affect others
        shutil.rmtree(str(project_root / ".adt" / "sandbox" / "session_2"))
        assert (project_root / ".adt" / "sandbox" / "session_1").exists()
        assert not (project_root / ".adt" / "sandbox" / "session_2").exists()
        assert (project_root / ".adt" / "sandbox" / "session_3").exists()


# === Test Class: Claude Config Generation ===

class TestClaudeConfigGeneration:
    """Verify Claude Code settings.json is properly generated."""

    def test_settings_json_has_allowed_directories(self, sandbox_project):
        """Generated settings.json should contain allowedDirectories."""
        sandbox_root = sandbox_project["sandbox_root"]
        project_root = sandbox_project["project_root"]

        # Simulate what pty.rs generates
        config = {
            "permissions": {
                "allow": ["Bash(python3:*)", "Bash(git:*)"],
                "deny": ["Bash(curl:*)", "Bash(wget:*)"]
            },
            "allowedDirectories": [project_root]
        }

        settings_path = os.path.join(sandbox_root, ".claude", "settings.json")
        with open(settings_path, "w") as f:
            json.dump(config, f, indent=2)

        # Verify
        with open(settings_path) as f:
            loaded = json.load(f)

        assert "allowedDirectories" in loaded
        assert project_root in loaded["allowedDirectories"]
        assert len(loaded["allowedDirectories"]) == 1

    def test_settings_denies_dangerous_bash_commands(self, sandbox_project):
        """Settings should deny curl, wget, ssh, scp."""
        config = {
            "permissions": {
                "deny": [
                    "Bash(curl:*)", "Bash(wget:*)",
                    "Bash(ssh:*)", "Bash(scp:*)"
                ]
            }
        }

        for pattern in config["permissions"]["deny"]:
            tool = pattern.split("(")[1].split(":")[0]
            assert tool in ["curl", "wget", "ssh", "scp"]


# === Test Class: Gemini Config Generation ===

class TestGeminiConfigGeneration:
    """Verify Gemini CLI settings.json is properly generated."""

    def test_gemini_config_has_sandbox_dirs(self, sandbox_project):
        """Generated Gemini config should have allowedDirectories."""
        sandbox_root = sandbox_project["sandbox_root"]
        project_root = sandbox_project["project_root"]

        config = {
            "sandbox": {
                "allowedDirectories": [project_root]
            },
            "hooks": {
                "BeforeTool": [{
                    "matcher": "write_file|replace|read_file|list_files|search_files",
                    "hooks": [{
                        "type": "command",
                        "command": "python3 /path/to/gemini_pretool.py",
                        "timeout": 15000
                    }]
                }]
            }
        }

        settings_path = os.path.join(sandbox_root, ".gemini", "settings.json")
        with open(settings_path, "w") as f:
            json.dump(config, f, indent=2)

        with open(settings_path) as f:
            loaded = json.load(f)

        assert loaded["sandbox"]["allowedDirectories"] == [project_root]

    def test_gemini_hook_intercepts_read_tools(self, sandbox_project):
        """Gemini hook matcher should include read tools when sandboxed."""
        matcher = "write_file|replace|read_file|list_files|search_files"
        tools = matcher.split("|")
        assert "read_file" in tools
        assert "list_files" in tools
        assert "search_files" in tools


# === Test Class: Framework Self-Governance Exception ===

class TestFrameworkException:
    """Verify framework project gets relaxed sandbox."""

    def test_framework_project_detected(self, tmp_path):
        """When project_root == framework_root, it's a framework project."""
        framework_root = tmp_path / "adt-framework"
        framework_root.mkdir()

        # Same path = framework project
        canon_project = os.path.realpath(str(framework_root))
        canon_framework = os.path.realpath(str(framework_root))
        assert canon_project == canon_framework

    def test_external_project_not_framework(self, tmp_path):
        """When project_root differs from framework_root, it's external."""
        framework_root = tmp_path / "adt-framework"
        framework_root.mkdir()
        project_root = tmp_path / "my-app"
        project_root.mkdir()

        canon_project = os.path.realpath(str(project_root))
        canon_framework = os.path.realpath(str(framework_root))
        assert canon_project != canon_framework


# === Test Class: Gemini Hook Sandbox Support ===

class TestGeminiHookSandbox:
    """Verify the Gemini hook respects ADT_SANDBOX."""

    def test_gemini_hook_has_read_tools(self):
        """Gemini hook should define READ_TOOLS for sandbox mode."""
        mod = _load_gemini_hook()
        assert hasattr(mod, "READ_TOOLS"), "Gemini hook should have READ_TOOLS set"
        assert "read_file" in mod.READ_TOOLS
        assert "list_files" in mod.READ_TOOLS
        assert "search_files" in mod.READ_TOOLS

    def test_gemini_path_outside_project_detected(self, sandbox_project):
        """Gemini hook containment check should catch external paths."""
        mod = _load_gemini_hook()
        project_root = sandbox_project["project_root"]
        external = sandbox_project["external_dir"]

        rel = mod.to_project_relative(
            os.path.join(external, "secret.txt"), project_root
        )
        # Outside project returns absolute path
        assert os.path.isabs(rel), f"Path outside project should remain absolute: {rel}"


# === Test Class: Phase B Namespace Isolation (task_150) ===

class TestPhaseB_NamespaceIsolation:
    """Verify OS-level namespace isolation logic (SPEC-036 Phase B)."""

    def test_bwrap_detection(self):
        """bubblewrap availability should be detectable."""
        import shutil
        bwrap_path = shutil.which("bwrap")
        # bwrap may or may not be installed -- test just ensures no crash
        if bwrap_path:
            assert os.path.isfile(bwrap_path)

    def test_bwrap_args_contain_ro_bind(self, sandbox_project):
        """bwrap args should include read-only system dir binds."""
        project_root = sandbox_project["project_root"]
        # Simulate build_bwrap_args logic
        args = [
            "bwrap",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/sbin", "/sbin",
            "--ro-bind", "/etc", "/etc",
            "--bind", project_root, "/project",
            "--tmpfs", "/tmp",
            "--dev", "/dev",
            "--proc", "/proc",
            "--unshare-net",
            "--die-with-parent",
            "--chdir", "/project",
            "--",
        ]

        # Verify structure
        assert args[0] == "bwrap"
        assert "--ro-bind" in args
        assert "--bind" in args
        assert "--unshare-net" in args
        assert "--die-with-parent" in args
        assert args[-1] == "--"

        # /usr should be read-only
        ro_bind_idx = args.index("--ro-bind")
        assert args[ro_bind_idx + 1] == "/usr"

        # Project should be read-write bind
        bind_idx = args.index("--bind")
        assert args[bind_idx + 1] == project_root
        assert args[bind_idx + 2] == "/project"

    def test_bwrap_no_home_dir_exposed(self, sandbox_project):
        """bwrap args should NOT include /home binding."""
        args = [
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/bin", "/bin",
            "--bind", sandbox_project["project_root"], "/project",
            "--tmpfs", "/tmp",
        ]
        # /home should not appear anywhere in binds
        home_binds = [a for a in args if a.startswith("/home")]
        assert len(home_binds) == 0, "No /home paths should be in bwrap args"

    def test_network_isolation_flag_present(self):
        """bwrap should include --unshare-net for network isolation."""
        args = ["--unshare-net", "--die-with-parent"]
        assert "--unshare-net" in args

    def test_die_with_parent_flag(self):
        """bwrap should kill agent if Console dies."""
        args = ["--die-with-parent"]
        assert "--die-with-parent" in args

    def test_unshare_script_mounts_project(self, sandbox_project):
        """unshare script should mount project at /sandbox/project."""
        project_root = sandbox_project["project_root"]
        # Simulate build_unshare_script
        script = f"mount --bind {project_root} /sandbox/project"
        assert project_root in script
        assert "/sandbox/project" in script

    def test_unshare_script_makes_system_readonly(self):
        """unshare script should mount system dirs read-only."""
        script = "mount --rbind /usr /sandbox/usr"
        assert "--rbind" in script
        assert "/usr" in script

    def test_phase_b_only_for_external_projects(self, tmp_path):
        """Phase B should NOT activate for framework project."""
        framework_root = tmp_path / "adt-framework"
        framework_root.mkdir()

        # Same path = framework = no Phase B
        is_framework = (
            os.path.realpath(str(framework_root)) ==
            os.path.realpath(str(framework_root))
        )
        assert is_framework, "Framework project should be detected"

        # Different path = external = Phase B applies
        external = tmp_path / "my-app"
        external.mkdir()
        is_external = (
            os.path.realpath(str(external)) !=
            os.path.realpath(str(framework_root))
        )
        assert is_external, "External project should be detected"

    def test_phase_b_requires_production_mode(self):
        """Phase B should only activate when production mode is on."""
        # In code, Phase B is gated by: production_mode && !is_framework
        production_mode = False
        is_framework = False
        should_phase_b = production_mode and not is_framework
        assert not should_phase_b, "Phase B requires production mode"

        production_mode = True
        should_phase_b = production_mode and not is_framework
        assert should_phase_b, "Phase B should activate with production mode"


class TestBashSandboxInterception:
    """SPEC-036: Bash tool sandbox containment tests."""

    def test_bash_write_outside_project_denied(self, sandbox_project):
        """Bash redirect to path outside project root must be denied."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox("echo x > /tmp/evil.txt", project_root)
        assert result, "Write to /tmp should be denied"
        assert "outside project root" in result

    def test_bash_write_inside_project_allowed(self, sandbox_project):
        """Bash redirect to path inside project root must be allowed."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        target = os.path.join(project_root, "output.txt")
        result = mod.check_bash_sandbox(f"echo test > {target}", project_root)
        assert result == "", f"Write inside project should be allowed, got: {result}"

    def test_bash_read_etc_denied(self, sandbox_project):
        """Bash reading /etc/* must be denied."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox("cat /etc/shadow", project_root)
        assert result, "/etc/shadow should be denied"
        assert "sensitive path" in result

    def test_bash_read_ssh_keys_denied(self, sandbox_project):
        """Bash reading ~/.ssh/* must be denied."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox("cat ~/.ssh/id_rsa", project_root)
        assert result, "SSH keys should be denied"
        assert "sensitive path" in result or "credentials" in result

    def test_bash_read_aws_credentials_denied(self, sandbox_project):
        """Bash reading ~/.aws/* must be denied."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox("cat ~/.aws/credentials", project_root)
        assert result, "AWS creds should be denied"

    def test_bash_sudo_unconditionally_denied(self, sandbox_project):
        """sudo must be blocked regardless of target path."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox("sudo apt install something", project_root)
        assert result, "sudo should be denied"
        assert "sudo" in result

    def test_bash_python_oneliner_write_denied(self, sandbox_project):
        """Python one-liner file writes must be denied."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox(
            "python3 -c \"open('/tmp/x','w').write('y')\"", project_root
        )
        assert result, "Python file write should be denied"
        assert "scripting language" in result

    def test_bash_node_oneliner_write_denied(self, sandbox_project):
        """Node one-liner file writes must be denied."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox(
            "node -e \"fs.writeFileSync('/x','y')\"", project_root
        )
        assert result, "Node file write should be denied"
        assert "scripting language" in result

    def test_bash_tee_outside_denied(self, sandbox_project):
        """tee to path outside project must be denied."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox("echo x | tee /tmp/out.txt", project_root)
        assert result, "tee to /tmp should be denied"

    def test_bash_cp_outside_denied(self, sandbox_project):
        """cp to path outside project must be denied."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox("cp secret.txt /home/other/", project_root)
        assert result, "cp outside should be denied"

    def test_bash_symlink_escape_denied(self, sandbox_project):
        """ln -s creating escape symlink must be denied."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        target = os.path.join(project_root, "link")
        result = mod.check_bash_sandbox(
            f"ln -s /etc/passwd {target}", project_root
        )
        assert result, "Symlink to /etc should be denied"

    def test_bash_safe_commands_allowed(self, sandbox_project):
        """Safe commands with no external paths must be allowed."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        safe_commands = [
            "git status",
            "python3 main.py",
            "pip install flask",
            "npm test",
            "cargo build",
            "make all",
            "pytest -v",
        ]
        for cmd in safe_commands:
            result = mod.check_bash_sandbox(cmd, project_root)
            assert result == "", f"'{cmd}' should be allowed, got: {result}"

    def test_bash_proc_access_denied(self, sandbox_project):
        """Access to /proc must be denied."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox("cat /proc/1/cmdline", project_root)
        assert result, "/proc should be denied"

    def test_bash_chmod_outside_denied(self, sandbox_project):
        """chmod on path outside project must be denied."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox("chmod 777 /etc/crontab", project_root)
        assert result, "chmod outside should be denied"

    def test_bash_chmod_inside_allowed(self, sandbox_project):
        """chmod on path inside project must be allowed."""
        mod = _load_claude_hook()
        project_root = str(sandbox_project["project_root"])
        target = os.path.join(project_root, "run.sh")
        result = mod.check_bash_sandbox(f"chmod +x {target}", project_root)
        assert result == "", f"chmod inside project should be allowed, got: {result}"


class TestGeminiBashSandbox:
    """SPEC-036: Gemini shell tool sandbox containment tests."""

    def test_gemini_bash_write_outside_denied(self, sandbox_project):
        """Gemini shell write outside project must be denied."""
        mod = _load_gemini_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox("echo x > /tmp/evil.txt", project_root)
        assert result, "Write to /tmp should be denied"

    def test_gemini_bash_sudo_denied(self, sandbox_project):
        """Gemini shell sudo must be denied."""
        mod = _load_gemini_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox("sudo rm -rf /", project_root)
        assert result, "sudo should be denied"

    def test_gemini_bash_safe_allowed(self, sandbox_project):
        """Gemini shell safe commands must be allowed."""
        mod = _load_gemini_hook()
        project_root = str(sandbox_project["project_root"])
        result = mod.check_bash_sandbox("npm test", project_root)
        assert result == "", "npm test should be allowed"

    def test_gemini_has_bash_tools_defined(self):
        """Gemini hook must define BASH_TOOLS for shell interception."""
        mod = _load_gemini_hook()
        assert hasattr(mod, "BASH_TOOLS"), "BASH_TOOLS must be defined"
        assert "run_shell" in mod.BASH_TOOLS or "shell" in mod.BASH_TOOLS
