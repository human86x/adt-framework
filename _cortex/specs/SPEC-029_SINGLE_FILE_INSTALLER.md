# SPEC-029: Single-File WSL/Linux Installer

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE)
**Created:** 2026-02-15
**Origin:** ADT Framework (human request -- distribution to collaborator Paul)

## Problem

The ADT Framework has three runtime components that must work together:
1. **DTTP Enforcement Service** (Python Flask on :5002)
2. **ADT Operational Panel** (Python Flask on :5001)
3. **ADT Operator Console** (Tauri desktop app)

Plus enforcement hooks that wire into Claude Code and Gemini CLI.

Currently, setup requires: clone repo, run bootstrap.sh, build Tauri from source (30+ min Rust compile). No mechanism to update an existing installation without creating duplicate service processes.

## Solution

A single bash script (`install.sh`) that Paul (or any collaborator) downloads and runs. It handles full lifecycle: fresh install, update, and service management.

```
curl -fsSL https://raw.githubusercontent.com/<repo>/main/install.sh | bash
```

Or: Paul receives the file directly, runs `bash install.sh`.

## Requirements

### R1: Self-Contained
- Single bash file, no dependencies beyond standard WSL/Linux tools (bash, curl, git)
- Installs its own prerequisites (Python3, pip, venv)

### R2: Idempotent (Install or Update)
- Detects existing installation at `~/adt-framework` (configurable)
- If repo exists: `git pull` instead of `git clone`
- If venv exists: reuse it, run `pip install -e .` to update
- If DTTP is running on :5002: stop it before restarting
- If Panel is running on :5001: stop it before restarting
- If Console AppImage exists: replace with latest version
- Never creates duplicate service processes

### R3: Service Management
- Detect running services by port (lsof/ss on :5001/:5002)
- Kill existing service processes cleanly before restart
- Start services in background with log files
- PID files at `$INSTALL_DIR/_cortex/ops/` for tracking

### R4: Console Binary Distribution
- Download pre-built AppImage from GitHub Releases (latest)
- If no release exists, skip Console with informational message
- Make AppImage executable, place in `$INSTALL_DIR/bin/`

### R5: Hook Awareness
- Hooks are already in the repo (`.claude/settings.local.json`, `.gemini/settings.json`)
- Print status: "Claude Code hooks: ACTIVE" / "Gemini CLI hooks: ACTIVE"
- Verify DTTP is reachable from hook perspective (curl localhost:5002/status)

### R6: Platform Detection
- Primary target: WSL (Ubuntu)
- Also support: native Linux (Debian/Ubuntu), macOS
- Detect platform and adapt package manager (apt vs brew)
- WSL-specific: use `cmd.exe /c start` for browser, detect Windows paths

### R7: Clear Output
- ASCII banner
- Step-by-step progress with color-coded status
- Final summary: all URLs, service PIDs, hook status, what to do next
- On error: clear message about what failed and how to fix

## Architecture

```
install.sh (single file)
  |
  +-- detect_platform()      # WSL / Linux / macOS
  +-- install_system_deps()  # python3, pip, venv, git, curl
  +-- setup_repo()           # clone or pull
  +-- setup_venv()           # create or reuse venv, pip install
  +-- stop_services()        # kill existing DTTP/Panel by port
  +-- start_services()       # launch DTTP + Panel with PID files
  +-- install_console()      # download AppImage from GitHub Releases
  +-- verify_hooks()         # check .claude/ and .gemini/ configs exist
  +-- print_summary()        # URLs, PIDs, hook status, next steps
```

## Service Detection Logic

```bash
# Find and kill existing service on port
kill_service_on_port() {
    local port=$1
    local pid=$(lsof -ti :$port 2>/dev/null || ss -tlnp "sport = :$port" | grep -oP 'pid=\K[0-9]+')
    if [ -n "$pid" ]; then
        kill $pid 2>/dev/null
        sleep 1
        kill -9 $pid 2>/dev/null  # force if still alive
    fi
}
```

## Installation Path

Default: `~/adt-framework`
Override: `INSTALL_DIR=/path/to/dir bash install.sh`

## File Placement

| Component | Location |
|-----------|----------|
| Repository | `$INSTALL_DIR/` |
| Virtual env | `$INSTALL_DIR/venv/` |
| Console AppImage | `$INSTALL_DIR/bin/adt-console.AppImage` |
| DTTP log | `$INSTALL_DIR/_cortex/ops/dttp.log` |
| Panel log | `$INSTALL_DIR/_cortex/ops/adt_center.log` |
| DTTP PID | `$INSTALL_DIR/_cortex/ops/dttp.pid` |
| Panel PID | `$INSTALL_DIR/_cortex/ops/adt_center.pid` |

## Post-Install Output

```
============================================
  ADT Framework is running!
============================================

  ADT Panel:     http://localhost:5001
  DTTP Gateway:  http://localhost:5002
  Console:       ~/adt-framework/bin/adt-console.AppImage

  Hooks:
    Claude Code:  ACTIVE (hooks fire on Write/Edit/NotebookEdit)
    Gemini CLI:   ACTIVE (hooks fire on write_file/replace)
    DTTP status:  HEALTHY (enforcement mode: development)

  To start a governed agent session:
    cd ~/adt-framework
    claude    # Claude Code -- hooks auto-activate
    gemini    # Gemini CLI -- hooks auto-activate

  To update later:
    bash ~/adt-framework/install.sh
```

## Scope Exclusions

- No Windows native support (WSL only)
- No Docker containerization (direct install)
- No auto-start on boot (user runs install.sh or bootstrap.sh)
- Console build from source not supported (binary download only)
