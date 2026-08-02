// ADT Operator Console — Tauri entry point
// SPEC-021: Human command center for multi-agent governance

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    adt_console::run();
}
