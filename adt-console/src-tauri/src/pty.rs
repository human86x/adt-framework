// PTY multiplexer — spawn and manage terminal processes
// SPEC-021 Phase A: portable-pty based process management
// SPEC-021 S9: Persistence and stability improvements
// SPEC-036: Agent Filesystem Sandbox (Phase A)

use portable_pty::{native_pty_system, CommandBuilder, MasterPty, PtySize};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::{Arc, Mutex};
use tauri::{Emitter, Runtime};

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
    command.to_string()
}


// --- SPEC-036: Agent Filesystem Sandbox ---

/// Environment variables that must NEVER be passed to sandboxed agent sessions.
/// These could leak sensitive credentials or paths outside the sandbox.
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
        let _ = Command::new("/bin/chmod")
            .args(["-R", "777", &sandbox_root.to_string_lossy()])
            .output();
        log::info!("[SANDBOX] Set sandbox permissions for agent user");
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
    dttp_url: &str,
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
        cmd.env("DTTP_URL", dttp_url);
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
        cmd.env("DTTP_URL", dttp_url);
    }

    // Remove sensitive environment variables
    // portable_pty's CommandBuilder inherits the parent env by default,
    // so we override dangerous vars with empty strings to effectively remove them
    for var in SANDBOX_ENV_DENYLIST {
        cmd.env(var, "");
    }

    // Also clear prefix-matched vars from the current process env
    for (key, _) in std::env::vars() {
        for prefix in SANDBOX_ENV_PREFIX_DENYLIST {
            if key.starts_with(prefix) && !SANDBOX_ENV_DENYLIST.contains(&key.as_str()) {
                cmd.env(&key, "");
            }
        }
    }

    log::info!(
        "[SANDBOX] Environment sanitized for {} session (namespace_mode={})",
        agent, namespace_mode
    );
}

/// Determine if a session should be sandboxed.
/// Returns true for agent sessions with a project CWD that differs from the framework root,
/// OR for any agent session when sandbox is explicitly desired.
fn should_sandbox(agent: &str, cwd: Option<&str>) -> bool {
    // Only sandbox agent sessions, not human shell sessions
    if agent == "shell" || agent == "human" {
        return false;
    }

    // If we have a CWD, sandbox is enabled
    cwd.is_some()
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
    // Smoke-test: run a trivial bwrap command to verify it actually works
    Command::new("/usr/bin/bwrap")
        .args(["--ro-bind", "/usr", "/usr", "--", "/usr/bin/true"])
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
/// NOTE: --unshare-net is enabled in Phase B (SPEC-036 task_148).
/// Network communication to host DTTP (localhost:5002) and ADT Panel (localhost:5001)
/// is bridged via socat.
fn build_bwrap_args(
    project_root: &Path,
    _dttp_port: u16,
    agent_binary_path: &str,
    framework_root: &Path,
) -> Vec<String> {
    let project_str = project_root.to_string_lossy().to_string();
    let framework_str = framework_root.to_string_lossy().to_string();

    let mut args = vec![
        "/usr/bin/bwrap".to_string(),
        "--unshare-net".to_string(), // Enable network isolation
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
    _dttp_port: u16,
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

/// Spawn socat background processes to bridge DTTP/Panel ports from host into the namespace.
/// Since bwrap's --unshare-net creates a new network namespace with only loopback,
/// the agent cannot reach localhost:5002 on the host.
/// We use a two-step bridge:
/// 1. Host Host-Port -> Host Unix-Socket (in sandbox)
/// 2. Namespace Host-Port (localhost) -> Namespace Unix-Socket (in sandbox)
fn spawn_network_bridges(
    sandbox_root: &Path,
    dttp_port: u16,
    panel_port: u16,
) -> Vec<std::process::Child> {
    let mut bridges = Vec::new();

    let dttp_sock = sandbox_root.join("dttp.sock");
    let panel_sock = sandbox_root.join("panel.sock");

    // 1. DTTP Bridge (Host Side: TCP -> Unix Socket)
    // socat UNIX-LISTEN:/path/to/dttp.sock,fork TCP:127.0.0.1:5002
    match Command::new("/usr/bin/socat")
        .args([
            &format!("UNIX-LISTEN:{},fork,reuseaddr", dttp_sock.to_string_lossy()),
            &format!("TCP:127.0.0.1:{}", dttp_port),
        ])
        .spawn()
    {
        Ok(child) => bridges.push(child),
        Err(e) => log::error!("[SANDBOX] Failed to spawn host DTTP bridge: {}", e),
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
    dttp_port: u16,
    panel_port: u16,
) -> (String, Vec<String>) {
    let dttp_sock = format!("/project/.adt/sandbox/{}/dttp.sock", session_id);
    let panel_sock = format!("/project/.adt/sandbox/{}/panel.sock", session_id);

    let agent_cmd = if args.is_empty() {
        command.to_string()
    } else {
        format!("{} {}", command, args.join(" "))
    };

    // The wrapper starts background socat bridges inside the namespace (Unix Socket -> TCP)
    // then execs the agent command.
    let script = format!(
        "socat TCP-LISTEN:{},fork,reuseaddr,bind=127.0.0.1 UNIX-CONNECT:{} & \
         socat TCP-LISTEN:{},fork,reuseaddr,bind=127.0.0.1 UNIX-CONNECT:{} & \
         exec {}",
        dttp_port, dttp_sock,
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
    dttp_port: u16,
    panel_port: u16,
    framework_root: &Path,
    session_id: &str,
) -> Option<(String, Vec<String>)> {
    let method = detect_isolation_method();

    match method {
        "bwrap" => {
            let mut bwrap_args = build_bwrap_args(project_root, dttp_port, command, framework_root);
            
            // Wrap the agent command with the network bridge script
            let (bridge_cmd, bridge_args) = build_bridge_wrapper(command, args, session_id, dttp_port, panel_port);
            bwrap_args.push(bridge_cmd);
            bwrap_args.extend(bridge_args);

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
            let setup_script = build_unshare_script(project_root, dttp_port, framework_root, command);
            
            // Wrap the agent command with the network bridge script
            let (bridge_cmd, bridge_args) = build_bridge_wrapper(command, args, session_id, dttp_port, panel_port);
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
}

struct PtySession {
    master: Box<dyn MasterPty + Send>,
    writer: Box<dyn Write + Send>,
    info: SessionInfo,
    metadata: PersistentSession,
    sandbox_root: Option<PathBuf>,
    bridge_processes: Vec<std::process::Child>,
}

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

        // Resolve the user's full PATH so we can find agent CLIs (gemini, claude)
        // that may be installed in non-standard locations (e.g. ~/.npm-global/bin/).
        // Tauri apps launched from desktop environments inherit a minimal PATH.
        let user_path = resolve_user_path();
        let resolved_command = resolve_command(command, &user_path);
        // Canonicalize to resolve symlinks (crucial for sandboxing npm-global modules)
        let canonical_command = PathBuf::from(&resolved_command)
            .canonicalize()
            .unwrap_or_else(|_| PathBuf::from(&resolved_command));
        let command_to_run = canonical_command.to_string_lossy().to_string();
        log::info!("[PTY PATH] Resolved '{}' -> '{}' (canonical: '{}')", 
                  command, resolved_command, command_to_run);

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

        // Determine DTTP and Panel ports
        let dttp_port_num = if let Some(path) = &cwd {
            let config_path = PathBuf::from(path).join("config").join("dttp.json");
            if config_path.exists() {
                fs::read_to_string(&config_path).ok()
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
        let framework_root = get_framework_root();
        let phase_b_wrap: Option<(String, Vec<String>)> = if production_mode && is_agent_session {
            if let Some(ref cwd_path) = cwd {
                let project_root = PathBuf::from(cwd_path);
                let is_fw = is_framework_project(&project_root, &framework_root);
                if !is_fw {
                    wrap_with_namespace(
                        &command_to_run,
                        args,
                        &project_root,
                        dttp_port_num,
                        panel_port_num,
                        &framework_root,
                        &session_id,
                    )
                } else {
                    None
                }
            } else {
                None
            }
        } else {
            None
        };

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
            for arg in args {
                c.arg(arg);
            }
            c
        } else {
            let mut c = CommandBuilder::new(&command_to_run);
            for arg in args {
                c.arg(arg);
            }
            c
        };

        // Bug 6 fix: skip cmd.cwd() when bwrap handles it via --chdir /project
        if phase_b_wrap.is_none() {
            if let Some(path) = &cwd {
                cmd.cwd(path);
            }
        }

        // Determine DTTP_URL for SDK communication
        let dttp_url = format!("http://localhost:{}", dttp_port_num);

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
                    } else if agent == "gemini" {
                        if let Err(e) = generate_gemini_sandbox_config(
                            &sb_root, &project_root, &framework_root, namespace_mode
                        ) {
                            log::error!("[SANDBOX] Gemini config generation failed: {}", e);
                        }
                        // Note: Do NOT inject --sandbox flag. Gemini's --sandbox requires
                        // docker/podman for container isolation. Our sandbox is DTTP-based
                        // (hook enforcement + env isolation), not container-based.
                        log::info!("[SANDBOX] Gemini DTTP hook sandbox configured (no --sandbox flag)");
                    }

                    // Apply sandbox environment (sanitize env vars, redirect HOME/TMPDIR)
                    // For external projects: full env sanitization
                    // For framework projects in production mode: still need HOME redirect
                    // because sudo -u agent sets HOME=/home/agent which may not exist
                    if !is_framework {
                        apply_sandbox_env(
                            &mut cmd, &sb_root, &project_root, agent, &dttp_url,
                            namespace_mode, &session_id,
                        );
                    } else if production_mode && is_agent_session {
                        // Framework project + production mode: redirect HOME/TMPDIR
                        // to sandbox so agents have a writable home directory
                        let sandbox_home = sb_root.join("home");
                        let sandbox_tmp = sb_root.join("tmp");
                        cmd.env("HOME", sandbox_home.to_string_lossy().as_ref());
                        cmd.env("TMPDIR", sandbox_tmp.to_string_lossy().as_ref());
                        cmd.env("DTTP_URL", &dttp_url);
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

        // Set environment variables for ADT context
        cmd.env("ADT_AGENT", agent);
        cmd.env("ADT_ROLE", role);
        cmd.env("ADT_SPEC_ID", spec_id);
        if sandbox_root.is_none() {
            // Only set DTTP_URL here if not already set by sandbox env
            cmd.env("DTTP_URL", &dttp_url);
        }
        cmd.env("TERM", "xterm-256color");
        cmd.env("PATH", &user_path);

        if let Some(path) = &cwd {
            if sandbox_root.is_none() {
                cmd.env("CLAUDE_PROJECT_DIR", path);
                cmd.env("GEMINI_PROJECT_DIR", path);
            }
        }

        let _child = pair
            .slave
            .spawn_command(cmd)
            .map_err(|e| format!("Failed to spawn process: {}", e))?;

        let writer = pair
            .master
            .take_writer()
            .map_err(|e| format!("Failed to get PTY writer: {}", e))?;

        if production_mode && is_agent_session {
            log::info!("[PTY PRODUCTION] Spawning as OS user 'agent' (sudo -u agent {})", command);
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
        };

        // Start reader thread — forwards PTY output to frontend via events
        let mut reader = pair
            .master
            .try_clone_reader()
            .map_err(|e| format!("Failed to clone PTY reader: {}", e))?;

        let event_session_id = session_id.clone();
        let app_handle_clone = app_handle.clone();
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
                        let data = String::from_utf8_lossy(&buf[..n]).to_string();
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
                bridge_processes = spawn_network_bridges(sb_root, dttp_port_num, panel_port_num);
            }
        }

        let session = PtySession {
            master: pair.master,
            writer,
            info: info.clone(),
            metadata,
            sandbox_root,
            bridge_processes,
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

            // Take bridge processes to kill them outside the lock
            bridge_processes = std::mem::take(&mut session.bridge_processes);
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
        };

        let json = serde_json::to_string(&session).unwrap();
        let decoded: PersistentSession = serde_json::from_str(&json).unwrap();
        assert_eq!(session.id, decoded.id);
        assert_eq!(session.args, decoded.args);
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
        };

        let json = serde_json::to_string(&info).unwrap();
        let decoded: SessionInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(info.id, decoded.id);
        assert_eq!(info.alive, decoded.alive);
        assert_eq!(decoded.sandboxed, Some(true));
        assert_eq!(decoded.sandbox_tier, Some("phase_b".to_string()));
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
        };

        let json = serde_json::to_string(&info).unwrap();
        let decoded: SessionInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(decoded.sandboxed, Some(false));
        assert_eq!(decoded.sandbox_tier, None);
    }

    #[test]
    fn test_bwrap_args_has_unshare_net() {
        // Phase B bwrap args must include --unshare-net
        let project = PathBuf::from("/tmp/test-project");
        let framework = PathBuf::from("/home/test/adt-framework");
        let args = build_bwrap_args(&project, 5002, "/usr/bin/claude", &framework);

        assert!(args.contains(&"--unshare-net".to_string()),
            "bwrap args must include --unshare-net for Phase B isolation");
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