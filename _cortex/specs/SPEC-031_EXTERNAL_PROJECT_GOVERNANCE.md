# SPEC-031: External Project Governance

**Author:** CLAUDE (Systems_Architect)
**Date:** 2026-02-17
**Status:** APPROVED
**Approved:** 2026-02-18 by Human
**References:** SPEC-014 (DTTP), SPEC-015 (Operational Center), SPEC-017 (Repository),
SPEC-019 (DTTP Standalone), SPEC-020 (Self-Governance), SPEC-021 (Operator Console),
SPEC-025 (Collaborative Bootstrap), ADT Whitepaper (Sheridan, 2026)

---

## 1. Problem Statement

The ADT Framework claims to be a "standalone, open-source governance system for AI
agents" that is "project-agnostic." In practice, it has only ever governed itself.
Every config path, every service instance, every hook registration assumes a single
project root: the framework's own directory.

**What we cannot currently do:**

1. Govern an external project (any codebase that is not the ADT Framework itself)
2. Run governance services for multiple projects simultaneously
3. Switch agent context between the framework and a governed project
4. Validate that our jurisdiction model works on non-framework directory layouts
5. Prove the framework is usable by anyone other than its own developers

**Why this matters now:**

The framework has reached functional completeness: ADS, SDD, DTTP, Operational Center,
Operator Console, Agent SDK, Shatterglass -- all built, all working. But "working on
ourselves" is not proof of value. Every design assumption we've made about directory
structure, role separation, and enforcement needs to be tested against a project we
did not design. External project governance is the stress test that turns a
self-referential prototype into a proven tool.

> "A governance framework that only governs itself is a thought experiment.
> A governance framework that governs real projects is infrastructure."

---

## 2. Design Principles

1. **The framework is not the project.** The ADT Framework (engines, SDK, Center,
   Console) is infrastructure. Governed projects are tenants. The framework continues
   to self-govern as "project zero," but it is not special -- it follows the same
   onboarding path any external project would.

2. **Isolation by default.** Each governed project gets its own `_cortex/` directory,
   its own `config/` directory, its own DTTP instance, and its own ADS event stream.
   One project's misconfigured jurisdiction cannot affect another project.

3. **Unified visibility.** While enforcement is per-project, the human operator sees
   all projects through a single ADT Center and Console. Cross-project views (ADS
   timeline, task boards, escalation counts) are aggregated, not siloed.

4. **Progressive governance.** A new project starts with sensible defaults and minimal
   configuration. The human tunes jurisdictions and specs as they learn what their
   project needs. Governance is not an upfront tax -- it grows with the project.

5. **Zero framework coupling.** A governed project must not depend on the ADT Framework
   source code being present in its directory. The framework is installed once
   (globally or in its own directory); projects reference it, not contain it.

---

## 3. Architecture

### 3.1 Component Model (Multi-Project)

```
                    ┌─────────────────────────────────────┐
                    │         HUMAN OPERATOR               │
                    │  ADT Console  |  ADT Center (web)    │
                    │  (unified view across all projects)  │
                    └────────┬──────────────┬──────────────┘
                             │              │
                    ┌────────┴──────────────┴──────────────┐
                    │        PROJECT REGISTRY               │
                    │   ~/.adt/projects.json                │
                    │   Tracks all governed projects,       │
                    │   their ports, status, and paths      │
                    └────────┬──────────────┬──────────────┘
                             │              │
              ┌──────────────┴──┐    ┌──────┴──────────────┐
              │  PROJECT ZERO    │    │  EXTERNAL PROJECT    │
              │  (adt-framework) │    │  (e.g., taskflow)    │
              │                  │    │                      │
              │  _cortex/        │    │  _cortex/            │
              │    ads/          │    │    ads/              │
              │    specs/        │    │    specs/            │
              │    tasks.json    │    │    tasks.json        │
              │    ops/          │    │    ops/              │
              │  config/         │    │  config/             │
              │    specs.json    │    │    specs.json        │
              │    jurisd.json   │    │    jurisd.json       │
              │    dttp.json     │    │    dttp.json         │
              │                  │    │                      │
              │  DTTP :5002      │    │  DTTP :5003          │
              └──────────────────┘    └──────────────────────┘
```

### 3.2 Key Architectural Decisions

**D1: Per-project DTTP instances (not multi-tenant)**

Each governed project runs its own DTTP service on a unique port. This provides:
- Complete isolation: one project's policy engine cannot interfere with another's
- Independent restart: updating one project's DTTP config does not restart others
- Simple mental model: one project = one DTTP = one port
- Failure isolation: if a project's DTTP crashes, others are unaffected

The alternative (one multi-tenant DTTP) was rejected because it introduces routing
complexity, shared failure modes, and makes the DTTP service stateful in ways that
conflict with the fail-closed principle.

**D2: Per-project `_cortex/` and `config/` directories**

Each governed project contains its own governance artifacts. These are generated
by `adt init` and are committed to the project's own git repository. This means:
- The project carries its governance rules with it (portable)
- Collaborators who clone the project get the governance config
- The framework installation is not polluted with per-project data

**D3: Centralized project registry at `~/.adt/projects.json`**

A machine-level registry tracks which projects are governed, what ports they use,
and their current status. This is the only shared state. The ADT Center and Console
read this registry to provide cross-project views.

**D4: ADT Center as aggregation layer**

The existing ADT Center (SPEC-015) is extended to read from multiple project roots
(via the registry). It does not become multi-tenant -- it reads files from multiple
`_cortex/` directories and presents a unified view. Each API endpoint gains an
optional `?project=<name>` filter parameter. Without the filter, responses include
data from all projects.

**D5: Console project context**

The Operator Console (SPEC-021) gains a project selector. Agent sessions are tagged
with a project. The context panel shows the active project's tasks, specs, and ADS
events. Session creation includes a project picker.

---

## 4. The `adt init` Command

### 4.1 Purpose

Initialize ADT governance in any directory. This is the entry point for bringing a
project under ADT governance.

### 4.2 Usage

```bash
adt init [path] [--name <project-name>] [--detect] [--port <dttp-port>]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `path` | `.` (current directory) | Project root directory |
| `--name` | Directory basename | Human-readable project name |
| `--detect` | On by default | Auto-detect project type and suggest roles/jurisdictions |
| `--port` | Auto-assign (5003+) | DTTP service port for this project |

### 4.3 What It Creates

```
<project-root>/
├── _cortex/
│   ├── AI_PROTOCOL.md          # Governance protocol (generated, project-specific)
│   ├── MASTER_PLAN.md          # Empty template for project plan
│   ├── ads/
│   │   └── events.jsonl        # Empty ADS log (genesis event written)
│   ├── specs/                  # Empty specs directory
│   ├── tasks.json              # Empty task registry
│   └── ops/
│       ├── active_role.txt     # Default: Systems_Architect
│       └── active_spec.txt     # Default: (empty)
├── config/
│   ├── specs.json              # Empty spec registry
│   ├── jurisdictions.json      # Generated from project detection
│   └── dttp.json               # Project-specific DTTP config (port, name)
└── .claude/                    # (if Claude Code detected)
    └── settings.local.json     # Hook config pointing to framework's SDK
```

### 4.4 Project Type Detection

When `--detect` is active (default), `adt init` examines the project directory to
determine its type and suggest appropriate jurisdictions:

| Detected Pattern | Project Type | Suggested Jurisdictions |
|-----------------|-------------|------------------------|
| `requirements.txt` or `setup.py` or `pyproject.toml` | Python | `src/`, `tests/`, `docs/`, `config/` |
| `package.json` | Node.js | `src/`, `tests/`, `public/`, `config/` |
| `Cargo.toml` | Rust | `src/`, `tests/`, `benches/`, `config/` |
| `go.mod` | Go | `cmd/`, `internal/`, `pkg/`, `config/` |
| `pom.xml` or `build.gradle` | Java/Kotlin | `src/main/`, `src/test/`, `config/` |
| None of the above | Generic | `src/`, `tests/`, `docs/`, `config/` |

The detected layout is used to populate `config/jurisdictions.json` with sensible
defaults for two starter roles: `Developer` and `Reviewer`. The human can customize
these after init.

### 4.5 Registry Update

After scaffolding, `adt init` registers the project in `~/.adt/projects.json`:

```json
{
  "projects": {
    "adt-framework": {
      "path": "/home/human/Projects/adt-framework",
      "dttp_port": 5002,
      "panel_port": 5001,
      "status": "active",
      "registered_at": "2026-02-01T00:00:00Z",
      "is_framework": true
    },
    "taskflow": {
      "path": "/home/human/Projects/taskflow",
      "dttp_port": 5003,
      "panel_port": null,
      "status": "active",
      "registered_at": "2026-02-17T00:00:00Z",
      "is_framework": false
    }
  },
  "next_dttp_port": 5004
}
```

The `is_framework` flag marks the ADT Framework itself. This project always exists
in the registry and cannot be deregistered.

### 4.6 Hook Configuration

`adt init` detects installed agent CLIs and configures hooks:

- **Claude Code:** Creates/updates `.claude/settings.local.json` with `PreToolUse`
  hook pointing to the framework's `claude_pretool.py` (absolute path).
- **Gemini CLI:** Creates/updates `.gemini/settings.json` with equivalent hook.

Hook scripts use the project's own `_cortex/ops/active_role.txt` and
`_cortex/ops/active_spec.txt` for DTTP requests, and the project's own DTTP port
from `config/dttp.json`.

---

## 5. Project Registry

### 5.1 Location

`~/.adt/projects.json` -- user-level, not project-level. Shared across all projects
on the machine.

### 5.2 Operations

| Command | Description |
|---------|-------------|
| `adt init <path>` | Register a new project (Section 4) |
| `adt projects list` | List all registered projects with status |
| `adt projects status [name]` | Show detailed status (DTTP running, ADS events, etc.) |
| `adt projects remove <name>` | Deregister (does NOT delete `_cortex/` from project) |
| `adt projects start <name>` | Start DTTP service for a specific project |
| `adt projects stop <name>` | Stop DTTP service for a specific project |
| `adt projects start-all` | Start DTTP for all active projects |

### 5.3 Port Management

DTTP ports are auto-assigned starting from 5003 (5002 is reserved for the framework).
The registry tracks `next_dttp_port` to avoid collisions. The human can override via
`--port` during `adt init` or by editing `config/dttp.json` in the project.

---

## 6. DTTP Multi-Project Changes

### 6.1 What Changes

The DTTP service itself (`adt_core/dttp/service.py`) requires minimal changes. It
already accepts `--project-root` as an argument. The key change is that multiple
instances run simultaneously, each bound to a different port and project root.

| Component | Change Required |
|-----------|----------------|
| `config.py` | Add `from_project_dttp_json()` classmethod that reads `<project>/config/dttp.json` |
| `service.py` | Read port from project's `config/dttp.json` instead of global default |
| `gateway.py` | No change -- sovereign/constitutional paths are framework-only concepts |
| `actions.py` | No change -- already parameterized by `project_root` |
| `policy.py` | No change -- already reads config at construction |
| `sync.py` | No change -- already parameterized by `project_root` |

### 6.2 Sovereign and Constitutional Paths

Sovereign and constitutional path protections (SPEC-020) apply ONLY to the ADT
Framework project (project zero). External projects do not have sovereign paths --
they have whatever the human configures in their `config/jurisdictions.json`.

The DTTP gateway already checks `SOVEREIGN_PATHS` and `CONSTITUTIONAL_PATHS` as
module-level constants. For external projects, these lists are empty because the
paths (`config/specs.json`, `_cortex/AI_PROTOCOL.md`, etc.) in an external project
are NOT framework infrastructure -- they are that project's own governance config,
editable by the project's own architect role.

**Implementation:** Add a `is_framework_project: bool` field to `DTTPConfig`. When
`False`, the sovereign/constitutional checks in `gateway.py` are skipped. The flag
is derived from the registry's `is_framework` field.

### 6.3 External Project Jurisdictions

External projects define their own roles and jurisdictions. A typical init for a
Python web app might produce:

```json
{
  "jurisdictions": {
    "Architect": {
      "paths": ["_cortex/", "config/", "docs/"],
      "action_types": ["edit", "patch", "create", "delete"],
      "locked": false
    },
    "Backend_Developer": {
      "paths": ["src/", "tests/", "config/"],
      "action_types": ["edit", "patch", "create", "delete"],
      "locked": false
    },
    "Frontend_Developer": {
      "paths": ["templates/", "static/", "public/"],
      "action_types": ["edit", "patch", "create"],
      "locked": false
    },
    "DevOps": {
      "paths": [".github/", "docker/", "scripts/", "Dockerfile"],
      "action_types": ["edit", "patch", "create", "delete"],
      "locked": false
    }
  }
}
```

Role names are not hardcoded. External projects can use whatever role names make
sense for their team.

---

## 7. ADT Center Multi-Project Changes

### 7.1 Project-Aware Data Loading

`adt_center/app.py` currently derives all data paths from a single `PROJECT_ROOT`.
This changes to read from the project registry:

```python
# Current (single project):
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ADS_PATH = os.path.join(PROJECT_ROOT, "_cortex", "ads", "events.jsonl")

# New (multi-project):
REGISTRY = load_registry()  # reads ~/.adt/projects.json
FRAMEWORK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# Data paths resolved per-request based on ?project= parameter
```

### 7.2 API Changes

All existing API endpoints gain an optional `project` query parameter:

| Endpoint | Without `?project=` | With `?project=taskflow` |
|----------|---------------------|--------------------------|
| `GET /api/ads/events` | Events from ALL projects (tagged) | Events from taskflow only |
| `GET /api/tasks` | Tasks from ALL projects (tagged) | Tasks from taskflow only |
| `GET /api/specs` | Specs from ALL projects (tagged) | Specs from taskflow only |
| `GET /api/governance/roles` | Roles from active project | Roles from taskflow |

Each response item includes a `project` field identifying which project it belongs to.

### 7.3 New Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/projects` | GET | List all registered projects with status |
| `GET /api/projects/<name>` | GET | Detailed project info (path, port, stats) |
| `POST /api/projects/init` | POST | Trigger `adt init` from the web UI |

### 7.4 Dashboard Changes

The dashboard page gains a project selector dropdown at the top. When "All Projects"
is selected, the dashboard shows aggregated stats. When a specific project is
selected, it shows that project's data only.

A new "Projects" page lists all governed projects with:
- Project name and path
- DTTP status (running/stopped, port)
- ADS event count
- Active specs and tasks count
- Quick actions (start/stop DTTP, open project)

---

## 8. Operator Console Multi-Project Changes

### 8.1 Session Creation

The session creation dialog (SPEC-021 Section 7.1) gains a project picker:

```
+----------------------------------+
|  NEW SESSION                     |
|                                  |
|  Project: [adt-framework    v]   |   <-- NEW
|           [taskflow          ]   |
|                                  |
|  Agent:   [Claude Code      v]   |
|  Role:    [Backend_Developer v]  |   <-- Roles loaded from selected project
|                                  |
|  [Launch]  [Cancel]              |
+----------------------------------+
```

When a project is selected, the role dropdown populates from that project's
`config/jurisdictions.json`. The agent session is spawned with:
- `CWD` set to the project's root directory
- `DTTP_URL` set to the project's DTTP port
- `CLAUDE_PROJECT_DIR` / `GEMINI_PROJECT_DIR` set to the project's root
- `ADT_SPEC_ID` cleared (agent selects spec via hive activation)

### 8.2 Project Grouping

Session tabs in the Console are grouped by project. A subtle divider or color
band separates project groups:

```
| [adt-framework]                    |  [taskflow]               |
| [@Arch] [@Back] [@Front] [@DevOps] |  [@Back] [@Front]         |
```

### 8.3 Context Panel

The context panel shows project-specific data based on the active session's project
tag. Tasks, specs, ADS events, and delegations are filtered to the session's project.

### 8.4 Status Bar

The bottom status bar shows the active project name alongside existing indicators:

```
[PROJECT: taskflow] [DTTP: :5003 connected] [ADS: 12 events] [Sessions: 2]
```

---

## 9. SDK Hook Changes

### 9.1 Project-Aware Hooks

The existing hooks (`claude_pretool.py`, `gemini_pretool.py`) already read
`CLAUDE_PROJECT_DIR` / `GEMINI_PROJECT_DIR` to determine the project root. The
key change is reading the DTTP port from the project's own `config/dttp.json`
instead of defaulting to 5002:

```python
# Current:
dttp_url = os.environ.get("DTTP_URL", "http://localhost:5002")

# New:
dttp_url = os.environ.get("DTTP_URL", read_project_dttp_url(project_dir))

def read_project_dttp_url(project_dir):
    dttp_json = os.path.join(project_dir, "config", "dttp.json")
    if os.path.exists(dttp_json):
        with open(dttp_json) as f:
            return f"http://localhost:{json.load(f).get('port', 5002)}"
    return "http://localhost:5002"  # fallback to framework default
```

### 9.2 Hook Installation

`adt init` installs hooks using absolute paths to the framework's SDK scripts.
This means:
- The hook scripts live in the framework's installation directory (not copied)
- Multiple projects share the same hook code (single source of truth)
- Hook updates propagate to all projects automatically

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit",
        "command": "/home/human/Projects/adt-framework/adt_sdk/hooks/claude_pretool.py"
      }
    ]
  }
}
```

---

## 10. The Sample Project: TaskFlow

### 10.1 Purpose

A minimal but realistic project used to validate external project governance. It
exercises the most common patterns: a Python backend, HTML templates, configuration
files, and tests. Small enough to fully govern, complex enough to expose real issues.

### 10.2 What TaskFlow Is

A simple task management CLI + web app. Features:
- Add, list, complete, and delete tasks
- SQLite storage
- Flask web interface with task list and form
- REST API for programmatic access
- Basic test suite

### 10.3 Directory Structure

```
taskflow/
├── src/
│   ├── __init__.py
│   ├── app.py              # Flask web app
│   ├── api.py              # REST API routes
│   ├── models.py           # SQLite models
│   └── cli.py              # CLI interface
├── templates/
│   ├── base.html
│   ├── index.html
│   └── task.html
├── static/
│   └── style.css
├── tests/
│   ├── test_models.py
│   ├── test_api.py
│   └── test_cli.py
├── config/
│   └── settings.json
├── requirements.txt
├── README.md
└── .gitignore
```

### 10.4 Governance Configuration (After `adt init`)

```
taskflow/
├── _cortex/                    # Added by adt init
│   ├── AI_PROTOCOL.md
│   ├── MASTER_PLAN.md
│   ├── ads/
│   │   └── events.jsonl
│   ├── specs/
│   ├── tasks.json
│   └── ops/
│       ├── active_role.txt
│       └── active_spec.txt
├── config/
│   ├── settings.json           # Project's own config
│   ├── specs.json              # Added by adt init
│   ├── jurisdictions.json      # Added by adt init (Python-detected defaults)
│   └── dttp.json               # Added by adt init (port: 5003)
├── .claude/
│   └── settings.local.json     # Added by adt init (hooks pointing to framework)
├── src/
│   └── ...
└── ...
```

### 10.5 Default Roles for TaskFlow

Generated by `adt init --detect`:

| Role | Jurisdiction | Rationale |
|------|-------------|-----------|
| `Architect` | `_cortex/`, `config/`, `docs/` | Governance artifacts and project config |
| `Backend_Developer` | `src/`, `tests/`, `config/settings.json` | Application code and tests |
| `Frontend_Developer` | `templates/`, `static/` | UI layer |
| `DevOps` | `.github/`, `scripts/`, `Dockerfile` | Build and deployment |

### 10.6 Validation Scenarios

TaskFlow will be used to validate:

| Scenario | Tests |
|----------|-------|
| `adt init` generates correct scaffold | Files created, registry updated |
| DTTP starts on assigned port | Service responds on :5003 |
| Agent hook routes to correct DTTP | Claude/Gemini writes go through :5003, not :5002 |
| Jurisdiction enforcement works | Backend_Developer cannot edit `templates/` |
| ADS logs to project's own events.jsonl | No cross-contamination with framework ADS |
| ADT Center shows both projects | Dashboard aggregates, filter works |
| Console session creation works | Project picker, role loading, correct CWD |
| Spec lifecycle works in external project | Create spec, approve, implement under spec |
| Cross-project agent switching | Agent moves from framework task to TaskFlow task |

---

## 11. Implementation Phases

### Phase A: Foundation (`adt init` + Project Registry)

**Scope:**
- Implement `adt init` command in `adt_core/cli.py`
- Project type detection (Python, Node, Rust, Go, Generic)
- Scaffold generation (`_cortex/`, `config/` files)
- Project registry (`~/.adt/projects.json`) with CRUD operations
- `adt projects list|status|remove|start|stop` commands
- Port auto-assignment logic
- Genesis ADS event written on init

**Acceptance:**
- `adt init /path/to/taskflow` creates complete governance scaffold
- `adt projects list` shows both adt-framework and taskflow
- `adt projects start taskflow` launches DTTP on :5003
- TaskFlow's DTTP responds to `GET /status` with correct project name

**Assigned to:** Backend_Engineer + DevOps_Engineer

### Phase B: DTTP Isolation

**Scope:**
- Add `from_project_dttp_json()` to `DTTPConfig`
- Add `is_framework_project` flag to `DTTPConfig`
- Sovereign/constitutional path checks conditional on `is_framework_project`
- Update `service.py` to read port from project's `config/dttp.json`
- Update SDK hooks to read DTTP URL from project's `config/dttp.json`
- Hook installation via `adt init` (absolute paths to framework SDK)

**Acceptance:**
- Framework DTTP on :5002 enforces sovereign paths
- TaskFlow DTTP on :5003 does NOT enforce sovereign paths
- Claude hook in TaskFlow routes writes to :5003
- Agent working in TaskFlow cannot write outside TaskFlow jurisdictions
- Agent working in framework cannot accidentally hit TaskFlow's DTTP

**Assigned to:** Backend_Engineer

### Phase C: ADT Center Aggregation

**Scope:**
- Refactor `app.py` to load project registry
- Add `?project=` filter to all API endpoints
- Add `project` field to all API response items
- New `GET /api/projects` endpoint
- New "Projects" page in web UI
- Dashboard project selector dropdown
- ADS event aggregation from multiple `events.jsonl` files

**Acceptance:**
- `GET /api/ads/events` returns events from both projects, tagged
- `GET /api/ads/events?project=taskflow` returns only TaskFlow events
- Dashboard shows project selector
- Projects page lists both projects with live status

**Assigned to:** Backend_Engineer + Frontend_Engineer

### Phase D: Console Integration

**Scope:**
- Session creation dialog gains project picker
- Roles load dynamically from selected project's `jurisdictions.json`
- Session tabs grouped by project
- Context panel project-aware
- Status bar shows active project
- `adt init` from Console (via API)

**Acceptance:**
- Can create a session for TaskFlow with correct roles
- Session CWD is TaskFlow's root directory
- Context panel shows TaskFlow's tasks and ADS events
- Can run both framework and TaskFlow sessions in same Console window

**Assigned to:** Frontend_Engineer + DevOps_Engineer

### Phase E: Sample Project & Validation

**Scope:**
- Create the TaskFlow sample project
- Run `adt init` against it
- Execute all validation scenarios from Section 10.6
- Document findings: what worked, what broke, what needs refinement
- Write integration tests for multi-project governance
- Update framework documentation

**Acceptance:**
- All 9 validation scenarios pass
- At least one full governance cycle completed on TaskFlow:
  write spec -> approve -> assign task -> agent implements -> DTTP enforces -> ADS logs
- Findings documented in `_cortex/docs/external_project_findings.md`

**Assigned to:** Systems_Architect + Backend_Engineer

---

## 12. What This Does NOT Cover (Future Specs)

1. **Remote project governance** -- governing a project on a remote server via SSH/tunnel
   (SPEC-024 territory)
2. **Project templates** -- pre-built governance configs for common frameworks
   (Django, Next.js, Rails, etc.)
3. **Multi-user governance** -- different humans governing different projects on the
   same machine
4. **Project migration** -- importing governance from another system
5. **Governance inheritance** -- child projects inheriting parent project rules
6. **Project archival** -- gracefully decommissioning governance from a completed project

---

## 13. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Port collisions on developer machines | DTTP instances fail to start | Auto-assignment + collision detection in registry |
| Config directory conflicts (`config/`) | External project already has `config/` | `adt init` merges; governance files have distinctive names |
| Hook path fragility | Hooks break if framework moves | Use symlinks or `~/.adt/framework_path` indirection |
| ADS performance with many projects | Center slows under aggregation | Lazy loading, per-project caching, pagination (already in SPEC-018) |
| Complexity creep | Multi-project adds cognitive load | Progressive disclosure: single-project is the default experience |
| Framework self-governance regression | Changes break framework's own governance | Framework tests run in CI; framework is always the first validation target |

---

## 14. Impact on Existing Specs

| Spec | Impact |
|------|--------|
| SPEC-014 (DTTP) | Minor: `is_framework_project` flag controls sovereign checks |
| SPEC-015 (Center) | Moderate: data loading refactored for multi-project |
| SPEC-017 (Repository) | None: framework structure unchanged |
| SPEC-019 (DTTP Service) | Minor: port read from project config |
| SPEC-020 (Self-Governance) | Minor: sovereign/constitutional checks framework-only |
| SPEC-021 (Console) | Moderate: project picker, session grouping |
| SPEC-025 (Bootstrap) | Synergy: `adt init` replaces parts of bootstrap flow |
| SPEC-027 (Shatterglass) | None: OS-level enforcement is per-project already |

---

## 15. ADT Compliance

1. **Governance by Construction:** External projects get governance scaffolding at
   init time, not as a retrofit. The `_cortex/` directory is part of the project
   from day one.

2. **Single Source of Truth:** Each project has its own ADS. The registry is the
   single source of truth for project membership. No shadow state.

3. **Traceability:** Every `adt init`, project registration, and DTTP start/stop
   is logged to the framework's own ADS (meta-governance).

4. **Accountability:** Agent sessions are tagged with their project. ADS events
   include a `project` field. Cross-project actions are impossible by design
   (DTTP instances are isolated).

5. **Fail-Closed:** If a project's DTTP is not running, hooks fail-closed and
   block writes. The framework's own DTTP continues independently.

---

## 16. Acceptance Criteria

### Core Functionality
- [ ] `adt init <path>` scaffolds governance in any directory
- [ ] Project type detection suggests appropriate jurisdictions
- [ ] Project registry tracks all governed projects
- [ ] Each project runs its own DTTP instance on a unique port
- [ ] ADS events are isolated per project (no cross-contamination)

### Multi-Project Operations
- [ ] `adt projects list` shows all registered projects with status
- [ ] `adt projects start/stop <name>` manages per-project DTTP lifecycle
- [ ] Multiple DTTP instances run simultaneously without conflicts
- [ ] SDK hooks route to the correct project's DTTP based on CWD

### Unified Visibility
- [ ] ADT Center aggregates data from all governed projects
- [ ] API endpoints support `?project=` filtering
- [ ] Dashboard shows project selector with per-project and aggregate views
- [ ] Console session creation includes project picker

### Sample Project Validation
- [ ] TaskFlow sample project created and governed
- [ ] Full governance cycle completed on TaskFlow
- [ ] All 9 validation scenarios from Section 10.6 pass
- [ ] Findings documented

### Backward Compatibility
- [ ] Framework self-governance continues unchanged
- [ ] Existing single-project workflows function without modification
- [ ] No breaking changes to existing API contracts (new fields are additive)

---

## 17. Approval

**Human Approval Required:** YES

This spec introduces multi-project governance -- a fundamental architectural change
to the ADT Framework. Implementation should not proceed until human approves this
design.

---

*"A governance framework that only governs itself is a thought experiment.
A governance framework that governs real projects is infrastructure."*
*-- ADT Framework (Sheridan, 2026)*

## 18. Amendment A: Multi-Project Isolation Hardening

**Author:** CLAUDE (Systems_Architect)
**Date:** 2026-02-18
**Status:** DRAFT (pending human approval)
**Supersedes:** Sections 2.1, 3.1, 6.2, 7.2, 8.1-8.4, and adds new constraints

---

### A.0 Motivation

The original SPEC-031 treated the ADT Framework as "project zero" -- first among equals
in the registry. Field experience reveals this creates dangerous ambiguity:

1. Agents on external projects inherit framework-only tier elevation rules (git_tag, git_push)
2. Shatterglass could theoretically be pointed at external projects with no feedback
3. The Projects page and Console mix framework with governed projects, creating confusion
4. Console panels always show framework data regardless of which project the session targets

This amendment establishes a hard architectural boundary: the framework is an **internal
forge** (infrastructure tooling), and external projects are **governed tenants** locked
to Tier 3. They are fundamentally different categories, not just a boolean flag.

> "The forge builds the tools. The tools govern the projects.
> The projects never modify the forge."

---

### A.1 Project Classification (replaces `is_framework` boolean)

Projects are classified by `project_type`:

| Type | Count | Description |
|------|-------|-------------|
| `forge` | Exactly 1 | The ADT Framework itself. Internal development infrastructure. |
| `governed` | 0..N | External projects under ADT governance. Tenants. |

The `project_type` field is added to the registry entry alongside the existing
`is_framework` boolean (which remains for backward compatibility).

```json
{
  "adt-framework": {
    "path": "/home/human/Projects/adt-framework",
    "dttp_port": 5002,
    "project_type": "forge",
    "is_framework": true
  },
  "taskflow": {
    "path": "/home/human/Projects/taskflow",
    "dttp_port": 5003,
    "project_type": "governed",
    "is_framework": false
  }
}
```

**Registry API additions:**
- `list_governed_projects()` -- returns only `project_type == "governed"` entries
- `get_forge()` -- returns the single forge project (or None)
- `is_forge(name)` -- convenience boolean check
- Backward compat: if `project_type` is missing, derive from `is_framework`

**Files:** `adt_core/registry.py`

---

### A.2 Tier 3 Enforcement for All External Projects (replaces Section 6.2)

External (governed) projects are **structurally locked to Tier 3**. This is not
configurable -- it is enforced in the gateway code based on `project_type`.

**What this means:**

| Protection | Framework (forge) | External (governed) |
|-----------|-------------------|---------------------|
| Sovereign paths (Tier 1) | YES -- hardcoded list | NO -- not applicable |
| Constitutional paths (Tier 2) | YES -- hardcoded list | NO -- not applicable |
| Git action tier elevation (Tier 2) | YES -- git_tag, git_push main | NO -- stays Tier 3 |
| Shatterglass privilege escalation | YES -- human-only | NO -- blocked entirely |
| Jurisdiction enforcement (Tier 3) | YES -- from config | YES -- from config |
| Policy engine validation (Tier 3) | YES -- from config | YES -- from config |
| Path containment | YES | YES |

**Gateway change:** The git tier-2 elevation check (currently unconditional) is
wrapped in an `if self.is_framework:` guard:

```python
# BEFORE (applies to all projects -- BUG):
if action == "git_tag":
    is_tier2 = True
elif action == "git_push" and params.get("branch") == "main":
    is_tier2 = True

# AFTER (framework only):
if self.is_framework:
    if action == "git_tag":
        is_tier2 = True
    elif action == "git_push" and params.get("branch") == "main":
        is_tier2 = True
```

**Path containment:** The gateway adds a path containment check after normalizing
the file path. The resolved absolute path must fall within the project root directory.
Any path that escapes (via `../` traversal) is denied with reason
`path_outside_project_root` and logged with `escalation: true`.

**Files:** `adt_core/dttp/gateway.py`, `adt_core/dttp/service.py`

---

### A.3 Shatterglass Exclusion (extends SPEC-027)

The Shatterglass Protocol is **exclusively available for the forge**. External
governed projects cannot use it. Period.

**Behavior when targeting external project:**
1. Print explicit refusal: "Shatterglass Protocol is exclusively for the ADT
   Framework (forge). External governed projects operate at Tier 3 only.
   No privilege escalation is possible."
2. Log `shatterglass_denied_external` event to framework ADS
3. Return without modifying any files or permissions

**Why:** Shatterglass exists to temporarily elevate human access to sovereign
files in the framework's own governance. External projects have no sovereign
files -- their governance config is editable by their own Architect role at
Tier 3. There is nothing to escalate.

**Files:** `adt_core/cli.py`

---

### A.4 API Separation: Forge vs Governed (replaces Section 7.2-7.3)

The API creates distinct endpoints that enforce the forge/governed boundary:

| Endpoint | Returns |
|----------|---------|
| `GET /api/projects` | Only `governed` projects (never includes forge) |
| `GET /api/forge` | Framework (forge) project metadata only |
| `GET /api/projects/all` | All projects including forge (admin/debug use) |

The existing `?project=` filter on data endpoints (`/api/tasks`, `/api/specs`,
`/api/ads/events`, `/api/governance/requests`, `/api/governance/delegations`)
continues to work. When `?project=` is omitted, these endpoints return data from
the **active project context** (not aggregated from all projects).

**Broken endpoints to fix:**
- `GET /api/governance/requests` -- currently hardcodes framework root path.
  Must honor `?project=` parameter using `_get_project_resources()`.
- `GET /api/governance/delegations` -- same issue. Must use project-aware
  data loading instead of global `app.ads_query` and `app.task_manager`.

**Files:** `adt_center/app.py`, `adt_center/api/governance_routes.py`

---

### A.5 UI Separation (replaces Section 7.4, extends Section 8)

#### Projects Page (ADT Center)

The Projects page shows **only governed projects**. The framework is NOT listed
in the project grid. Instead, a small collapsible status indicator at the top
shows forge status (DTTP port, uptime). Each governed project card displays a
"Tier 3" badge to reinforce enforcement level.

#### Console Project Picker

The Console session creation dropdown separates forge from governed using
HTML `<optgroup>` elements:

```
+-- Internal Forge --------+
|  adt-framework (forge)   |
+-- Governed Projects -----+
|  taskflow (/path/to/...) |
|  myapp (/path/to/...)    |
+--------------------------+
```

#### Console Context Panel (CRITICAL BUG FIX)

The context panel, Hive Tracker, and governance panel currently ignore project
context entirely. All fetch calls go to the API without `?project=` parameter,
so they always return framework data regardless of which session is active.

**Fix:** Every data fetch in `context.js` and `governance.js` must include
`?project=${projectName}` derived from the active session's project tag.
The session object carries the project as `cwd` (or a new `project` field).
When the user switches sessions, panel data reloads for the new session's
project.

| File | Functions to fix |
|------|-----------------|
| `context.js` | `fetchRequests()`, `fetchDelegations()`, `fetchSpecs()`, `fetchTaskData()`, `fetchADSEvents()` |
| `governance.js` | `fetchAll()` (3 parallel fetches) |
| `app.js` | `loadProjects()` (separate forge from governed in dropdown) |

**Files:** `adt-console/src/js/context.js`, `adt-console/src/js/governance.js`,
`adt-console/src/js/app.js`, `adt_center/templates/projects.html`

---

### A.6 Hook Auto-Installation (documents existing behavior)

When `adt init` is run on a new project, hooks are automatically installed
for detected agent CLIs:

- **Claude Code:** `.claude/settings.local.json` with `PreToolUse` hook
  pointing to framework's `adt_sdk/hooks/claude_pretool.py` (absolute path)
- **Gemini CLI:** `.gemini/settings.json` with equivalent `BeforeTool` hook

Hook scripts read the DTTP URL from the project's own `config/dttp.json`,
ensuring enforcement routes to the correct per-project DTTP instance.

This is already implemented in `adt_core/cli.py:install_hooks()`. This
amendment documents it as a mandatory part of the `adt init` contract.

**Files:** `adt_core/cli.py` (existing, no changes needed)

---

### A.7 Isolation Invariants (new section)

These invariants MUST hold at all times:

1. **Port isolation:** Each project's DTTP runs on a unique port. No sharing.
2. **ADS isolation:** Each project writes to its own `_cortex/ads/events.jsonl`. Events never cross-contaminate between projects.
3. **Jurisdiction isolation:** Each project defines its own roles and paths in its own `config/jurisdictions.json`. Framework jurisdictions do not apply to external projects.
4. **Path containment:** The DTTP gateway denies any file operation that resolves outside the project root directory.
5. **Tier isolation:** External projects cannot access Tier 1 or Tier 2 protections. These are forge-only concepts.
6. **Shatterglass isolation:** External projects cannot trigger Shatterglass. Attempts are denied and logged.
7. **UI isolation:** Console panels show data from the active session's project only. No accidental framework data leakage into external project views.

---

### A.8 Implementation Tasks

| Task | Description | Priority |
|------|-------------|----------|
| Registry: add `project_type` field | Add field to registry, helper methods | high |
| Gateway: tier-3 lock for external projects | Wrap git tier-2 checks in `is_framework` guard | critical |
| Gateway: path containment check | Deny paths resolving outside project root | critical |
| Shatterglass: explicit external refusal | Print error, log to ADS, return | high |
| API: separate forge from governed endpoints | Split `/api/projects`, add `/api/forge` | high |
| API: fix `/requests` and `/delegations` | Honor `?project=` parameter | high |
| Console: project-aware panel fetching | Add `?project=` to all fetch calls in context.js, governance.js | critical |
| Console: project picker separation | Optgroup labels for forge vs governed | medium |
| Projects page: exclude forge from grid | Template change, forge status bar | medium |
| Spec amendment documentation | This document | done |

---

### A.9 Acceptance Criteria (Amendment A)

- [ ] `project_type` field present in registry entries
- [ ] `git_tag` action on external project stays Tier 3 (no elevation)
- [ ] `git_push` to main on external project stays Tier 3 (no elevation)
- [ ] Path traversal (`../../etc/passwd`) denied on all projects
- [ ] `adt shatterglass activate --project taskflow` prints refusal
- [ ] `GET /api/projects` returns only governed projects
- [ ] `GET /api/forge` returns framework metadata
- [ ] Console panels show correct project data when session switches
- [ ] `/api/governance/requests?project=taskflow` returns taskflow requests
- [ ] Projects page does not list framework in main grid

---

### A.10 Governance File Protection in External Projects (Defense in Depth)

#### The Problem

Every governed project contains files that control its own enforcement rules:

```
config/jurisdictions.json   -- defines who can access what
config/specs.json           -- defines what specs authorize what actions
config/dttp.json            -- defines DTTP port and enforcement mode
_cortex/AI_PROTOCOL.md      -- governance protocol
_cortex/MASTER_PLAN.md      -- project plan and spec registry
```

If an agent can modify any of these, it can rewrite the rules that govern it.
This is **self-modification** -- the fundamental violation that SPEC-020 was
designed to prevent in the framework.

The forge solves this with Sovereign Paths (Tier 1) and Shatterglass. External
projects need equivalent protection but through their own mechanism.

#### Solution: Two-Layer Defense (Belt and Suspenders)

**Layer 1: DTTP Gateway Enforcement (Software)**

The gateway maintains a `GOVERNANCE_LOCKED` path list that applies to ALL
projects (forge and governed alike). These paths are always denied to agents
regardless of role, spec, or jurisdiction configuration:

```python
# Hardcoded in gateway.py -- cannot be configured away
GOVERNANCE_LOCKED = [
    "config/jurisdictions.json",
    "config/specs.json",
    "config/dttp.json",
    "_cortex/AI_PROTOCOL.md",
    "_cortex/MASTER_PLAN.md",
]
```

When an agent attempts to write to a governance-locked path:
1. DTTP denies the request immediately (before jurisdiction check)
2. Logs `governance_lock_violation` to the project's ADS
3. Returns denial with reason `governance_file_protected`
4. Sets `escalation: true` for human visibility

**This check runs BEFORE jurisdiction validation.** Even if an Architect role
has `config/` in its jurisdiction, governance-locked files within that path
are still denied. The jurisdiction grants access to other files in `config/`
(like `config/settings.json`) but never to the governance files.

**Relationship to forge sovereign paths:** In the forge, `SOVEREIGN_PATHS`
continues to exist as a superset concept (includes the sovereign denial and
break-glass protocol). `GOVERNANCE_LOCKED` is a simpler check -- pure denial,
no break-glass, no Shatterglass. For the forge, both checks run (sovereign
first, governance-locked is redundant but harmless).

**Layer 2: OS-Level File Permissions (Hardware)**

When `setup_shatterglass.sh` (SPEC-027) is run for a governed project,
governance files are set to permissions that prevent agent OS users from
writing:

```
config/jurisdictions.json   human:human 644  (owner read/write, others read-only)
config/specs.json           human:human 644
config/dttp.json            human:human 644
_cortex/AI_PROTOCOL.md      human:human 644
_cortex/MASTER_PLAN.md      human:human 644
```

The `agent` OS user (which agent CLIs run as in production) physically cannot
write to these files. Even if the DTTP gateway has a bug, the OS blocks it.

**When each layer catches violations:**

| Scenario | Layer 1 (DTTP) | Layer 2 (OS) |
|----------|---------------|--------------|
| Development mode (same OS user) | Catches it | Not active |
| Production mode (separate OS users) | Catches it | Also catches it |
| DTTP service is down | Fail-closed blocks all writes | Catches it |
| DTTP has a bypass bug | Missed | Catches it |
| Agent uses shell directly (no hook) | Missed | Catches it |

#### How the Human Edits Governance Files

The human modifies governance files through:

1. **ADT Center web UI** -- The Governance Configurator (SPEC-026) provides
   a visual editor for jurisdictions and specs. These API endpoints write
   directly as the human user (not through DTTP).
2. **Direct file editing** -- The human opens the file in their editor.
   No DTTP check applies to human file access.
3. **CLI commands** -- `adt` CLI commands that modify governance configs
   run as the human user.

Agents NEVER modify governance files. If an agent needs a jurisdiction change,
it submits a request to `_cortex/requests.md` and the human reviews it through
the Center UI.

#### ADS Event Schema

```json
{
  "action_type": "governance_lock_violation",
  "description": "DENIED: Agent attempted to modify governance-locked file config/jurisdictions.json",
  "tier": 1,
  "escalation": true,
  "authorized": false
}
```

#### Implementation

**File:** `adt_core/dttp/gateway.py`

Add governance lock check BEFORE sovereign path check. It runs for all
projects (forge and governed):

```python
# 0. Governance Lock Check -- applies to ALL projects
if normalized_path in GOVERNANCE_LOCKED:
    # Log and deny
    return {"status": "denied", "reason": "governance_file_protected"}

# 1. Sovereign Path Check (Tier 1) -- forge only
if self.is_framework and normalized_path in SOVEREIGN_PATHS:
    # ... existing sovereign logic
```

**File:** `scripts/setup_shatterglass.sh`

Extend to accept `--project <path>` flag. When targeting an external project,
sets governance file permissions to `human:human 644` without the full
Shatterglass activation/deactivation ceremony (no timer, no session token).
This is a one-time setup, not a temporary escalation.

**Files:** `adt_core/dttp/gateway.py`, `scripts/setup_shatterglass.sh`

---

### A.11 Updated Isolation Invariants (replaces A.7)

These invariants MUST hold at all times:

1. **Port isolation:** Each project's DTTP runs on a unique port. No sharing.
2. **ADS isolation:** Each project writes to its own `_cortex/ads/events.jsonl`.
   Events never cross-contaminate between projects.
3. **Jurisdiction isolation:** Each project defines its own roles and paths in
   its own `config/jurisdictions.json`. Framework jurisdictions do not apply
   to external projects.
4. **Path containment:** The DTTP gateway denies any file operation that
   resolves outside the project root directory.
5. **Tier isolation:** External projects operate at Tier 3 only. No Tier 1/2
   elevation is possible.
6. **Governance lock:** Governance configuration files (`jurisdictions.json`,
   `specs.json`, `dttp.json`, `AI_PROTOCOL.md`, `MASTER_PLAN.md`) are denied
   to ALL agents in ALL projects at the DTTP level. OS permissions provide
   secondary enforcement in production.
7. **Shatterglass isolation:** External projects cannot trigger Shatterglass.
   Attempts are denied and logged.
8. **UI isolation:** Console panels show data from the active session's project
   only. No accidental framework data leakage into external project views.

---

### A.12 Forge-to-Project Governance Propagation (amends A.10)

#### Principle

> "A project's own agents cannot modify its governance files.
> The forge can push updates to all governed projects."

The GOVERNANCE_LOCKED check in A.10 blocks agents operating **within a
project's own DTTP instance** from modifying that project's governance files.
But the forge -- as the central governance authority -- retains the ability
to propagate governance updates to all governed projects.

#### Use Case

1. A flaw is discovered in how `jurisdictions.json` handles path matching
2. A forge agent (Backend_Engineer) fixes the template/schema in the framework
3. The human reviews and approves the fix
4. The fix is propagated to taskflow and all other governed projects via
   `adt governance apply`

#### Mechanism: `adt governance apply`

New CLI command under the `adt` tool:

```bash
# Apply governance update to a specific project
adt governance apply <project-name> [--file jurisdictions.json|specs.json|dttp.json|AI_PROTOCOL.md]

# Apply to all governed projects
adt governance apply --all [--file jurisdictions.json]

# Preview changes without applying (dry run)
adt governance apply <project-name> --dry-run
```

**How it works:**

1. Reads the governance template/fix from the forge's own config or a
   designated update payload
2. Validates the update against the project's current state (diff preview)
3. Writes the updated governance file to the target project
4. Logs `governance_propagated` event to BOTH the forge ADS and the
   project's ADS (dual-logged for traceability)
5. Restarts the project's DTTP service to pick up the new config

**Authorization:**

| Actor | Can propagate? | Mechanism |
|-------|---------------|-----------|
| Human (direct) | YES | `adt governance apply` CLI |
| Forge agent (via DTTP) | YES | Forge DTTP authorizes writes to governed project governance paths |
| Project's own agent | NO | Project DTTP denies via GOVERNANCE_LOCKED |

**Key distinction:** The forge's DTTP instance (port 5002) can authorize a
forge agent to write governance files in external projects. The project's own
DTTP instance (port 5003+) always denies its own agents from writing those
same files. The enforcement is per-DTTP-instance, not per-file.

#### Updated GOVERNANCE_LOCKED Logic

```python
# In gateway.py request():

# 0. Governance Lock Check
if normalized_path in GOVERNANCE_LOCKED:
    if self.is_framework:
        # Forge agents CAN write governance files in external projects
        # (the path will be in an external project's directory)
        # Normal sovereign check still applies for forge's OWN governance files
        pass  # Fall through to sovereign check below
    else:
        # Project's own agents CANNOT modify their own governance files
        return {"status": "denied", "reason": "governance_file_protected"}
```

For the forge, the existing SOVEREIGN_PATHS check (Tier 1) still protects
the forge's own `config/jurisdictions.json`. But when a forge agent targets
an external project's `config/jurisdictions.json`, the sovereign check does
not apply (it only protects forge paths), and the governance lock allows it
because `is_framework=True`.

#### ADS Event Schema

```json
{
  "action_type": "governance_propagated",
  "description": "Propagated jurisdictions.json update to project 'taskflow'",
  "spec_ref": "SPEC-031",
  "tier": 1,
  "authorized": true,
  "action_data": {
    "source": "forge",
    "target_project": "taskflow",
    "file": "config/jurisdictions.json",
    "diff_summary": "Added path containment rule to Backend_Developer role"
  }
}
```

#### Propagation Flow Diagram

```
   FORGE (adt-framework)                    GOVERNED PROJECT (taskflow)
   =====================                    ==========================

   1. Bug discovered in
      jurisdiction handling
           |
   2. Backend_Engineer fixes
      template in forge
           |
   3. Human approves fix
           |
   4. adt governance apply taskflow
           |
           +---> Forge DTTP (:5002)
                 validates forge agent
                 has authority
                      |
                      +---> Writes to taskflow/config/jurisdictions.json
                      |
                      +---> Logs to forge ADS (governance_propagated)
                      |
                      +---> Logs to taskflow ADS (governance_received)
                      |
                      +---> Restarts taskflow DTTP (:5003)

   Project's own agents (on :5003)
   CANNOT modify jurisdictions.json
   at any point in this flow.
```

#### Safety Constraints

1. **Human approval required:** The `adt governance apply` command requires
   human confirmation (interactive prompt) unless `--yes` flag is passed.
2. **Diff preview:** Always shows what will change before applying.
3. **Dual ADS logging:** Both forge and project get events for traceability.
4. **Rollback:** Previous governance file is backed up to
   `config/.governance_backup/jurisdictions.json.<timestamp>` before overwrite.
5. **No cascading:** Propagation does not trigger further propagations.
   One level only.
