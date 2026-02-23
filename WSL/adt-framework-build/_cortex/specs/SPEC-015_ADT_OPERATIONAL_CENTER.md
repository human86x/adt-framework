# SPEC-015: ADT Operational Center

**Status:** APPROVED
**Priority:** CRITICAL
**Owner:** Systems_Architect + Human
**Created:** 2026-02-05
**References:** ADT Whitepaper (Sheridan, 2026), SPEC-014 (DTTP), SPEC-003 (Static Panel - superseded)
**Framework Origin:** ADT Section 2 -- "DTTP as an open-source application layer, analogous to platforms such as Apache"

---

## 1. Purpose

This spec defines the **ADT Operational Center** -- a standalone Flask application that IS the ADT Framework incarnated as software. It is the human's governance interface and the DTTP enforcement engine in one application.

### 1.1 The Core Principle

**The ADT Framework is not part of the project it governs.** A court system is not part of the businesses it regulates. A building code is not part of the building. The ADT Operational Center is an independent application that connects TO governed projects, enforces their governance, and provides human oversight.

### 1.2 What This Changes

```
BEFORE (static panel):
  _cortex/ads/events.jsonl → compile_ads.py → data.json → FTP → static HTML
  Human reads display. No interaction. Approvals done via terminal commands.
  Agents self-enforce. Trust-based.

AFTER (ADT Operational Center):
  ADT Flask App ← reads → project ADS, specs, tasks
  ADT Flask App ← API → agents submit DTTP requests
  ADT Flask App ← web → human approves, clears, manages
  ADT Flask App → mirror → oceanpulse.pt (public read-only display)
```

### 1.3 Relationship to Other Specs

```
ADT Whitepaper (Sheridan, 2026)
├── ADT_CONSTITUTION.md (principles)
├── AI_PROTOCOL.md (agent rules -- updated for DTTP)
├── SPEC-003 (static panel) ──► SUPERSEDED by this spec
│   └── oceanpulse.pt/adt_panel/ becomes public mirror only
├── SPEC-014 (DTTP engine) ──► INCORPORATED into this app
│   └── gateway.py becomes a Flask module, not a CLI tool
└── SPEC-015 (this spec) ──► ADT as a real application
```

---

## 2. Architecture

### 2.1 Separation of Framework and Project

```
INDEPENDENT CODEBASE:
/home/human/Projects/adt_framework/          # The ADT app (its own repo)
├── app.py                                   # Flask application entry
├── dttp/                                    # DTTP engine module
│   ├── gateway.py                           # Validation + execution
│   ├── engine.py                            # File ops, SSH, FTP proxying
│   └── chain.py                             # Hash chain + ADS logging
├── api/                                     # API blueprints
│   ├── dttp_routes.py                       # Agent-facing DTTP endpoints
│   ├── governance_routes.py                 # Human-facing governance endpoints
│   └── ads_routes.py                        # ADS query endpoints
├── ui/                                      # Web interface
│   ├── templates/                           # Jinja2 templates
│   └── static/                              # CSS, JS
├── config/
│   ├── projects.json                        # Governed project connections
│   └── secrets.json                         # Credentials (mode 600, owner dttp)
├── mirror/                                  # Static export generator
│   └── export.py                            # Compile to static HTML for public mirror
├── tests/                                   # Unit + integration tests
└── requirements.txt

GOVERNED PROJECT (unchanged):
/home/human/Projects/oceanpulse_phase_one/   # The project being governed
├── _cortex/
│   ├── ads/events.jsonl                     # ADS (written by ADT app only)
│   ├── specs/                               # Spec files
│   ├── active_tasks/                        # Lock files
│   └── tasks.json                           # Task registry
├── firmware/                                # Project code
├── obs_center/                              # Project code
└── ...
```

The ADT app reads and writes the project's `_cortex/` directory. It could theoretically govern multiple projects.

### 2.2 Runtime Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   ADT OPERATIONAL CENTER                     │
│                   (Flask App, runs as dttp user)             │
│                   http://localhost:5001                       │
│                                                             │
│  ┌───────────────────────┐  ┌────────────────────────────┐  │
│  │   WEB UI (Human)      │  │   API (Agents)             │  │
│  │                       │  │                            │  │
│  │   /                   │  │   POST /dttp/request       │  │
│  │   /ads                │  │   GET  /dttp/status        │  │
│  │   /specs              │  │                            │  │
│  │   /tasks              │  │   Authentication:          │  │
│  │   /escalations        │  │   Agent session token      │  │
│  │   /sessions           │  │   validated against ADS    │  │
│  │   /dttp               │  │                            │  │
│  │   /mirror             │  │                            │  │
│  └───────────┬───────────┘  └──────────┬─────────────────┘  │
│              │                         │                    │
│              ▼                         ▼                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              DTTP ENGINE                              │   │
│  │                                                      │   │
│  │   1. Validate (spec, jurisdiction, locks, role)      │   │
│  │   2. Execute (local write / SSH / FTP)               │   │
│  │   3. Log (atomic ADS entry with hash chain)          │   │
│  │   4. Return result                                   │   │
│  │                                                      │   │
│  │   Fail-closed: any error = DENY                      │   │
│  └──────────────────────────────────────────────────────┘   │
│              │                                              │
└──────────────┼──────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  GOVERNED PROJECT: /home/human/Projects/oceanpulse_phase_one │
│                                                              │
│   _cortex/ads/events.jsonl    (read/write by ADT app)        │
│   _cortex/specs/*.md          (read/write by ADT app)        │
│   _cortex/tasks.json          (read/write by ADT app)        │
│   firmware/                   (write via DTTP only)          │
│   obs_center/                 (write via DTTP only)          │
│   adt_panel/                  (write via DTTP only)          │
└──────────────────────────────────────────────────────────────┘
               │
               │ (periodic static export)
               ▼
┌──────────────────────────────────────────────────────────────┐
│  PUBLIC MIRROR: oceanpulse.pt/adt_panel/                     │
│                                                              │
│   Static HTML + data.json (read-only, no interaction)        │
│   For external stakeholders, regulators, Paul Sheridan       │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 Three-User Model (Inherited from SPEC-014)

| User | Role | Access |
|------|------|--------|
| `human` | Project owner | Full access everywhere. Launches AI tools as `agent`. Accesses ADT web UI directly. |
| `agent` | AI tools (Claude/Gemini) | Read-only project files. Can ONLY reach `localhost:5001` (ADT API). No direct writes, SSH, FTP. |
| `dttp` | ADT Flask app | Write access to project. Owns credentials. Runs the Flask app. Outbound SSH/FTP allowed. |

### 2.4 Network Model

```
agent user:
  ALLOW:  localhost:5001 (ADT API -- the only write interface)
  ALLOW:  localhost:5000 (Obs Center -- read telemetry)
  ALLOW:  outbound HTTPS to AI API endpoints (Claude/Gemini API)
  DROP:   all other outbound (SSH, FTP, HTTP to arbitrary hosts)

dttp user:
  ALLOW:  all (SSH to Pis, FTP to oceanpulse.pt, etc.)
  LISTENS: localhost:5001

human user:
  ALLOW:  all (unrestricted)
```

---

## 3. Web UI (Human Interface)

### 3.1 Dashboard (`/`)

The landing page. At-a-glance governance status.

- **Active Sessions:** Which agents are running, what role, how long
- **ADS Stats:** Total events, today's events, compliance rate
- **Escalations:** Active count (red badge), recently cleared
- **DTTP Stats:** Requests today, allow rate, denial rate
- **Spec Status:** Approved / Draft / Pending counts
- **Task Progress:** Completed / In Progress / Pending

### 3.2 ADS Timeline (`/ads`)

Live event feed from `events.jsonl`.

- Chronological timeline (newest first)
- Filter by: agent, role, action_type, spec_ref, date range
- Click event to expand full detail (JSON)
- Hash chain integrity indicator (green = valid, red = broken)
- Auto-refresh (configurable interval)
- Export to CSV/JSON

### 3.3 Spec Registry (`/specs`)

All specifications with their status and actions.

- List all specs with status badge (APPROVED / DRAFT / PENDING)
- Click to view full spec content (rendered Markdown)
- **APPROVE button** on non-approved specs (opens confirmation modal)
  - Shows spec title, author, date
  - "I have reviewed this specification and approve it for execution"
  - On confirm: updates spec .md file status + logs `spec_approved` to ADS + updates `specs.json`
- **REJECT button** with reason field
- Spec coverage matrix (which specs have active work, which are dormant)

### 3.4 Task Board (`/tasks`)

Kanban-style task management.

- Three columns: Pending / In Progress / Completed
- Drag-and-drop to change status (logs to ADS)
- Click task for detail view (description, subtasks, dependencies)
- Assign agent/role
- Dependency graph visualization
- Filter by spec, milestone, role

### 3.5 Escalation Center (`/escalations`)

Active issues requiring human attention.

- Active escalations with severity indicators
- Full event context (what happened, who reported, when)
- **Clear button** with resolution notes
  - On confirm: logs `escalation_resolution` to ADS with `ref_id`
- Resolution chain visualization (problem → fix → verification)
- Historical escalations (cleared, with resolution details)

### 3.6 Agent Sessions (`/sessions`)

Live agent monitoring.

- Currently active sessions (agent, role, start time, event count)
- Session timeline (events within a session)
- Lock status (who holds what locks)
- **Force-release lock** button (emergency, logs escalation)

### 3.7 DTTP Monitor (`/dttp`)

Real-time enforcement visibility.

- Live feed of DTTP requests (allow/deny)
- Denial details (which check failed, what was attempted)
- Response time metrics
- Gateway health status
- Orphan detection (pre-action without post-action)

### 3.8 Mirror Export (`/mirror`)

Public mirror management.

- Preview of what will be exported
- **Export Now** button (compile static HTML + data.json)
- **Deploy to oceanpulse.pt** button (FTP upload via DTTP)
- Last sync timestamp
- Diff view (what changed since last export)

---

## 4. API (Agent Interface)

### 4.1 DTTP Request Endpoint

```
POST /dttp/request
Content-Type: application/json

{
  "agent": "CLAUDE",
  "role": "Embedded_Engineer",
  "session_id": "claude_embedded_20260205",
  "spec_ref": "SPEC-002",
  "action": "edit",
  "file": "firmware/main_mega/main_mega.ino",
  "content": "... file content or diff ...",
  "rationale": "Adding sensor abstraction layer"
}

Response (success):
{
  "status": "allowed",
  "event_id": "evt_20260205_123456_789",
  "result": "file_written",
  "bytes_written": 4096
}

Response (denied):
{
  "status": "denied",
  "reason": "SPEC-002 does not authorise role Frontend_Engineer",
  "check_failed": "spec_role_auth",
  "event_id": "evt_20260205_123456_790"
}
```

### 4.2 DTTP Deploy Endpoint

```
POST /dttp/request
{
  "agent": "CLAUDE",
  "role": "Embedded_Engineer",
  "session_id": "claude_embedded_20260205",
  "spec_ref": "SPEC-002",
  "action": "deploy",
  "target": "pi_main",
  "file": "firmware/main_mega/main_mega.ino",
  "rationale": "Deploying v1.3 firmware with sensor abstraction"
}

Response:
{
  "status": "allowed",
  "event_id": "evt_20260205_123500_001",
  "result": {
    "scp": "success",
    "compile": "success",
    "flash": "success",
    "output": "avrdude: 32768 bytes written..."
  }
}
```

### 4.3 DTTP FTP Sync Endpoint

```
POST /dttp/request
{
  "agent": "CLAUDE",
  "role": "Overseer",
  "session_id": "claude_overseer_20260205",
  "spec_ref": "SPEC-003",
  "action": "ftp_sync",
  "target": "oceanpulse",
  "files": ["data.json", "panel.js", "index.html"],
  "rationale": "Syncing latest ADS compilation to public mirror"
}
```

### 4.4 DTTP Status Endpoint

```
GET /dttp/status

{
  "status": "operational",
  "uptime": "4h 23m",
  "project": "oceanpulse_phase_one",
  "ads_events": 135,
  "chain_integrity": "valid",
  "active_sessions": 2,
  "requests_today": 47,
  "denials_today": 3
}
```

### 4.5 ADS Query Endpoint

```
GET /ads/events?limit=20&agent=CLAUDE&action_type=file_edit

[
  {"id": "evt_...", "ts": "...", ...},
  ...
]
```

### 4.6 Authentication

Agents authenticate using their `session_id`. The ADT app validates:
1. Session exists in ADS (a `session_start` event was logged)
2. Session is not ended (no `session_end` event)
3. Agent and role match the session

The human accesses the web UI directly (localhost -- no external exposure). Future: add login for remote access.

---

## 5. DTTP Engine (Incorporated from SPEC-014)

The DTTP engine from SPEC-014 becomes a Python module inside the ADT app, not a standalone CLI tool.

### 5.1 Validation (5 checks, unchanged from SPEC-014)

1. Role assigned
2. Jurisdiction match (from `config/jurisdictions.json`)
3. No lock conflict (from project's `_cortex/active_tasks/`)
4. Spec exists and is active (from `config/specs.json`)
5. Spec authorises role (from `config/specs.json`)

### 5.2 Execution

- **Local writes:** Direct file I/O (ADT app runs as `dttp` user with write permission)
- **SSH operations:** Paramiko or subprocess SSH using credentials from `config/secrets.json`
- **FTP operations:** ftplib using credentials from `config/secrets.json`

### 5.3 Atomic Logging

Every operation: pre-action log → execute → post-action log. Same semantics as SPEC-014 Section 4.

### 5.4 Fail-Closed

Any error in validation, execution, or logging: DENY. The system never fails open.

---

## 6. Project Connection

### 6.1 projects.json

The ADT app knows which projects it governs:

```json
{
  "version": "1.0",
  "projects": {
    "oceanpulse_phase_one": {
      "path": "/home/human/Projects/oceanpulse_phase_one",
      "ads": "_cortex/ads/events.jsonl",
      "specs_dir": "_cortex/specs",
      "tasks": "_cortex/tasks.json",
      "locks": "_cortex/active_tasks",
      "status": "active"
    }
  }
}
```

Future: add more projects. The ADT app governs them all from one interface.

### 6.2 specs.json and jurisdictions.json

These move from the project directory to the ADT app's `config/` directory. They are project-specific configuration that the ADT app reads. The project itself doesn't need them -- only the governance layer does.

---

## 7. Impact on SPEC-014 (DTTP)

SPEC-014 is **incorporated**, not replaced. The DTTP engine spec remains valid. What changes:

| SPEC-014 Concept | Original Design | SPEC-015 Evolution |
|-----------------|-----------------|-------------------|
| Agent interface | CLI: `dttp request --action edit ...` | API: `POST /dttp/request` |
| Privilege escalation | sudo -u dttp gateway.py | Flask app runs as dttp user natively |
| Human interface | Terminal commands | Web UI at localhost:5001 |
| Spec approval | Edit .md file manually | Click "Approve" in web UI |
| ADS viewing | Read JSONL manually | Live timeline with filters |
| Configuration | Files in _cortex/dttp/ | Files in adt_framework/config/ |

SPEC-014 Phase 4 (Permission Switch) and Phase 5 (Live Enforcement) remain unchanged. The three-user model, iptables rules, and credential isolation all apply.

---

## 8. Implementation Phases

### CRITICAL: Same safe development path as SPEC-014

Phases 1-3 are built under current permissions. The ADT app is developed and tested as a normal Flask app. Phase 4 (SPEC-014 permission switch) activates enforcement. Nothing breaks during development.

### Phase 1: Core App Scaffold

**Deliverables:**
- Flask app with blueprint structure
- DTTP engine module (gateway.py ported from SPEC-014 design)
- Basic API endpoints (POST /dttp/request, GET /dttp/status)
- Project connection config (projects.json, specs.json, jurisdictions.json)
- Unit tests for DTTP engine

**Assigned to:** DevOps_Engineer
**System impact:** ZERO. Separate codebase, separate directory.

### Phase 2: Human Web UI

**Deliverables:**
- Dashboard page
- ADS Timeline (live feed)
- Spec Registry with Approve/Reject buttons
- Task Board
- Escalation Center
- DTTP Monitor

**Assigned to:** Frontend_Engineer + DevOps_Engineer
**System impact:** ZERO. Web UI is independent.

### Phase 3: Integration Testing

**Deliverables:**
- DTTP engine tested against real project structure (copy, not live)
- API tested with simulated agent requests
- Web UI tested with real ADS data
- Shadow mode: ADT app runs alongside current system, observing

**System impact:** ZERO. Testing against copies.

### Phase 4: Permission Switch (SPEC-014 Phase 4)

Same as SPEC-014. Human creates users, sets permissions, configures iptables.

**Additional step:** Start the ADT Flask app as the `dttp` user:
```bash
sudo -u dttp python3 /home/human/Projects/adt_framework/app.py
```

### Phase 5: Live Enforcement

Agents use `POST /dttp/request` for all write operations. Human uses web UI for governance. Public mirror synced periodically.

---

## 9. Tech Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Backend | Flask (Python) | Already in OceanPulse stack, lightweight |
| DTTP Engine | Python module | Same language as existing log.py, gateway logic |
| Web UI | Jinja2 + Bootstrap 5 + vanilla JS | Matches existing ADT panel tech, no build step |
| Live updates | Server-Sent Events (SSE) or polling | Simple, no WebSocket complexity |
| SSH proxy | Paramiko | Pure Python SSH, no shell dependency |
| FTP proxy | ftplib | Python standard library |
| ADS access | Direct JSONL read/append | Same as current, with fcntl locking |
| Hash chain | SHA-256 (hashlib) | Same as current log.py |
| Testing | pytest | Standard Python testing |

---

## 10. Success Criteria

### 10.1 Framework Independence

- [ ] ADT app runs from its own directory (not inside governed project)
- [ ] ADT app connects to project via configuration (projects.json)
- [ ] ADT app could govern a second project with only config changes
- [ ] Removing ADT app does not break the governed project's code

### 10.2 Human Governance

- [ ] Human can approve specs from web UI (logged to ADS)
- [ ] Human can clear escalations from web UI (logged to ADS)
- [ ] Human can view live ADS timeline with filters
- [ ] Human can manage tasks from web UI
- [ ] Human can force-release locks from web UI
- [ ] Human can trigger mirror export and FTP deploy

### 10.3 Agent Enforcement (DTTP)

- [ ] Agents can submit DTTP requests via API
- [ ] All 5 validation checks enforced
- [ ] Local file writes executed and logged atomically
- [ ] SSH deployments executed and logged atomically
- [ ] FTP syncs executed and logged atomically
- [ ] Denials logged with escalation flag
- [ ] Fail-closed on any error

### 10.4 Public Mirror

- [ ] Static export generates functional HTML + data.json
- [ ] FTP deploy to oceanpulse.pt works via DTTP
- [ ] Mirror is read-only (no interaction, no write-back)
- [ ] External stakeholders can view governance state

### 10.5 ADT Whitepaper Alignment

- [ ] "Analogous to platforms such as Apache" -- ADT app IS the application layer
- [ ] "Humans define intent, automation enforces" -- Web UI for intent, DTTP for enforcement
- [ ] "Single Authoritative Data Source" -- ADS is the sole source, UI derives from it
- [ ] "Continuous auditability" -- every UI action logged to ADS
- [ ] "Governance is an intrinsic system property" -- enforced by OS + application layer

---

## 11. What This Is NOT

1. **Not a project management tool.** It's a governance framework. Tasks exist to track governance obligations, not replace Jira.
2. **Not part of OceanPulse.** It governs OceanPulse. It could govern any project.
3. **Not a monitoring system.** The Obs Center monitors the buoy. The ADT Center monitors the development process.
4. **Not optional.** Once activated, the ADT app IS the only write path. It's not an overlay -- it's the foundation.

---

## 12. Amendments

This spec may be amended as implementation reveals practical constraints. All amendments logged to ADS with `spec_ref: SPEC-015`.

---

*"Governance is an intrinsic system property, not an external overlay."*
*-- ADT Framework (Sheridan, 2026)*
