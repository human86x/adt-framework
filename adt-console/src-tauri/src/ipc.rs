// IPC commands — Frontend <-> Rust communication
// SPEC-021: Tauri command handlers for session management, tray, notifications,
// project file access, and system integration

use crate::pty::{PtyManager, SessionInfo};
use crate::tray::{self, TrayStatus};
use serde::Deserialize;

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
    pub start_dttp: Option<bool>,
}

#[derive(Deserialize)]
pub struct ProjectNameRequest {
    pub name: String,
}
// --- Session commands ---

#[tauri::command]
pub fn create_session<R: Runtime>(
    request: CreateSessionRequest,
    pty_manager: State<PtyManager>,
    app_handle: tauri::AppHandle<R>,
) -> Result<SessionInfo, String> {
    let project_name = request.project.as_deref().unwrap_or("adt-framework");
    log::info!(
        "[IPC RECV] create_session: project={}, agent={}, role={}, cmd={}, args={:?}",
        project_name, request.agent, request.role, request.command, request.args
    );
    pty_manager.create_session(
        None,
        project_name,
        &request.agent,
        &request.role,
        &request.spec_id,
        &request.command,
        &request.args,
        request.cwd,
        request.cols,
        request.rows,
        app_handle,
    )
}

#[tauri::command]
pub fn close_session(
    request: SessionIdRequest,
    pty_manager: State<PtyManager>,
) -> Result<(), String> {
    log::info!("[IPC RECV] close_session: id={}", request.session_id);
    pty_manager.close_session(&request.session_id)
}

#[tauri::command]
pub fn write_to_session(
    request: WriteRequest,
    pty_manager: State<PtyManager>,
) -> Result<(), String> {
    log::debug!(
        "[IPC RECV] write_to_session: id={}, data_len={}",
        request.session_id, request.data.len()
    );
    pty_manager.write_to_session(&request.session_id, request.data.as_bytes())
}

#[tauri::command]
pub fn resize_session(
    request: ResizeRequest,
    pty_manager: State<PtyManager>,
) -> Result<(), String> {
    log::info!(
        "[IPC RECV] resize_session: id={}, cols={}, rows={}",
        request.session_id, request.cols, request.rows
    );
    pty_manager.resize_session(&request.session_id, request.cols, request.rows)
}

#[tauri::command]
pub fn list_sessions(pty_manager: State<PtyManager>) -> Vec<SessionInfo> {
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

    // Optionally start DTTP for the new project
    if request.start_dttp.unwrap_or(false) {
        if let Err(e) = start_project_dttp_inner(&request.name.unwrap_or_else(|| {
            std::path::Path::new(&request.path)
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| "project".to_string())
        })) {
            log::warn!("Failed to auto-start DTTP: {}", e);
        }
    }

    Ok(stdout)
}

/// List all registered projects with DTTP status enrichment.
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

    // Parse, enrich with DTTP status, return
    let mut registry: serde_json::Value = serde_json::from_str(&content)
        .map_err(|e| format!("Invalid registry JSON: {}", e))?;

    if let Some(projects) = registry.get_mut("projects") {
        if let Some(arr) = projects.as_array_mut() {
            for project in arr.iter_mut() {
                if let Some(port) = project.get("port").and_then(|p| p.as_u64()) {
                    let dttp_running = check_port(port as u16);
                    project.as_object_mut().map(|obj| {
                        obj.insert("dttp_running".to_string(), serde_json::Value::Bool(dttp_running));
                    });
                }
            }
        }
    }

    serde_json::to_string(&registry)
        .map_err(|e| format!("Failed to serialize: {}", e))
}

/// Start DTTP service for a named project.
#[tauri::command]
pub fn start_project_dttp(request: ProjectNameRequest) -> Result<String, String> {
    log::info!("[IPC RECV] start_project_dttp: name={}", request.name);
    start_project_dttp_inner(&request.name)
}

/// Stop DTTP service for a named project.
#[tauri::command]
pub fn stop_project_dttp(request: ProjectNameRequest) -> Result<String, String> {
    log::info!("[IPC RECV] stop_project_dttp: name={}", request.name);

    let python = find_python().ok_or("Python not found")?;
    let mut cmd = std::process::Command::new(&python);
    cmd.arg("-m").arg("adt_core.cli").arg("projects").arg("stop").arg(&request.name);

    if let Ok(cwd) = std::env::current_dir() {
        cmd.env("PYTHONPATH", &cwd);
    }

    let output = cmd.output().map_err(|e| format!("Failed to stop DTTP: {}", e))?;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Failed to stop DTTP: {}", stderr));
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

fn start_project_dttp_inner(name: &str) -> Result<String, String> {
    let python = find_python().ok_or("Python not found")?;
    let mut cmd = std::process::Command::new(&python);
    cmd.arg("-m").arg("adt_core.cli").arg("projects").arg("start").arg(name);

    if let Ok(cwd) = std::env::current_dir() {
        cmd.env("PYTHONPATH", &cwd);
    }

    let output = cmd.output().map_err(|e| format!("Failed to start DTTP: {}", e))?;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Failed to start DTTP: {}", stderr));
    }

    Ok(stdout)
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
        let pty_manager = PtyManager::new();
        app.manage(pty_manager);
        let state = app.state::<PtyManager>();
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
