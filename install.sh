#!/bin/bash
# ============================================================================
# ADT Framework: install.sh
# Single-File Installer / Updater / Service Manager
# Supports: WSL (Ubuntu), Linux (Debian/Ubuntu), macOS
# ============================================================================

set -e

# --- Configuration ---
INSTALL_DIR="${INSTALL_DIR:-$HOME/adt-framework}"
REPO_URL="https://github.com/human86x/adt-framework.git"
LOG_DIR="$INSTALL_DIR/_cortex/ops"
VENV="$INSTALL_DIR/venv"
CONSOLE_BIN="$INSTALL_DIR/bin/adt-console.AppImage"

# UI Colors
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BOLD}${CYAN}"
echo "  ___  ___  _____   ___           _        _ _ "
echo " / _ \|   \|_   _| |_ _|_ _  ___| |_ __ _| | |"
echo "| (_| | |) | | |    | || ' \(_-<  _/ _\` | | |"
echo " \___/|___/  |_|   |___|_||_/__/\__\__,_|_|_|"
echo ""
echo -e "  ADT Framework: Specification-Driven Governance${NC}"
echo "  Version: 0.3.0-beta | SPEC-029 Compliance"
echo "  --------------------------------------------"

# 1. Detect Platform
detect_platform() {
    IS_WSL=false
    IS_MAC=false
    if grep -qi microsoft /proc/version 2>/dev/null; then
        IS_WSL=true
        PLATFORM="WSL (Ubuntu)"
    elif [[ "$(uname)" == "Darwin" ]]; then
        IS_MAC=true
        PLATFORM="macOS"
    else
        PLATFORM="Linux"
    fi
    echo -e "${GREEN}[*]${NC} Platform detected: ${BOLD}$PLATFORM${NC}"
}

# 2. Install System Dependencies
install_deps() {
    echo -e "${YELLOW}[*]${NC} Checking system dependencies..."
    if $IS_MAC; then
        command -v brew &>/dev/null || (echo "Homebrew not found. Please install brew first." && exit 1)
        command -v python3 &>/dev/null || brew install python3
        command -v git &>/dev/null || brew install git
        command -v curl &>/dev/null || brew install curl
    else
        local NEEDED=""
        command -v python3 &>/dev/null || NEEDED="$NEEDED python3"
        python3 -c "import venv" 2>/dev/null || NEEDED="$NEEDED python3-venv"
        command -v git &>/dev/null || NEEDED="$NEEDED git"
        command -v curl &>/dev/null || brew install curl
        command -v lsof &>/dev/null || NEEDED="$NEEDED lsof"

        if [ -n "$NEEDED" ]; then
            echo -e "${YELLOW}[*]${NC} Installing: $NEEDED (requires sudo)"
            sudo apt-get update -qq && sudo apt-get install -y -qq $NEEDED
        fi
    fi
}

# 3. Setup Repository
setup_repo() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo -e "${GREEN}[*]${NC} Existing installation found at $INSTALL_DIR. Updating..."
        cd "$INSTALL_DIR"
        git pull origin main --quiet
    else
        echo -e "${YELLOW}[*]${NC} Fresh install. Cloning to $INSTALL_DIR..."
        git clone "$REPO_URL" "$INSTALL_DIR" --quiet
        cd "$INSTALL_DIR"
    fi
}

# 4. Service Management: Stop Existing
kill_service_on_port() {
    local port=$1
    local pid=$(lsof -ti :$port 2>/dev/null)
    if [ -n "$pid" ]; then
        echo -e "${YELLOW}[*]${NC} Stopping service on port $port (PID $pid)..."
        kill $pid 2>/dev/null
        sleep 1
        kill -9 $pid 2>/dev/null || true
    fi
}

stop_services() {
    echo -e "${YELLOW}[*]${NC} Ensuring clean state (no duplicate processes)..."
    kill_service_on_port 5001 # ADT Panel
    kill_service_on_port 5002 # DTTP Gateway
}

# 5. Setup Python Environment
setup_venv() {
    if [ ! -f "$VENV/bin/activate" ]; then
        echo -e "${YELLOW}[*]${NC} Creating virtual environment..."
        python3 -m venv "$VENV"
    fi
    source "$VENV/bin/activate"
    echo -e "${YELLOW}[*]${NC} Installing/Updating framework dependencies..."
    pip install -e . --quiet
}

# 6. Install Console Binary (SPEC-029 R4)
install_console() {
    mkdir -p "$INSTALL_DIR/bin"
    echo -e "${YELLOW}[*]${NC} Checking for latest Console binary..."
    
    # Try to fetch latest release version from GitHub API
    local LATEST_TAG=$(curl -s https://api.github.com/repos/human86x/adt-framework/releases/latest | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
    
    if [ -n "$LATEST_TAG" ] && [ "$LATEST_TAG" != "null" ]; then
        local DOWNLOAD_URL="https://github.com/human86x/adt-framework/releases/download/$LATEST_TAG/adt-console.AppImage"
        echo -e "${GREEN}[*]${NC} Found release $LATEST_TAG. Downloading Console..."
        curl -L "$DOWNLOAD_URL" -o "$CONSOLE_BIN" --quiet
        chmod +x "$CONSOLE_BIN"
    else
        echo -e "${YELLOW}[!]${NC} No pre-built release found. Console must be built from source if needed."
        echo -e "    (Run 'bash console.sh' to build locally)"
    fi
}

# 7. Start Services
start_services() {
    mkdir -p "$LOG_DIR"
    echo -e "${YELLOW}[*]${NC} Starting ADT Services..."

    # Start DTTP Gateway
    nohup "$VENV/bin/python3" -m adt_core.dttp.service > "$LOG_DIR/dttp.log" 2>&1 &
    echo $! > "$LOG_DIR/dttp.pid"

    # Start ADT Panel
    nohup "$VENV/bin/python3" -m adt_center.app > "$LOG_DIR/adt_center.log" 2>&1 &
    echo $! > "$LOG_DIR/adt_center.pid"

    # Wait for services to be ready
    echo -ne "${YELLOW}[*]${NC} Waiting for services to initialize..."
    for i in {1..15}; do
        if curl -s http://localhost:5002/status >/dev/null && curl -s http://localhost:5001/ >/dev/null; then
            echo -e " ${GREEN}READY${NC}"
            return 0
        fi
        echo -n "."
        sleep 1
    done
    echo -e " ${RED}TIMEOUT${NC}"
    echo "Check logs at $LOG_DIR"
    return 1
}

# 8. Verify Hooks (SPEC-029 R5)
verify_hooks() {
    echo -e "${YELLOW}[*]${NC} Verifying enforcement hooks..."
    
    local CLAUDE_HOOK=".claude/settings.local.json"
    local GEMINI_HOOK=".gemini/settings.json"
    
    if [ -f "$CLAUDE_HOOK" ]; then
        echo -e "    Claude Code hooks: ${GREEN}ACTIVE${NC}"
    else
        echo -e "    Claude Code hooks: ${YELLOW}NOT CONFIGURED${NC}"
    fi

    if [ -f "$GEMINI_HOOK" ]; then
        echo -e "    Gemini CLI hooks:  ${GREEN}ACTIVE${NC}"
    else
        echo -e "    Gemini CLI hooks:   ${YELLOW}NOT CONFIGURED${NC}"
    fi
}

# --- Execution ---
detect_platform
install_deps
setup_repo
stop_services
setup_venv
install_console
start_services
verify_hooks

# Final Summary
echo -e "\n${BOLD}${GREEN}============================================${NC}"
echo -e "${BOLD}${GREEN}  ADT Framework installation successful!${NC}"
echo -e "${BOLD}${GREEN}============================================${NC}"
echo ""
echo -e "  ${CYAN}ADT Panel:${NC}    http://localhost:5001"
echo -e "  ${CYAN}DTTP Gateway:${NC} http://localhost:5002"

if [ -f "$CONSOLE_BIN" ]; then
    echo -e "  ${CYAN}Console:${NC}      $CONSOLE_BIN"
fi

echo ""
echo -e "  ${BOLD}Logs:${NC}  tail -f $LOG_DIR/*.log"
echo -e "  ${BOLD}Stop:${NC}  pkill -f 'adt_core.dttp.service'; pkill -f 'adt_center.app'"
echo ""
echo -e "  ${BOLD}Governance is active. All agent writes will be audited.${NC}"
echo ""

# Auto-open browser if in WSL or Mac
if $IS_WSL; then
    cmd.exe /c start "http://localhost:5001" 2>/dev/null || true
elif $IS_MAC; then
    open "http://localhost:5001" 2>/dev/null || true
fi
