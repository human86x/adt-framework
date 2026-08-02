#!/bin/bash
# ADT Framework Unified Starter
# Launches both DTCP Enforcement Service and Operational Center UI

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_ROOT/_cortex/ops"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python3"

mkdir -p "$LOG_DIR"

# Wait for a service to become healthy (up to 15 seconds)
wait_for_service() {
    local url="$1"
    local name="$2"
    local max_attempts=60
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

# 1. Start DTCP Service (:$DTCP_PORT — default 5002; WSL uses 5003 via env)
DTCP_PORT="${DTCP_PORT:-5002}"
if curl -s "http://localhost:${DTCP_PORT}/status" > /dev/null; then
    echo "[!] DTCP Service already running."
else
    echo "[+] Starting DTCP Enforcement Service (:${DTCP_PORT})..."
    if $PRODUCTION_MODE; then
        echo "    (running as OS user 'dttp')"
        nohup sudo -u dttp "$VENV_PYTHON" -m adt_core.dtcp.service > "$LOG_DIR/dtcp.log" 2>&1 &
    else
        nohup "$VENV_PYTHON" -m adt_core.dtcp.service > "$LOG_DIR/dtcp.log" 2>&1 &
    fi
    wait_for_service "http://localhost:${DTCP_PORT}/status" "DTCP"
fi

# 2. Start Operational Center (:5001)
if curl -s http://localhost:5001/ > /dev/null; then
    echo "[!] Operational Center already running."
else
    echo "[+] Starting Operational Center UI (:5001)..."
    DISPLAY=:0 nohup "$VENV_PYTHON" -m adt_center.app > "$LOG_DIR/adt_center.log" 2>&1 &
    wait_for_service "http://localhost:5001/" "ADT Panel"
fi

# 3. Start Operator Console (Tauri)
echo "[+] Starting ADT Operator Console (Tauri)..."
CONSOLE_BIN=""
# Find candidates and pick the one with the latest modification time
RELEASE_BIN="$PROJECT_ROOT/adt-console/src-tauri/target/release/adt-console"
DEBUG_BIN="$PROJECT_ROOT/adt-console/src-tauri/target/debug/adt-console"
APPIMAGE_BIN="$PROJECT_ROOT/bin/adt-console.AppImage"
SYSTEM_BIN="$(which adt-console 2>/dev/null || true)"

if [ -x "$RELEASE_BIN" ] && [ -x "$DEBUG_BIN" ]; then
    if [ "$RELEASE_BIN" -nt "$DEBUG_BIN" ]; then
        CONSOLE_BIN="$RELEASE_BIN"
    else
        CONSOLE_BIN="$DEBUG_BIN"
    fi
elif [ -x "$RELEASE_BIN" ]; then
    CONSOLE_BIN="$RELEASE_BIN"
elif [ -x "$DEBUG_BIN" ]; then
    CONSOLE_BIN="$DEBUG_BIN"
elif [ -x "$APPIMAGE_BIN" ]; then
    CONSOLE_BIN="$APPIMAGE_BIN"
elif [ -n "$SYSTEM_BIN" ] && [ -x "$SYSTEM_BIN" ]; then
    CONSOLE_BIN="$SYSTEM_BIN"
fi

if [ -n "$CONSOLE_BIN" ]; then
    echo "    Using: $CONSOLE_BIN"
    "$CONSOLE_BIN" > "$LOG_DIR/console.log" 2>&1 &
else
    echo "[!] Console binary not found. Run 'bash install.sh' or 'bash console.sh' to install."
fi

echo "--------------------------------"
echo "Services active:"
echo "  - DTCP Gateway: http://localhost:${DTCP_PORT}"
echo "  - ADT Panel:    http://localhost:5001"
echo ""
echo "Monitoring logs:"
echo "  tail -f _cortex/ops/*.log"
echo "--------------------------------"
