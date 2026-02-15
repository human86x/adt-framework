// File system watchers — live ADS event monitoring
// SPEC-021: notify-based watchers for governance data files

use notify::{Config, Event, EventKind, RecommendedWatcher, RecursiveMode, Watcher};
use std::path::Path;
use std::sync::mpsc;
use tauri::{Emitter, Runtime};

pub fn start_watchers<R: Runtime>(app_handle: tauri::AppHandle<R>) -> Result<(), Box<dyn std::error::Error>> {
    let (tx, rx) = mpsc::channel();

    let mut watcher = RecommendedWatcher::new(tx, Config::default())?;

    // Watch _cortex/ for ADS events, task changes, phase updates
    let cortex_path = Path::new("_cortex");
    if cortex_path.exists() {
        watcher.watch(cortex_path, RecursiveMode::Recursive)?;
        log::info!("Watching _cortex/ for governance data changes");
    } else {
        log::warn!("_cortex/ path not found, watcher standing by");
    }

    // Move watcher into a long-lived container or just forget it so it doesn't drop
    // In a thread, we just need to keep it in scope.
    
    // Process events in a loop
    std::thread::spawn(move || {
        // Keep watcher alive by moving it into this closure
        let _keep_alive = watcher;
        
        loop {
            match rx.recv() {
                Ok(Ok(event)) => {
                    handle_fs_event(&app_handle, &event);
                }
                Ok(Err(e)) => {
                    log::error!("Watch error: {}", e);
                }
                Err(e) => {
                    log::error!("Channel error: {}", e);
                    break;
                }
            }
        }
    });

    Ok(())
}

fn handle_fs_event<R: Runtime>(app_handle: &tauri::AppHandle<R>, event: &Event) {
    let paths: Vec<String> = event
        .paths
        .iter()
        .filter_map(|p| p.to_str().map(String::from))
        .collect();

    match &event.kind {
        EventKind::Modify(_) | EventKind::Create(_) => {
            for path in &paths {
                if path.ends_with("events.jsonl") {
                    let _ = app_handle.emit("ads-updated", path.clone());
                } else if path.ends_with("tasks.json") {
                    let _ = app_handle.emit("tasks-updated", path.clone());
                } else if path.ends_with("requests.md") {
                    let _ = app_handle.emit("requests-updated", path.clone());
                } else if path.ends_with("phases.json") {
                    let _ = app_handle.emit("phases-updated", path.clone());
                }
            }
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tauri::test::{mock_builder, mock_context, noop_assets};
    use notify::event::{EventKind, ModifyKind};
    use std::path::PathBuf;

    #[test]
    fn test_handle_ads_update_event() {
        let app = mock_builder().build(mock_context(noop_assets())).unwrap();
        let handle = app.handle();
        
        let event = Event {
            kind: EventKind::Modify(ModifyKind::Data(notify::event::DataChange::Content)),
            paths: vec![PathBuf::from("_cortex/ads/events.jsonl")],
            attrs: Default::default(),
        };
        
        // This just verifies it doesn't crash. 
        // In a real integration test we'd listen for the emit.
        handle_fs_event(handle, &event);
    }

    #[test]
    fn test_handle_tasks_update_event() {
        let app = mock_builder().build(mock_context(noop_assets())).unwrap();
        let handle = app.handle();
        
        let event = Event {
            kind: EventKind::Create(notify::event::CreateKind::File),
            paths: vec![PathBuf::from("_cortex/tasks.json")],
            attrs: Default::default(),
        };
        
        handle_fs_event(handle, &event);
    }
}
