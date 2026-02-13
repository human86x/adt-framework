// PTY multiplexer — spawn and manage terminal processes
// SPEC-021 Phase A: portable-pty based process management
// SPEC-021 S9: Persistence and stability improvements

use portable_pty::{native_pty_system, CommandBuilder, MasterPty, PtySize};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tauri::{Emitter, Runtime};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionInfo {
    pub id: String,
    pub agent: String,
    pub role: String,
    pub command: String,
    pub alive: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PersistentSession {
    pub id: String,
    pub agent: String,
    pub role: String,
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
        agent: &str,
        role: &str,
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

        let mut cmd = CommandBuilder::new(command);
        for arg in args {
            cmd.arg(arg);
        }

        if let Some(path) = &cwd {
            cmd.cwd(path);
        }

        // Set environment variables for ADT context
        cmd.env("ADT_AGENT", agent);
        cmd.env("ADT_ROLE", role);
        cmd.env("DTTP_URL", "http://localhost:5002");
        cmd.env("TERM", "xterm-256color");

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

        let info = SessionInfo {
            id: session_id.clone(),
            agent: agent.to_string(),
            role: role.to_string(),
            command: command.to_string(),
            alive: true,
        };

        let metadata = PersistentSession {
            id: session_id.clone(),
            agent: agent.to_string(),
            role: role.to_string(),
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
                &s.agent,
                &s.role,
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
            agent: "claude".to_string(),
            role: "Backend_Engineer".to_string(),
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
            agent: "claude".to_string(),
            role: "Backend_Engineer".to_string(),
            command: "bash".to_string(),
            alive: true,
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