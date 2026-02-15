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

// --- Session commands ---

#[tauri::command]
pub fn create_session<R: Runtime>(
    request: CreateSessionRequest,
    pty_manager: State<PtyManager>,
    app_handle: tauri::AppHandle<R>,
) -> Result<SessionInfo, String> {
    log::info!(
        "[IPC RECV] create_session: agent={}, role={}, cmd={}, args={:?}",
        request.agent, request.role, request.command, request.args
    );
    pty_manager.create_session(
        None,
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
}
