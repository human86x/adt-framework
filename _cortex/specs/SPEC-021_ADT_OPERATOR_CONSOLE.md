# SPEC-021: ADT Operator Console

**Author:** CLAUDE (Systems_Architect)
**Date:** 2026-02-09
**Status:** APPROVED
**Extends:** SPEC-015 (ADT Operational Center)
**References:** SPEC-003 (Dashboard Views), SPEC-014 (DTTP), ADT Whitepaper (Sheridan, 2026)

---

## 1. Problem Statement

The ADT Framework governs AI agents across multiple roles (Systems_Architect,
Backend_Engineer, Frontend_Engineer, DevOps_Engineer, Overseer). In practice, the
human operator runs multiple agent sessions (Claude Code, Gemini CLI, future agents)
simultaneously, each in a separate terminal window on separate desktop workspaces.

**Current operator experience:**

1. Agent sessions are scattered across OS desktop workspaces
2. No visual identification -- every terminal looks the same
3. Switching requires remembering which desktop has which agent
4. No contextual information visible (role, task, spec, ADS events)
5. The human governor has no governance workstation

**Impact on governance:**

The ADT Framework provides engines for data integrity (ADS), specification management
(SDD), and enforcement (DTTP), but provides no tooling for the human who operates
all of it. The governor has no control room. Every ADT adopter will face this same
problem and reinvent their own ad-hoc solution.

**Principle:**

> If the ADT Framework proposes a new way to govern AI agents, it should also
> propose the workspace from which that governance is exercised.

---

## 2. Proposed Solution

A cross-platform desktop application -- the **ADT Console** -- that serves as the
human operator's unified command center for all AI agent sessions.

### 2.1 Design Principles

1. **Single window** -- all agent sessions live inside one application, not scattered
   across OS windows. Switching is internal, not OS-level.
2. **Instant identification** -- every agent session is visually distinct with role,
   agent name, current task, and active spec always visible.
3. **Keyboard-first** -- global shortcuts switch between agents from anywhere on the
   desktop. No mouse hunting.
4. **Cross-platform** -- identical experience on Linux, macOS, and Windows with
   near-zero dependencies.
5. **Enforcement boundary** -- agent sessions are spawned with restricted permissions.
   The Console is the privilege separation point between human and agent.
6. **Framework-native** -- ships as part of the ADT Framework, not an afterthought.

### 2.2 Technology Choice: Tauri

| Criterion | Electron | Tauri |
|-----------|----------|-------|
| Install size | 150-200 MB | 5-10 MB |
| RAM usage | High (bundled Chromium) | Low (system WebView) |
| Global shortcuts | Yes | Yes |
| System tray | Yes | Yes |
| Native notifications | Yes | Yes |
| Backend language | Node.js | **Rust** |
| Cross-platform | Yes | Yes |
| Security model | Chromium sandbox | System WebView + Rust |
| Process spawning | Node child_process | Rust portable-pty |

**Decision: Tauri.**

Tauri provides a native desktop application with a Rust backend and web frontend.
The Rust layer handles PTY management, file system watchers, and system integration.
The web frontend (bundled inside the app binary) handles the UI. The install
footprint is minimal and the security model aligns with ADT's fail-closed philosophy.

---

## 3. Architecture

### 3.1 Component Overview

```
+------------------------------------------------------------+
|                ADT CONSOLE (Tauri App)                      |
|                                                             |
|  +------------------------------------------------------+  |
|  |  Web Frontend (HTML/CSS/JS)                          |  |
|  |  - Tabbed workspace with agent sessions              |  |
|  |  - xterm.js terminal emulation                       |  |
|  |  - Context panels (role, task, ADS feed)             |  |
|  |  - Dashboard / overview mode                         |  |
|  +------------------------------------------------------+  |
|                          |                                  |
|  +------------------------------------------------------+  |
|  |  Rust Backend (Tauri core)                           |  |
|  |  - PTY multiplexer (spawn/manage agent processes)    |  |
|  |  - File watchers (events.jsonl, tasks.json)          |  |
|  |  - System integration (tray, shortcuts, notify)      |  |
|  |  - WebSocket server (terminal I/O)                   |  |
|  +------------------------------------------------------+  |
|                          |                                  |
+------------------------------------------------------------+
                           |
              HTTP + WebSocket connections
                           |
+------------------------------------------------------------+
|              ADT CENTER (Flask backend)                     |
|              (existing, from SPEC-015)                      |
|                                                             |
|  - ADS query API (GET /ads/events)                         |
|  - Task API (GET /tasks)                                    |
|  - Spec API (GET /specs)                                    |
|  - DTTP proxy (POST /dttp/request)                          |
|  - Session registration                                     |
+------------------------------------------------------------+
                           |
                    reads / writes
                           |
+------------------------------------------------------------+
|              PROJECT _cortex/                               |
|  - ads/events.jsonl    (ADS event log)                      |
|  - tasks.json          (task registry)                      |
|  - specs/              (specification files)                |
|  - phases.json         (phase structure, from SPEC-003)     |
+------------------------------------------------------------+
```

### 3.2 Two-Component Model

| Component | Role | Technology | Distribution |
|-----------|------|-----------|--------------|
| **ADT Center** | Governance server. ADS, SDD, DTTP engines. API endpoints. | Python / Flask | `pip install adt-framework` |
| **ADT Console** | Operator workspace. Terminal management. System integration. | Rust + Web (Tauri) | Single binary per platform (~10 MB) |

The Center runs as a background service. The Console connects to it. Both are
optional -- the Center works without the Console (agents use the API directly),
and the Console works without the Center (using local file watchers for context).
For governance monitoring via browser, use the ADT Center web UI (SPEC-015).

### 3.3 Cross-Platform Support

| Platform | WebView Engine | PTY Mechanism | Dependencies |
|----------|---------------|---------------|-------------|
| **Linux** | WebKitGTK | POSIX PTY | `webkit2gtk` (one package) |
| **macOS** | WKWebView | POSIX PTY | None (ships with macOS) |
| **Windows** | WebView2 (Edge) | ConPTY | None (ships with Win 10/11) |

Rust's `portable-pty` crate abstracts PTY differences across all three platforms.
xterm.js renders terminals identically in all WebView engines.

---

## 4. User Interface

### 4.1 Main Layout

```
+------------------------------------------------------------------+
|  [ADT]  [@Architect] [@Backend] [@Frontend] [@DevOps]  | [O] [_] |
+------------------------------------------------------------------+
|         |                                    |                     |
| Session |  Terminal Area                     |  Context Panel      |
|  List   |                                    |                     |
|         |  $ claude --role architect         |  ROLE               |
| -----   |  > Reading MASTER_PLAN.md...       |  Systems_Architect  |
| [A] Arc |  > Reviewing SPEC-020 status       |                     |
|  CLAUDE  |  > ...                             |  AGENT              |
|  idle   |                                    |  CLAUDE              |
|         |                                    |                     |
| [B] Bck |                                    |  TASK               |
|  GEMINI  |                                    |  (none active)      |
|  task14 |                                    |                     |
|         |                                    |  SPEC               |
| [F] Fnt |                                    |  ---                |
|  CLAUDE  |                                    |                     |
|  task05 |                                    |  SESSION            |
|         |                                    |  1h 23m             |
| [D] Dev |                                    |  43 events          |
|  GEMINI  |                                    |                     |
|  idle   |                                    | ------------------- |
|         |                                    |  RECENT ADS         |
| -----   |                                    |  > session_start    |
| [dash]  |                                    |  > spec_review      |
|         |                                    |  > plan_update      |
|         |                                    |                     |
+------------------------------------------------------------------+
|  [ADS: 43 events] [Sessions: 4] [Escalations: 0]    12:34:56 UTC |
+------------------------------------------------------------------+
```

**Layout regions:**

| Region | Content |
|--------|---------|
| **Top bar** | ADT logo + agent session tabs (color-coded, always visible) |
| **Left sidebar** | Session list with status badges. Click to switch. Collapsible. |
| **Center** | Active terminal (xterm.js). Full PTY, full color, full interaction. |
| **Right sidebar** | Context panel: role, agent, task, spec, ADS feed for this session. Collapsible. |
| **Bottom bar** | Global status: total ADS events, active sessions, escalation count, clock. |

### 4.2 Session Tabs

Each tab represents one agent session. The tab shows:

```
+---------------------------+
| [color] AGENT  Role  [x] |
|  badge  name   short      |
+---------------------------+

Examples:
  [blue]  CLAUDE  Arch   -- Systems_Architect session
  [green] GEMINI  Back   -- Backend_Engineer session
  [blue]  CLAUDE  Front  -- Frontend_Engineer session
  [green] GEMINI  DevOps -- DevOps_Engineer session
```

**Color coding:**
- Blue tones = Claude agent sessions
- Green tones = Gemini agent sessions
- Yellow = session has pending escalation
- Red = session has unresolved denial or error
- Grey = session idle / disconnected

### 4.3 Context Panel

The right sidebar shows live context for the selected session, sourced from the
ADT Center API and local file watchers:

**Session Info:**
- Role name (e.g., Backend_Engineer)
- Agent name (e.g., GEMINI)
- Session uptime
- Total ADS events this session

**Current Work:**
- Active task (from tasks.json, filtered by assigned_to)
- Task status and priority
- Linked spec reference
- Blocked-by dependencies

**Recent ADS Events:**
- Last 10 events from this agent/session
- Color-coded by action_type (green = completion, yellow = edit, red = denial)
- Click to expand full event JSON

**Delegation Chain (from SPEC-003):**
- Who delegated the current task
- Which spec authorized it
- Traceability breadcrumb: Spec -> Delegator -> Role -> Task

### 4.4 Dashboard Mode

Pressing `Ctrl+D` or clicking the dashboard icon shows an overview of all sessions:

```
+------------------------------------------------------------------+
|  ADT OPERATOR DASHBOARD                                           |
+------------------------------------------------------------------+
|                                                                    |
|  +-------------------+  +-------------------+                      |
|  | CLAUDE            |  | GEMINI            |                      |
|  | Systems_Architect |  | Backend_Engineer  |                      |
|  | idle              |  | task_014          |                      |
|  |                   |  | SPEC-020          |                      |
|  | [mini terminal]   |  | [mini terminal]   |                      |
|  +-------------------+  +-------------------+                      |
|                                                                    |
|  +-------------------+  +-------------------+                      |
|  | CLAUDE            |  | GEMINI            |                      |
|  | Frontend_Engineer |  | DevOps_Engineer   |                      |
|  | task_005          |  | idle              |                      |
|  | SPEC-016          |  |                   |                      |
|  | [mini terminal]   |  | [mini terminal]   |                      |
|  +-------------------+  +-------------------+                      |
|                                                                    |
+------------------------------------------------------------------+
|  Tasks: 14/18 done | Specs: 6 approved, 1 draft | ADS: 43 events  |
+------------------------------------------------------------------+
```

All four sessions visible simultaneously with miniature terminal previews.
Click any card to switch to that session full-screen.

### 4.5 Split View

`Ctrl+\` splits the terminal area to show two sessions side by side:

```
+-------------------------------+-------------------------------+
| CLAUDE - Architect            | GEMINI - Backend              |
|                               |                               |
| $ reviewing SPEC-020...       | $ implementing task_014...    |
|                               |                               |
+-------------------------------+-------------------------------+
```

Useful for coordinating between an architect session and an engineer session.

---


### 4.4 Role-Centric Context Panel (The 'Hive View')
The right sidebar must be upgraded from a static display to a live 'Role Pipeline':
1. **Task Filter:** Automatically filter global tasks to only show those assigned to the session's active role.
2. **Delegation Feed:** Show a 'Requests for this Role' list, pulling from ADS events where the role is the target of a delegation.
3. **Pre-flight Check:** A 'Ready to Work' indicator that turns green only when ROLE, SPEC, and CWD (Current Working Directory) are all in alignment.

## 5. Keyboard Shortcuts

### 5.1 Global Shortcuts (work from any application)

These are registered at the OS level by the Tauri app. They bring the Console
to the foreground and switch to the specified session.

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+A` | Switch to Console (or bring to front) |
| `Ctrl+Shift+1` | Switch to session slot 1 |
| `Ctrl+Shift+2` | Switch to session slot 2 |
| `Ctrl+Shift+3` | Switch to session slot 3 |
| `Ctrl+Shift+4` | Switch to session slot 4 |
| `Ctrl+Shift+5` | Switch to session slot 5 |

### 5.2 In-App Shortcuts (when Console is focused)

| Shortcut | Action |
|----------|--------|
| `Ctrl+Tab` | Next session tab |
| `Ctrl+Shift+Tab` | Previous session tab |
| `Ctrl+1` through `Ctrl+5` | Switch to session by slot number |
| `Ctrl+D` | Toggle dashboard mode |
| `Ctrl+\` | Toggle split view |
| `Ctrl+B` | Toggle left sidebar (session list) |
| `Ctrl+I` | Toggle right sidebar (context panel) |
| `Ctrl+N` | New session (opens agent/role picker) |
| `Ctrl+W` | Close current session (with confirmation) |
| `Ctrl+Shift+E` | Focus ADS event feed |

### 5.3 Customization

Keybindings are configurable via `~/.adt/console/keybindings.json`. The defaults
above are sensible for all three platforms. macOS users may prefer `Cmd` over `Ctrl`
-- Tauri handles this mapping.

---

## 6. System Integration

### 6.1 System Tray

The Console places an icon in the system tray / menu bar:

```
Tray icon states:
  [green circle]  -- all sessions nominal
  [yellow circle] -- pending escalation or warning
  [red circle]    -- unresolved denial or error
  [grey circle]   -- no active sessions
```

**Tray menu:**
- Show/Hide Console
- Active sessions list (click to switch)
- Recent escalations
- Quick launch: New Session
- Settings
- Quit

### 6.2 Native Notifications

The Console sends OS-native notifications for high-priority events:

| Event | Notification |
|-------|-------------|
| DTTP denial | "DENIED: Backend_Engineer blocked from editing sovereign path" |
| Escalation raised | "ESCALATION: Jurisdiction violation by GEMINI" |
| Task completed | "task_014 completed by GEMINI (Backend_Engineer)" |
| Session ended | "CLAUDE Frontend_Engineer session ended (42 events)" |

Notifications are configurable. The operator can mute per event type or per role.

### 6.3 Launch on Login (Optional)

The Console can register itself to start on login:
- Linux: XDG autostart entry
- macOS: Login Items
- Windows: Startup folder / registry

Starts minimized to tray, ready for global shortcuts.

---

## 7. Session Management

### 7.1 Creating a Session

From the Console, the operator can launch a new agent session:

```
+----------------------------------+
|  NEW SESSION                     |
|                                  |
|  Agent:  [Claude Code v]         |
|          [Gemini CLI   ]         |
|          [Custom...    ]         |
|                                  |
|  Role:   [Systems_Architect v]   |
|          [Backend_Engineer   ]   |
|          [Frontend_Engineer  ]   |
|          [DevOps_Engineer    ]   |
|          [Overseer           ]   |
|                                  |
|  Project: /home/human/Projects/  |
|           adt-framework          |
|                                  |
|  [Launch]  [Cancel]              |
+----------------------------------+
```

The Console spawns the agent process in a PTY, attaches xterm.js to it, and
registers the session with the ADT Center (which logs `session_start` to ADS).

### 7.2 Agent Launch Commands

The Console maintains a registry of known agent types and their launch commands:

```json
{
  "agents": {
    "claude-code": {
      "name": "Claude Code",
      "command": "claude",
      "args": [],
      "icon": "claude.svg",
      "color": "#6B7FD7"
    },
    "gemini-cli": {
      "name": "Gemini CLI",
      "command": "gemini",
      "args": [],
      "icon": "gemini.svg",
      "color": "#4CAF50"
    }
  }
}
```

Custom agents can be added. Any CLI tool that runs in a terminal can be managed.

### 7.3 Session Lifecycle

```
[New Session] -> PTY spawned -> Agent starts -> session_start logged to ADS
     |                                              |
     v                                              v
[Active] -> operator interacts via terminal    ADS events accumulate
     |                                              |
     v                                              v
[Close Session] -> Agent receives SIGHUP/exit -> session_end logged to ADS
                -> PTY cleaned up
                -> Tab removed (or greyed out with "ended" label)
```

### 7.4 Session Persistence

If the Console is closed and reopened, it reconnects to any running agent
processes (PTYs survive if the Rust backend keeps them alive). Sessions can
also be intentionally detached (like tmux detach) and reattached later.

---

## 8. Agent Sandboxing & DTTP Enforcement

### 8.1 Core Principle

**Agent sessions launched by the Console are read-only.** Agents cannot write to
disk directly. All write operations go through DTTP, which validates authorization
and executes the write as the privileged `dttp` user. The Console is the privilege
separation boundary.

### 8.2 Three-User Model (from SPEC-014)

| Process | Runs As | Filesystem Access | Write Path |
|---------|---------|-------------------|------------|
| **ADT Console** | `human` | Full read/write | Direct (it's the human's app) |
| **Agent PTYs** | `agent` | **Read-only** | DTTP only (`POST /dttp/request`) |
| **DTTP Service** | `dttp` | Read/write project files | Executes validated writes |

The Console runs as the `human` user (unrestricted). But agent processes it spawns
are restricted to `agent` permissions -- read-only access to project files, write
access only through the DTTP gateway.

### 8.3 How The Console Spawns Restricted Agents

**Development mode** (current -- single user, no OS-level separation):

```
Console spawns PTY:
  command: claude (or gemini)
  user: current user (same as Console)
  enforcement: SDK hooks route writes to DTTP (honor system)
```

Agents use the ADT SDK hooks to submit write requests to DTTP. There is no OS-level
enforcement -- the agent could theoretically write directly. This mode is for
development and testing.

**Production mode** (SPEC-014 Phase 4 -- OS-level privilege separation):

```
Console spawns PTY:
  command: sudo -u agent claude (or gemini)
  user: 'agent' (restricted OS user)
  enforcement: OS permissions (read-only) + SDK hooks + DTTP
```

The `agent` OS user has read-only access to project files. Even if an agent
bypasses SDK hooks and attempts a direct write, the OS blocks it. DTTP (running
as `dttp` user) is the only process that can write. Belt and suspenders.

### 8.4 Console Configuration

```json
{
  "enforcement_mode": "development",
  "agent_user": "agent",
  "dttp_url": "http://localhost:5002",
  "modes": {
    "development": {
      "spawn_command": "{agent_command}",
      "description": "Agent runs as current user. SDK hooks enforce DTTP."
    },
    "production": {
      "spawn_command": "sudo -u {agent_user} {agent_command}",
      "description": "Agent runs as restricted user. OS + SDK + DTTP enforce."
    }
  }
}
```

The mode is set in `~/.adt/console/config.json`. The Console displays the current
enforcement mode in the bottom status bar so the operator always knows the
protection level.

### 8.5 Write Flow Through DTTP

```
Agent wants to edit a file:
  1. Agent (or SDK hook) sends POST /dttp/request to localhost:5002
  2. DTTP validates: spec authorization, role jurisdiction, path safety
  3. If approved: DTTP writes file as 'dttp' user, logs to ADS
  4. If denied: DTTP logs denial + escalation to ADS
  5. Console watches ADS -> context panel updates -> notification if denied
```

The agent never touches the filesystem for writes. The Console never writes on
behalf of agents. DTTP is the sole write authority. This is the ADT enforcement
model made concrete.

### 8.6 Visual Enforcement Indicators

The Console displays the enforcement state at all times:

```
Bottom bar:
  [ENFORCEMENT: production]  -- green badge, OS-level protection active
  [ENFORCEMENT: development] -- yellow badge, SDK-level only
```

Per-session context panel:
```
  WRITE ACCESS: DTTP only
  DTTP STATUS: connected (localhost:5002)
  DENIALS THIS SESSION: 0
```

---

## 9. Data Sources

The Console pulls live data from two sources:

### 9.1 ADT Center API (existing endpoints)

| Endpoint | Data | Used For |
|----------|------|----------|
| `GET /ads/events` | ADS event stream | Context panel, dashboard stats, notifications |
| `GET /api/tasks` | Task registry | Current task display, dashboard progress |
| `GET /api/specs` | Spec registry | Active spec reference, dashboard status |
| `GET /dttp/status` | DTTP gateway status | Bottom bar, system tray color |

### 9.2 Local File Watchers (Rust backend)

For responsiveness, the Rust layer watches key files directly:

| File | Watch For | Action |
|------|----------|--------|
| `_cortex/ads/events.jsonl` | New lines appended | Update ADS feed in real time |
| `_cortex/tasks.json` | File modified | Refresh task display |
| `_cortex/phases.json` | File modified | Refresh hierarchy view |

File watchers use `notify` (Rust crate) for cross-platform filesystem events.
This gives sub-second reactivity without polling.

---

## 10. Build & Distribution

### 10.1 Repository Structure

```
adt-console/
+-- src-tauri/
|   +-- src/
|   |   +-- main.rs            # Tauri entry point
|   |   +-- pty.rs             # PTY multiplexer (portable-pty)
|   |   +-- watcher.rs         # File system watchers (notify)
|   |   +-- tray.rs            # System tray management
|   |   +-- shortcuts.rs       # Global keyboard shortcuts
|   |   +-- ipc.rs             # Frontend <-> Rust communication
|   +-- Cargo.toml
|   +-- tauri.conf.json
|
+-- src/                        # Web frontend (bundled in Tauri app)
|   +-- index.html
|   +-- css/
|   |   +-- console.css        # Main stylesheet, dark theme
|   +-- js/
|   |   +-- app.js             # Application controller
|   |   +-- terminal.js        # xterm.js terminal management
|   |   +-- sessions.js        # Session lifecycle
|   |   +-- context.js         # Context panel logic
|   |   +-- dashboard.js       # Dashboard/overview mode
|   |   +-- shortcuts.js       # In-app keyboard shortcuts
|   +-- assets/
|       +-- icons/             # Agent and role icons
|
+-- tests/
+-- .github/
|   +-- workflows/
|       +-- build.yml          # CI: build Linux, macOS, Windows
|       +-- release.yml        # CD: publish binaries on tag
+-- README.md
+-- LICENSE                    # AGPL-3.0 (same as ADT Framework)
```

### 10.2 CI/CD Pipeline

GitHub Actions using `tauri-action`:

```
On push to main:
  -> Build Linux (x86_64): .AppImage, .deb
  -> Build macOS (x86_64, aarch64): .dmg
  -> Build Windows (x86_64): .msi, .exe

On tag (v*):
  -> All of the above
  -> Create GitHub Release with all binaries
  -> Update Homebrew tap
  -> Update winget manifest
```

### 10.3 Install Methods

| Platform | Method | Command |
|----------|--------|---------|
| **Linux** | AppImage (universal) | Download, chmod +x, run |
| **Linux** | Debian/Ubuntu | `sudo dpkg -i adt-console.deb` |
| **Linux** | From source | `cargo install adt-console` |
| **macOS** | Homebrew | `brew install adt-framework/tap/adt-console` |
| **macOS** | DMG | Download, drag to Applications |
| **Windows** | winget | `winget install adt-console` |
| **Windows** | MSI installer | Download and run |

For browser-based governance monitoring (no terminal management), use the
ADT Center web UI at `http://localhost:5001` (SPEC-015).

### 10.4 Size Targets

| Platform | Target Size |
|----------|------------|
| Linux AppImage | < 15 MB |
| macOS DMG | < 15 MB |
| Windows MSI | < 12 MB |

---

## 11. Relationship to Existing Components

### 11.1 Component Map (Updated)

```
ADT Framework
+-- ADS Engine (adt_core/ads/)          -- Data integrity
+-- SDD Engine (adt_core/sdd/)          -- Specification management
+-- DTTP Gateway (adt_core/dttp/)       -- Enforcement
+-- Operational Center (adt_center/)    -- Governance server + web UI
+-- Agent SDK (adt_sdk/)                -- Agent client library
+-- Operator Console (adt-console/)     -- Human command center  <-- NEW
```

### 11.2 Spec Relationships

| Spec | Relationship |
|------|-------------|
| **SPEC-015** | Parent. The Console connects to the Operational Center for data and API. |
| **SPEC-003** | Sibling. Delegation Tree and Hierarchy Views from SPEC-003 can be rendered in the Console's dashboard mode. |
| **SPEC-014** | Dependency. DTTP status feeds the tray icon and notification system. |
| **SPEC-019** | Integration. DTTP standalone service status shown in Console. |
| **SPEC-020** | Consumer. Sovereign/constitutional path violations trigger Console notifications. |

### 11.3 What This Does NOT Replace

- The ADT Center web UI remains fully functional in a browser
- The Agent SDK remains the programmatic interface for agents
- Agents can still run in plain terminals without the Console
- The Console is the **recommended** operator experience, not a requirement

---

## 12. Implementation Phases

### Phase A: Foundation

**Deliverables:**
- Tauri project scaffold with Rust backend
- PTY multiplexer: spawn and manage terminal processes
- xterm.js integration: render PTY output in WebView
- Basic tabbed layout: create/switch/close sessions
- WebSocket bridge: terminal I/O between xterm.js and Rust PTY

**Acceptance:** Can launch two agent sessions in tabs and switch between them.

### Phase B: Context & Identity

**Deliverables:**
- Session configuration (agent type, role, project path)
- Context panel: role, agent, session info (static at first)
- ADT Center API integration: pull tasks, specs, ADS events
- Color-coded tabs by agent type
- Left sidebar with session list

**Acceptance:** Each session tab shows correct role/agent identity with live task data.

### Phase C: System Integration

**Deliverables:**
- Global keyboard shortcuts (Ctrl+Shift+1-5)
- System tray with status indicator
- Native notifications for escalations and denials
- Launch-on-login option
- In-app keyboard shortcuts (Ctrl+Tab, Ctrl+D, etc.)

**Acceptance:** Can switch to a specific agent session from any desktop application
using a global shortcut. Tray icon reflects session status.

### Phase D: Dashboard & Advanced Views

**Deliverables:**
- Dashboard mode (all sessions overview with mini terminals)
- Split view (two sessions side by side)
- ADS event feed in context panel (live, filtered per session)
- Delegation chain display (from SPEC-003)
- Session persistence (reconnect to running PTYs on restart)

**Acceptance:** Full operator experience as described in Section 4.

### Phase E: Distribution

**Deliverables:**
- CI/CD pipeline for all three platforms
- Homebrew tap, winget manifest
- AppImage for Linux
- Documentation and first-run guide

**Acceptance:** A new ADT adopter on any platform can install and use the Console
within 5 minutes.

---

## 13. Future Considerations

These are explicitly **out of scope** for SPEC-021 v1 but noted for future specs:

1. **Multi-project support** -- tabs grouped by project, switch between governed projects
2. **Remote Console** -- connect to an ADT Center on a remote server (SSH tunnel or HTTPS)
3. **Session recording** -- replay agent sessions for audit or training
4. **Agent templates** -- pre-configured session profiles (e.g., "Start Claude as Backend_Engineer with SPEC-020 context")
5. **Voice notifications** -- audio alerts for critical escalations
6. **Plugin system** -- third-party extensions for the Console

---

## 14. ADT Compliance

This spec maintains ADT principles:

1. **Governance by Construction:** The Console surfaces governance data (ADS events,
   spec status, task tracking) as the operator's primary view, not an afterthought.
2. **Single Source of Truth:** All data comes from the ADS and project files. The
   Console creates no shadow state.
3. **Traceability:** Every session launch and termination is logged to ADS. The
   context panel shows delegation chains.
4. **Accountability:** Agent/role identification is always visible. The operator
   always knows who is doing what under which authority.
5. **Fail-Closed:** If the Console loses connection to the ADT Center, session
   context panels show a warning state. Terminals continue to function (they are
   local PTYs) but governance context is flagged as stale.

---

## 15. Acceptance Criteria

### Core Functionality
- [ ] Single-window application with tabbed agent sessions
- [ ] xterm.js terminals connected to real PTY processes
- [ ] Create, switch, and close sessions from within the Console
- [ ] Sessions display agent name, role, current task, and linked spec

### Cross-Platform
- [ ] Builds and runs on Linux (x86_64)
- [ ] Builds and runs on macOS (x86_64, aarch64)
- [ ] Builds and runs on Windows 10/11 (x86_64)
- [ ] Install size under 15 MB on all platforms

### System Integration
- [ ] Global keyboard shortcuts switch to specific sessions from any app
- [ ] System tray icon with session status color coding
- [ ] Native OS notifications for escalations and DTTP denials
- [ ] Configurable keybindings via JSON file

### Operator Experience
- [ ] Dashboard mode shows all sessions simultaneously
- [ ] Split view for side-by-side session comparison
- [ ] Context panel shows live ADS events filtered to current session
- [ ] Left sidebar provides session list with status badges
- [ ] Bottom bar shows global ADS stats and escalation count

### Distribution
- [ ] CI/CD builds all three platforms from one codebase
- [ ] Available via Homebrew (macOS), winget (Windows), AppImage (Linux)
- [ ] Documentation covers installation on all three platforms

### Agent Sandboxing (Section 8)
- [ ] Development mode: agents spawn as current user with SDK hooks
- [ ] Production mode: agents spawn as restricted `agent` user via sudo
- [ ] Enforcement mode displayed in bottom status bar at all times
- [ ] DTTP connection status shown per session in context panel
- [ ] DTTP denials trigger immediate notification to operator

### ADT Compliance
- [ ] Session start/end logged to ADS
- [ ] No shadow state -- all data sourced from ADS and project files
- [ ] Console functions without ADT Center (terminals work, context is unavailable)
- [ ] Escalation notifications cannot be silenced without explicit configuration

---

## 16. Approval

**Human Approval Required:** YES

This spec introduces a new component to the ADT Framework. Implementation should
not proceed until human approves this design.

**APPROVED:** 2026-02-09 by Human

---

*"The governor needs a control room."*
*-- ADT Framework (Sheridan, 2026)*
