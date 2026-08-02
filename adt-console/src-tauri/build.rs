use std::fs::{read_to_string, File};
use std::io::Write;
use std::path::Path;

fn main() {
    // Build timestamp: local time WITH timezone offset (%z gives e.g. +0100).
    // Chrono's %:z would print +01:00; %z is more compact. User complained about
    // seeing UTC when their clock read 22:50 local — this fixes that.
    let build_time = chrono::Local::now()
        .format("%Y-%m-%d %H:%M %z")
        .to_string();
    let build_time_path = Path::new("../src/build_time.txt");
    let mut ft = File::create(&build_time_path).unwrap();
    ft.write_all(build_time.as_bytes()).unwrap();

    // Version: parse tauri.conf.json so the frontend header never drifts from
    // the actual bundled version. Cheap substring extract — no serde dep in
    // build-deps.
    let version = read_to_string("tauri.conf.json")
        .ok()
        .and_then(|s| {
            let key = "\"version\":";
            let i = s.find(key)?;
            let rest = &s[i + key.len()..];
            let start = rest.find('"')? + 1;
            let end = rest[start..].find('"')?;
            Some(rest[start..start + end].to_string())
        })
        .unwrap_or_else(|| "unknown".to_string());
    let version_path = Path::new("../src/version.txt");
    let mut fv = File::create(&version_path).unwrap();
    fv.write_all(version.as_bytes()).unwrap();

    // Rerun if the version bumps in tauri.conf.json.
    println!("cargo:rerun-if-changed=tauri.conf.json");

    tauri_build::build()
}
