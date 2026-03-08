#!/bin/bash
# ADT Operator Console Starter
# Runs the Tauri desktop application in development mode

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
CONSOLE_DIR="$PROJECT_ROOT/adt-console"
LOG_FILE="$PROJECT_ROOT/_cortex/ops/console.log"

echo "--- ADT Operator Console Activation ---"
BINARY="$CONSOLE_DIR/src-tauri/target/debug/adt-console"

if [ -f "$BINARY" ]; then
    echo "[+] Running compiled binary..."
    RUST_LOG=info "$BINARY"
else
    echo "[+] Starting Tauri dev environment..."
    cd "$CONSOLE_DIR" && RUST_LOG=info cargo tauri dev
fi

echo "---------------------------------------"
echo "The Console window will appear shortly."
echo "Note: First run may take a few minutes to compile Rust dependencies."
echo "---------------------------------------"
