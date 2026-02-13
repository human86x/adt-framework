// ADT Operator Console — Tauri entry point
// SPEC-021: Human command center for multi-agent governance

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use adt_console::{ipc, pty, shortcuts, tray, watcher};
use tauri::Manager;

fn main() {
    env_logger::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            let handle = app.handle().clone();

            // Initialize PTY manager
            let pty_manager = pty::PtyManager::new();
            app.manage(pty_manager);

            // Setup system tray
            if let Err(e) = tray::setup_tray(&handle) {
                log::error!("System tray setup failed: {}", e);
            }

            // Register global keyboard shortcuts
            shortcuts::ensure_default_config();
            if let Err(e) = shortcuts::register_shortcuts(&handle) {
                log::error!("Global shortcuts registration failed: {}", e);
            }

            // Start file watcher for ADS events
            let watcher_handle = handle.clone();
            if let Err(e) = watcher::start_watchers(watcher_handle) {
                log::error!("File watcher failed: {}", e);
            }

            // Restore previous sessions
            pty_manager.restore_sessions(handle.clone());

            log::info!("ADT Console initialized");
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            ipc::create_session,
            ipc::close_session,
            ipc::write_to_session,
            ipc::resize_session,
            ipc::list_sessions,
            ipc::update_tray_status,
            ipc::send_notification,
            ipc::read_project_file,
            ipc::toggle_autostart,
        ])
        .run(tauri::generate_context!())
        .expect("error running ADT Console");
}
