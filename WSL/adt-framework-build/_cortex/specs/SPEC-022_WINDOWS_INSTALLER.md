# SPEC-022: ADT Framework Windows Ready Installer

**Status:** DRAFT
**Priority:** MEDIUM
**Owner:** Systems_Architect (spec), DevOps_Engineer (implementation)
**Created:** 2026-02-12
**References:** SPEC-014 (DTTP), SPEC-015 (Operational Center), SPEC-021 (Operator Console)

---

## 1. Purpose

Provide a seamless, "one-click" installation experience for Windows users to deploy the ADT Framework. The installer must bundle all core services (DTTP, Panel, Console) and configure them for automatic startup, removing the barrier to entry for human operators.

---

## 2. Components to Bundle

| Component | Technology | Delivery Method |
|-----------|------------|-----------------|
| **DTTP Service** | Python (Flask) | PyInstaller Executable (`adt-dttp.exe`) |
| **ADT Panel** | Python (Flask) | PyInstaller Executable (`adt-panel.exe`) |
| **ADT Console** | Rust (Tauri) | Native MSI/EXE (`adt-console.exe`) |
| **Environment** | Python 3.11+ | Embedded Python distribution (portable) |

---

## 3. Installer Strategy: Inno Setup

We will use **Inno Setup** to compile the final `.exe` installer. It is lightweight, supports Pascal scripting for complex configurations, and is industry-standard for Windows applications.

### 3.1 Installation Steps

1.  **Extract Binaries:** Place services in `C:\Program Files\ADT Framework\`.
2.  **Initialize Config:** Create default `config/` directory in `%APPDATA%\ADT\`.
3.  **Path Registration:** Add `adt-console.exe` to the System PATH.
4.  **Shortcut Creation:**
    *   **Desktop:** "ADT Operator Console"
    *   **Start Menu:** "ADT Framework" folder containing Console, Panel Link, and Uninstall.
5.  **Auto-Launch Configuration:** 
    *   Add `adt-dttp.exe` and `adt-panel.exe` to Windows Registry `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`.
    *   *Optional:* Setup as Windows Services using `nssm` (Non-Sucking Service Manager).

---

## 4. Technical Requirements

### 4.1 PyInstaller Bundling
The Flask applications must be compiled into standalone executables to avoid requiring the user to install Python or manage virtual environments manually.

```bash
# Example for DTTP
pyinstaller --onefile --name adt-dttp adt_core/dttp/service.py
```

### 4.2 Portable Configuration
The framework must be updated to look for `specs.json` and `jurisdictions.json` in `%APPDATA%\ADT\config\` if they are not found in the current working directory.

---

## 5. User Workflow (Post-Install)

1.  User runs `ADT_Framework_Setup.exe`.
2.  Installer finishes and launches **ADT Operator Console**.
3.  Console detects services are running locally.
4.  User sees "System Nominal" in the tray.
5.  User can immediately launch their first agent session.

---

## 8. Agent Hook Auto-Configuration

To ensure ADT enforcement works immediately, the installer must configure the hooks for supported agents (Claude Code, Gemini CLI).

### 8.1 Hook Deployment
The Python hook scripts (`adt_sdk/hooks/claude_pretool.py` and `gemini_pretool.py`) will be compiled into Windows executables (`adt-claude-hook.exe`, `adt-gemini-hook.exe`) and placed in `C:\Program Files\ADT Framework\hooks\`.

### 8.2 Path Resolution
The hooks will be configured to find the DTTP service via the `DTTP_URL` environment variable (default: `http://localhost:5002`), which the installer sets system-wide.

### 8.3 Auto-Injection Script
A post-install script will:
1.  Scan `%USERPROFILE%` for `.claude/settings.local.json` and `.gemini/settings.json`.
2.  If found, parse the JSON and inject the ADT hook configuration.
3.  If a hook already exists, append or warn the user.
4.  If the directories don't exist, create them with a default config so that the next time the agent is installed, ADT is already active.


---

## 6. Implementation Tasks

| Task | Description | Assigned To |
|------|-------------|-------------|
| **task_039** | Create PyInstaller build scripts for DTTP and ADT Panel. | Backend_Engineer |
| **task_040** | Write Inno Setup Script (`.iss`) for ADT Framework. | DevOps_Engineer |
| **task_041** | Update `config.py` to support Windows `%APPDATA%` paths. | Backend_Engineer |
| **task_042** | Implement "Launch on Startup" toggle in Console settings. | Frontend_Engineer |

---

## 7. Acceptance Criteria

- [ ] Installer produces a single `.exe` file.
- [ ] Installation completes without requiring manual command-line intervention.
- [ ] ADT Console shortcut appears on Desktop and Start Menu.
- [ ] Rebooting the PC automatically starts DTTP and ADT Panel services.
- [ ] Uninstaller cleanly removes all binaries and optional config.

---

*"Making governance effortless for the human operator."*
