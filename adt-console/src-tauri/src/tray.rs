// System tray management — status indicator and menu
// SPEC-021 Phase C: Tray icon with session status colors and quick actions

use tauri::{Runtime, 
    image::Image,
    menu::{MenuBuilder, MenuItemBuilder, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager,
};

/// Tray status states matching SPEC-021 Section 6.1
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TrayStatus {
    /// All sessions nominal
    Nominal,
    /// Pending escalation or warning
    Warning,
    /// Unresolved denial or error
    Error,
    /// No active sessions
    Idle,
}

/// Generate a solid-color icon (16x16 RGBA) for the given status
fn status_icon(status: TrayStatus) -> Image<'static> {
    let (r, g, b) = match status {
        TrayStatus::Nominal => (76, 175, 80),    // green
        TrayStatus::Warning => (255, 193, 7),     // yellow
        TrayStatus::Error => (244, 67, 54),       // red
        TrayStatus::Idle => (158, 158, 158),      // grey
    };

    // 16x16 RGBA bitmap — filled circle on transparent background
    let size: u32 = 16;
    let mut rgba = vec![0u8; (size * size * 4) as usize];
    let center = size as f32 / 2.0;
    let radius = center - 1.0;

    for y in 0..size {
        for x in 0..size {
            let dx = x as f32 - center + 0.5;
            let dy = y as f32 - center + 0.5;
            let dist = (dx * dx + dy * dy).sqrt();
            let idx = ((y * size + x) * 4) as usize;

            if dist <= radius {
                rgba[idx] = r;
                rgba[idx + 1] = g;
                rgba[idx + 2] = b;
                rgba[idx + 3] = 255;
            }
        }
    }

    Image::new_owned(rgba, size, size)
}

/// Initialize the system tray with menu and event handlers
pub fn setup_tray<R: Runtime>(app: &AppHandle<R>) -> Result<(), Box<dyn std::error::Error>> {
    let show_item = MenuItemBuilder::with_id("show", "Show Console")
        .build(app)?;
    let hide_item = MenuItemBuilder::with_id("hide", "Hide Console")
        .build(app)?;
    let new_session_item = MenuItemBuilder::with_id("new_session", "New Session...")
        .build(app)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit_item = MenuItemBuilder::with_id("quit", "Quit ADT Console")
        .build(app)?;

    let menu = MenuBuilder::new(app)
        .items(&[
            &show_item,
            &hide_item,
            &separator,
            &new_session_item,
            &PredefinedMenuItem::separator(app)?,
            &quit_item,
        ])
        .build()?;

    let icon = status_icon(TrayStatus::Idle);

    let _tray = TrayIconBuilder::new()
        .icon(icon)
        .tooltip("ADT Console — No active sessions")
        .menu(&menu)
        .on_menu_event(move |app, event| {
            match event.id().as_ref() {
                "show" => {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
                "hide" => {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.hide();
                    }
                }
                "new_session" => {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                        let _ = app.emit("tray-new-session", ());
                    }
                }
                "quit" => {
                    app.exit(0);
                }
                _ => {}
            }
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
        })
        .build(app)?;

    log::info!("System tray initialized");
    Ok(())
}

/// Update tray icon and tooltip based on session status
pub fn update_tray_status<R: Runtime>(app: &AppHandle<R>, status: TrayStatus, session_count: u32, escalations: u32) {
    if let Some(tray) = app.tray_by_id("main") {
        let icon = status_icon(status);
        let _ = tray.set_icon(Some(icon));

        let tooltip = match status {
            TrayStatus::Nominal => format!("ADT Console — {} session(s)", session_count),
            TrayStatus::Warning => format!("ADT Console — {} escalation(s) pending", escalations),
            TrayStatus::Error => format!("ADT Console — {} denial(s) unresolved", escalations),
            TrayStatus::Idle => "ADT Console — No active sessions".to_string(),
        };
        let _ = tray.set_tooltip(Some(&tooltip));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_status_icon_creation() {
        let icon = status_icon(TrayStatus::Nominal);
        assert_eq!(icon.width(), 16);
        assert_eq!(icon.height(), 16);
        assert!(icon.rgba().len() > 0);
    }
    
    #[test]
    fn test_tray_status_enum() {
        assert_ne!(TrayStatus::Nominal, TrayStatus::Error);
        assert_eq!(TrayStatus::Idle, TrayStatus::Idle);
    }
}
