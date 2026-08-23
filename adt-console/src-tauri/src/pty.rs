// PTY multiplexer — spawn and manage terminal processes
// SPEC-021 Phase A: portable-pty based process management
// SPEC-021 S9: Persistence and stability improvements
// SPEC-036: Agent Filesystem Sandbox (Phase A)
// SPEC-057: Agent Mailbox spawn-time AUTO/MANUAL mode + comms dirs

use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtySize};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{Emitter, Runtime};

#[cfg(unix)]
use std::os::unix::process::CommandExt;
#[cfg(unix)]
use nix::sys::signal::{self, Signal};
#[cfg(unix)]
use nix::unistd::Pid;

/// Resolve the user's login shell PATH.
/// Tauri apps launched from desktop environments often inherit a minimal PATH
/// that doesn't include user-installed tools (npm global, cargo, etc.).
/// This runs the user's shell to get the full PATH.
fn resolve_user_path() -> String {
    let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/bash".to_string());
    // Use -li (login + interactive) so both .profile AND .bashrc are sourced.
    // Many users add PATH entries in .bashrc which -l alone won't pick up
    // (non-interactive login shells skip .bashrc on bash).
    for flags in &[["-li", "-c", "echo $PATH"], ["-l", "-c", "echo $PATH"]] {
        if let Ok(output) = Command::new(&shell)
            .args(flags.as_slice())
            .output()
        {
            let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !path.is_empty() {
                return path;
            }
        }
    }
    // Fallback: current PATH plus common user binary locations
    let current = std::env::var("PATH").unwrap_or_default();
    let home = std::env::var("HOME").unwrap_or_else(|_| "/root".to_string());
    format!(
        "{}/.npm-global/bin:{}/.cargo/bin:{}/.local/bin:{}",
        home, home, home, current
    )
}

/// Resolve a command name to its absolute path using the user's full PATH.
/// Falls back to the original command name if resolution fails.
fn resolve_command(command: &str, user_path: &str) -> String {
    if command.starts_with('/') {
        return command.to_string();
    }
    for dir in user_path.split(':') {
        let candidate = PathBuf::from(dir).join(command);
        if candidate.exists() {
            if let Some(path_str) = candidate.to_str() {
                return path_str.to_string();
            }
        }
    }
    // Env var override: AGY_EXECPATH, CLAUDE_EXECPATH, GEMINI_EXECPATH, etc.
    let env_var = format!("{}_EXECPATH", command.to_uppercase().replace('-', "_"));
    if let Ok(p) = std::env::var(&env_var) {
        if PathBuf::from(&p).exists() { return p; }
    }
    // Common install locations beyond PATH (covers Tauri-from-Apps-grid case
    // where PATH is stripped down to /usr/bin:/bin).
    let home = std::env::var("HOME").unwrap_or_else(|_| "/root".to_string());
    let extras = vec![
        format!("{}/.local/bin/{}", home, command),
        format!("{}/.npm-global/bin/{}", home, command),
        format!("{}/.cargo/bin/{}", home, command),
        format!("/usr/local/bin/{}", command),
        format!("/usr/bin/{}", command),
        format!("/opt/antigravity/bin/{}", command),
        format!("/snap/bin/{}", command),
    ];
    for p in &extras {
        if PathBuf::from(p).exists() { return p.clone(); }
    }
    command.to_string()
}

/// Pre-spawn validation: confirms resolved binary exists. Returns operator-friendly error
/// if missing, with searched paths + install hint.
fn validate_agent_binary(agent: &str, resolved: &str, user_path: &str) -> Result<String, String> {
    let p = PathBuf::from(resolved);
    if p.exists() && p.is_file() {
        return Ok(resolved.to_string());
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| "~".to_string());
    let install_hint = match agent {
        "agy" | "antigravity" => "Install agy from https://antigravity.google then re-launch the Console.",
        "claude" => "Install Claude Code CLI from https://docs.claude.com/en/docs/claude-code then re-launch.",
        "gemini" => "Install via: npm install -g @google/gemini-cli",
        _ => "Install the missing CLI and re-launch the Console.",
    };
    Err(format!(
        "{} binary not found. Searched PATH ({}) plus {}/.local/bin/, {}/.npm-global/bin/, /usr/local/bin/, /opt/antigravity/bin/, /snap/bin/. {}",
        agent, user_path.split(':').collect::<Vec<_>>().join(", "), home, home, install_hint
    ))
}


// --- SPEC-036: Agent Filesystem Sandbox ---

/// Environment variables that must NEVER be passed to sandboxed agent sessions.
/// These could leak sensitive credentials or paths outside the sandbox.

/// Environment variables that are EXPLICITLY allowed to pass into sandboxed sessions.
const SANDBOX_ENV_ALLOWLIST: &[&str] = &[
    "GEMINI_API_KEY",
    "CLAUDE_CONFIG_DIR",
    "GEMINI_CONFIG_DIR",
    // SPEC-062 Amendment D: pass-through for keyring access so agy can re-use
    // cached OAuth from the host gnome-keyring-daemon instead of forcing OAuth
    // on every spawn.
    "DBUS_SESSION_BUS_ADDRESS",
    "XDG_RUNTIME_DIR",
    "GNOME_KEYRING_CONTROL",
    "XDG_SESSION_TYPE",
    "DISPLAY",
];

const SANDBOX_ENV_DENYLIST: &[&str] = &[
    "SSH_AUTH_SOCK", "SSH_AGENT_PID",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "AWS_DEFAULT_REGION", "AWS_PROFILE",
    "GCP_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT",
    "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID",
    "AZURE_SUBSCRIPTION_ID",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "ADT_FRAMEWORK_ROOT",
    "GITHUB_TOKEN", "GH_TOKEN", "GITLAB_TOKEN",
    "NPM_TOKEN", "PYPI_TOKEN",
    "DATABASE_URL", "REDIS_URL",
    "DOCKER_HOST",
    // Note (SPEC-108 rollback 2026-08-15): ANTIGRAVITY_LS_ADDRESS,
    // ANTIGRAVITY_CSRF_TOKEN, ANTIGRAVITY_SESSION_TOKEN were briefly added
    // but AGY needs all three to talk to its own local Language Server
    // and to remember auth state -- stripping forced re-auth on every
    // spawn. Left out here; the LS + CSRF + session token vars are AGY's
    // own attack surface, out of scope for the ADT sandbox. See SPEC-108
    // §9 for the deferred egress-proxy + per-session credential
    // scoping story.
];

/// Prefixes for environment variables that should be stripped from sandboxed sessions.
const SANDBOX_ENV_PREFIX_DENYLIST: &[&str] = &[
    "AWS_", "GCP_", "AZURE_", "GOOGLE_CLOUD_",
];

/// Create the sandbox directory structure for a session.
/// Returns the sandbox root path: <project_root>/.adt/sandbox/<session_id>/
fn create_sandbox_dir(project_root: &Path, session_id: &str) -> Result<PathBuf, String> {
    let sandbox_root = project_root
        .join(".adt")
        .join("sandbox")
        .join(session_id);

    // Create subdirectories
    for subdir in &[".claude", ".gemini", "home", "tmp"] {
        fs::create_dir_all(sandbox_root.join(subdir))
            .map_err(|e| format!("Failed to create sandbox dir {}: {}", subdir, e))?;
    }

    // In production mode, make sandbox dirs writable by the 'agent' OS user.
    // The Tauri process runs as 'human' and creates dirs owned by human:human,
    // but sudo -u agent needs the agent user to write to HOME/TMPDIR inside the sandbox.
    if is_production_mode() {
        let _ = Command::new("/usr/bin/sudo")
            .args(["/bin/chmod", "-R", "777", &sandbox_root.to_string_lossy()])
            .output();
        log::info!("[SANDBOX] Set sandbox permissions for agent user via sudo");
    }

    log::info!("[SANDBOX] Created sandbox at {:?}", sandbox_root);
    Ok(sandbox_root)
}

/// Clean up a session's sandbox directory.
fn cleanup_sandbox(project_root: &Path, session_id: &str) {
    let sandbox_root = project_root
        .join(".adt")
        .join("sandbox")
        .join(session_id);

    if sandbox_root.exists() {
        if let Err(e) = fs::remove_dir_all(&sandbox_root) {
            log::warn!("[SANDBOX] Failed to cleanup {:?}: {}", sandbox_root, e);
        } else {
            log::info!("[SANDBOX] Cleaned up sandbox for {}", session_id);
        }
    }
}

/// Generate Claude Code sandbox settings file.
/// This file is loaded via `claude --settings <path>` to enforce sandbox restrictions.
/// Uses Claude Code's native permission system to deny access outside project root.
/// When `namespace_mode` is true, hook paths use /adt-framework/ (the bwrap mount point)
/// instead of host absolute paths.
fn generate_claude_sandbox_config(
    sandbox_root: &Path,
    project_root: &Path,
    framework_root: &Path,
    namespace_mode: bool,
) -> Result<PathBuf, String> {
    let _project_str = project_root.to_string_lossy();

    // Hook script path -- inside namespace it's at /adt-framework/..., on host it's absolute
    let hook_path = if namespace_mode {
        "/adt-framework/adt_sdk/hooks/claude_pretool.py".to_string()
    } else {
        let hook_script = framework_root
            .join("adt_sdk")
            .join("hooks")
            .join("claude_pretool.py");
        hook_script.to_string_lossy().to_string()
    };

    // Claude Code uses `permissions.deny` patterns and `hooks` in settings.json.
    // The --settings flag merges these with the project's own settings.
    let config = serde_json::json!({
        "permissions": {
            "deny": [
                "Bash(curl:*)",
                "Bash(wget:*)",
                "Bash(ssh:*)",
                "Bash(scp:*)"
            ]
        },
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write|Edit|NotebookEdit|Read|Glob|Grep|Bash",
                    "hooks": [{
                        "type": "command",
                        "command": format!("python3 {}", hook_path),
                        "timeout": 15
                    }]
                }
            ]
        }
    });

    let settings_path = sandbox_root.join("claude_sandbox_settings.json");
    let json_str = serde_json::to_string_pretty(&config)
        .map_err(|e| format!("Failed to serialize Claude config: {}", e))?;
    fs::write(&settings_path, &json_str)
        .map_err(|e| format!("Failed to write Claude sandbox config: {}", e))?;

    log::info!("[SANDBOX] Generated Claude sandbox settings at {:?}", settings_path);
    Ok(settings_path)
}

/// Generate Gemini CLI sandbox settings.json.
/// Gemini CLI uses --sandbox flag and .gemini/settings.json in CWD.
/// We write a settings.json in the project's .gemini/ dir with extended hooks.
/// When `namespace_mode` is true, hook paths use /adt-framework/ mount point.
fn generate_gemini_sandbox_config(
    _sandbox_root: &Path,
    project_root: &Path,
    framework_root: &Path,
    namespace_mode: bool,
) -> Result<(), String> {
    // Determine hook script path -- namespace uses /adt-framework/ mount
    let hook_path = if namespace_mode {
        "/adt-framework/adt_sdk/hooks/gemini_pretool.py".to_string()
    } else {
        let hook_script = framework_root
            .join("adt_sdk")
            .join("hooks")
            .join("gemini_pretool.py");
        hook_script.to_string_lossy().to_string()
    };

    // Write extended hook config that intercepts BOTH read and write tools
    let config = serde_json::json!({
        "hooks": {
            "BeforeTool": [{
                "matcher": "write_file|replace|read_file|list_files|search_files|run_shell|shell",
                "hooks": [{
                    "type": "command",
                    "command": format!("python3 {}", hook_path),
                    "timeout": 15000
                }]
            }]
        }
    });

    // Write to project's .gemini/settings.json (Gemini reads from CWD)
    let gemini_dir = project_root.join(".gemini");
    let _ = fs::create_dir_all(&gemini_dir);
    let settings_path = gemini_dir.join("settings.json");

    // Only write if no settings.json exists (don't overwrite project config)
    if !settings_path.exists() {
        let json_str = serde_json::to_string_pretty(&config)
            .map_err(|e| format!("Failed to serialize Gemini config: {}", e))?;
        fs::write(&settings_path, json_str)
            .map_err(|e| format!("Failed to write Gemini sandbox config: {}", e))?;
        log::info!("[SANDBOX] Generated Gemini config at {:?}", settings_path);
    } else {
        log::info!("[SANDBOX] Gemini settings.json already exists, skipping generation");
    }

    Ok(())
}

/// Apply sandbox environment variables to a CommandBuilder.
/// Sanitizes the environment by:
/// 1. Redirecting HOME and TMPDIR to sandbox directories
/// 2. Setting ADT_SANDBOX=1 and ADT_SANDBOX_ROOT
/// 3. Removing sensitive env vars (cloud creds, SSH keys, etc.)
/// 4. Pointing agent config dirs to sandbox copies
/// When `namespace_mode` is true, paths are relative to the bwrap mount layout
/// (/project, /adt-framework) instead of host absolute paths.
fn apply_sandbox_env(
    cmd: &mut CommandBuilder,
    sandbox_root: &Path,
    project_root: &Path,
    agent: &str,
    dtcp_url: &str,
    namespace_mode: bool,
    session_id: &str,
) {

    if namespace_mode {
        // Inside bwrap: project is at /project, framework at /adt-framework
        let ns_sandbox_home = format!("/project/.adt/sandbox/{}/home", session_id);
        cmd.env("HOME", &ns_sandbox_home);
        cmd.env("TMPDIR", "/tmp");
        cmd.env("ADT_SANDBOX", "1");
        cmd.env("ADT_SANDBOX_ROOT", "/project");
        cmd.env("ADT_PROJECT_DIR", "/project");
        cmd.env("DTCP_URL", dtcp_url);
        cmd.env("DTTP_URL", dtcp_url); // Fallback
        cmd.env("PYTHONPATH", "/adt-framework");
    } else {
        // Phase A only: host absolute paths
        let sandbox_home = sandbox_root.join("home");
        let sandbox_tmp = sandbox_root.join("tmp");
        let project_str = project_root.to_string_lossy().to_string();

        cmd.env("HOME", sandbox_home.to_string_lossy().as_ref());
        cmd.env("TMPDIR", sandbox_tmp.to_string_lossy().as_ref());
        cmd.env("ADT_SANDBOX", "1");
        cmd.env("ADT_SANDBOX_ROOT", &project_str);
        cmd.env("ADT_PROJECT_DIR", &project_str);
        cmd.env("DTCP_URL", dtcp_url);
        cmd.env("DTTP_URL", dtcp_url); // Fallback
    }

    // Pass through allowed variables from the host environment
    for var in SANDBOX_ENV_ALLOWLIST {
        if let Ok(val) = std::env::var(var) {
            cmd.env(var, val);
        }
    }

    // Remove sensitive environment variables.
    // Amended 2026-08-15 (SPEC-108): use env_remove instead of env(var, "")
    // — setting to empty leaves the var *present with empty value*, which
    // some tools treat as "still set" and follow (e.g. gpg-agent walks
    // SSH_AUTH_SOCK even when empty; keyring libs re-derive it from
    // XDG_RUNTIME_DIR). env_remove actually deletes the entry from the
    // child's inherited env.
    for var in SANDBOX_ENV_DENYLIST {
        cmd.env_remove(*var);
    }

    // Also remove prefix-matched vars from the current process env
    for (key, _) in std::env::vars() {
        for prefix in SANDBOX_ENV_PREFIX_DENYLIST {
            if key.starts_with(prefix) && !SANDBOX_ENV_DENYLIST.contains(&key.as_str()) {
                cmd.env_remove(&key);
            }
        }
    }

    log::info!(
        "[SANDBOX] Environment sanitized for {} session (namespace_mode={})",
        agent, namespace_mode
    );
}


/// Ensure the spawned child can reach the operator's gnome-keyring so that
/// agy (and any agent using libsecret / go-keyring / python-keyring) reuses
/// cached OAuth tokens instead of re-prompting on every spawn.
///
/// These are safe to set unconditionally — they point at the user's own
/// session bus and runtime dir, both populated by systemd at login.
/// Overriding covers the case where the console was launched via a GTK
/// .desktop entry with a stripped env (no DBUS_SESSION_BUS_ADDRESS).
fn apply_keyring_env(cmd: &mut CommandBuilder) {
    let uid = nix::unistd::getuid().as_raw();
    let runtime_dir = format!("/run/user/{}", uid);
    let dbus_addr = format!("unix:path={}/bus", runtime_dir);
    cmd.env("XDG_RUNTIME_DIR", &runtime_dir);
    cmd.env("DBUS_SESSION_BUS_ADDRESS", &dbus_addr);
}

/// Human-writable console settings file. Read at every spawn so the UI
/// toggle takes effect on the next new session (no Console restart needed).
/// Perms are enforced 0600 on write so PTY child agents (which typically
/// don't run as the operator UID once sandboxed) cannot mutate it.
const CONSOLE_SETTINGS_REL: &str = ".adt/console_settings.json";

fn console_settings_path() -> Option<PathBuf> {
    dirs::home_dir().map(|h| h.join(CONSOLE_SETTINGS_REL))
}

/// Read the dev_mode field from console_settings.json.
///
/// Returns:
/// - `Some(true)`  → operator explicitly toggled Dev Mode ON.
/// - `Some(false)` → operator explicitly toggled Dev Mode OFF (sandbox pinned).
/// - `None`        → no file / no dev_mode field → fall back to env var.
///
/// The tri-state matters because the UI toggle must be able to OVERRIDE a
/// polluted shell env (e.g. `systemd --user` inherited `ADT_DEV_MODE=1` at
/// login and there's no way to clear it short of a re-login). If the
/// operator has ever clicked the toggle, that click wins.
pub fn read_ui_dev_mode() -> Option<bool> {
    let path = console_settings_path()?;
    let raw = fs::read_to_string(&path).ok()?;
    for line in raw.lines() {
        let t = line.trim();
        if t.starts_with("\"dev_mode\"") || t.starts_with("dev_mode") {
            if t.contains("true") { return Some(true); }
            if t.contains("false") { return Some(false); }
        }
    }
    None
}

/// Determine if a session should be sandboxed.
/// Returns true for agent sessions with a project CWD.
///
/// Amended 2026-08-15: framework sessions ARE now sandboxed too (the previous
/// `!is_fw` bypass was gap 2 from the operator's audit). Only `agent == shell|human`
/// bypasses. The dev-mode escape hatch is honored either via env
/// `ADT_DEV_MODE=1` (legacy shell control) OR via the UI toggle persisted in
/// `~/.adt/console_settings.json::dev_mode` (operator-writable only).
fn should_sandbox(agent: &str, cwd: Option<&str>) -> bool {
    if agent == "shell" || agent == "human" {
        return false;
    }
    !effective_sandbox_disabled_with_reason().0 && cwd.is_some()
}

/// Compute effective sandbox_disabled state, prioritizing UI file over env.
/// Returns (disabled, human_readable_reason).
pub fn effective_sandbox_disabled_with_reason() -> (bool, &'static str) {
    // UI file always wins if present -- necessary because systemd --user
    // inherits ADT_DEV_MODE=1 from login and there's no clean way to
    // clear it without a re-login. The UI toggle must be able to pin the
    // sandbox ON regardless of a polluted shell env.
    match read_ui_dev_mode() {
        Some(true)  => (true,  "ui_toggle_dev_mode_on"),
        Some(false) => (false, "ui_toggle_pinned_sandbox_on"),
        None => {
            let env_disable = std::env::var("ADT_DEV_MODE")
                .map(|v| v == "1")
                .unwrap_or(false);
            if env_disable {
                (true, "env_var_ADT_DEV_MODE_1")
            } else {
                (false, "default_sandbox_on")
            }
        }
    }
}

/// Get the framework root directory (where the ADT Framework is installed).
fn get_framework_root() -> PathBuf {
    if let Ok(root) = std::env::var("ADT_FRAMEWORK_ROOT") {
        let path = PathBuf::from(root);
        if path.exists() {
            return path;
        }
    }
    // Fallback 1: Standard location
    if let Some(home) = dirs::home_dir() {
        let path = home.join("Projects/adt-framework");
        if path.exists() {
            return path;
        }
    }
    // Fallback 2: Current executable directory traversal (for development)
    if let Ok(exe_path) = std::env::current_exe() {
        let mut curr = exe_path.parent();
        while let Some(path) = curr {
            if path.join("_cortex").exists() {
                return path.to_path_buf();
            }
            curr = path.parent();
        }
    }
    // Final fallback: current directory
    PathBuf::from(".")
}

/// SPEC-057: Determine the default messaging mode for a session based on role.
/// Systems_Architect spawns in MANUAL (human is directly engaged there).
/// All worker roles spawn in AUTO (automated orchestration expected).
fn default_messaging_mode_for_role(role: &str) -> &'static str {
    if role == "Systems_Architect" {
        "MANUAL"
    } else {
        "AUTO"
    }
}

/// SPEC-057: Create the per-session mailbox directory tree under
/// `<framework_root>/_cortex/comms/agents/<session_id>/{inbox,outbox,pending}`.
/// Failure is logged but non-fatal: PTY spawn should not abort if the comms
/// tree cannot be created (the watcher will recreate on first message).
fn create_comms_dirs(framework_root: &Path, session_id: &str) {
    let session_root = framework_root
        .join("_cortex")
        .join("comms")
        .join("agents")
        .join(session_id);
    for subdir in &["inbox", "outbox", "pending"] {
        let path = session_root.join(subdir);
        if let Err(e) = fs::create_dir_all(&path) {
            log::warn!("[COMMS] Failed to create {:?}: {}", path, e);
            return;
        }
    }
    log::info!("[COMMS] Created mailbox at {:?}", session_root);
}

/// Check if a project path is the framework itself.
fn is_framework_project(project_root: &Path, framework_root: &Path) -> bool {
    // Canonicalize both paths for reliable comparison
    let canon_project = project_root.canonicalize().unwrap_or_else(|_| project_root.to_path_buf());
    let canon_framework = framework_root.canonicalize().unwrap_or_else(|_| framework_root.to_path_buf());
    canon_project == canon_framework
}


// --- SPEC-036 Phase B: OS-Level Namespace Isolation ---

/// Check if bubblewrap (bwrap) is available AND functional on the system.
/// Just checking existence is insufficient — unprivileged user namespaces may be
/// disabled (sysctl kernel.unprivileged_userns_clone=0), causing bwrap to fail
/// with "Permission denied" at runtime despite the binary existing.
fn has_bubblewrap() -> bool {
    if !Path::new("/usr/bin/bwrap").exists() {
        return false;
    }
    // Smoke-test bwrap end-to-end. Amended 2026-08-15: the previous
    // `--ro-bind /usr /usr` was insufficient — on distros where /bin,
    // /lib64 and friends are separate from /usr the sandbox couldn't
    // resolve /usr/bin/true. Also missing --unshare-user meant hosts
    // needing bwrap's setuid path (AppArmor + no unpriv userns) failed
    // even though bwrap would work correctly for a real spawn. Full
    // `--ro-bind / /` + explicit `--unshare-user` mirrors what we
    // actually ask bwrap to do in wrap_with_namespace(), so a passing
    // probe genuinely means a real spawn will work.
    Command::new("/usr/bin/bwrap")
        .args(["--unshare-user", "--ro-bind", "/", "/", "--", "/usr/bin/true"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// Check if user namespaces are supported (unshare works without root).
fn has_user_namespaces() -> bool {
    Command::new("/usr/bin/unshare")
        .args(["--user", "--map-root-user", "true"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// Build the command prefix for bubblewrap (bwrap) sandboxing.
/// This creates a minimal filesystem view containing only the project root
/// and essential system directories (read-only).
/// Amended 2026-08-15: --unshare-net removed. The socat bridge scheme
/// (SPEC-036 task_148) was still routing agent traffic through host
/// localhost sockets via a bash-quoted wrapper — that wrapper broke
/// with parens in agent commands ("Syntax error: `(` unexpected") and
/// also cut the agents off from external APIs (Anthropic, Google). We
/// keep filesystem isolation (the primary jurisdictional guarantee)
/// but let agents reach the network directly, matching SPEC-105
/// spawn.py's `network="full"` default.
fn build_bwrap_args(
    project_root: &Path,
    _dtcp_port: u16,

    agent_binary_path: &str,
    framework_root: &Path,
) -> Vec<String> {
    let project_str = project_root.to_string_lossy().to_string();
    let framework_str = framework_root.to_string_lossy().to_string();

    let mut args = vec![
        "/usr/bin/bwrap".to_string(),
        // Essential system dirs (read-only)
        "--ro-bind".to_string(), "/usr".to_string(), "/usr".to_string(),
        "--ro-bind".to_string(), "/lib".to_string(), "/lib".to_string(),
        "--ro-bind".to_string(), "/bin".to_string(), "/bin".to_string(),
        "--ro-bind".to_string(), "/sbin".to_string(), "/sbin".to_string(),
        "--ro-bind".to_string(), "/etc".to_string(), "/etc".to_string(),
    ];

    // /usr/local contains many user tools and often their targets (e.g. /usr/local/nodejs)
    if Path::new("/usr/local").exists() {
        args.extend_from_slice(&[
            "--ro-bind".to_string(), "/usr/local".to_string(), "/usr/local".to_string(),
        ]);
    }

    // /lib64 exists on some distros
    if Path::new("/lib64").exists() {
        args.extend_from_slice(&[
            "--ro-bind".to_string(), "/lib64".to_string(), "/lib64".to_string(),
        ]);
    }

    // /lib32 on some distros
    if Path::new("/lib32").exists() {
        args.extend_from_slice(&[
            "--ro-bind".to_string(), "/lib32".to_string(), "/lib32".to_string(),
        ]);
    }

    // Agent binary context (parent + sibling lib dir for npm/cargo)
    // We try to find a sensible 'root' to mount so that dependencies are available
    let binary_path = Path::new(agent_binary_path);
    let mut mount_root = binary_path.parent().map(|p| p.to_path_buf());

    // Heuristic: if inside .npm-global or .cargo, mount the whole thing
    if let Some(ref path) = mount_root {
        let path_str = path.to_string_lossy();
        if path_str.contains(".npm-global") {
            if let Some(idx) = path_str.find(".npm-global") {
                mount_root = Some(PathBuf::from(&path_str[..idx + 11]));
            }
        } else if path_str.contains(".cargo") {
            if let Some(idx) = path_str.find(".cargo") {
                mount_root = Some(PathBuf::from(&path_str[..idx + 6]));
            }
        }
    }

    if let Some(root) = mount_root {
        if root.exists() {
            let root_str = root.to_string_lossy().to_string();
            args.extend_from_slice(&["--ro-bind".to_string(), root_str.clone(), root_str.clone()]);
        }
    }

    // Common user tool directories (npm global, cargo, pipx, etc.)
    let home = std::env::var("HOME").unwrap_or_else(|_| "/root".to_string());
    for tool_dir in &[
        format!("{}/.npm-global/bin", home),
        format!("{}/.cargo/bin", home),
        format!("{}/.local/bin", home),
    ] {
        if Path::new(tool_dir).exists()
            && !binary_path.starts_with(tool_dir)
        {
            args.extend_from_slice(&[
                "--ro-bind".to_string(), tool_dir.clone(), tool_dir.clone(),
            ]);
        }
    }

    // Framework root (read-only at /adt-framework so hooks can execute)
    args.extend_from_slice(&[
        "--ro-bind".to_string(), framework_str, "/adt-framework".to_string(),
    ]);

    // Python venv inside framework (for hook dependencies like `requests`)
    let venv_path = framework_root.join(".venv");
    if venv_path.exists() {
        let venv_str = venv_path.to_string_lossy().to_string();
        args.extend_from_slice(&[
            "--ro-bind".to_string(), venv_str, "/adt-framework/.venv".to_string(),
        ]);
    }

    // DNS: /etc/resolv.conf is a symlink to /run/systemd/resolve/... on
    // systemd-resolved distros. Without /run in the sandbox that symlink
    // dangles and DNS lookup fails, breaking any agent that has to reach
    // an external API (2026-08-15: claude api.anthropic.com FailedToOpenSocket).
    // Bind the resolver stub read-only if it exists.
    if Path::new("/run/systemd/resolve").exists() {
        args.extend_from_slice(&[
            "--ro-bind".to_string(),
            "/run/systemd/resolve".to_string(),
            "/run/systemd/resolve".to_string(),
        ]);
    }

    // Auth state: agents cache OAuth tokens in their per-agent config dirs
    // (~/.claude for Claude Code, ~/.gemini for AGY/Gemini CLI). These MUST
    // be read-write, not read-only:
    //   - agy refreshes its token during use and writes it back to
    //     ~/.gemini/... — a read-only bind causes the write to fail, agy
    //     falls back to keyring, and keyring times out after 10s from
    //     inside the mount namespace (no user session to prompt).
    //   - claude similarly rotates the ~/.claude/*.json state.
    // Trade-off (SPEC-108 §5 finding): the sandbox CAN mutate the
    // operator's real token store. Justified because (a) both agents are
    // trusted authenticated tools of the operator, (b) blocking these
    // writes just moves the trust boundary — the agents fail into
    // interactive re-auth prompts which the operator can't answer from
    // inside a headless sandbox, (c) the alternative is a per-session
    // copy-in-copy-out overlay which is essentially SPEC-105 workspace
    // pattern applied to interactive sessions -- big spec, deferred.
    for dir_name in &[".claude", ".gemini", ".antigravity"] {
        let host_path = format!("{}/{}", home, dir_name);
        if Path::new(&host_path).exists() {
            args.extend_from_slice(&[
                "--bind".to_string(), host_path.clone(), host_path,
            ]);
        }
    }
    // Loose auth files in $HOME (not inside a dir). Claude Code stores its
    // OAuth session in ~/.claude.json (regular file, sibling of .claude/),
    // not inside .claude/ itself. Without this bind claude falls back to
    // interactive login even when .claude/.credentials.json is available.
    for file_name in &[".claude.json", ".claude.json.backup"] {
        let host_path = format!("{}/{}", home, file_name);
        if Path::new(&host_path).exists() {
            args.extend_from_slice(&[
                "--bind".to_string(), host_path.clone(), host_path,
            ]);
        }
    }
    // gcloud/cloud auth stays read-only; AGY doesn't rotate it during use.
    let gcloud = format!("{}/.config/gcloud", home);
    if Path::new(&gcloud).exists() {
        args.extend_from_slice(&[
            "--ro-bind".to_string(), gcloud.clone(), gcloud,
        ]);
    }

    // Keyring + DBUS session sockets (rw — libsecret needs write to talk to
    // gnome-keyring-daemon over its unix socket). Enables OAuth token
    // retrieval without prompting.
    let uid = nix::unistd::getuid().as_raw();
    let runtime_user = format!("/run/user/{}", uid);
    if Path::new(&runtime_user).exists() {
        args.extend_from_slice(&[
            "--bind".to_string(), runtime_user.clone(), runtime_user,
        ]);
    }
    // Fallback: also expose a bare /run so other symlinks (e.g. NetworkManager)
    // don't dangle. Empty tmpfs so nothing writable leaks.
    // (Skipped when /run/systemd/resolve already got covered above; extra
    // --tmpfs would collide with the bind mount.)

    args.extend_from_slice(&[
        // Project directory (read-write)
        "--bind".to_string(), project_str.clone(), "/project".to_string(),
        // Temporary directories
        "--tmpfs".to_string(), "/tmp".to_string(),
        // Device and proc filesystems
        "--dev".to_string(), "/dev".to_string(),
        "--proc".to_string(), "/proc".to_string(),
        // Kill agent if Console dies
        "--die-with-parent".to_string(),
        // Set working directory
        "--chdir".to_string(), "/project".to_string(),
        // Separator before the actual command
        "--".to_string(),
    ]);

    args
}

/// Build the command prefix for unshare-based namespace isolation.
/// This is the preferred method when user namespaces are available.
fn build_unshare_script(
    project_root: &Path,
    _dtcp_port: u16,
    framework_root: &Path,
    agent_binary_path: &str,
) -> String {
    let project_str = project_root.to_string_lossy();
    let framework_str = framework_root.to_string_lossy();

    // Determine binary mount point
    let binary_path = Path::new(agent_binary_path);
    let mut mount_root = binary_path.parent().map(|p| p.to_path_buf());

    // Heuristic: if inside .npm-global or .cargo, mount the whole thing
    if let Some(ref path) = mount_root {
        let path_str = path.to_string_lossy();
        if path_str.contains(".npm-global") {
            if let Some(idx) = path_str.find(".npm-global") {
                mount_root = Some(PathBuf::from(&path_str[..idx + 11]));
            }
        } else if path_str.contains(".cargo") {
            if let Some(idx) = path_str.find(".cargo") {
                mount_root = Some(PathBuf::from(&path_str[..idx + 6]));
            }
        }
    }

    let mut binary_mount = String::new();
    if let Some(root) = mount_root {
        if root.exists() {
            let root_str = root.to_string_lossy();
            binary_mount.push_str(&format!("/usr/bin/mkdir -p /sandbox{root}; /usr/bin/mount --rbind {root} /sandbox{root}; ", root = root_str));
        }
    }

    // Include /usr/local if it exists
    let local_mount = if Path::new("/usr/local").exists() {
        "/usr/bin/mkdir -p /sandbox/usr/local; /usr/bin/mount --rbind /usr/local /sandbox/usr/local; "
    } else {
        ""
    };

    format!(
        r#"/usr/bin/mount --make-rprivate / 2>/dev/null; /usr/bin/mkdir -p /sandbox/project /sandbox/usr /sandbox/lib /sandbox/bin /sandbox/sbin /sandbox/etc /sandbox/tmp /sandbox/dev /sandbox/proc /sandbox/adt-framework; /usr/bin/mount --bind {project} /sandbox/project; /usr/bin/mount --rbind /usr /sandbox/usr; /usr/bin/mount --rbind /lib /sandbox/lib; /usr/bin/mount --rbind /bin /sandbox/bin; /usr/bin/mount --rbind /sbin /sandbox/sbin; /usr/bin/mount --rbind /etc /sandbox/etc; /usr/bin/mount --rbind {framework} /sandbox/adt-framework; {local_mount} {bin_mount} /usr/bin/test -d /lib64 && /usr/bin/mkdir -p /sandbox/lib64 && /usr/bin/mount --rbind /lib64 /sandbox/lib64; /usr/bin/mount -t tmpfs tmpfs /sandbox/tmp; /usr/bin/mount -t devtmpfs devtmpfs /sandbox/dev 2>/dev/null || true; /usr/bin/mount -t proc proc /sandbox/proc; cd /sandbox && /usr/sbin/pivot_root . /sandbox/tmp 2>/dev/null && /usr/bin/umount -l /tmp/tmp 2>/dev/null; cd /project"#,
        project = project_str,
        framework = framework_str,
        local_mount = local_mount,
        bin_mount = binary_mount
    )
}

/// Spawn socat background processes to bridge DTCP/Panel ports from host into the namespace.
/// Since bwrap's --unshare-net creates a new network namespace with only loopback,
/// the agent cannot reach localhost:5002 on the host.
/// We use a two-step bridge:
/// 1. Host Host-Port -> Host Unix-Socket (in sandbox)
/// 2. Namespace Host-Port (localhost) -> Namespace Unix-Socket (in sandbox)
fn spawn_network_bridges(
    sandbox_root: &Path,
    dtcp_port: u16,
    panel_port: u16,
) -> Vec<std::process::Child> {
    let mut bridges = Vec::new();

    let dtcp_sock = sandbox_root.join("dtcp.sock");
    let panel_sock = sandbox_root.join("panel.sock");

    // 1. DTCP Bridge (Host Side: TCP -> Unix Socket)
    // socat UNIX-LISTEN:/path/to/dtcp.sock,fork TCP:127.0.0.1:5002
    match Command::new("/usr/bin/socat")
        .args([
            &format!("UNIX-LISTEN:{},fork,reuseaddr", dtcp_sock.to_string_lossy()),
            &format!("TCP:127.0.0.1:{}", dtcp_port),
        ])
        .spawn()
    {
        Ok(child) => bridges.push(child),
        Err(e) => log::error!("[SANDBOX] Failed to spawn host DTCP bridge: {}", e),
    }

    // 2. ADT Panel Bridge (Host Side: TCP -> Unix Socket)
    match Command::new("/usr/bin/socat")
        .args([
            &format!("UNIX-LISTEN:{},fork,reuseaddr", panel_sock.to_string_lossy()),
            &format!("TCP:127.0.0.1:{}", panel_port),
        ])
        .spawn()
    {
        Ok(child) => bridges.push(child),
        Err(e) => log::error!("[SANDBOX] Failed to spawn host Panel bridge: {}", e),
    }

    bridges
}

/// Build a shell wrapper to start the namespace-side of the network bridge.
fn build_bridge_wrapper(
    command: &str,
    args: &[String],
    session_id: &str,
    dtcp_port: u16,
    panel_port: u16,
) -> (String, Vec<String>) {
    let dtcp_sock = format!("/project/.adt/sandbox/{}/dtcp.sock", session_id);
    let panel_sock = format!("/project/.adt/sandbox/{}/panel.sock", session_id);

    let agent_cmd = if args.is_empty() {
        command.to_string()
    } else {
        format!("{} {}", command, args.join(" "))
    };

    // The wrapper starts background socat bridges inside the namespace (Unix Socket -> TCP)
    // then execs the agent command.
    // The wrapper starts background socat bridges inside the namespace (Unix Socket -> TCP)
    // then execs the agent command.
    // We also bring up the loopback interface (lo) inside the new network namespace.
    let script = format!(
        "/usr/sbin/ip link set lo up || true; \
         socat TCP-LISTEN:{},fork,reuseaddr,bind=127.0.0.1 UNIX-CONNECT:{} & \
         socat TCP-LISTEN:{},fork,reuseaddr,bind=127.0.0.1 UNIX-CONNECT:{} & \
         exec {}",
        dtcp_port, dtcp_sock,
        panel_port, panel_sock,
        agent_cmd
    );

    ("/bin/sh".to_string(), vec!["-c".to_string(), script])
}

/// Determine the isolation method for Phase B.
/// Returns: "bwrap", "unshare", or "none"
fn detect_isolation_method() -> &'static str {
    if has_bubblewrap() {
        "bwrap"
    } else if has_user_namespaces() {
        "unshare"
    } else {
        "none"
    }
}

/// Wrap a command with namespace isolation for Phase B (Tier 1 production mode).
/// Returns the modified command and args, or None if isolation is not available.
fn wrap_with_namespace(
    command: &str,
    args: &[String],
    project_root: &Path,
    dtcp_port: u16,
    panel_port: u16,
    framework_root: &Path,
    session_id: &str,
) -> Option<(String, Vec<String>)> {
    let method = detect_isolation_method();

    match method {
        "bwrap" => {
            let mut bwrap_args = build_bwrap_args(project_root, dtcp_port, command, framework_root);

            // Amended 2026-08-15: no bridge wrapper now that --unshare-net is
            // gone. build_bridge_wrapper generated a bash-quoted script that
            // failed on any command containing shell-special chars (parens,
            // etc). Pass the agent command + args directly.
            let _ = (panel_port, session_id); // silence unused warnings
            bwrap_args.push(command.to_string());
            bwrap_args.extend(args.iter().cloned());

            // bwrap is the command, everything else is args
            let bwrap_cmd = bwrap_args.remove(0);
            log::info!(
                "[SANDBOX PHASE B] Using bubblewrap isolation for session {}",
                session_id
            );
            Some((bwrap_cmd, bwrap_args))
        }
        "unshare" => {
            // unshare with mount namespace
            let setup_script = build_unshare_script(project_root, dtcp_port, framework_root, command);
            
            // Wrap the agent command with the network bridge script
            let (bridge_cmd, bridge_args) = build_bridge_wrapper(command, args, session_id, dtcp_port, panel_port);
            let agent_script = format!("{} {}", bridge_cmd, bridge_args.join(" "));
            
            let full_script = format!("{}; {}", setup_script, agent_script);

            log::info!(
                "[SANDBOX PHASE B] Using unshare namespace isolation for session {}",
                session_id
            );
            Some((
                "/usr/bin/unshare".to_string(),
                vec![
                    "--mount".to_string(),
                    "--net".to_string(),
                    "--map-root-user".to_string(),
                    "--fork".to_string(),
                    "--".to_string(),
                    "/usr/bin/bash".to_string(),
                    "-c".to_string(),
                    full_script,
                ],
            ))
        }
        _ => {
            log::warn!(
                "[SANDBOX PHASE B] No isolation method available (no bwrap, no user namespaces). Falling back to Phase A only."
            );
            None
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionInfo {
    pub id: String,
    pub project: String,
    pub agent: String,
    pub role: String,
    pub spec_id: String,
    pub command: String,
    pub alive: bool,
    pub agent_user: Option<String>,
    pub sandboxed: Option<bool>,
    pub sandbox_tier: Option<String>,
    pub parent_session_id: Option<String>,
    pub task_id: Option<String>,
    // SPEC-057: AUTO or MANUAL. Default derived from role at spawn.
    #[serde(default)]
    pub messaging_mode: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PersistentSession {
    pub id: String,
    pub project: String,
    pub agent: String,
    pub role: String,
    pub spec_id: String,
    pub command: String,
    pub args: Vec<String>,
    pub cwd: Option<String>,
    pub parent_session_id: Option<String>,
    pub task_id: Option<String>,
    // SPEC-057: persisted so restored sessions keep their toggle state.
    #[serde(default)]
    pub messaging_mode: Option<String>,
}

struct PtySession {
    master: Box<dyn MasterPty + Send>,
    child: Box<dyn Child + Send>,
    writer: Box<dyn Write + Send>,
    info: SessionInfo,
    metadata: PersistentSession,
    sandbox_root: Option<PathBuf>,
    bridge_processes: Vec<std::process::Child>,
    output_buffer: Arc<Mutex<VecDeque<u8>>>,
}

#[derive(Clone)]
pub struct PtyManager {
    sessions: Arc<Mutex<HashMap<String, PtySession>>>,
    next_id: Arc<Mutex<u32>>,
}

/// Detect if Shatterglass production mode is active.
/// Production mode requires EXPLICIT human activation via the Console UI toggle,
/// which creates the flag file ~/.adt/production_mode.
/// This replaces heuristic detection to prevent false positives during partial setup.
pub fn is_production_mode() -> bool {
    let flag_path = production_mode_flag_path();
    if !flag_path.exists() {
        return false;
    }

    // Flag file exists -- verify the agent OS user also exists,
    // otherwise production mode would fail on sudo -u agent
    std::fs::read_to_string("/etc/passwd")
        .map(|content| content.lines().any(|line| line.starts_with("agent:")))
        .unwrap_or(false)
}

/// Path to the production mode flag file.
pub fn production_mode_flag_path() -> PathBuf {
    let mut path = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
    path.push(".adt");
    path.push("production_mode");
    path
}

/// Enable production mode (called from IPC on human button click).
pub fn enable_production_mode() -> Result<(), String> {
    // Pre-check: agent user must exist
    let agent_exists = std::fs::read_to_string("/etc/passwd")
        .map(|content| content.lines().any(|line| line.starts_with("agent:")))
        .unwrap_or(false);
    if !agent_exists {
        return Err("Cannot enable production mode: 'agent' OS user does not exist. Run setup_shatterglass.sh first.".to_string());
    }

    let flag_path = production_mode_flag_path();
    if let Some(parent) = flag_path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    fs::write(&flag_path, "enabled\n")
        .map_err(|e| format!("Failed to create production mode flag: {}", e))?;
    log::info!("[SHATTERGLASS] Production mode ENABLED by human action");
    Ok(())
}

/// Disable production mode (called from IPC on human button click).
pub fn disable_production_mode() -> Result<(), String> {
    let flag_path = production_mode_flag_path();
    if flag_path.exists() {
        fs::remove_file(&flag_path)
            .map_err(|e| format!("Failed to remove production mode flag: {}", e))?;
    }
    log::info!("[SHATTERGLASS] Production mode DISABLED by human action");
    Ok(())
}

impl PtyManager {
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(Mutex::new(HashMap::new())),
            next_id: Arc::new(Mutex::new(1)),
        }
    }

    fn get_sessions_file() -> PathBuf {
        let mut path = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
        path.push(".adt");
        path.push("console");
        let _ = fs::create_dir_all(&path);
        path.push("sessions.json");
        path
    }

    fn save_state(&self) {
        let sessions = self.sessions.lock();
        if let Ok(sessions_map) = sessions {
            let persistent: Vec<PersistentSession> = sessions_map
                .values()
                .map(|s| s.metadata.clone())
                .collect();
            
            let file_path = Self::get_sessions_file();
            if let Ok(json) = serde_json::to_string_pretty(&persistent) {
                if let Err(e) = fs::write(&file_path, json) {
                    log::error!("[PTY PERSIST] Failed to write sessions.json: {}", e);
                }
            }
        }
    }

    pub fn load_persistent_sessions() -> Vec<PersistentSession> {
        let file_path = Self::get_sessions_file();
        if !file_path.exists() {
            return Vec::new();
        }

        match fs::read_to_string(&file_path) {
            Ok(content) => {
                serde_json::from_str(&content).unwrap_or_else(|e| {
                    log::error!("[PTY PERSIST] Failed to parse sessions.json: {}", e);
                    Vec::new()
                })
            }
            Err(e) => {
                log::error!("[PTY PERSIST] Failed to read sessions.json: {}", e);
                Vec::new()
            }
        }
    }

    pub fn create_session<R: Runtime>(
        &self,
        reserved_id: Option<String>,
        project: &str,
        agent: &str,
        role: &str,
        spec_id: &str,
        command: &str,
        args: &[String],
        cwd: Option<String>,
        parent_session_id: Option<String>,
        task_id: Option<String>,
        build_id: Option<String>,
        adt_mode: Option<String>,
        adt_task_ids: Option<String>,
        context_hint: Option<String>,
        skip_permissions: bool,
        cols: u16,
        rows: u16,
        app_handle: tauri::AppHandle<R>,
    ) -> Result<SessionInfo, String> {
        let pty_system = native_pty_system();

        let pair = pty_system
            .openpty(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| format!("Failed to open PTY: {}", e))?;

        // Build command and args
        let mut final_command = command.to_string();
        let mut final_args = args.to_vec();

        // SPEC-042: Build harness command with correct flags if not already provided
        if (agent == "claude" || agent == "gemini" || agent == "agy") && (final_command == "claude" || final_command == "gemini" || final_command == "agy" || final_command == "bash" || final_command == "") {
             if agent == "gemini" {
                 final_command = "gemini".to_string();
                 if !final_args.iter().any(|a| a.contains("/summon")) {
                     final_args.push("-i".to_string());
                     final_args.push(format!("/summon {}", role.to_lowercase()));
                     final_args.push("--yolo".to_string());
                 }
             } else if agent == "claude" {
                 final_command = "claude".to_string();
                 if !final_args.iter().any(|a| a.contains("/hive")) {
                     let role_suffix = role.replace("_Engineer", "").replace("Systems_", "").to_lowercase();
                     final_args.push(format!("/hive-{}", role_suffix));
                 }
                 if skip_permissions && !final_args.iter().any(|a| a == "--dangerously-skip-permissions") {
                     final_args.push("--dangerously-skip-permissions".to_string());
                 }
             } else if agent == "agy" {
                 final_command = "agy".to_string();
                 if !final_args.iter().any(|a| a.contains("/summon")) {
                     let role_suffix = role.replace("_Engineer", "").replace("Systems_", "").to_lowercase();
                     final_args.push("-i".to_string());
                     final_args.push(format!("/summon {}", role_suffix));
                 }
                 if skip_permissions && !final_args.iter().any(|a| a == "--dangerously-skip-permissions") {
                     final_args.push("--dangerously-skip-permissions".to_string());
                 }
             }
        }

        // Resolve the user's full PATH so we can find agent CLIs (gemini, claude)
        // that may be installed in non-standard locations (e.g. ~/.npm-global/bin/).
        // Tauri apps launched from desktop environments inherit a minimal PATH.
        let user_path = resolve_user_path();
        let resolved_command = resolve_command(&final_command, &user_path);
        // Pre-spawn validation: surface a clear "binary not found + install hint"
        // instead of the cryptic "os error 2" Paul saw.
        if agent == "agy" || agent == "claude" || agent == "gemini" {
            if let Err(msg) = validate_agent_binary(agent, &resolved_command, &user_path) {
                log::error!("[PTY VALIDATE] {}", msg);
                return Err(msg);
            }
        }
        // Canonicalize to resolve symlinks (crucial for sandboxing npm-global modules)
        let canonical_command = PathBuf::from(&resolved_command)
            .canonicalize()
            .unwrap_or_else(|_| PathBuf::from(&resolved_command));
        let command_to_run = canonical_command.to_string_lossy().to_string();
        log::info!("[PTY PATH] Resolved '{}' -> '{}' (canonical: '{}')",
                  final_command, resolved_command, command_to_run);
        log::info!(
            "[PTY SPAWN INPUT] agent={} role={} raw_cmd='{}' final_args={:?} cwd={:?} parent={:?}",
            agent, role, final_command, final_args, cwd, parent_session_id
        );

        // SPEC-027: In production mode, wrap agent commands with sudo -u agent.
        // Shell sessions requested by the human remain as the human user.
        let production_mode = is_production_mode();
        let is_agent_session = agent != "shell" && agent != "human";
        let agent_user = if production_mode && is_agent_session {
            Some("agent".to_string())
        } else {
            None
        };

        // Generate session ID early (needed for sandbox directory naming)
        let session_id = if let Some(id) = reserved_id {
            id
        } else {
            let mut next_id_lock = self.next_id.lock().map_err(|_| "Mutex poisoned")?;
            let id = format!("session_{}", *next_id_lock);
            *next_id_lock += 1;
            id
        };

        // Determine DTCP and Panel ports
        let dtcp_port_num = if let Some(path) = &cwd {
            let config_path = PathBuf::from(path).join("config").join("dtcp.json");
            let old_config_path = PathBuf::from(path).join("config").join("dttp.json");
            let final_path = if config_path.exists() { config_path } else { old_config_path };

            if final_path.exists() {
                fs::read_to_string(&final_path).ok()
                    .and_then(|c| serde_json::from_str::<serde_json::Value>(&c).ok())
                    .and_then(|j| j.get("port").and_then(|p| p.as_u64()))
                    .map(|p| p as u16)
                    .unwrap_or(5002)
            } else {
                5002
            }
        } else {
            5002
        };
        let panel_port_num = 5001; // Default Panel port

        // SPEC-036 Phase B: Determine if namespace isolation applies
        // Must be decided before building CommandBuilder
        //
        // Amended 2026-08-15 (operator audit):
        //   Gap 1 (dev-mode escape): honored via env ADT_DEV_MODE=1 OR UI
        //     toggle at ~/.adt/console_settings.json::dev_mode. UI toggle
        //     is human-writable only (Tauri IPC, 0600 file perms).
        //   Gap 2 (framework bypass): the previous `if !is_fw { ... } else
        //     { None }` fall-through meant Console sessions targeting the
        //     framework itself were NEVER sandboxed. Removed -- framework
        //     sessions are sandboxed the same way as external ones.
        //   Gap 3 (fail-open): if is_agent_session and sandbox is NOT
        //     disabled but wrap_with_namespace returned None (no isolation
        //     backend available on this host), we refuse to spawn. Fail-
        //     closed like SPEC-105 6f.
        let framework_root = get_framework_root();
        // UI file wins over env; see effective_sandbox_disabled_with_reason.
        let (sandbox_disabled, sandbox_disabled_reason) =
            effective_sandbox_disabled_with_reason();
        if sandbox_disabled {
            log::warn!("[SANDBOX] DISABLED for new session (reason={})", sandbox_disabled_reason);
        }

        let phase_b_wrap: Option<(String, Vec<String>)> = if is_agent_session && !sandbox_disabled {
            if let Some(ref cwd_path) = cwd {
                let project_root = PathBuf::from(cwd_path);
                wrap_with_namespace(
                    &command_to_run,
                    &final_args,
                    &project_root,
                    dtcp_port_num,
                    panel_port_num,
                    &framework_root,
                    &session_id,
                )
            } else {
                None
            }
        } else {
            None
        };

        // Gap 3 fail-closed. If the caller wants an agent session with a real
        // project cwd and sandbox is NOT disabled by env/UI, but the isolation
        // backend picked "none" (bwrap + unshare both unavailable), refuse.
        // Emit a warn so ops know the host is missing bwrap/userns.
        if is_agent_session && !sandbox_disabled && cwd.is_some() && phase_b_wrap.is_none() {
            log::error!(
                "[SANDBOX] Refusing to spawn agent session {}: no isolation \
                 backend available (bwrap + unshare both unusable) and \
                 sandbox is not explicitly disabled. Fix: install bwrap and \
                 grant userns, OR enable dev mode via the Console toggle.",
                session_id
            );
            return Err(format!(
                "sandbox_unavailable: agent session {} refused because bwrap \
                 and unshare are both unusable on this host and sandbox is \
                 not explicitly disabled. Install bwrap (recommended) or \
                 toggle Dev Mode in the Console.",
                session_id
            ));
        }

        log::info!(
            "[PTY WRAP DECISION] is_agent_session={} sandbox_disabled={} ({}) cwd_is_some={} phase_b_wrap_is_some={}",
            is_agent_session,
            sandbox_disabled,
            sandbox_disabled_reason,
            cwd.is_some(),
            phase_b_wrap.is_some()
        );
        if let Some((ref ns_cmd, ref ns_args)) = phase_b_wrap {
            log::info!(
                "[PTY WRAP NS] ns_cmd='{}' ns_args_len={} first10={:?}",
                ns_cmd, ns_args.len(),
                ns_args.iter().take(10).cloned().collect::<Vec<_>>()
            );
        }

        let mut cmd = if let Some((ref ns_cmd, ref ns_args)) = phase_b_wrap {
            // Phase B: Namespace-wrapped command (production + external project)
            let mut c = CommandBuilder::new(ns_cmd);
            for arg in ns_args {
                c.arg(arg);
            }
            c
        } else if let Some(ref _agent_user) = agent_user {
            // Production mode: run as OS user 'agent' via sudo.
            // Use -E to preserve environment (HOME, TMPDIR, etc.) set by sandbox
            // setup — without this, sudo resets HOME to /home/agent (from /etc/passwd)
            // which may not exist, causing agents to crash on startup.
            let mut c = CommandBuilder::new("/usr/bin/sudo");
            c.arg("-E");
            c.arg("-u");
            c.arg("agent");
            c.arg(&command_to_run);
            for arg in &final_args {
                c.arg(arg);
            }
            c
        } else {
            let mut c = CommandBuilder::new(&command_to_run);
            for arg in &final_args {
                c.arg(arg);
            }
            c
        };

        // Inject keyring/DBUS env unconditionally so agy reuses its OAuth token
        // (regardless of whether the console itself was launched with these set).
        apply_keyring_env(&mut cmd);

        // Bug 6 fix: skip cmd.cwd() when bwrap handles it via --chdir /project
        if phase_b_wrap.is_none() {
            if let Some(path) = &cwd {
                cmd.cwd(path);
            }
        }

        // Determine DTCP_URL for SDK communication
        let dtcp_url = format!("http://localhost:{}", dtcp_port_num);

        // SPEC-036: Set up sandbox for agent sessions
        let namespace_mode = phase_b_wrap.is_some();
        let sandbox_root = if should_sandbox(agent, cwd.as_deref()) {
            let project_root = PathBuf::from(cwd.as_deref().unwrap());
            let is_framework = is_framework_project(&project_root, &framework_root);

            match create_sandbox_dir(&project_root, &session_id) {
                Ok(sb_root) => {
                    // Generate agent-specific sandbox configs and inject CLI flags
                    if agent == "claude" {
                        match generate_claude_sandbox_config(
                            &sb_root, &project_root, &framework_root, namespace_mode
                        ) {
                            Ok(settings_path) => {
                                // Bug 4 fix: rewrite --settings path for namespace mode
                                let settings_str = if namespace_mode {
                                    format!("/project/.adt/sandbox/{}/claude_sandbox_settings.json", session_id)
                                } else {
                                    settings_path.to_string_lossy().to_string()
                                };
                                cmd.arg("--settings");
                                cmd.arg(&settings_str);
                                log::info!("[SANDBOX] Claude --settings {} injected", settings_str);
                            }
                            Err(e) => {
                                log::error!("[SANDBOX] Claude config generation failed: {}", e);
                            }
                        }

                        // Credential Inheritance for Claude: copy ~/.claude/.credentials.json
                        // and symlink user-level config so the sandboxed CLI doesn't ask to log in.
                        if let Some(host_home) = dirs::home_dir() {
                            let sandbox_home_dir = sb_root.join("home");
                            let host_claude_dir = host_home.join(".claude");
                            let sandbox_claude_dir = sandbox_home_dir.join(".claude");

                            #[cfg(unix)]
                            {
                                use std::os::unix::fs::PermissionsExt;
                                use std::os::unix::fs::symlink;

                                if let Err(e) = fs::create_dir_all(&sandbox_claude_dir) {
                                    log::warn!("[SANDBOX] Failed to create sandbox .claude dir: {}", e);
                                } else {
                                    let _ = fs::set_permissions(
                                        &sandbox_claude_dir,
                                        fs::Permissions::from_mode(0o777),
                                    );

                                    if host_claude_dir.exists() {
                                        for name in &[
                                            "settings.json",
                                            "commands",
                                            "agents",
                                            "plugins",
                                            "CLAUDE.md",
                                            "statsig",
                                        ] {
                                            let host_file = host_claude_dir.join(name);
                                            if host_file.exists() {
                                                let sandbox_link = sandbox_claude_dir.join(name);
                                                let _ = fs::remove_file(&sandbox_link);
                                                if let Err(e) = symlink(&host_file, &sandbox_link) {
                                                    log::warn!("[SANDBOX] Failed to symlink .claude/{}: {}", name, e);
                                                }
                                            }
                                        }

                                        let host_creds = host_claude_dir.join(".credentials.json");
                                        if host_creds.exists() {
                                            let sandbox_creds = sandbox_claude_dir.join(".credentials.json");
                                            let _ = fs::remove_file(&sandbox_creds);
                                            match fs::copy(&host_creds, &sandbox_creds) {
                                                Ok(_) => {
                                                    let _ = fs::set_permissions(
                                                        &sandbox_creds,
                                                        fs::Permissions::from_mode(0o666),
                                                    );
                                                    log::info!("[SANDBOX] Copied fresh .credentials.json for Claude");
                                                }
                                                Err(e) => log::warn!("[SANDBOX] Failed to copy .credentials.json: {}", e),
                                            }
                                        }

                                        log::info!("[SANDBOX] Claude credentials set up in sandbox .claude dir");
                                    }

                                    // Claude Code keeps the user-identity record at $HOME/.claude.json
                                    // (a sibling of .claude/, not inside it). Without this, the CLI
                                    // creates a fresh empty .claude.json and treats the user as logged out.
                                    let host_claude_json = host_home.join(".claude.json");
                                    if host_claude_json.exists() {
                                        let sandbox_claude_json = sandbox_home_dir.join(".claude.json");
                                        let _ = fs::remove_file(&sandbox_claude_json);
                                        match fs::copy(&host_claude_json, &sandbox_claude_json) {
                                            Ok(_) => {
                                                let _ = fs::set_permissions(
                                                    &sandbox_claude_json,
                                                    fs::Permissions::from_mode(0o666),
                                                );
                                                log::info!("[SANDBOX] Copied fresh .claude.json for Claude (user identity)");
                                            }
                                            Err(e) => log::warn!("[SANDBOX] Failed to copy .claude.json: {}", e),
                                        }
                                    }
                                }
                            }
                        }
                    } else if agent == "gemini" || agent == "agy" {
                        if let Err(e) = generate_gemini_sandbox_config(
                            &sb_root, &project_root, &framework_root, namespace_mode
                        ) {
                            log::error!("[SANDBOX] Gemini config generation failed: {}", e);
                        }
                        
                        // Credential Inheritance: Link global credentials and npm-global from host home to sandbox home
                        if let Some(host_home) = dirs::home_dir() {
                            let sandbox_home_dir = sb_root.join("home");
                            
                            // 1. .gemini directory (auth tokens)
                            // We create a REAL directory (not a symlink) so agent can write inside it.
                            // host's trustedFolders.json is root:600 and inaccessible to agent user,
                            // so we generate a fresh one pre-trusting the project root.
                            let host_gemini_dir = host_home.join(".gemini");
                            let sandbox_gemini_dir = sandbox_home_dir.join(".gemini");

                            #[cfg(unix)]
                            {
                                use std::os::unix::fs::PermissionsExt;
                                use std::os::unix::fs::symlink;

                                // Create real directory
                                if let Err(e) = fs::create_dir_all(&sandbox_gemini_dir) {
                                    log::warn!("[SANDBOX] Failed to create sandbox .gemini dir: {}", e);
                                } else {
                                    // chmod 777 so agent user can write inside it
                                    let _ = fs::set_permissions(
                                        &sandbox_gemini_dir,
                                        fs::Permissions::from_mode(0o777),
                                    );

                                    // Write a fresh trustedFolders.json pre-trusting the project root.
                                    // Gemini CLI expects flat { "<path>": "<trustLevel>" } — not a wrapped array.
                                    let trusted_json = format!(
                                        "{{\"{}\":\"TRUST_FOLDER\"}}\n",
                                        project_root.to_string_lossy()
                                    );
                                    let tf_path = sandbox_gemini_dir.join("trustedFolders.json");
                                    match fs::write(&tf_path, &trusted_json) {
                                        Ok(_) => {
                                            let _ = fs::set_permissions(
                                                &tf_path,
                                                fs::Permissions::from_mode(0o666),
                                            );
                                            log::info!("[SANDBOX] Wrote trustedFolders.json for Gemini");
                                        }
                                        Err(e) => log::warn!("[SANDBOX] Failed to write trustedFolders.json: {}", e),
                                    }

                                    if host_gemini_dir.exists() {
                                        // Symlink read-only / non-secret files from host .gemini
                                        for name in &[
                                            "settings.json",
                                            "trusted_hooks.json",
                                            "state.json",
                                            "installation_id",
                                            "google_accounts.json",
                                            "projects.json",
                                            "config",
                                        ] {
                                            let host_file = host_gemini_dir.join(name);
                                            if host_file.exists() {
                                                let sandbox_link = sandbox_gemini_dir.join(name);
                                                if let Err(e) = symlink(&host_file, &sandbox_link) {
                                                    log::warn!("[SANDBOX] Failed to symlink .gemini/{}: {}", name, e);
                                                }
                                            }
                                        }

                                        // Copy oauth_creds.json — remove first so human (Tauri) can overwrite agent-owned file on restart
                                        let host_oauth = host_gemini_dir.join("oauth_creds.json");
                                        if host_oauth.exists() {
                                            let sandbox_oauth = sandbox_gemini_dir.join("oauth_creds.json");
                                            let _ = fs::remove_file(&sandbox_oauth);
                                            match fs::copy(&host_oauth, &sandbox_oauth) {
                                                Ok(_) => {
                                                    #[cfg(unix)]
                                                    {
                                                        use std::os::unix::fs::PermissionsExt;
                                                        let _ = fs::set_permissions(
                                                            &sandbox_oauth,
                                                            fs::Permissions::from_mode(0o666),
                                                        );
                                                    }
                                                    log::info!("[SANDBOX] Copied fresh oauth_creds.json (mode 666 so 'agent' user can read regardless of group)");
                                                }
                                                Err(e) => log::warn!("[SANDBOX] Failed to copy oauth_creds.json: {}", e),
                                            }
                                        }

                                        log::info!("[SANDBOX] Gemini credentials set up in sandbox .gemini dir");
                                    }
                                }
                            }

                            // 2. .npm-global directory (Gemini CLI binaries)
                            let host_npm_dir = host_home.join(".npm-global");
                            let sandbox_npm_dir = sandbox_home_dir.join(".npm-global");
                            
                            if host_npm_dir.exists() {
                                #[cfg(unix)]
                                {
                                    use std::os::unix::fs::symlink;
                                    if let Err(e) = symlink(&host_npm_dir, &sandbox_npm_dir) {
                                        log::warn!("[SANDBOX] Failed to symlink .npm-global: {}", e);
                                    } else {
                                        log::info!("[SANDBOX] npm-global symlinked from host");
                                    }
                                }
                            }
                        }

                        log::info!("[SANDBOX] Gemini DTCP hook sandbox configured");
                    }

                    // Apply sandbox environment (sanitize env vars, redirect HOME/TMPDIR)
                    // For external projects: full env sanitization
                    // For framework projects in production mode: still need HOME redirect
                    // because sudo -u agent sets HOME=/home/agent which may not exist
                    if !is_framework {
                        apply_sandbox_env(
                            &mut cmd, &sb_root, &project_root, agent, &dtcp_url,
                            namespace_mode, &session_id,
                        );
                    } else if production_mode && is_agent_session {
                        // Framework project + production mode: redirect HOME/TMPDIR
                        // to sandbox so agents have a writable home directory
                        let sandbox_home = sb_root.join("home");
                        let sandbox_tmp = sb_root.join("tmp");
                        cmd.env("HOME", sandbox_home.to_string_lossy().as_ref());
                        cmd.env("TMPDIR", sandbox_tmp.to_string_lossy().as_ref());
                        cmd.env("DTCP_URL", &dtcp_url);
                        cmd.env("DTTP_URL", &dtcp_url); // Fallback
                        log::info!(
                            "[SANDBOX] Framework project production mode: HOME={:?}, TMPDIR={:?}",
                            sandbox_home, sandbox_tmp
                        );
                    }

                    log::info!(
                        "[SANDBOX] Session {} sandboxed at {:?} (framework_project={}, namespace_mode={})",
                        session_id, sb_root, is_framework, namespace_mode
                    );
                    Some(sb_root)
                }
                Err(e) => {
                    log::error!("[SANDBOX] Failed to create sandbox for {}: {}", session_id, e);
                    None
                }
            }
        } else {
            None
        };

        // SPEC-057: Resolve spawn-time messaging mode default by role.
        let messaging_mode = default_messaging_mode_for_role(role).to_string();

        // SPEC-057: Create per-session mailbox directories before spawn so the
        // first inbox/outbox writes from the agent or watcher race-free.
        create_comms_dirs(&framework_root, &session_id);

        // Set environment variables for ADT context
        cmd.env("ADT_AGENT", agent);
        cmd.env("ADT_ROLE", role);
        cmd.env("ADT_SPEC_ID", spec_id);
        cmd.env("ADT_HARNESS", agent);
        cmd.env("ADT_SESSION_ID", &session_id);
        cmd.env("ADT_MSG_MODE", &messaging_mode);
        cmd.env("ADT_FRAMEWORK_ROOT", framework_root.to_string_lossy().as_ref());
        
        if let Some(path) = &cwd {
            cmd.env("ADT_PROJECT_DIR", path);
        }

        if let Some(pid) = &parent_session_id {
            cmd.env("ADT_PARENT_SESSION_ID", pid);
        }
        if let Some(tid) = &task_id {
            cmd.env("ADT_TASK_ID", tid);
        }
        if let Some(mode) = &adt_mode {
            cmd.env("ADT_MODE", mode);
        }
        if let Some(bid) = &build_id {
            cmd.env("ADT_BUILD_ID", bid);
        }
        if let Some(tids) = &adt_task_ids {
            cmd.env("ADT_TASK_IDS", tids);
        }
        if sandbox_root.is_none() {
            // Only set DTCP_URL here if not already set by sandbox env
            cmd.env("DTCP_URL", &dtcp_url);
            cmd.env("DTTP_URL", &dtcp_url); // Fallback
        }
        cmd.env("TERM", "xterm-256color");
        cmd.env("PATH", &user_path);

        let agy_model = if let Some(pos) = final_args.iter().position(|x| x == "--model") {
            final_args.get(pos + 1).cloned()
        } else {
            None
        };
        if let Some(m) = agy_model {
            cmd.env("AGY_MODEL", &m);
        }

        if let Some(path) = &cwd {
            let project_dir_val = if namespace_mode {
                "/project".to_string()
            } else {
                path.clone()
            };
            cmd.env("CLAUDE_PROJECT_DIR", &project_dir_val);
            cmd.env("GEMINI_PROJECT_DIR", &project_dir_val);
        }

        // Diagnostic: capture the CommandBuilder argv + cwd before spawn.
        // portable_pty stores argv[0] as the program to exec, so we log the
        // full argv and check argv[0] existence to catch "os error 2" cases.
        {
            let argv: Vec<String> = cmd
                .get_argv()
                .iter()
                .map(|s| s.to_string_lossy().to_string())
                .collect();
            let cwd_dbg = cmd
                .get_cwd()
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_else(|| "<inherit>".to_string());
            let prog = argv.first().cloned().unwrap_or_default();
            log::info!(
                "[PTY SPAWN PRE] program='{}' cwd='{}' argc={} argv={:?}",
                prog, cwd_dbg, argv.len(), argv
            );
            if prog.starts_with('/') && !Path::new(&prog).exists() {
                log::error!(
                    "[PTY SPAWN PRE] program path does not exist on host: '{}'",
                    prog
                );
            }
            if cwd_dbg != "<inherit>" && !Path::new(&cwd_dbg).exists() {
                log::error!(
                    "[PTY SPAWN PRE] cwd path does not exist on host: '{}'",
                    cwd_dbg
                );
            }
        }

        let child = pair
            .slave
            .spawn_command(cmd)
            .map_err(|e| format!("Failed to spawn process: {}", e))?;

        let mut writer = pair
            .master
            .take_writer()
            .map_err(|e| format!("Failed to get PTY writer: {}", e))?;

        if production_mode && is_agent_session {
            log::info!("[PTY PRODUCTION] Spawning as OS user 'agent' (sudo -u agent {})", command);
        }

        // SPEC-042 §7.1: Inject context_hint into PTY stdin after a 1.5s startup delay
        if let Some(hint) = context_hint {
            let sessions_clone = Arc::clone(&self.sessions);
            let sid_clone = session_id.clone();
            std::thread::spawn(move || {
                std::thread::sleep(std::time::Duration::from_millis(1500));
                if let Ok(mut sessions) = sessions_clone.lock() {
                    if let Some(session) = sessions.get_mut(&sid_clone) {
                        let _ = session.writer.write_all(hint.as_bytes());
                        let _ = session.writer.write_all(b"\n");
                        let _ = session.writer.flush();
                        log::info!("[SWARM] Injected context_hint for session {}", sid_clone);
                    }
                }
            });
        }

        // SPEC-049 task_306: Inject bootstrap hook if task_id is present
        if let Some(ref tid) = task_id {
            if agent == "gemini" || agent == "claude" {
                let bootstrap = format!(
                    "\n# --- CROSS-AI BOOTSTRAP ---\n\
                     # ADT_TASK_ID={}\n\
                     # Instructions: GET {}/governance/cross_ai/task/{} to fetch your manifest.\n\
                     # Log cross_ai_task_accepted to ADS immediately.\n\
                     # --- END BOOTSTRAP ---\n\n",
                    tid, dtcp_url, tid
                );
                // We don't use inject_command here because we want it to be part of the initial PTY stream
                // but not necessarily executed as a shell command yet.
                // However, for Gemini CLI/Claude to see it as a "message", we might need to steer it.
                // For MVP, we'll write it to the writer.
                let _ = writer.write_all(bootstrap.as_bytes());
                let _ = writer.flush();
                log::info!("[PTY BOOTSTRAP] Injected bootstrap hook for task {}", tid);
            }
        }

        // SPEC-055 Amendment A: Run orchestrator/worker boot hook and inject preamble
        if adt_mode.as_deref() == Some("orchestrator") || adt_mode.as_deref() == Some("worker") {
            let hook_path = if adt_mode.as_deref() == Some("orchestrator") {
                "adt_sdk/hooks/orchestrator_boot.py"
            } else {
                "adt_sdk/hooks/worker_boot.py"
            };
            let hook_cwd = cwd.as_deref().unwrap_or(".");
            match std::process::Command::new("python3")
                .arg(hook_path)
                .current_dir(hook_cwd)
                .env("ADT_MODE", adt_mode.as_deref().unwrap_or(""))
                .env("ADT_ROLE", role)
                .env("ADT_SPEC_ID", spec_id)
                .env("ADT_BUILD_ID", build_id.as_deref().unwrap_or(""))
                .env("ADT_TASK_IDS", adt_task_ids.as_deref().unwrap_or(""))
                .env("ADT_PARENT_SESSION_ID", parent_session_id.as_deref().unwrap_or(""))
                .output()
            {
                Ok(output) if !output.stdout.is_empty() => {
                    let _ = writer.write_all(&output.stdout);
                    let _ = writer.flush();
                    log::info!("[PTY BOOT] Injected {} for session {}", hook_path, session_id);
                }
                Ok(_) => log::warn!("[PTY BOOT] {} produced no output", hook_path),
                Err(e) => log::error!("[PTY BOOT] Failed to run {}: {}", hook_path, e),
            }
        }

        let info = SessionInfo {
            id: session_id.clone(),
            project: project.to_string(),
            agent: agent.to_string(),
            role: role.to_string(),
            spec_id: spec_id.to_string(),
            command: command.to_string(),
            alive: true,
            agent_user: agent_user,
            sandboxed: if sandbox_root.is_some() { Some(true) } else { Some(false) },
            sandbox_tier: if namespace_mode {
                Some("phase_b".to_string())
            } else if sandbox_root.is_some() {
                Some("phase_a".to_string())
            } else {
                None
            },
            parent_session_id: parent_session_id.clone(),
            task_id: task_id.clone(),
            messaging_mode: Some(messaging_mode.clone()),
        };

        let metadata = PersistentSession {
            id: session_id.clone(),
            project: project.to_string(),
            agent: agent.to_string(),
            role: role.to_string(),
            spec_id: spec_id.to_string(),
            command: command.to_string(),
            args: args.to_vec(),
            cwd: cwd.clone(),
            parent_session_id: parent_session_id,
            task_id: task_id,
            messaging_mode: Some(messaging_mode),
        };

        // Start reader thread — forwards PTY output to frontend via events
        let mut reader = pair
            .master
            .try_clone_reader()
            .map_err(|e| format!("Failed to clone PTY reader: {}", e))?;

        let event_session_id = session_id.clone();
        let app_handle_clone = app_handle.clone();
        let output_buffer = Arc::new(Mutex::new(VecDeque::with_capacity(65536)));
        let thread_buffer = output_buffer.clone();

        std::thread::spawn(move || {
            let mut buf = [0u8; 4096];
            loop {
                match reader.read(&mut buf) {
                    Ok(0) => {
                        // PTY closed
                        let _ = app_handle_clone.emit(
                            &format!("pty-closed-{}", event_session_id),
                            (),
                        );
                        break;
                    }
                    Ok(n) => {
                        let data_bytes = &buf[..n];
                        // Update ring buffer
                        if let Ok(mut buffer) = thread_buffer.lock() {
                            buffer.extend(data_bytes);
                            while buffer.len() > 65536 {
                                buffer.pop_front();
                            }
                        }

                        let data = String::from_utf8_lossy(data_bytes).to_string();
                        // Use trace level to avoid log flooding
                        log::trace!("[PTY -> FE] session: {}, bytes: {}", event_session_id, n);
                        if let Err(e) = app_handle_clone.emit(
                            &format!("pty-output-{}", event_session_id),
                            data,
                        ) {
                            log::error!("[PTY ERROR] Failed to emit output for {}: {}", event_session_id, e);
                            break;
                        }
                    }
                    Err(e) => {
                        log::error!("[PTY ERROR] read error for {}: {}", event_session_id, e);
                        break;
                    }
                }
            }
        });

        let mut bridge_processes = Vec::new();
        if namespace_mode {
            if let Some(ref sb_root) = sandbox_root {
                bridge_processes = spawn_network_bridges(sb_root, dtcp_port_num, panel_port_num);
            }
        }

        let session = PtySession {
            master: pair.master,
            child,
            writer,
            info: info.clone(),
            metadata,
            sandbox_root,
            bridge_processes,
            output_buffer,
        };

        {
            let mut sessions = self.sessions.lock().map_err(|_| "Mutex poisoned")?;
            sessions.insert(session_id, session);
        }

        self.save_state();
        log::info!("[PTY CREATE] session {} created successfully", info.id);
        Ok(info)
    }

    pub fn write_to_session(&self, session_id: &str, data: &[u8]) -> Result<(), String> {
        let mut sessions = self.sessions.lock().map_err(|_| "Mutex poisoned")?;
        let session = sessions
            .get_mut(session_id)
            .ok_or_else(|| {
                log::error!("[PTY WRITE ERROR] session {} not found", session_id);
                format!("Session not found: {}", session_id)
            })?;

        session
            .writer
            .write_all(data)
            .map_err(|e| {
                log::error!("[PTY WRITE ERROR] write failed for {}: {}", session_id, e);
                format!("Write failed: {}", e)
            })?;

        session
            .writer
            .flush()
            .map_err(|e| {
                log::error!("[PTY WRITE ERROR] flush failed for {}: {}", session_id, e);
                format!("Flush failed: {}", e)
            })?;

        Ok(())
    }

    pub fn inject_command(&self, session_id: &str, command: &str) -> Result<(), String> {
        let mut sessions = self.sessions.lock().map_err(|_| "Mutex poisoned")?;
        let session = sessions.get_mut(session_id)
            .ok_or_else(|| format!("Session {} not found", session_id))?;

        // Ensure command ends with a newline for execution
        let mut full_cmd = command.to_string();
        if !full_cmd.ends_with('\n') {
            full_cmd.push('\n');
        }

        session.writer.write_all(full_cmd.as_bytes())
            .map_err(|e| format!("Failed to inject command: {}", e))?;
        session.writer.flush()
            .map_err(|e| format!("Failed to flush injected command: {}", e))?;

        log::info!("[PTY STEER] Injected command into {}: {}", session_id, command.trim());
        Ok(())
    }

    pub fn replay_session_output<R: Runtime>(
        &self,
        session_id: &str,
        app_handle: tauri::AppHandle<R>,
    ) -> Result<(), String> {
        let sessions = self.sessions.lock().map_err(|_| "Mutex poisoned")?;
        let session = sessions.get(session_id).ok_or_else(|| format!("Session not found: {}", session_id))?;
        
        let buffer = session.output_buffer.lock().map_err(|_| "Buffer mutex poisoned")?;
        if buffer.is_empty() {
            return Ok(());
        }

        let data = String::from_utf8_lossy(&buffer.iter().cloned().collect::<Vec<u8>>()).to_string();
        
        app_handle.emit(&format!("pty-output-{}", session_id), data)
            .map_err(|e| format!("Failed to emit replay: {}", e))?;
        
        log::info!("[PTY REPLAY] Replayed {} bytes for session {}", buffer.len(), session_id);
        Ok(())
    }

    pub fn get_session_output(&self, session_id: &str) -> Result<String, String> {
        let sessions = self.sessions.lock().map_err(|_| "Mutex poisoned")?;
        let session = sessions.get(session_id).ok_or_else(|| format!("Session not found: {}", session_id))?;
        
        let buffer = session.output_buffer.lock().map_err(|_| "Buffer mutex poisoned")?;
        let data = String::from_utf8_lossy(&buffer.iter().cloned().collect::<Vec<u8>>()).to_string();
        Ok(data)
    }

    pub fn resize_session(&self, session_id: &str, cols: u16, rows: u16) -> Result<(), String> {
        let sessions = self.sessions.lock().map_err(|_| "Mutex poisoned")?;
        let session = sessions
            .get(session_id)
            .ok_or_else(|| format!("Session not found: {}", session_id))?;

        session
            .master
            .resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| format!("Resize failed: {}", e))?;

        Ok(())
    }

    pub fn close_session(&self, session_id: &str) -> Result<(), String> {
        let sandbox_info: Option<(PathBuf, String)>;
        let bridge_processes: Vec<std::process::Child>;
        let mut main_child: Option<Box<dyn Child + Send>> = None;
        
        {
            let mut sessions = self.sessions.lock().map_err(|_| "Mutex poisoned")?;
            let mut session = sessions.remove(session_id)
                .ok_or_else(|| format!("Session not found: {}", session_id))?;
            
            sandbox_info = session.sandbox_root.as_ref().map(|_sb| {
                let project_root = session.metadata.cwd.as_ref()
                    .map(PathBuf::from)
                    .unwrap_or_else(|| PathBuf::from("."));
                (project_root, session_id.to_string())
            });

            // Take bridge processes and the main child to kill them outside the lock
            bridge_processes = std::mem::take(&mut session.bridge_processes);
            main_child = Some(session.child);
        }

        // Kill the main agent process
        if let Some(mut child) = main_child {
            log::info!("[PTY CLOSE] Terminating main process for session {}", session_id);
            let _ = child.kill();
            
            // Wait up to 500ms for child to exit
            for _ in 0..10 {
                if let Ok(Some(_)) = child.try_wait() {
                    break;
                }
                thread::sleep(Duration::from_millis(50));
            }
        }

        // Kill all associated bridge processes
        for mut child in bridge_processes {
            let _ = child.kill();
            let _ = child.wait();
        }

        // SPEC-036: Clean up sandbox directory after session closes
        if let Some((project_root, sid)) = sandbox_info {
            cleanup_sandbox(&project_root, &sid);
        }
        self.save_state();
        Ok(())
    }

    pub fn list_sessions(&self) -> Vec<SessionInfo> {
        match self.sessions.lock() {
            Ok(sessions) => sessions.values().map(|s| s.info.clone()).collect(),
            Err(_) => Vec::new(),
        }
    }

    pub fn restore_sessions<R: Runtime>(&self, app_handle: tauri::AppHandle<R>) {
        let persistent = Self::load_persistent_sessions();
        if persistent.is_empty() {
            return;
        }

        log::info!("[PTY RESTORE] Restoring {} sessions", persistent.len());
        
        // Update next_id to avoid collisions
        let mut max_id = 0;
        for s in &persistent {
            if s.id.starts_with("session_") {
                if let Ok(id_num) = s.id[8..].parse::<u32>() {
                    if id_num > max_id {
                        max_id = id_num;
                    }
                }
            }
        }
        
        if let Ok(mut next_id) = self.next_id.lock() {
            *next_id = max_id + 1;
        }

        for s in persistent {
            let _ = self.create_session(
                Some(s.id),
                &s.project,
                &s.agent,
                &s.role,
                &s.spec_id,
                &s.command,
                &s.args,
                s.cwd,
                s.parent_session_id,
                s.task_id,
                None, // build_id
                None, // adt_mode
                None, // adt_task_ids
                None, // context_hint
                false, // skip_permissions
                120, // Default cols
                30,  // Default rows
                app_handle.clone(),
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_persistent_session_serde() {
        let session = PersistentSession {
            id: "test_id".to_string(),
            project: "adt-framework".to_string(),
            agent: "claude".to_string(),
            role: "Backend_Engineer".to_string(),
            spec_id: "SPEC-021".to_string(),
            command: "bash".to_string(),
            args: vec!["-c".to_string(), "ls".to_string()],
            cwd: Some("/tmp".to_string()),
            parent_session_id: None,
            task_id: None,
            messaging_mode: Some("AUTO".to_string()),
        };

        let json = serde_json::to_string(&session).unwrap();
        let decoded: PersistentSession = serde_json::from_str(&json).unwrap();
        assert_eq!(session.id, decoded.id);
        assert_eq!(session.args, decoded.args);
        assert_eq!(decoded.messaging_mode, Some("AUTO".to_string()));
    }

    #[test]
    fn test_session_info_serde() {
        let info = SessionInfo {
            id: "test_id".to_string(),
            project: "adt-framework".to_string(),
            agent: "claude".to_string(),
            role: "Backend_Engineer".to_string(),
            spec_id: "SPEC-021".to_string(),
            command: "bash".to_string(),
            alive: true,
            agent_user: Some("agent".to_string()),
            sandboxed: Some(true),
            sandbox_tier: Some("phase_b".to_string()),
            parent_session_id: None,
            task_id: None,
            messaging_mode: Some("AUTO".to_string()),
        };

        let json = serde_json::to_string(&info).unwrap();
        let decoded: SessionInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(info.id, decoded.id);
        assert_eq!(info.alive, decoded.alive);
        assert_eq!(decoded.sandboxed, Some(true));
        assert_eq!(decoded.sandbox_tier, Some("phase_b".to_string()));
        assert_eq!(decoded.messaging_mode, Some("AUTO".to_string()));
    }

    #[test]
    fn test_session_info_serde_no_sandbox() {
        let info = SessionInfo {
            id: "shell_1".to_string(),
            project: "adt-framework".to_string(),
            agent: "shell".to_string(),
            role: "human".to_string(),
            spec_id: "".to_string(),
            command: "bash".to_string(),
            alive: true,
            agent_user: None,
            sandboxed: Some(false),
            sandbox_tier: None,
            parent_session_id: None,
            task_id: None,
            messaging_mode: None,
        };

        let json = serde_json::to_string(&info).unwrap();
        let decoded: SessionInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(decoded.sandboxed, Some(false));
        assert_eq!(decoded.sandbox_tier, None);
        assert_eq!(decoded.messaging_mode, None);
    }

    #[test]
    fn test_default_messaging_mode_for_role() {
        // SPEC-057: Systems_Architect is the only role spawning in MANUAL by default.
        assert_eq!(default_messaging_mode_for_role("Systems_Architect"), "MANUAL");
        assert_eq!(default_messaging_mode_for_role("Backend_Engineer"), "AUTO");
        assert_eq!(default_messaging_mode_for_role("Frontend_Engineer"), "AUTO");
        assert_eq!(default_messaging_mode_for_role("DevOps_Engineer"), "AUTO");
        assert_eq!(default_messaging_mode_for_role("Overseer"), "AUTO");
        assert_eq!(default_messaging_mode_for_role("unknown_role"), "AUTO");
    }

    #[test]
    fn test_create_comms_dirs_makes_subtree() {
        // SPEC-057: create_comms_dirs must build inbox/outbox/pending under
        // <framework_root>/_cortex/comms/agents/<session_id>/.
        let tmp = std::env::temp_dir().join(format!(
            "adt_comms_test_{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(&tmp).unwrap();

        let session_id = "test_session_057";
        create_comms_dirs(&tmp, session_id);

        let session_root = tmp
            .join("_cortex")
            .join("comms")
            .join("agents")
            .join(session_id);
        assert!(session_root.join("inbox").is_dir());
        assert!(session_root.join("outbox").is_dir());
        assert!(session_root.join("pending").is_dir());

        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_bwrap_args_no_longer_unshares_net() {
        // Amended 2026-08-15: --unshare-net removed so agents can reach
        // external APIs (Anthropic, Google). FS isolation retained via
        // --ro-bind + --bind. See build_bwrap_args() header comment.
        let project = PathBuf::from("/tmp/test-project");
        let framework = PathBuf::from("/home/test/adt-framework");
        let args = build_bwrap_args(&project, 5002, "/usr/bin/claude", &framework);

        assert!(!args.contains(&"--unshare-net".to_string()),
            "bwrap args must NOT include --unshare-net after 2026-08-15 amendment");
        assert!(args.contains(&"--die-with-parent".to_string()));
        assert!(args.contains(&"--chdir".to_string()));
    }

    #[test]
    fn test_bwrap_args_has_framework_mount() {
        let project = PathBuf::from("/tmp/test-project");
        let framework = PathBuf::from("/home/test/adt-framework");
        let args = build_bwrap_args(&project, 5002, "/usr/bin/claude", &framework);

        // Framework must be mounted at /adt-framework for hooks
        let ro_positions: Vec<usize> = args.iter().enumerate()
            .filter(|(_, a)| a.as_str() == "--ro-bind")
            .map(|(i, _)| i)
            .collect();

        let has_framework_mount = ro_positions.iter().any(|&i| {
            i + 2 < args.len()
                && args[i + 1] == "/home/test/adt-framework"
                && args[i + 2] == "/adt-framework"
        });
        assert!(has_framework_mount, "Framework root must be mounted at /adt-framework");
    }

    #[test]
    fn test_bwrap_args_has_project_bind() {
        let project = PathBuf::from("/tmp/test-project");
        let framework = PathBuf::from("/home/test/adt-framework");
        let args = build_bwrap_args(&project, 5002, "/usr/bin/claude", &framework);

        let bind_idx = args.iter().position(|a| a == "--bind").unwrap();
        assert_eq!(args[bind_idx + 1], "/tmp/test-project");
        assert_eq!(args[bind_idx + 2], "/project");
    }

    #[test]
    fn test_pty_manager_new_empty() {
        let manager = PtyManager::new();
        assert_eq!(manager.list_sessions().len(), 0);
    }
}