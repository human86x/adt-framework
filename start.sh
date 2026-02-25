#!/bin/bash
# ADT Framework Unified Starter
# Launches both DTTP Enforcement Service and Operational Center UI

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_ROOT/_cortex/ops"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python3"

mkdir -p "$LOG_DIR"

# Wait for a service to become healthy (up to 15 seconds)
wait_for_service() {
    local url="$1"
    local name="$2"
    local max_attempts=15
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo "    [$name ready]"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    echo "    [WARNING: $name not responding after ${max_attempts}s -- check $LOG_DIR]"
    return 1
}

echo "--- ADT Framework Activation ---"

# Detect production mode (SPEC-027): explicit flag file + agent/dttp OS users
PRODUCTION_MODE=false
if [ -f "$HOME/.adt/production_mode" ] && id -u agent &>/dev/null && id -u dttp &>/dev/null; then
    PRODUCTION_MODE=true
    echo "[*] Production mode detected (Shatterglass active)"
fi

# 1. Start DTTP Service (:5002)
if curl -s http://localhost:5002/status > /dev/null; then
    echo "[!] DTTP Service already running."
else
    echo "[+] Starting DTTP Enforcement Service (:5002)..."
    if $PRODUCTION_MODE; then
        echo "    (running as OS user 'dttp')"
        nohup sudo -u dttp "$VENV_PYTHON" -m adt_core.dttp.service > "$LOG_DIR/dttp.log" 2>&1 &
    else
        nohup "$VENV_PYTHON" -m adt_core.dttp.service > "$LOG_DIR/dttp.log" 2>&1 &
    fi
    wait_for_service "http://localhost:5002/status" "DTTP"
fi

# 2. Start Operational Center (:5001)
if curl -s http://localhost:5001/ > /dev/null; then
    echo "[!] Operational Center already running."
else
    echo "[+] Starting Operational Center UI (:5001)..."
    nohup "$VENV_PYTHON" -m adt_center.app > "$LOG_DIR/adt_center.log" 2>&1 &
    wait_for_service "http://localhost:5001/" "ADT Panel"
fi

# 3. Start Operator Console (Tauri)
echo "[+] Starting ADT Operator Console (Tauri)..."
CONSOLE_BIN="$PROJECT_ROOT/adt-console/src-tauri/target/release/adt-console"
if [ ! -x "$CONSOLE_BIN" ]; then
    CONSOLE_BIN="$PROJECT_ROOT/adt-console/src-tauri/target/debug/adt-console"
fi
if [ -x "$CONSOLE_BIN" ]; then
    GDK_BACKEND=x11 WEBKIT_DISABLE_COMPOSITING_MODE=1 "$CONSOLE_BIN" > "$LOG_DIR/console.log" 2>&1 &
else
    echo "[!] Console binary not found. Build with: cd adt-console && cargo tauri build"
fi

echo "--------------------------------"
echo "Services active:"
echo "  - DTTP Gateway: http://localhost:5002"
echo "  - ADT Panel:    http://localhost:5001"
echo ""
echo "Monitoring logs:"
echo "  tail -f _cortex/ops/*.log"
echo "--------------------------------"
