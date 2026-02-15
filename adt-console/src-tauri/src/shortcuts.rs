// Global keyboard shortcuts — OS-level hotkeys for session switching
// SPEC-021 Phase C: Register global shortcuts that work from any application

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::{AppHandle, Emitter, Manager, Runtime};
use tauri_plugin_global_shortcut::GlobalShortcutExt;

/// Keybinding configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KeybindingsConfig {
    /// Bring console to front
    #[serde(default = "default_show_console")]
    pub show_console: String,
    /// Switch to session slot 1-5
    #[serde(default = "default_session_slots")]
    pub session_slots: Vec<String>,
}

fn default_show_console() -> String {
    "Ctrl+Shift+KeyA".to_string()
}

fn default_session_slots() -> Vec<String> {
    vec![
        "Ctrl+Shift+Digit1".to_string(),
        "Ctrl+Shift+Digit2".to_string(),
        "Ctrl+Shift+Digit3".to_string(),
        "Ctrl+Shift+Digit4".to_string(),
        "Ctrl+Shift+Digit5".to_string(),
    ]
}

impl Default for KeybindingsConfig {
    fn default() -> Self {
        Self {
            show_console: default_show_console(),
            session_slots: default_session_slots(),
        }
    }
}

/// Load keybindings from ~/.adt/console/keybindings.json or use defaults
pub fn load_keybindings() -> KeybindingsConfig {
    let config_path = keybindings_path();
    if config_path.exists() {
        match fs::read_to_string(&config_path) {
            Ok(content) => {
                match serde_json::from_str(&content) {
                    Ok(config) => {
                        log::info!("Loaded keybindings from {:?}", config_path);
                        return config;
                    }
                    Err(e) => {
                        log::warn!("Failed to parse keybindings: {}, using defaults", e);
                    }
                }
            }
            Err(e) => {
                log::warn!("Failed to read keybindings file: {}, using defaults", e);
            }
        }
    }
    KeybindingsConfig::default()
}

fn keybindings_path() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".adt")
        .join("console")
        .join("keybindings.json")
}

/// Register all global shortcuts
pub fn register_shortcuts<R: Runtime>(app: &AppHandle<R>) -> Result<(), Box<dyn std::error::Error>> {
    let config = load_keybindings();

    // Register "show console" shortcut
    let show_app = app.clone();
    app.global_shortcut().on_shortcut(
        config.show_console.as_str(),
        move |_app, _shortcut, _event| {
            if let Some(window) = show_app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        },
    )?;
    log::info!("Registered global shortcut: show_console = {}", config.show_console);

    // Register session slot shortcuts (1-5)
    for (idx, shortcut_str) in config.session_slots.iter().enumerate() {
        let slot = idx + 1;
        let slot_app = app.clone();

        match app.global_shortcut().on_shortcut(
            shortcut_str.as_str(),
            move |_app, _shortcut, _event| {
                if let Some(window) = slot_app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                    let _ = slot_app.emit("global-switch-session", slot as u32);
                }
            },
        ) {
            Ok(()) => {
                log::info!("Registered global shortcut: session slot {} = {}", slot, shortcut_str);
            }
            Err(e) => {
                log::warn!("Failed to register shortcut '{}': {}", shortcut_str, e);
            }
        }
    }

    log::info!("Global shortcuts registered successfully");
    Ok(())
}

/// Write default keybindings config file if it doesn't exist
pub fn ensure_default_config() {
    let config_path = keybindings_path();
    if !config_path.exists() {
        if let Some(parent) = config_path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        let default = KeybindingsConfig::default();
        if let Ok(json) = serde_json::to_string_pretty(&default) {
            let _ = fs::write(&config_path, json);
            log::info!("Created default keybindings at {:?}", config_path);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_keybindings() {
        let config = KeybindingsConfig::default();
        assert_eq!(config.show_console, "Ctrl+Shift+KeyA");
        assert_eq!(config.session_slots.len(), 5);
        assert_eq!(config.session_slots[0], "Ctrl+Shift+Digit1");
    }

    #[test]
    fn test_keybindings_serde() {
        let config = KeybindingsConfig::default();
        let json = serde_json::to_string(&config).unwrap();
        let decoded: KeybindingsConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(config.show_console, decoded.show_console);
    }
}
