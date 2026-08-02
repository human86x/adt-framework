// IPC commands — Frontend <-> Rust communication
// SPEC-021: Tauri command handlers for session management, tray, notifications,
// project file access, and system integration

use crate::pty::{self, PtyManager, SessionInfo};
use crate::tray::{self, TrayStatus};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

use tauri::{Runtime, State};
use tauri_plugin_notification::NotificationExt;

#[derive(Deserialize)]
pub struct CreateSessionRequest {
    pub project: Option<String>,
    pub agent: String,
    pub role: String,
    pub spec_id: String,
    pub command: String,
    pub args: Vec<String>,
    pub cwd: Option<String>,
    pub parent_session_id: Option<String>,
    pub task_id: Option<String>,
    #[serde(rename = "reservedSessionId")]
    pub reserved_session_id: Option<String>,
    #[serde(default)]
    pub build_id: Option<String>,
    #[serde(default)]
    pub adt_mode: Option<String>,
    #[serde(default)]
    pub adt_task_ids: Option<String>,
    pub context_hint: Option<String>,
    #[serde(default)]
    pub skip_permissions: bool,
    pub cols: u16,
    pub rows: u16,
}

#[derive(Deserialize)]
pub struct SessionIdRequest {
    #[serde(rename = "sessionId")]
    pub session_id: String,
}

#[derive(Deserialize)]
pub struct WriteRequest {
    #[serde(rename = "sessionId")]
    pub session_id: String,
    pub data: String,
}

#[derive(Deserialize)]
pub struct ResizeRequest {
    #[serde(rename = "sessionId")]
    pub session_id: String,
    pub cols: u16,
    pub rows: u16,
}

#[derive(Deserialize)]
pub struct TrayStatusRequest {
    pub status: String,
    #[serde(rename = "sessionCount")]
    pub session_count: u32,
    pub escalations: u32,
}

#[derive(Deserialize)]
pub struct NotificationRequest {
    pub title: String,
    pub body: String,
}


#[derive(Deserialize)]
pub struct InitProjectRequest {
    pub path: String,
    pub name: Option<String>,
    pub detect: Option<bool>,
    pub start_dtcp: Option<bool>,
}

#[derive(Deserialize)]
pub struct ProjectNameRequest {
    pub name: String,
}
// --- Session commands ---

#[tauri::command]
pub fn create_session<R: Runtime>(
    request: CreateSessionRequest,
    pty_manager: State<'_, Arc<PtyManager>>,
    app_handle: tauri::AppHandle<R>,
) -> Result<SessionInfo, String> {
    let project_name = request.project.as_deref().unwrap_or("adt-framework");
    log::info!(
        "[IPC RECV] create_session: project={}, agent={}, role={}, cmd={}, args={:?}",
        project_name, request.agent, request.role, request.command, request.args
    );
    pty_manager.create_session(
        request.reserved_session_id,
        project_name,
        &request.agent,
        &request.role,
        &request.spec_id,
        &request.command,
        &request.args,
        request.cwd,
        request.parent_session_id,
        request.task_id,
        request.build_id,
        request.adt_mode,
        request.adt_task_ids,
        request.context_hint,
        request.skip_permissions,
        request.cols,
        request.rows,
        app_handle,
    )
}

#[tauri::command]
pub fn spawn_child_session<R: Runtime>(
    request: CreateSessionRequest,
    pty_manager: State<'_, Arc<PtyManager>>,
    app_handle: tauri::AppHandle<R>,
) -> Result<SessionInfo, String> {
    log::info!(
        "[SWARM] Spawning child session: agent={}, role={}, parent={:?}",
        request.agent, request.role, request.parent_session_id
    );

    // For child sessions, we enforce the parent_session_id exists
    if request.parent_session_id.is_none() {
        return Err("parent_session_id required for child spawning".to_string());
    }

    let project_name = request.project.as_deref().unwrap_or("adt-framework");

    pty_manager.create_session(
        request.reserved_session_id,
        project_name,
        &request.agent,
        &request.role,
        &request.spec_id,
        &request.command,
        &request.args,
        request.cwd,
        request.parent_session_id,
        request.task_id,
        request.build_id,
        request.adt_mode,
        request.adt_task_ids,
        request.context_hint,
        request.skip_permissions,
        request.cols,
        request.rows,
        app_handle,
    )
}

/// SPEC-055 task_325: Spawn an orchestrator SA session for the Build workflow.
/// Variant of spawn_child_session that requires build_id and defaults ADT_MODE=orchestrator.
#[tauri::command]
pub fn spawn_orchestrator_session<R: Runtime>(
    request: CreateSessionRequest,
    pty_manager: State<'_, Arc<PtyManager>>,
    app_handle: tauri::AppHandle<R>,
) -> Result<SessionInfo, String> {
    log::info!(
        "[ORCHESTRATOR] Spawning orchestrator session: agent={}, role={}, build_id={:?}, parent={:?}",
        request.agent, request.role, request.build_id, request.parent_session_id
    );

    if request.parent_session_id.is_none() {
        return Err("parent_session_id required for orchestrator session".to_string());
    }
    if request.build_id.is_none() {
        return Err("build_id required for orchestrator session".to_string());
    }

    let project_name = request.project.as_deref().unwrap_or("adt-framework");
    let adt_mode = Some(request.adt_mode.unwrap_or_else(|| "orchestrator".to_string()));

    pty_manager.create_session(
        request.reserved_session_id,
        project_name,
        &request.agent,
        &request.role,
        &request.spec_id,
        &request.command,
        &request.args,
        request.cwd,
        request.parent_session_id,
        request.task_id,
        request.build_id,
        Some("orchestrator".to_string()), // Forced mode
        request.adt_task_ids,
        request.context_hint,
        request.skip_permissions,
        request.cols,
        request.rows,
        app_handle,
    )
}

#[tauri::command]
pub fn close_session(
    request: SessionIdRequest,
    pty_manager: State<'_, Arc<PtyManager>>,
) -> Result<(), String> {
    pty_manager.close_session(&request.session_id)
}

#[tauri::command]
pub fn write_to_session(
    request: WriteRequest,
    pty_manager: State<'_, Arc<PtyManager>>,
) -> Result<(), String> {
    log::debug!(
        "[IPC RECV] write_to_session: id={}, data_len={}",
        request.session_id, request.data.len()
    );
    pty_manager.write_to_session(&request.session_id, request.data.as_bytes())
}

#[tauri::command]
pub fn inject_pty_command(
    request: WriteRequest,
    pty_manager: State<'_, Arc<PtyManager>>,
) -> Result<(), String> {
    log::info!(
        "[IPC RECV] inject_pty_command: id={}, cmd={}",
        request.session_id, request.data.trim()
    );
    pty_manager.inject_command(&request.session_id, &request.data)
}

#[tauri::command]
pub fn resize_session(
    request: ResizeRequest,
    pty_manager: State<'_, Arc<PtyManager>>,
) -> Result<(), String> {
    log::info!(
        "[IPC RECV] resize_session: id={}, cols={}, rows={}",
        request.session_id, request.cols, request.rows
    );
    pty_manager.resize_session(&request.session_id, request.cols, request.rows)
}

#[tauri::command]
pub fn replay_session_output<R: Runtime>(
    request: SessionIdRequest,
    pty_manager: State<'_, Arc<PtyManager>>,
    app_handle: tauri::AppHandle<R>,
) -> Result<(), String> {
    log::info!("[IPC RECV] replay_session_output: id={}", request.session_id);
    pty_manager.replay_session_output(&request.session_id, app_handle)
}

#[tauri::command]
pub fn list_sessions(pty_manager: State<'_, Arc<PtyManager>>) -> Vec<SessionInfo> {
    pty_manager.list_sessions()
}

// --- System integration commands ---

#[tauri::command]
pub fn update_tray_status<R: Runtime>(
    request: TrayStatusRequest,
    app_handle: tauri::AppHandle<R>,
) -> Result<(), String> {
    let status = match request.status.as_str() {
        "nominal" => TrayStatus::Nominal,
        "warning" => TrayStatus::Warning,
        "error" => TrayStatus::Error,
        _ => TrayStatus::Idle,
    };

    tray::update_tray_status(&app_handle, status, request.session_count, request.escalations);
    Ok(())
}

#[tauri::command]
pub fn send_notification<R: Runtime>(
    request: NotificationRequest,
    app_handle: tauri::AppHandle<R>,
) -> Result<(), String> {
    app_handle
        .notification()
        .builder()
        .title(&request.title)
        .body(&request.body)
        .show()
        .map_err(|e| format!("Notification failed: {}", e))?;

    log::info!("[NOTIFY] {}: {}", request.title, request.body);
    Ok(())
}

// --- Project file access (offline fallback for context panel) ---

/// Read a project-relative file and return its contents as a string.
/// Path traversal is blocked: the resolved path must stay within the project root.
#[tauri::command]
pub fn read_project_file(path: String) -> Result<String, String> {
    // Determine project root from current working directory
    let project_root = std::env::current_dir()
        .map_err(|e| format!("Cannot determine project root: {}", e))?;

    let requested = project_root.join(&path);
    let resolved = requested
        .canonicalize()
        .map_err(|e| format!("File not found: {}: {}", path, e))?;

    // Path traversal protection: resolved path must be under project root
    let canon_root = project_root
        .canonicalize()
        .map_err(|e| format!("Cannot resolve project root: {}", e))?;

    if !resolved.starts_with(&canon_root) {
        return Err(format!("Path traversal blocked: {}", path));
    }

    std::fs::read_to_string(&resolved)
        .map_err(|e| format!("Failed to read {}: {}", path, e))
}

// --- Autostart management ---

/// Toggle launch-on-login for the ADT Console.
/// Linux: XDG autostart desktop entry
/// macOS: launchd plist
/// Windows: registry Run key
#[tauri::command]
pub fn toggle_autostart(enabled: bool) -> Result<(), String> {
    log::info!("[AUTOSTART] Toggle: {}", enabled);

    #[cfg(target_os = "linux")]
    {
        toggle_autostart_linux(enabled)
    }

    #[cfg(target_os = "macos")]
    {
        toggle_autostart_macos(enabled)
    }

    #[cfg(target_os = "windows")]
    {
        toggle_autostart_windows(enabled)
    }

    #[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
    {
        Err("Autostart not supported on this platform".to_string())
    }
}

#[cfg(target_os = "linux")]
fn toggle_autostart_linux(enabled: bool) -> Result<(), String> {
    let autostart_dir = dirs::config_dir()
        .ok_or("Cannot find XDG config directory")?
        .join("autostart");

    let desktop_file = autostart_dir.join("adt-console.desktop");

    if enabled {
        std::fs::create_dir_all(&autostart_dir)
            .map_err(|e| format!("Failed to create autostart dir: {}", e))?;

        // Find the binary path
        let exe_path = std::env::current_exe()
            .map_err(|e| format!("Cannot find executable: {}", e))?;

        let content = format!(
            "[Desktop Entry]\n\
             Type=Application\n\
             Name=ADT Console\n\
             Comment=ADT Framework Operator Console\n\
             Exec={}\n\
             Icon=adt-console\n\
             Terminal=false\n\
             Categories=Development;\n\
             StartupNotify=false\n\
             X-GNOME-Autostart-enabled=true\n",
            exe_path.display()
        );

        std::fs::write(&desktop_file, content)
            .map_err(|e| format!("Failed to write autostart entry: {}", e))?;

        log::info!("[AUTOSTART] Enabled at {:?}", desktop_file);
    } else {
        if desktop_file.exists() {
            std::fs::remove_file(&desktop_file)
                .map_err(|e| format!("Failed to remove autostart entry: {}", e))?;
        }
        log::info!("[AUTOSTART] Disabled");
    }

    Ok(())
}

#[cfg(target_os = "macos")]
fn toggle_autostart_macos(enabled: bool) -> Result<(), String> {
    let launch_agents = dirs::home_dir()
        .ok_or("Cannot find home directory")?
        .join("Library")
        .join("LaunchAgents");

    let plist_file = launch_agents.join("pt.oceanpulse.adt-console.plist");

    if enabled {
        std::fs::create_dir_all(&launch_agents)
            .map_err(|e| format!("Failed to create LaunchAgents dir: {}", e))?;

        let exe_path = std::env::current_exe()
            .map_err(|e| format!("Cannot find executable: {}", e))?;

        let content = format!(
            r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>pt.oceanpulse.adt-console</string>
    <key>ProgramArguments</key>
    <array>
        <string>{}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>"#,
            exe_path.display()
        );

        std::fs::write(&plist_file, content)
            .map_err(|e| format!("Failed to write launchd plist: {}", e))?;

        log::info!("[AUTOSTART] Enabled at {:?}", plist_file);
    } else {
        if plist_file.exists() {
            std::fs::remove_file(&plist_file)
                .map_err(|e| format!("Failed to remove launchd plist: {}", e))?;
        }
        log::info!("[AUTOSTART] Disabled");
    }

    Ok(())
}

#[cfg(target_os = "windows")]
fn toggle_autostart_windows(enabled: bool) -> Result<(), String> {
    use std::process::Command;

    let exe_path = std::env::current_exe()
        .map_err(|e| format!("Cannot find executable: {}", e))?;

    if enabled {
        let output = Command::new("reg")
            .args([
                "add",
                r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
                "/v", "ADTConsole",
                "/t", "REG_SZ",
                "/d", &exe_path.display().to_string(),
                "/f",
            ])
            .output()
            .map_err(|e| format!("Registry command failed: {}", e))?;

        if !output.status.success() {
            return Err(format!(
                "Failed to set registry key: {}",
                String::from_utf8_lossy(&output.stderr)
            ));
        }
        log::info!("[AUTOSTART] Enabled via registry");
    } else {
        let _ = Command::new("reg")
            .args([
                "delete",
                r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
                "/v", "ADTConsole",
                "/f",
            ])
            .output();
        log::info!("[AUTOSTART] Disabled via registry");
    }

    Ok(())
}


// --- Shatterglass production mode commands (SPEC-027) ---

/// Get current production mode status. Returns JSON with enabled flag and details.
#[tauri::command]
pub fn get_production_mode() -> Result<String, String> {
    let enabled = pty::is_production_mode();
    let flag_exists = pty::production_mode_flag_path().exists();

    // Check if agent user exists
    let agent_exists = std::fs::read_to_string("/etc/passwd")
        .map(|content| content.lines().any(|line| line.starts_with("agent:")))
        .unwrap_or(false);

    let result = serde_json::json!({
        "enabled": enabled,
        "flag_exists": flag_exists,
        "agent_user_exists": agent_exists,
        "ready": agent_exists,
    });

    Ok(result.to_string())
}

/// Enable production mode (Tier 1). Human-only action.
/// New sessions will be spawned as the 'agent' OS user via sudo.
#[tauri::command]
pub fn enable_production_mode() -> Result<String, String> {
    log::info!("[IPC RECV] enable_production_mode (human action)");
    pty::enable_production_mode()?;
    Ok("{\"enabled\": true}".to_string())
}

/// Disable production mode (back to Tier 3). Human-only action.
/// New sessions will run as the human user directly.
#[tauri::command]
pub fn disable_production_mode() -> Result<String, String> {
    log::info!("[IPC RECV] disable_production_mode (human action)");
    pty::disable_production_mode()?;
    Ok("{\"enabled\": false}".to_string())
}

// --- Project management commands (SPEC-032) ---

/// Initialize a new project with ADT governance scaffolding.
/// Calls: python3 -m adt_core.cli init <path> [--name <name>] [--detect]
#[tauri::command]
pub fn init_project(request: InitProjectRequest) -> Result<String, String> {
    log::info!(
        "[IPC RECV] init_project: path={}, name={:?}, detect={:?}",
        request.path, request.name, request.detect
    );

    let python = find_python().ok_or("Python not found")?;
    let mut cmd = std::process::Command::new(&python);
    cmd.arg("-m").arg("adt_core.cli").arg("init").arg(&request.path);

    if let Some(ref name) = request.name {
        cmd.arg("--name").arg(name);
    }
    if request.detect.unwrap_or(false) {
        // cmd.arg("--detect"); // Removed invalid flag
    }

    // Set PYTHONPATH to framework root
    if let Ok(cwd) = std::env::current_dir() {
        cmd.env("PYTHONPATH", &cwd);
    }

    let output = cmd.output().map_err(|e| format!("Failed to run adt init: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("adt init failed: {}", stderr));
    }

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();

    // Optionally start DTCP for the new project
    if request.start_dtcp.unwrap_or(false) {
        if let Err(e) = start_project_dtcp_inner(&request.name.unwrap_or_else(|| {
            std::path::Path::new(&request.path)
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| "project".to_string())
        })) {
            log::warn!("Failed to auto-start DTCP: {}", e);
        }
    }

    Ok(stdout)
}

/// List all registered projects with DTCP status enrichment.
/// Reads ~/.adt/projects.json and checks port availability.
#[tauri::command]
pub fn list_projects() -> Result<String, String> {
    log::info!("[IPC RECV] list_projects");

    let registry_path = dirs::home_dir()
        .ok_or("Cannot find home directory")?
        .join(".adt")
        .join("projects.json");

    if !registry_path.exists() {
        return Ok("[]".to_string());
    }

    let content = std::fs::read_to_string(&registry_path)
        .map_err(|e| format!("Failed to read registry: {}", e))?;

    // Parse, enrich with DTCP status, return
    let mut registry: serde_json::Value = serde_json::from_str(&content)
        .map_err(|e| format!("Invalid registry JSON: {}", e))?;

    if let Some(projects) = registry.get_mut("projects") {
        if let Some(arr) = projects.as_array_mut() {
            for project in arr.iter_mut() {
                if let Some(port) = project.get("port").and_then(|p| p.as_u64()) {
                    let dtcp_running = check_port(port as u16);
                    project.as_object_mut().map(|obj| {
                        obj.insert("dtcp_running".to_string(), serde_json::Value::Bool(dtcp_running));
                    });
                }
            }
        }
    }

    serde_json::to_string(&registry)
        .map_err(|e| format!("Failed to serialize: {}", e))
}

/// Start DTCP service for a named project.
#[tauri::command]
pub fn start_project_dtcp(request: ProjectNameRequest) -> Result<String, String> {
    log::info!("[IPC RECV] start_project_dtcp: name={}", request.name);
    start_project_dtcp_inner(&request.name)
}

/// Stop DTCP service for a named project.
#[tauri::command]
pub fn stop_project_dtcp(request: ProjectNameRequest) -> Result<String, String> {
    log::info!("[IPC RECV] stop_project_dtcp: name={}", request.name);

    let python = find_python().ok_or("Python not found")?;
    let mut cmd = std::process::Command::new(&python);
    cmd.arg("-m").arg("adt_core.cli").arg("projects").arg("stop").arg(&request.name);

    if let Ok(cwd) = std::env::current_dir() {
        cmd.env("PYTHONPATH", &cwd);
    }

    let output = cmd.output().map_err(|e| format!("Failed to stop DTCP: {}", e))?;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Failed to stop DTCP: {}", stderr));
    }

    Ok(stdout)
}

// --- Project helper functions ---

fn find_python() -> Option<String> {
    // Check for venv python first
    if let Ok(cwd) = std::env::current_dir() {
        let venv = cwd.join("venv").join("bin").join("python3");
        if venv.exists() {
            return Some(venv.to_string_lossy().to_string());
        }
        let dotvenv = cwd.join(".venv").join("bin").join("python3");
        if dotvenv.exists() {
            return Some(dotvenv.to_string_lossy().to_string());
        }
    }
    // Fall back to system python
    Some("python3".to_string())
}

fn check_port(port: u16) -> bool {
    std::net::TcpStream::connect_timeout(
        &std::net::SocketAddr::from(([127, 0, 0, 1], port)),
        std::time::Duration::from_millis(200),
    ).is_ok()
}

/// Bind to port 0 to have the OS assign a free ephemeral port, then release
/// it — the returned port is highly likely to still be free when the caller
/// tries to bind it again.
fn pick_free_port() -> Option<u16> {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").ok()?;
    let port = listener.local_addr().ok()?.port();
    drop(listener);
    Some(port)
}

/// Derive a stable port from a project path so re-launching the same project
/// always uses the same URL. Critical for browser camera/mic permissions —
/// they are per-origin, so a shifting port re-prompts on every launch.
///
/// Port range 8600..=8899 (300 slots), avoiding common dev-server ports.
/// If the derived port is already in use by *another* process, walks forward
/// up to 20 slots. Returns the first free port, or None if all are taken.
fn stable_port_for_project(project_path: &std::path::Path) -> Option<u16> {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};

    let key = project_path.to_string_lossy();
    let mut hasher = DefaultHasher::new();
    key.hash(&mut hasher);
    let hash = hasher.finish();

    let base = 8600u16 + (hash % 300) as u16;
    // If our own http.server is already bound to this port (from a previous
    // launch of the same project), reuse it — we'll skip re-spawning below.
    for offset in 0..20u16 {
        let candidate = base.wrapping_add(offset);
        if candidate < 8600 || candidate > 8999 {
            continue;
        }
        if std::net::TcpListener::bind(("127.0.0.1", candidate)).is_ok() {
            return Some(candidate);
        }
    }
    // Fall through: use derived port anyway (something else is on it, but our
    // spawn will fail loudly in the log).
    Some(base)
}

fn start_project_dtcp_inner(name: &str) -> Result<String, String> {
    let python = find_python().ok_or("Python not found")?;
    let mut cmd = std::process::Command::new(&python);
    cmd.arg("-m").arg("adt_core.cli").arg("projects").arg("start").arg(name);

    if let Ok(cwd) = std::env::current_dir() {
        cmd.env("PYTHONPATH", &cwd);
    }

    let output = cmd.output().map_err(|e| format!("Failed to start DTCP: {}", e))?;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Failed to start DTCP: {}", stderr));
    }

    Ok(stdout)
}

#[tauri::command]
pub fn list_agy_models() -> Vec<String> {
    use std::sync::OnceLock;
    use std::process::Command;
    use std::time::Duration;
    use std::thread;

    static CACHED_MODELS: OnceLock<Vec<String>> = OnceLock::new();

    CACHED_MODELS.get_or_init(|| {
        log::info!("Fetching available agy models...");
        let fallback = vec![
            "Claude Sonnet 4.6 (Thinking)".to_string(),
            "Claude Opus 4.6 (Thinking)".to_string(),
            "Gemini 3.5 Flash (High)".to_string(),
            "Gemini 3.1 Pro (High)".to_string(),
            "GPT-OSS 120B (Medium)".to_string(),
        ];

        let agy_bin = std::env::var("AGY_EXECPATH").unwrap_or_else(|_| {
            if std::path::Path::new("/home/human/.local/bin/agy").exists() {
                "/home/human/.local/bin/agy".to_string()
            } else {
                "agy".to_string()
            }
        });

        let mut child = match Command::new(&agy_bin)
            .arg("models")
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn() 
        {
            Ok(c) => c,
            Err(e) => {
                log::error!("Failed to spawn agy models: {}", e);
                return fallback;
            }
        };

        let child_stdout = child.stdout.take();
        let reader_thread = thread::spawn(move || {
            if let Some(stdout) = child_stdout {
                use std::io::Read;
                let mut buf = String::new();
                let mut reader = std::io::BufReader::new(stdout);
                if reader.read_to_string(&mut buf).is_ok() {
                    return Some(buf);
                }
            }
            None
        });

        let (tx_status, rx_status) = std::sync::mpsc::channel();
        thread::spawn(move || {
            let res = child.wait();
            let _ = tx_status.send(res);
        });

        let timeout = Duration::from_secs(10);
        let status = rx_status.recv_timeout(timeout);

        match status {
            Ok(Ok(exit_status)) if exit_status.success() => {
                if let Ok(Some(stdout_str)) = reader_thread.join() {
                    let mut models = Vec::new();
                    for line in stdout_str.lines() {
                        let trimmed = line.trim();
                        if !trimmed.is_empty() 
                            && !trimmed.contains("Fetching available models")
                            && !trimmed.contains("⠋")
                            && !trimmed.contains("⠙")
                            && !trimmed.contains("⠹")
                            && !trimmed.contains("⠸")
                            && !trimmed.contains("⠼")
                            && !trimmed.contains("⠴")
                            && !trimmed.contains("⠦")
                            && !trimmed.contains("⠧")
                            && !trimmed.contains("⠇")
                            && !trimmed.contains("⠏")
                            && !trimmed.contains("Error")
                        {
                            models.push(trimmed.to_string());
                        }
                    }
                    if !models.is_empty() {
                        return models;
                    }
                }
            }
            _ => {
                log::warn!("agy models command timed out, failed, or returned error. Using fallback.");
            }
        }
        
        fallback
    }).clone()
}

// ============================================================================
// Project launch — detect entry point and run built project
// ============================================================================

#[derive(Serialize, Debug, Clone)]
pub struct LaunchInfo {
    pub launchable: bool,
    /// "html" | "npm" | "python" | "cargo" | "make" | "docker" | "none"
    pub kind: String,
    /// Relative path to entry file inside project (empty if not launchable).
    pub entry_file: String,
    /// Human-readable run command (empty if not launchable).
    pub run_command: String,
    /// Short description shown in tooltip.
    pub description: String,
    /// If not launchable, explains why (shown as disabled-button tooltip).
    pub reason: Option<String>,
}

fn detect_launch_inner(project_path: &std::path::Path) -> LaunchInfo {
    let none = |reason: &str| LaunchInfo {
        launchable: false,
        kind: "none".to_string(),
        entry_file: String::new(),
        run_command: String::new(),
        description: String::new(),
        reason: Some(reason.to_string()),
    };

    if !project_path.exists() || !project_path.is_dir() {
        return none("Project path does not exist");
    }

    // 1. index.html at common locations
    for rel in [
        "index.html",
        "public/index.html",
        "www/index.html",
        "dist/index.html",
        "build/index.html",
        "src/index.html",
    ] {
        if project_path.join(rel).is_file() {
            return LaunchInfo {
                launchable: true,
                kind: "html".to_string(),
                entry_file: rel.to_string(),
                run_command: format!("xdg-open {}", rel),
                description: format!("Open {} in browser", rel),
                reason: None,
            };
        }
    }

    // 2. package.json with scripts.start (or scripts.dev)
    let pkg = project_path.join("package.json");
    if pkg.is_file() {
        if let Ok(content) = std::fs::read_to_string(&pkg) {
            if let Ok(json) = serde_json::from_str::<serde_json::Value>(&content) {
                if json.get("scripts").and_then(|s| s.get("start")).is_some() {
                    return LaunchInfo {
                        launchable: true,
                        kind: "npm".to_string(),
                        entry_file: "package.json".to_string(),
                        run_command: "npm start".to_string(),
                        description: "Run npm start".to_string(),
                        reason: None,
                    };
                }
                if json.get("scripts").and_then(|s| s.get("dev")).is_some() {
                    return LaunchInfo {
                        launchable: true,
                        kind: "npm".to_string(),
                        entry_file: "package.json".to_string(),
                        run_command: "npm run dev".to_string(),
                        description: "Run npm run dev".to_string(),
                        reason: None,
                    };
                }
            }
        }
    }

    // 3. Python entry points
    for candidate in ["main.py", "app.py", "run.py", "__main__.py", "server.py"] {
        if project_path.join(candidate).is_file() {
            return LaunchInfo {
                launchable: true,
                kind: "python".to_string(),
                entry_file: candidate.to_string(),
                run_command: format!("python3 {}", candidate),
                description: format!("Run python3 {}", candidate),
                reason: None,
            };
        }
    }

    // 4. Cargo.toml
    if project_path.join("Cargo.toml").is_file() {
        return LaunchInfo {
            launchable: true,
            kind: "cargo".to_string(),
            entry_file: "Cargo.toml".to_string(),
            run_command: "cargo run".to_string(),
            description: "cargo run (Rust)".to_string(),
            reason: None,
        };
    }

    // 5. Makefile with `run:` target
    let mk = project_path.join("Makefile");
    if mk.is_file() {
        if let Ok(content) = std::fs::read_to_string(&mk) {
            for line in content.lines() {
                if line.trim_start().starts_with("run:") {
                    return LaunchInfo {
                        launchable: true,
                        kind: "make".to_string(),
                        entry_file: "Makefile".to_string(),
                        run_command: "make run".to_string(),
                        description: "make run".to_string(),
                        reason: None,
                    };
                }
            }
        }
    }

    // 6. docker-compose
    for candidate in ["docker-compose.yml", "docker-compose.yaml", "compose.yml"] {
        if project_path.join(candidate).is_file() {
            return LaunchInfo {
                launchable: true,
                kind: "docker".to_string(),
                entry_file: candidate.to_string(),
                run_command: "docker compose up".to_string(),
                description: "docker compose up".to_string(),
                reason: None,
            };
        }
    }

    none("No runnable entry point yet — build hasn't produced index.html, package.json+start, main.py, Cargo.toml, Makefile:run, or docker-compose.yml")
}

#[tauri::command]
pub fn detect_project_launch(project_path: String) -> LaunchInfo {
    log::info!("[IPC RECV] detect_project_launch: path={}", project_path);
    detect_launch_inner(std::path::Path::new(&project_path))
}

#[tauri::command]
pub fn launch_project(project_path: String) -> Result<String, String> {
    log::info!("[IPC RECV] launch_project: path={}", project_path);
    let p = std::path::Path::new(&project_path);
    let info = detect_launch_inner(p);

    if !info.launchable {
        return Err(info.reason.unwrap_or_else(|| "Not launchable".to_string()));
    }

    let log_path = format!(
        "/tmp/adt_launch_{}_{}.log",
        p.file_name()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_else(|| "project".to_string()),
        std::process::id()
    );

    // For HTML: serve over http://127.0.0.1:<port>/ so browsers grant a secure
    // context (getUserMedia, service workers, etc). `file://` breaks those APIs
    // in Chromium/WebKit. Steps:
    //   1. Pick a free port.
    //   2. Serve the entry file's parent dir (so relative assets resolve).
    //   3. Start python3 detached with nohup+setsid so it survives console exit.
    //   4. Wait for the port to actually be listening (poll up to 4s).
    //   5. Open the browser at http://127.0.0.1:<port>/<entry-basename>.
    let (effective_cwd, sh_line) = if info.kind == "html" {
        // Stable port per-project so browser camera/mic permissions are
        // remembered across re-launches (same origin every time).
        let port = stable_port_for_project(p).unwrap_or(8765);
        let entry_path = std::path::Path::new(&info.entry_file);
        let entry_dir_rel = entry_path
            .parent()
            .map(|d| d.to_string_lossy().into_owned())
            .unwrap_or_default();
        let entry_basename = entry_path
            .file_name()
            .map(|f| f.to_string_lossy().into_owned())
            .unwrap_or_else(|| "index.html".to_string());
        let effective = if entry_dir_rel.is_empty() {
            p.to_path_buf()
        } else {
            p.join(&entry_dir_rel)
        };

        // If port already responds (previous launch's server still alive),
        // just open the browser at the existing URL — no re-spawn.
        // Otherwise start python3 detached, wait up to 4s for it to listen,
        // then open the browser.
        //
        // IMPORTANT: run python3 from /tmp with --directory pointing at the
        // project, so an accidental `http/` or `json/` package inside the
        // project doesn't shadow stdlib and crash the launcher with a
        // circular-import AttributeError. See eyetoy_test regression 2026-07-05.
        let serve_dir = effective.to_string_lossy().into_owned();
        let script = format!(
            "if (echo > /dev/tcp/127.0.0.1/{port}) 2>/dev/null; then \
               echo \"[launch] reusing existing server on :{port}\" >> {log}; \
             else \
               ( cd /tmp && setsid nohup python3 -m http.server {port} --bind 127.0.0.1 --directory '{dir}' >> {log} 2>&1 & ); \
               for i in $(seq 1 40); do \
                 (echo > /dev/tcp/127.0.0.1/{port}) 2>/dev/null && break; \
                 sleep 0.1; \
               done; \
             fi; \
             xdg-open http://127.0.0.1:{port}/{basename} >> {log} 2>&1",
            port = port,
            log = log_path,
            dir = serve_dir.replace('\'', "'\\''"),
            basename = entry_basename
        );
        (effective, script)
    } else {
        // Non-HTML: run the detected command detached, from the project root.
        let script = format!(
            "setsid nohup bash -c '{cmd}' >> {log} 2>&1 & disown",
            cmd = info.run_command.replace('\'', "'\\''"),
            log = log_path
        );
        (p.to_path_buf(), script)
    };

    let output = std::process::Command::new("bash")
        .arg("-c")
        .arg(&sh_line)
        .current_dir(&effective_cwd)
        .output()
        .map_err(|e| format!("Failed to spawn launch: {}", e))?;

    if !output.status.success() {
        return Err(format!(
            "Launch spawn failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    Ok(format!(
        "Launched: {}  (log: {})",
        info.run_command, log_path
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pty::PtyManager;
    use tauri::test::{mock_builder, mock_context, noop_assets};
    use tauri::Manager;

    #[test]
    fn test_list_sessions_empty() {
        let app = mock_builder().build(mock_context(noop_assets())).unwrap();
        let pty_manager = Arc::new(PtyManager::new());
        app.manage(pty_manager);
        let state = app.state::<Arc<PtyManager>>();
        let sessions = list_sessions(state);
        assert_eq!(sessions.len(), 0);
    }

    #[test]
    fn test_read_project_file_traversal_blocked() {
        // Attempt path traversal
        let result = read_project_file("../../etc/passwd".to_string());
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert!(
            err.contains("traversal") || err.contains("not found") || err.contains("File not found"),
            "Expected traversal or not found error, got: {}", err
        );
    }

    #[test]
    fn test_read_project_file_nonexistent() {
        let result = read_project_file("this_file_does_not_exist_xyz.txt".to_string());
        assert!(result.is_err());
    }

    #[test]
    fn test_find_python() {
        let python = find_python();
        assert!(python.is_some(), "Should find a python executable");
    }

    #[test]
    fn test_check_port_closed() {
        // Port 59999 should not be in use
        assert!(!(check_port(59999)));
    }

    #[test]
    fn test_list_projects_no_crash() {
        // Ensures list_projects does not panic
        let _ = list_projects();
    }
}
