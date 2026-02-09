# SPEC-019: DTTP Standalone Service Architecture

**Status:** APPROVED
**Priority:** HIGH
**Owner:** Systems_Architect
**Created:** 2026-02-07
**References:** SPEC-014 (DTTP Implementation), SPEC-015 (Operational Center), SPEC-017 (Repository), REQ-001
**Triggered By:** REQ-001 from Backend_Engineer — "Standalone DTTP Service from Day One"

---

## 1. Purpose

This spec redefines DTTP as a **standalone service** rather than an in-process library embedded in the Operational Center. It supersedes the phased extraction approach in SPEC-014 Sections 5.3-5.5, replacing "build embedded, extract later" with "build standalone, restrict later."

### 1.1 Problem Statement

SPEC-014 describes a 5-phase rollout where DTTP starts as Python modules imported directly into the Flask app (`adt_center/app.py`), then gets extracted into a privilege-separated process at Phase 4. Gemini built it this way — `adt_core/dttp/` is wired into `create_app()` as in-process function calls.

This creates two architectural problems identified by the Backend Engineer:

1. **Interface drift.** In-process function calls have different error handling, timeout, and serialization characteristics than HTTP calls. Extracting later means rewriting every integration point.

2. **Late integration risk.** The hardest part of privilege separation isn't `chmod` — it's making the service work as an independent process with its own lifecycle. Pushing this to Phase 4 front-loads the easy work and back-loads the hard work.

### 1.2 Solution

Build DTTP as a standalone HTTP service from the start. Two operational modes, **same codebase**:

```
DEVELOPMENT MODE (current phase):
  - DTTP runs as a separate process on :5002
  - Agents and Operational Center communicate via HTTP
  - Everyone runs as OS user `human` — no privilege separation
  - Full edit access to all code and config
  - Functionally identical to production, minus OS restrictions

PRODUCTION MODE (Phase 4+ of SPEC-014):
  - Same DTTP service, same code, same API
  - Runs under `dttp` OS user with write permissions
  - Agents run under `agent` OS user (read-only + API access)
  - iptables and file permissions enforced
  - The ONLY difference: who runs the process and what OS permissions apply
```

The principle: **what you build is what you ship.**

---

## 2. DTTP Service API

### 2.1 Endpoints

The DTTP service exposes three HTTP endpoints:

#### `POST /request`

The enforcement gateway. Validates, executes, and logs an action.

**Request:**
```json
{
  "agent": "GEMINI",
  "role": "backend_engineer",
  "spec_id": "SPEC-017",
  "action": "edit",
  "params": {
    "file": "adt_core/ads/logger.py",
    "content": "..."
  },
  "rationale": "Fix path traversal vulnerability per SPEC-018 Section 2.1"
}
```

**Response (approved):**
```json
{
  "status": "approved",
  "request_id": "req_20260207_143022_001",
  "action": "edit",
  "result": {
    "status": "success",
    "result": "file_written",
    "bytes": 2048
  },
  "ads_event_id": "evt_20260207_143022_456"
}
```

**Response (denied):**
```json
{
  "status": "denied",
  "request_id": "req_20260207_143022_002",
  "reason": "Role frontend_engineer not authorized for spec SPEC-017",
  "ads_event_id": "evt_20260207_143022_457"
}
```

HTTP status codes: `200` for approved, `403` for denied, `400` for malformed request, `500` for internal error.

#### `GET /status`

Health check and service metadata.

**Response:**
```json
{
  "service": "dttp",
  "version": "0.1.0",
  "mode": "development",
  "uptime_seconds": 3600,
  "policy_loaded": true,
  "specs_count": 6,
  "jurisdictions_count": 5,
  "total_requests": 42,
  "total_denials": 3
}
```

#### `GET /policy`

Read-only view of the current loaded policy. For monitoring and debugging.

**Response:**
```json
{
  "specs": { "...loaded specs.json..." },
  "jurisdictions": { "...loaded jurisdictions.json..." },
  "last_reload": "2026-02-07T14:30:00Z"
}
```

### 2.2 Request IDs

Every request receives a unique `request_id` in format `req_YYYYMMDD_HHMMSS_NNN`. This ID appears in both the HTTP response and the corresponding ADS event, enabling end-to-end tracing.

---

## 3. Service Architecture

### 3.1 Directory Structure

```
adt_core/dttp/
├── __init__.py
├── service.py          # NEW — Flask app for standalone DTTP service
├── gateway.py          # EXISTING — core validation + execution logic (unchanged)
├── policy.py           # EXISTING — fail-closed policy engine (unchanged)
├── jurisdictions.py    # EXISTING — role-path mapping (unchanged)
├── actions.py          # EXISTING — action handlers (unchanged)
└── config.py           # NEW — service configuration (ports, paths, mode)
```

The key insight: `gateway.py`, `policy.py`, `jurisdictions.py`, and `actions.py` remain **unchanged**. They are the domain logic. `service.py` is a thin HTTP wrapper that:

1. Accepts HTTP requests
2. Deserializes JSON
3. Calls `DTTPGateway.request()`
4. Serializes the response
5. Returns HTTP status codes

### 3.2 Service Entry Point

```
adt_core/dttp/service.py:
    create_dttp_app(config: DTTPConfig) -> Flask
```

Started via:
```bash
# Development
python -m adt_core.dttp.service --port 5002 --mode development

# Production (run as dttp user)
sudo -u dttp python -m adt_core.dttp.service --port 5002 --mode production
```

### 3.3 Configuration

```
adt_core/dttp/config.py:
    @dataclass
    class DTTPConfig:
        port: int = 5002
        mode: str = "development"        # "development" or "production"
        ads_path: str = ""               # path to events.jsonl
        specs_config: str = ""           # path to specs.json
        jurisdictions_config: str = ""   # path to jurisdictions.json
        project_root: str = ""           # root of governed project
        project_name: str = ""           # name for display/logging
```

Config loaded from environment variables or a config file at `config/dttp.json`. Environment variables take precedence (12-factor app pattern).

---

## 4. Integration Changes

### 4.1 Operational Center (`adt_center/`)

**Current (embedded):**
```python
# app.py
from adt_core.dttp.gateway import DTTPGateway
gateway = DTTPGateway(policy, handler, logger)
app.dttp_gateway = gateway
```

**New (HTTP client):**
```python
# app.py
import requests
DTTP_URL = os.environ.get("DTTP_URL", "http://localhost:5002")
# No DTTP imports. No gateway instantiation.
```

```python
# api/dttp_routes.py
@dttp_bp.route("/api/dttp/request", methods=["POST"])
def dttp_request():
    response = requests.post(f"{DTTP_URL}/request", json=request.json)
    return jsonify(response.json()), response.status_code
```

The Operational Center becomes a **proxy** to the DTTP service, not the host of it. It adds the web UI layer (dashboard, timeline, spec approval) but delegates all enforcement to DTTP.

### 4.2 Agent SDK (`adt_sdk/`)

**Current:** `ADTClient` already talks over HTTP to the Operational Center's `/api/dttp/request`, which forwards to the in-process gateway.

**New:** `ADTClient` talks directly to the DTTP service:

```python
class ADTClient:
    def __init__(self, dttp_url="http://localhost:5002", ...):
        self.dttp_url = dttp_url
```

The SDK interface doesn't change. Only the URL changes from the Operational Center to the DTTP service directly. This eliminates the proxy hop for agent requests.

### 4.3 Dashboard Monitoring

The Operational Center dashboard reads DTTP status via `GET /status` and displays:
- DTTP service health (up/down)
- Current mode (development/production)
- Request/denial counts
- Policy state via `GET /policy`

---

## 5. Development vs Production Mode

### 5.1 What Changes Between Modes

| Aspect | Development | Production |
|--------|-------------|------------|
| OS user | `human` | `dttp` |
| File permissions | Normal | `dttp` has write, `agent` has read-only |
| Network rules | None | iptables blocks agent SSH/FTP |
| DTTP code | Editable by all | Only `human` can edit |
| Config files | Editable by all | Only `human` can edit |
| DTTP port | :5002 | :5002 |
| API behavior | **Identical** | **Identical** |
| Validation logic | **Identical** | **Identical** |
| ADS logging | **Identical** | **Identical** |

### 5.2 What Does NOT Change

The DTTP service code, API, validation logic, policy engine, action handlers, and ADS logging are **exactly the same** in both modes. The `mode` field in config affects only:

1. What gets reported in `GET /status` response
2. Log messages (for operational clarity)

All security enforcement in production comes from **OS-level permissions**, not from code branches. There are no `if mode == "production"` conditionals in the enforcement path.

---

## 6. Relationship to SPEC-014

This spec **does not replace** SPEC-014. SPEC-014 defines the security model (three-user privilege separation, five-point validation, fail-closed policy). That model is unchanged.

This spec **supersedes** SPEC-014's phased rollout (Sections 5.3-5.5) with:

| SPEC-014 Phase | Original Plan | New Plan (This Spec) |
|---------------|---------------|----------------------|
| Phase 1: Build | Library in adt_core/dttp/ | Standalone service in adt_core/dttp/ |
| Phase 2: Test | Unit tests of library | Unit + integration tests over HTTP |
| Phase 3: Shadow | Shadow mode as library | Shadow mode as service (already running separately) |
| Phase 4: Permission Switch | Extract library → service, create OS users, set permissions | Create OS users, set permissions (service already exists) |
| Phase 5: Live | Go live | Go live |

Phase 4 goes from "rewrite + deploy + permission switch" to just "permission switch." The risk is dramatically reduced because the service has been running and tested in its final form since Phase 1.

---

## 7. Implementation Tasks

| Task | Description | Assigned To | Depends On |
|------|-------------|-------------|------------|
| task_008 | Create `adt_core/dttp/service.py` — standalone Flask app wrapping DTTPGateway | Backend_Engineer | SPEC-018 Phase A (security fixes) |
| task_009 | Create `adt_core/dttp/config.py` — DTTPConfig dataclass with env var loading | Backend_Engineer | — |
| task_010 | Refactor `adt_center/app.py` — remove in-process DTTP, add HTTP client to DTTP service | Backend_Engineer | task_008 |
| task_011 | Update `adt_sdk/client.py` — point to DTTP service URL instead of Operational Center | Backend_Engineer | task_008 |
| task_012 | Integration tests — full flow over HTTP: SDK → DTTP service → action → ADS | Backend_Engineer | task_008, task_010 |
| task_013 | Update dashboard — read DTTP status from `GET /status`, display service health | Frontend_Engineer | task_008, task_010 |

---

## 8. Acceptance Criteria

SPEC-019 is **COMPLETED** when:

1. `python -m adt_core.dttp.service` starts a standalone HTTP service on :5002
2. `POST /request` validates, executes, and logs actions identical to current in-process behavior
3. `GET /status` returns service health and statistics
4. `GET /policy` returns loaded policy state
5. Operational Center communicates with DTTP over HTTP (no in-process imports of gateway)
6. Agent SDK communicates directly with DTTP service
7. All existing tests pass against the HTTP service
8. No `if mode ==` conditionals in the enforcement path

---

*"What you build is what you ship. The gap between development and production should be the OS user, not the architecture."*
