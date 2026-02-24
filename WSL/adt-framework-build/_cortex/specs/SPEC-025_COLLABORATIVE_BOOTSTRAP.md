# SPEC-025: ADT Collaborative Bootstrap

**Status:** APPROVED
**Priority:** HIGH
**Owner:** Systems_Architect (spec), Backend_Engineer + DevOps_Engineer (implementation)
**Created:** 2026-02-13
**References:** SPEC-015 (Operational Center), SPEC-024 (ADT Connect)

---

## 1. Purpose

Enable a remote collaborator (e.g., Paul on Windows 11 + WSL) to experience and contribute to the ADT Framework with a single command. The framework becomes its own development tool: Paul runs v0.3, creates specs that drive v0.4.

> "The framework builds itself through its own governance."

---

## 2. Problem

- Paul has Windows 11 with WSL (Ubuntu) but no Rust, no Tauri, no existing Python env
- He needs to see: specs, tasks, ADS audit trail, DTTP configuration
- He needs to CREATE specs and feedback that sync back to the shared project
- The setup must be a single file, zero prior knowledge required

---

## 3. Architecture

### 3.1 What Paul Gets

A **Git clone** (or zip) of the `adt-framework` repository containing a `bootstrap.sh` at the root. He runs it in WSL. It:

1. Installs Python 3 + pip + venv (if missing)
2. Creates a virtual environment
3. Installs Flask + dependencies via `pip install -e .`
4. Starts the DTTP Service on `:5002`
5. Starts the ADT Operational Center on `:5001`
6. Opens `http://localhost:5001` in his default browser

No Rust. No Tauri. No Node.js. Just Python and a browser.

### 3.2 What Paul Sees (ADT Panel)

The existing Operational Center (SPEC-015) already provides:
- **Dashboard:** Active sessions, denial count, task/spec overview
- **ADS Timeline:** Full audit log of every agent action
- **Specs Page:** All specifications with full markdown content
- **Tasks Board:** All tasks with status, dependencies, assignments
- **DTTP Monitor:** Enforcement status, policy, recent decisions
- **About/Help:** ADT principles and architecture (SPEC-016)

### 3.3 What Paul Can Do (NEW)

**Spec Creation via Panel UI:**
- New "Create Spec" button on the Specs page
- Form: Spec ID (auto-suggested), Title, Status (DRAFT), Content (Markdown)
- Saves to `_cortex/specs/SPEC-XXX_TITLE.md`
- Logged to ADS as `spec_created` event with `agent: HUMAN`

**Feedback via Panel UI:**
- New "Request" button on Dashboard
- Appends structured feedback to `_cortex/requests.md`
- Logged to ADS as `request_submitted` event

### 3.4 Sync Mechanism

**Git is the transport.** Both collaborators work on the same repository.

```
Paul (v0.3)                    You (development)
    |                               |
    |-- creates SPEC-026 ---------> |
    |-- pushes to GitHub            |
    |                               |-- pulls Paul's specs
    |                               |-- builds v0.4 using ADT governance
    |                               |-- pushes v0.4
    |<--- pulls v0.4 -------------- |
    |-- experiences improvements    |
    |-- creates more specs -------> |
    ...                            ...
```

---

## 4. Bootstrap Script Requirements

**File:** `bootstrap.sh` (root of repository)

### 4.1 Prerequisites (auto-installed)
- Python >= 3.9
- pip
- python3-venv
- git (for sync)

### 4.2 Behavior
1. Detect OS (WSL/Linux/macOS)
2. Install missing system dependencies via apt (WSL/Ubuntu) or brew (macOS)
3. Create `venv/` if not present
4. `pip install -e .` (installs adt-framework + all deps)
5. Start DTTP service (background, port 5002)
6. Start ADT Panel (background, port 5001)
7. Wait for services to be healthy (curl check)
8. Print status banner with URLs
9. Attempt to open browser (`xdg-open` / `wslview` / `open`)

### 4.3 Idempotency
- Safe to run multiple times
- Skips already-running services
- Skips already-created venv (unless corrupted)

---

## 5. New API Endpoints

### 5.1 POST /api/specs (Create Spec)

```json
{
  "id": "SPEC-026",
  "title": "My Improvement Idea",
  "status": "DRAFT",
  "content": "# SPEC-026: My Improvement Idea\n\n## Purpose\n..."
}
```

- Validates ID format (SPEC-NNN)
- Prevents overwriting existing specs
- Writes markdown file to `_cortex/specs/SPEC-NNN_TITLE.md`
- Logs `spec_created` to ADS

### 5.2 POST /api/requests (Submit Feedback)

```json
{
  "author": "Paul",
  "type": "feature|bug|improvement",
  "description": "The DTTP monitor should show..."
}
```

- Appends to `_cortex/requests.md` with timestamp
- Logs `request_submitted` to ADS

---

## 6. Implementation Tasks

| Task | Description | Assigned To |
|------|-------------|-------------|
| task_052 | Create `bootstrap.sh` WSL/Linux/macOS bootstrap script | DevOps_Engineer |
| task_053 | Add POST /api/specs endpoint (create spec via Panel) | Backend_Engineer |
| task_054 | Add POST /api/requests endpoint (submit feedback) | Backend_Engineer |
| task_055 | Add "Create Spec" UI to Specs page template | Frontend_Engineer |
| task_056 | Add "Submit Feedback" UI to Dashboard template | Frontend_Engineer |

---

## 7. Acceptance Criteria

- [ ] Paul can clone repo and run `bash bootstrap.sh` on fresh WSL Ubuntu
- [ ] Services start within 60 seconds on first run
- [ ] ADT Panel is accessible at `http://localhost:5001`
- [ ] Paul can see all specs, tasks, ADS events, DTTP status
- [ ] Paul can create a new DRAFT spec via the Panel UI
- [ ] Paul can submit feedback/requests via the Panel UI
- [ ] Created specs appear as proper markdown files in `_cortex/specs/`
- [ ] All actions are logged to ADS
- [ ] `git add . && git push` syncs Paul's contributions back

---

## 8. Versioning

The bootstrap script prints the framework version from `setup.py`. This is the version Paul experiences.

| Version | Milestone |
|---------|-----------|
| v0.1.0 | Core engines (ADS, SDD, DTTP) |
| v0.2.0 | Operational Center + Agent SDK |
| v0.3.0 | Self-Governance + Operator Console + Collaborative Bootstrap |
| v0.4.0 | *Driven by Paul's specs from v0.3* |

---

*"Send the framework to build the framework."*
