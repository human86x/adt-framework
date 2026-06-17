use std::io::Write;
use std::fs::File;
use std::path::Path;

fn main() {
    let build_time = chrono::Utc::now().format("%Y-%m-%d %H:%M:%S UTC").to_string();
    let dest_path = Path::new("../src/build_time.txt");
    let mut f = File::create(&dest_path).unwrap();
    f.write_all(build_time.as_bytes()).unwrap();

    tauri_build::build()
}