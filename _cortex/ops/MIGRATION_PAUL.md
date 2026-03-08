# ADT Framework: Migration Guide for Paul

This guide details how to update your existing ADT Framework installation to the latest version (v0.3.2+) which includes the new ADT Panel, Operator Console, and hardened SPEC-036 sandboxing.

## Quick Update (Recommended)

The new version includes a unified installer that handles repository updates, dependency management, and service orchestration.

Run the following command from within your existing framework directory:

```bash
bash install.sh
```

**What this script does:**
1. Detects your platform (Linux, macOS, or WSL).
2. Pulls the latest code from the repository.
3. Updates the Python virtual environment and installs new dependencies.
4. Downloads the latest pre-built **ADT Console** binary (AppImage).
5. Restarts the **DTTP Gateway** (Port 5002) and **ADT Panel** (Port 5001).

---

## Verifying the Update

### 1. The ADT Panel
Open your browser to: [http://localhost:5001](http://localhost:5001)
You should see the new Operational Center dashboard showing your project status, ADS events, and task progress.

### 2. The Operator Console
The console binary is located at `bin/adt-console.AppImage`.
You can start it directly or use the launcher script:
```bash
./console.sh
```

### 3. Agent Enforcement
Your Gemini CLI and Claude Code sessions are now protected by the hardened Phase B sandbox.
- **Gemini CLI:** Interception is now active for `run_shell_command`.
- **Network Isolation:** Agents are now isolated in a network namespace, with traffic bridged only to the DTTP service via Unix sockets.

---

## Troubleshooting

- **Port Conflicts:** If services fail to start, ensure ports 5001 and 5002 are free.
- **Permissions:** If running in production mode, ensuring the 'agent' and 'dttp' OS users exist (the installer will warn you if they are missing).
- **Manual Build:** If the pre-built Console binary doesn't work on your specific Linux distro, you can build it from source:
  ```bash
  bash console.sh
  ```

---
*The framework governs itself by its own principles.*