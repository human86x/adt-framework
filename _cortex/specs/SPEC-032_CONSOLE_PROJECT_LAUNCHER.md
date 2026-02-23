# SPEC-032: Console Project Launcher

**Author:** CLAUDE (Systems_Architect)
**Date:** 2026-02-20
**Status:** APPROVED
**Approved:** 2026-02-20 by Human
**Extends:** SPEC-021 (Operator Console), SPEC-031 (External Project Governance)
**References:** SPEC-014 (DTTP), SPEC-025 (Collaborative Bootstrap)

---

## 1. Problem Statement

The ADT Console currently opens to an empty terminal view with "No active sessions"
and a hint to press Ctrl+N. The operator must manually create a session, pick a
project, role, agent, and spec every time. This is friction that violates the
Console's design principle of being a "unified command center."

**What the operator sees today:**
1. Launch Console -- blank screen
2. Press Ctrl+N -- session creation dialog (4 fields)
3. Select project, role, spec, agent
4. Launch

**What the operator should see:**
1. Launch Console -- **Project Launcher** window
2. Pick action: Open project, Create project, Import project, or Forge Mode
3. Single click to enter the workspace

The Project Launcher is the **front door** of the ADT Framework. It is the first
thing a new adopter sees. It must communicate that this tool governs projects and
that the operator is in command.

---

## 2. Proposed Solution

On startup (and accessible via Ctrl+Shift+P at any time), the Console displays
a **Project Launcher** overlay. This replaces the current blank empty state.

---

## 3. Project Launcher Design

### 3.1 Layout

```
+-------------------------------------------------------------------+
|                                                                   |
|                      *  ADT Framework                             |
|                      Operator Console                             |
|                                                                   |
|  +-------------------------------------------------------------+ |
|  |  Search projects...                                          | |
|  +-------------------------------------------------------------+ |
|                                                                   |
|  +----------------+  +----------------+  +----------------+       |
|  |                |  |                |  |                |       |
|  |   INTERNAL     |  |    CREATE      |  |    IMPORT      |       |
|  |   FORGE MODE   |  |    PROJECT     |  |    PROJECT     |       |
|  |                |  |                |  |                |       |
|  |  Work on the   |  |  Scaffold a    |  |  Add ADT to    |       |
|  |  ADT Framework |  |  new governed  |  |  an existing   |       |
|  |  itself        |  |  project       |  |  project        |       |
|  |                |  |                |  |                |       |
|  +----------------+  +----------------+  +----------------+       |
|                                                                   |
|  --- Governed Projects ------------------------------------------ |
|                                                                   |
|  +-------------------------------------------------------------+ |
|  |  taskflow          /home/user/Projects/taskflow        :5003 | |
|  |  * DTTP running    3 specs  12 tasks  47 ADS events          | |
|  +--------------------------------------------------------------+ |
|  |  webapp            /home/user/Projects/webapp          :5004 | |
|  |  o DTTP stopped    1 spec   4 tasks   8 ADS events          | |
|  +-------------------------------------------------------------+ |
|                                                                   |
|  --- Recent Sessions ------------------------------------------- |
|                                                                   |
|  Backend_Engineer @ taskflow (Claude) .............. 2h ago       |
|  Frontend_Engineer @ adt-framework (Gemini) ........ yesterday    |
|                                                                   |
+-------------------------------------------------------------------+
```

### 3.2 Actions

#### Internal Forge Mode
- Opens the Console workspace scoped to the ADT Framework project itself
- Equivalent to selecting `adt-framework` as the project
- The session creation dialog opens with project pre-set to adt-framework
- Special visual indicator: amber border on forge mode sessions

#### Create Project
- Opens a **Create Project wizard** (multi-step dialog):
  1. **Project name** (lowercase, hyphenated) and **path** (browse or type)
  2. **Project type detection**: if path exists, scan for `requirements.txt`,
     `package.json`, `Cargo.toml`, `go.mod` and suggest jurisdictions
  3. **Role configuration**: pre-populate standard roles or customize
  4. **Confirm**: show summary of what will be created
- On confirm, the Console invokes the backend to:
  1. Create the directory if it doesn't exist
  2. Run `adt init` equivalent: create `_cortex/` scaffold, `config/` governance
     files, genesis ADS event
  3. Register in `~/.adt/projects.json` with auto-assigned DTTP port
  4. Install Claude Code hooks (`.claude/settings.local.json`, `.claude/commands/`)
  5. Install Gemini CLI hooks (`.gemini/settings.json`)
  6. Copy hive command definitions to `.claude/commands/`
  7. Start DTTP service for the project
- Returns to launcher with the new project in the list

#### Import Project
- Opens a **path picker** (type path or browse)
- Detects if `_cortex/` already exists:
  - If yes: register project (already initialized, just add to registry)
  - If no: run full `adt init` scaffold creation, then register
- Same hook installation and DTTP startup as Create
- Returns to launcher with imported project in the list

#### Open Project (click on project card)
- Opens the Console workspace scoped to that project
- Session creation dialog opens with project pre-selected
- If DTTP is not running for this project, offer to start it

#### Recent Sessions (click on recent entry)
- Directly re-opens a session with the same project/role/agent configuration
- Fastest path back to where the operator left off

### 3.3 Project Cards

Each governed project card displays:
- **Project name** (bold)
- **Path** (monospace, truncated with tooltip)
- **DTTP port** and **status** (green dot = running, grey dot = stopped)
- **Stats**: spec count, task count, ADS event count (fetched from API)
- **Quick actions**: Start/Stop DTTP, Remove (with confirmation)

### 3.4 Search

The search bar filters across:
- Project names
- Project paths
- Recent session descriptions

---

## 4. Backend IPC Commands (New/Modified)

### 4.1 New: `init_project`

Called by the Create Project and Import Project wizards.

```typescript
invoke('init_project', {
  request: {
    path: string,       // Absolute path
    name: string,       // Project name
    detect: boolean,    // Auto-detect project type
    start_dttp: boolean // Start DTTP after init
  }
})
```

Internally calls `python3 -m adt_core.cli init <path> --name <name> --detect`
as a subprocess. This reuses all existing logic including hook installation and
hive command copying (implemented in task_087/task_090).

### 4.2 New: `list_projects`

Returns the project registry from `~/.adt/projects.json` enriched with live
DTTP status checks (port open/closed) and stats from each project's `_cortex/`.

```typescript
invoke('list_projects') -> [{
  name: string,
  path: string,
  port: number,
  dttp_running: boolean,
  is_framework: boolean,
  stats: { specs: number, tasks: number, ads_events: number }
}]
```

### 4.3 New: `start_project_dttp` / `stop_project_dttp`

Start or stop the DTTP service for a specific project.

```typescript
invoke('start_project_dttp', { project_name: string })
invoke('stop_project_dttp', { project_name: string })
```

---

## 5. Lifecycle

### 5.1 App Startup

```
App Launch
  |
  v
Restore previous sessions (existing logic)
  |
  v
Any active sessions restored?
  |         |
  YES       NO
  |         |
  v         v
Normal     Show Project
Console    Launcher
view       overlay
```

### 5.2 Project Launcher Triggers

The launcher appears:
1. On startup if no sessions are active
2. When user presses **Ctrl+Shift+P** (new global shortcut)
3. When user clicks "Projects" button in the top bar (new button)
4. When last session is closed

### 5.3 Launcher Dismissal

The launcher is dismissed when:
1. User selects a project (opens session creation dialog)
2. User presses Escape (returns to empty console if no sessions)
3. User switches to an existing session tab

---

## 6. Guided Setup System

### 6.1 Purpose

New users and first-time project creators need more than a scaffold -- they need
a guided path from "I have an idea" to "my project is functional and governed."
The Guide System is an optional, toggleable overlay that walks the operator through
the full project lifecycle step-by-step.

### 6.2 Activation

- **On by default** for the first project a user creates
- **Toggle**: Settings > "Show Setup Guide" checkbox (persisted in localStorage)
- **Re-activate**: Right-click project card > "Restart Guide"
- **Keyboard**: Ctrl+Shift+G toggles guide visibility for active project
- Guide state is **per-project** (stored in `_cortex/ops/guide_state.json`)

### 6.3 Guide Steps

The guide progresses through 7 stages. Each stage has:
- A **title** and **explanation** (what this step achieves)
- **Action buttons** (perform the step) or **auto-detection** (step completes itself)
- A **skip** option (for experienced users)
- A **progress indicator** (step N of 7, with completed steps checked off)

```
Stage 1: DESCRIBE YOUR PROJECT
+---------------------------------------------------------------+
|  Step 1 of 7                                    [Skip] [Hide] |
|                                                               |
|  What is this project?                                        |
|                                                               |
|  Project name:  [ my-webapp                        ]          |
|  Description:   [ A Flask web app for tracking     ]          |
|                 [ customer support tickets          ]          |
|  Tech stack:    [x] Python  [ ] Node  [ ] Rust  [ ] Go       |
|                 [ ] Other: [____________]                      |
|                                                               |
|  This information seeds your MASTER_PLAN.md and helps         |
|  the framework suggest appropriate roles and jurisdictions.   |
|                                                               |
|                                         [Next: Set Up Folder] |
+---------------------------------------------------------------+

Stage 2: SET UP FOLDER
+---------------------------------------------------------------+
|  Step 2 of 7                                    [Skip] [Hide] |
|                                                               |
|  Where should the project live?                               |
|                                                               |
|  Path: [ /home/user/Projects/my-webapp      ] [Browse]        |
|                                                               |
|  [x] Create directory if it doesn't exist                     |
|  [x] Initialize git repository                                |
|  [x] Create standard project structure for Python             |
|                                                               |
|  Preview of what will be created:                             |
|    my-webapp/                                                 |
|      src/                                                     |
|      tests/                                                   |
|      requirements.txt                                         |
|      README.md                                                |
|      _cortex/        (ADT governance)                         |
|      config/         (ADT configuration)                      |
|      .claude/        (Agent hooks)                            |
|      .gemini/        (Agent hooks)                            |
|                                                               |
|                                      [Create Project Folder]  |
+---------------------------------------------------------------+

Stage 3: CONFIGURE GOVERNANCE
+---------------------------------------------------------------+
|  Step 3 of 7                                    [Skip] [Hide] |
|                                                               |
|  Who works on what?                                           |
|                                                               |
|  The framework uses roles to control which AI agent can       |
|  edit which files. Here are suggested roles based on your     |
|  Python project:                                              |
|                                                               |
|  [x] Backend_Engineer    src/, tests/, *.py                   |
|  [x] Frontend_Engineer   templates/, static/, *.html, *.css   |
|  [x] Systems_Architect   _cortex/, docs/                      |
|  [ ] DevOps_Engineer     .github/, Dockerfile, ops/           |
|  [ ] Overseer            _cortex/ads/ (read-only audit)       |
|                                                               |
|  You can customize these later in the Governance page.        |
|                                                               |
|                                       [Save Roles & Continue] |
+---------------------------------------------------------------+

Stage 4: WRITE YOUR FIRST SPEC
+---------------------------------------------------------------+
|  Step 4 of 7                                    [Skip] [Hide] |
|                                                               |
|  What should be built first?                                  |
|                                                               |
|  In ADT, every feature starts with a specification.           |
|  Describe the first thing you want your agents to build:      |
|                                                               |
|  Title: [ User authentication with login/register pages   ]   |
|                                                               |
|  Description (what, not how):                                 |
|  [ Users should be able to register with email/password,  ]   |
|  [ log in, and see a dashboard. Use Flask-Login.          ]   |
|  [                                                        ]   |
|                                                               |
|  This creates SPEC-001 in your project. Agents cannot         |
|  write code without an approved spec -- that's the rule.      |
|                                                               |
|                                      [Create SPEC-001]        |
+---------------------------------------------------------------+

Stage 5: START GOVERNANCE SERVICES
+---------------------------------------------------------------+
|  Step 5 of 7                                    [Skip] [Hide] |
|                                                               |
|  Starting enforcement services...                             |
|                                                               |
|  [*] DTTP service on :5003 ............... Running             |
|  [*] Project registered in ADT ........... Done               |
|  [*] Agent hooks installed ............... Done               |
|  [ ] ADT Panel visibility ............... Checking...         |
|                                                               |
|  Your project is now governed. Any AI agent working in        |
|  this directory will have its file edits checked against      |
|  the roles you configured.                                    |
|                                                               |
|                                         [Next: Launch Agent]  |
+---------------------------------------------------------------+

Stage 6: LAUNCH YOUR FIRST AGENT SESSION
+---------------------------------------------------------------+
|  Step 6 of 7                                    [Skip] [Hide] |
|                                                               |
|  Time to put an agent to work.                                |
|                                                               |
|  Agent:  ( ) Claude Code  ( ) Gemini CLI  ( ) Shell           |
|  Role:   [Backend_Engineer v]                                 |
|  Spec:   [SPEC-001: User authentication v]                    |
|                                                               |
|  The agent will start in your project directory with          |
|  the selected role. It can only edit files within that        |
|  role's jurisdiction. Try asking it to implement SPEC-001.    |
|                                                               |
|                                          [Launch Session]     |
+---------------------------------------------------------------+

Stage 7: YOU'RE GOVERNING
+---------------------------------------------------------------+
|  Step 7 of 7                                         [Close]  |
|                                                               |
|  Your project is set up and governed.                         |
|                                                               |
|  What you can do now:                                         |
|                                                               |
|  * Open the ADT Panel (Ctrl+G) to see specs, tasks, and      |
|    the ADS audit trail for your project                       |
|  * Create more specs as your project grows                    |
|  * Add more agent sessions (Ctrl+N) for parallel work         |
|  * Configure governance rules in the Governance page          |
|  * Use /hive-* commands to assign agent roles dynamically     |
|                                                               |
|  Tip: The Hive Tracker (right panel) shows your project's     |
|  tasks, delegations, and recent activity in real time.        |
|                                                               |
|  [ ] Don't show this guide for new projects                   |
|                                                               |
|                              [Open ADT Panel]  [Start Working] |
+---------------------------------------------------------------+
```

### 6.4 Guide State Persistence

Each project stores guide progress in `_cortex/ops/guide_state.json`:

```json
{
  "guide_enabled": true,
  "current_step": 4,
  "completed_steps": [1, 2, 3],
  "skipped_steps": [],
  "started_at": "2026-02-20T10:00:00Z",
  "completed_at": null
}
```

The Console reads this on project open and resumes from `current_step`.

### 6.5 Auto-Detection

Some steps can auto-complete by detecting existing state:
- Step 2 auto-completes if the directory and `_cortex/` already exist
- Step 3 auto-completes if `config/jurisdictions.json` is already configured
- Step 5 auto-completes if DTTP is already running on the project's port

This means importing an existing ADT project skips to the first incomplete step.

### 6.6 Guide Panel Position

The guide renders as a **bottom sheet** overlay on the terminal area:
- Does not cover the sidebar or context panel
- Collapsible to a thin progress bar showing "Step N of 7 -- click to expand"
- Semi-transparent background so the terminal is still partially visible
- Slides up/down with smooth animation

### 6.7 Design Principles

1. **Never block the operator.** Every step has Skip. The guide is a suggestion,
   not a gate. The operator is always in command.
2. **Respect what exists.** If files/config already exist, acknowledge them
   instead of overwriting. Auto-detect and auto-advance.
3. **Teach by doing.** Each step performs a real action (creates files, starts
   services). The guide is not a tutorial to read -- it is a wizard that builds.
4. **Disappear when done.** After Step 7, the guide collapses and does not
   return unless explicitly re-activated.

---

## 7. File Jurisdiction

| File | Role |
|------|------|
| `adt-console/src/js/launcher.js` (NEW) | Frontend_Engineer |
| `adt-console/src/js/guide.js` (NEW) | Frontend_Engineer |
| `adt-console/src/css/launcher.css` (NEW) | Frontend_Engineer |
| `adt-console/src/index.html` (modify) | Frontend_Engineer |
| `adt-console/src/js/sessions.js` (modify) | Frontend_Engineer |
| `adt-console/src/js/app.js` (modify) | Frontend_Engineer |
| `adt-console/src-tauri/src/ipc.rs` (modify) | DevOps_Engineer |
| `adt-console/src-tauri/src/pty.rs` (modify) | DevOps_Engineer |

---

## 8. Task Breakdown

### Phase A: Project Launcher UI
1. Create `launcher.js` and `launcher.css` with the launcher overlay layout
2. Wire launcher to startup flow in `app.js` (show on launch if no sessions)
3. Implement project card list with live stats from `GET /api/projects`
4. Internal Forge Mode action card (pre-selects adt-framework)

### Phase B: Backend IPC for Project Management
5. Add `init_project` IPC command to `ipc.rs` (calls `adt init` subprocess)
6. Add `list_projects`, `start_project_dttp`, `stop_project_dttp` IPC commands

### Phase C: Create & Import Wizards
7. Create Project wizard UI (multi-step dialog)
8. Import Project wizard UI (path picker + init)

### Phase D: Guided Setup System
9. Create `guide.js` with 7-step guide engine and state machine
10. Step 1-2: Describe project + set up folder (forms, preview, directory creation)
11. Step 3-4: Configure governance + write first spec (role picker, spec editor)
12. Step 5-7: Start services + launch agent + completion (auto-detection, launch)
13. Guide state persistence (`_cortex/ops/guide_state.json`) and auto-resume
14. Guide toggle in settings, Ctrl+Shift+G shortcut, per-project state

### Phase E: Polish
15. Recent sessions section on launcher (from `~/.adt/console/sessions.json`)
16. Search/filter on launcher
17. Ctrl+Shift+P shortcut and top-bar Projects button
18. Auto-show launcher when last session closes

---

## 9. Acceptance Criteria

1. Console launches to Project Launcher (not blank screen) when no sessions exist
2. "Internal Forge Mode" opens workspace scoped to adt-framework
3. "Create Project" scaffolds a complete ADT-ready project with one wizard flow
4. "Import Project" adds ADT governance to an existing codebase
5. Project cards show live DTTP status and project stats
6. Ctrl+Shift+P opens the launcher from anywhere in the Console
7. Recent sessions allow one-click return to previous work context
8. Hive commands are installed in new/imported projects automatically
9. Guided Setup System walks user through all 7 steps from idea to running agent
10. Guide auto-detects existing state and skips completed steps
11. Guide is toggleable (on by default for first project, off via settings)
12. Guide state persists per-project and resumes on re-open
13. Every guide step has a Skip option -- guide never blocks the operator
