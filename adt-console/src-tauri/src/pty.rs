// PTY multiplexer — spawn and manage terminal processes
// SPEC-021 Phase A: portable-pty based process management
// SPEC-021 S9: Persistence and stability improvements

use portable_pty::{native_pty_system, CommandBuilder, MasterPty, PtySize};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::process::Command;
use std::sync::{Arc, Mutex};
use tauri::{Emitter, Runtime};

/// Resolve the user's login shell PATH.
/// Tauri apps launched from desktop environments often inherit a minimal PATH
/// that doesn't include user-installed tools (npm global, cargo, etc.).
/// This runs the user's shell to get the full PATH.
fn resolve_user_path() -> String {
    let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/bash".to_string());
    if let Ok(output) = Command::new(&shell)
        .args(["-l", "-c", "echo $PATH"])
        .output()
    {
        let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !path.is_empty() {
            return path;
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
        log::info!("[PTY PATH] Resolved '{}' -> '{}'", command, resolved_command);

        // SPEC-027: In production mode, wrap agent commands with sudo -u agent.
        // Shell sessions requested by the human remain as the human user.
        let production_mode = is_production_mode();
        let is_agent_session = agent != "shell" && agent != "human";
        let agent_user = if production_mode && is_agent_session {
            Some("agent".to_string())
        } else {
            None
        };

        let mut cmd = if let Some(ref _agent_user) = agent_user {
            // Wrap with sudo -u agent: sudo -u agent <command> [args...]
            let mut c = CommandBuilder::new("sudo");
            c.arg("-u");
            c.arg("agent");
            c.arg(&resolved_command);
            for arg in args {
                c.arg(arg);
            }
            c
        } else {
            let mut c = CommandBuilder::new(&resolved_command);
            for arg in args {
                c.arg(arg);
            }
            c
        };

        if let Some(path) = &cwd {
            cmd.cwd(path);
        }

        // Determine DTTP_URL from project config if available
        let dttp_url = if let Some(path) = &cwd {
            let config_path = PathBuf::from(path).join("config").join("dttp.json");
            if config_path.exists() {
                if let Ok(content) = fs::read_to_string(config_path) {
                    if let Ok(json) = serde_json::from_str::<serde_json::Value>(&content) {
                        if let Some(port) = json.get("port").and_then(|p| p.as_u64()) {
                            format!("http://localhost:{}", port)
                        } else {
                            "http://localhost:5002".to_string()
                        }
                    } else {
                        "http://localhost:5002".to_string()
                    }
                } else {
                    "http://localhost:5002".to_string()
                }
            } else {
                "http://localhost:5002".to_string()
            }
        } else {
            "http://localhost:5002".to_string()
        };

        // Set environment variables for ADT context
        cmd.env("ADT_AGENT", agent);
        cmd.env("ADT_ROLE", role);
        cmd.env("ADT_SPEC_ID", spec_id);
        cmd.env("DTTP_URL", dttp_url);
        cmd.env("TERM", "xterm-256color");
        cmd.env("PATH", &user_path);

        if let Some(path) = &cwd {
            cmd.env("CLAUDE_PROJECT_DIR", path);
            cmd.env("GEMINI_PROJECT_DIR", path);
        }

        let _child = pair
            .slave
            .spawn_command(cmd)
            .map_err(|e| format!("Failed to spawn process: {}", e))?;

        // Generate or reserve session ID
        let session_id = if let Some(id) = reserved_id {
            id
        } else {
            let mut next_id_lock = self.next_id.lock().map_err(|_| "Mutex poisoned")?;
            let id = format!("session_{}", *next_id_lock);
            *next_id_lock += 1;
            id
        };

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

        let session = PtySession {
            master: pair.master,
            writer,
            info: info.clone(),
            metadata,
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
        {
            let mut sessions = self.sessions.lock().map_err(|_| "Mutex poisoned")?;
            sessions.remove(session_id).ok_or_else(|| format!("Session not found: {}", session_id))?;
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
        };

        let json = serde_json::to_string(&info).unwrap();
        let decoded: SessionInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(info.id, decoded.id);
        assert_eq!(info.alive, decoded.alive);
    }

    #[test]
    fn test_pty_manager_new_empty() {
        let manager = PtyManager::new();
        assert_eq!(manager.list_sessions().len(), 0);
    }
}