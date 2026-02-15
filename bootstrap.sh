#!/bin/bash
# ============================================================================
# ADT Framework Bootstrap
# One command to experience the governance framework
#
# Usage:  bash bootstrap.sh
# Works:  WSL (Ubuntu), Linux, macOS
# ============================================================================

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_ROOT/venv"
LOG_DIR="$PROJECT_ROOT/_cortex/ops"

echo -e "${BOLD}${CYAN}"
echo "  ___  ___  _____   ___                                    _   "
echo " / _ \|   \|_   _| | __| _ __ _ _ __  _____ __ _____ _ _| |__"
echo "| (_| | |) | | |   | _| '_/ _\` | '  \/ -_) V  V / _ \ '_| / /"
echo " \___/|___/  |_|   |_||_| \__,_|_|_|_\___|\_/\_/\___/_| |_\_\\"
echo ""
echo -e "  Governance-Native AI Agent Management${NC}"
echo ""

# -------------------------------------------------------------------
# 1. Detect platform
# -------------------------------------------------------------------
IS_WSL=false
IS_MAC=false

if grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
    echo -e "${GREEN}[+]${NC} Platform: Windows Subsystem for Linux (WSL)"
elif [[ "$(uname)" == "Darwin" ]]; then
    IS_MAC=true
    echo -e "${GREEN}[+]${NC} Platform: macOS"
else
    echo -e "${GREEN}[+]${NC} Platform: Linux"
fi

# -------------------------------------------------------------------
# 2. Install system dependencies
# -------------------------------------------------------------------
install_deps() {
    if $IS_MAC; then
        if ! command -v python3 &>/dev/null; then
            echo -e "${YELLOW}[*]${NC} Installing Python 3 via Homebrew..."
            brew install python3
        fi
    else
        local NEEDED=""
        command -v python3 &>/dev/null || NEEDED="python3"
        python3 -c "import venv" 2>/dev/null || NEEDED="$NEEDED python3-venv"
        command -v pip3 &>/dev/null || python3 -c "import pip" 2>/dev/null || NEEDED="$NEEDED python3-pip"
        command -v curl &>/dev/null || NEEDED="$NEEDED curl"

        if [ -n "$NEEDED" ]; then
            echo -e "${YELLOW}[*]${NC} Installing system packages:${BOLD} $NEEDED${NC}"
            sudo apt-get update -qq && sudo apt-get install -y -qq $NEEDED
        fi
    fi
    echo -e "${GREEN}[+]${NC} Python $(python3 --version 2>&1 | cut -d' ' -f2) ready"
}

install_deps

# -------------------------------------------------------------------
# 3. Create virtual environment
# -------------------------------------------------------------------
if [ ! -f "$VENV/bin/activate" ]; then
    echo -e "${YELLOW}[*]${NC} Creating virtual environment..."
    python3 -m venv "$VENV"
    echo -e "${GREEN}[+]${NC} Virtual environment created"
else
    echo -e "${GREEN}[+]${NC} Virtual environment exists"
fi

source "$VENV/bin/activate"

# -------------------------------------------------------------------
# 4. Install framework
# -------------------------------------------------------------------
echo -e "${YELLOW}[*]${NC} Installing ADT Framework..."
pip install -e "$PROJECT_ROOT" --quiet 2>&1 | tail -1
echo -e "${GREEN}[+]${NC} ADT Framework installed"

# -------------------------------------------------------------------
# 5. Start services
# -------------------------------------------------------------------
mkdir -p "$LOG_DIR"

# DTTP Enforcement Service (:5002)
if curl -s http://localhost:5002/status > /dev/null 2>&1; then
    echo -e "${GREEN}[+]${NC} DTTP Service already running on :5002"
else
    echo -e "${YELLOW}[*]${NC} Starting DTTP Enforcement Service..."
    nohup "$VENV/bin/python3" -m adt_core.dttp.service > "$LOG_DIR/dttp.log" 2>&1 &
    DTTP_PID=$!

    # Wait for healthy
    for i in $(seq 1 15); do
        if curl -s http://localhost:5002/status > /dev/null 2>&1; then
            echo -e "${GREEN}[+]${NC} DTTP Service running on :5002 (PID $DTTP_PID)"
            break
        fi
        sleep 1
    done
fi

# ADT Operational Center (:5001)
if curl -s http://localhost:5001/ > /dev/null 2>&1; then
    echo -e "${GREEN}[+]${NC} ADT Panel already running on :5001"
else
    echo -e "${YELLOW}[*]${NC} Starting ADT Operational Center..."
    nohup "$VENV/bin/python3" -m adt_center.app > "$LOG_DIR/adt_center.log" 2>&1 &
    PANEL_PID=$!

    for i in $(seq 1 15); do
        if curl -s http://localhost:5001/ > /dev/null 2>&1; then
            echo -e "${GREEN}[+]${NC} ADT Panel running on :5001 (PID $PANEL_PID)"
            break
        fi
        sleep 1
    done
fi

# -------------------------------------------------------------------
# 6. Verify
# -------------------------------------------------------------------
echo ""
DTTP_OK=false
PANEL_OK=false

if curl -s http://localhost:5002/status > /dev/null 2>&1; then
    DTTP_OK=true
fi
if curl -s http://localhost:5001/ > /dev/null 2>&1; then
    PANEL_OK=true
fi

if $DTTP_OK && $PANEL_OK; then
    echo -e "${GREEN}${BOLD}============================================${NC}"
    echo -e "${GREEN}${BOLD}  ADT Framework is running!${NC}"
    echo -e "${GREEN}${BOLD}============================================${NC}"
    echo ""
    echo -e "  ${CYAN}ADT Panel:${NC}    http://localhost:5001"
    echo -e "  ${CYAN}DTTP Gateway:${NC} http://localhost:5002"
    echo ""
    echo -e "  ${BOLD}What you can do:${NC}"
    echo -e "    - View all specs, tasks, and ADS audit trail"
    echo -e "    - Monitor DTTP enforcement decisions"
    echo -e "    - Create new specs (Specs page)"
    echo -e "    - Submit feedback (Dashboard)"
    echo ""
    echo -e "  ${BOLD}To sync your contributions:${NC}"
    echo -e "    git add _cortex/ && git commit -m 'Paul: new spec' && git push"
    echo ""
    echo -e "  ${BOLD}Logs:${NC}  tail -f _cortex/ops/*.log"
    echo -e "  ${BOLD}Stop:${NC}  pkill -f 'adt_core.dttp.service'; pkill -f 'adt_center.app'"
    echo ""

    # Try to open browser
    URL="http://localhost:5001"
    if $IS_WSL; then
        # WSL: use Windows browser
        cmd.exe /c start "$URL" 2>/dev/null || explorer.exe "$URL" 2>/dev/null || true
    elif $IS_MAC; then
        open "$URL" 2>/dev/null || true
    else
        xdg-open "$URL" 2>/dev/null || true
    fi
else
    echo -e "${RED}${BOLD}[!] Something went wrong.${NC}"
    $DTTP_OK || echo -e "${RED}    DTTP Service failed to start. Check: $LOG_DIR/dttp.log${NC}"
    $PANEL_OK || echo -e "${RED}    ADT Panel failed to start. Check: $LOG_DIR/adt_center.log${NC}"
    exit 1
fi
