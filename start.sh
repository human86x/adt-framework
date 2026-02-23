#!/bin/bash
# ADT Framework Unified Starter
# Launches both DTTP Enforcement Service and Operational Center UI

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_ROOT/_cortex/ops"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python3"

mkdir -p "$LOG_DIR"

echo "--- ADT Framework Activation ---"

# Detect production mode (SPEC-027): agent and dttp OS users exist
PRODUCTION_MODE=false
if id -u agent &>/dev/null && id -u dttp &>/dev/null; then
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
    sleep 2
fi

# 2. Start Operational Center (:5001)
if curl -s http://localhost:5001/ > /dev/null; then
    echo "[!] Operational Center already running."
else
    echo "[+] Starting Operational Center UI (:5001)..."
    nohup "$VENV_PYTHON" -m adt_center.app > "$LOG_DIR/adt_center.log" 2>&1 &
    sleep 2
fi

# 3. Start Operator Console (Tauri)
echo "[+] Starting ADT Operator Console (Tauri)..."
# We run this in the background and dont wait for it
"$PROJECT_ROOT/adt-console/src-tauri/target/release/adt-console" > "$LOG_DIR/console.log" 2>&1 &

echo "--------------------------------"
echo "Services active:"
echo "  - DTTP Gateway: http://localhost:5002"
echo "  - ADT Panel:    http://localhost:5001"
echo ""
echo "Monitoring logs:"
echo "  tail -f _cortex/ops/*.log"
echo "--------------------------------"
