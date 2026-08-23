pub mod ipc;
pub mod pty;
pub mod shim;
pub mod shortcuts;
pub mod tray;
pub mod watcher;

use std::sync::Arc;
use tauri::Manager;

pub fn run() {
    // Default to `info` level when RUST_LOG is unset so PTY spawn diagnostics
    // land in ~/console.log without the operator having to set an env var.
    // RUST_LOG (if present) still wins — parse_default_env respects it.
    env_logger::Builder::from_env(
        env_logger::Env::default().default_filter_or("info"),
    )
    .init();

    // Initialize PTY manager
    let pty_manager = Arc::new(pty::PtyManager::new());

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .manage(pty_manager.clone())
        .setup(move |app| {
            let handle = app.handle();

            // Restore previous sessions
            pty_manager.restore_sessions(handle.clone());

            // Start SPEC-053 Shim Server
            let shim_server = shim::ShimServer::new(pty_manager.clone());
            shim_server.start();

            // Setup system tray
            if let Err(e) = tray::setup_tray(handle) {
                log::error!("System tray setup failed: {}", e);
            }

            // Register global keyboard shortcuts
            shortcuts::ensure_default_config();
            if let Err(e) = shortcuts::register_shortcuts(handle) {
                log::error!("Global shortcuts registration failed: {}", e);
            }

            // Start file watcher for ADS events
            if let Err(e) = watcher::start_watchers(handle.clone()) {
                log::error!("File watcher failed: {}", e);
            }

            // ADT_DEV_URL: point webview at a local file server instead of
            // embedded assets so frontend changes don't require a Cargo rebuild.
            // Usage: ADT_DEV_URL=http://localhost:8080 ./adt-console
            if let Ok(dev_url) = std::env::var("ADT_DEV_URL") {
                if let Some(win) = app.get_webview_window("main") {
                    if let Ok(url) = dev_url.parse() {
                        let _ = win.navigate(url);
                    }
                }
            }

            log::info!("ADT Console initialized");
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            ipc::create_session,
            ipc::spawn_child_session,
            ipc::spawn_orchestrator_session,
            ipc::close_session,
            ipc::write_to_session,
            ipc::inject_pty_command,
            ipc::resize_session,
            ipc::replay_session_output,
            ipc::list_sessions,
            ipc::update_tray_status,
            ipc::send_notification,
            ipc::read_project_file,
            ipc::toggle_autostart,
            ipc::init_project,
            ipc::list_projects,
            ipc::start_project_dtcp,
            ipc::stop_project_dtcp,
            ipc::get_production_mode,
            ipc::enable_production_mode,
            ipc::disable_production_mode,
            ipc::list_agy_models,
            ipc::detect_project_launch,
            ipc::launch_project,
            ipc::get_dev_mode,
            ipc::set_dev_mode,
        ])
        .run(tauri::generate_context!())
        .expect("error running ADT Console");
}
