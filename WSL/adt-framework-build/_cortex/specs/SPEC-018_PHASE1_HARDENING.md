# SPEC-018: Phase 1 Hardening

**Status:** APPROVED
**Priority:** HIGH
**Owner:** Systems_Architect
**Created:** 2026-02-07
**References:** SPEC-014, SPEC-015, SPEC-017, Architectural Review (2026-02-07)
**Triggered By:** Systems_Architect code review of Phase 1 deliverables

---

## 1. Purpose

Phase 1 core modules (ADS, SDD, DTTP, Operational Center, Agent SDK) were delivered by Backend_Engineer. An architectural review identified **6 critical**, **6 high**, and multiple medium-severity issues. This spec defines the mandatory fixes before Phase 2 work begins.

### 1.1 Principle

> "The framework governs itself by its own principles."

A governance framework with a path traversal vulnerability or hardcoded project names is not governing -- it is pretending. These fixes are not enhancements; they are **prerequisites to self-governance**.

---

## 2. Critical Fixes (Must Complete)

### 2.1 Path Traversal Vulnerability

**Location:** `adt_core/dttp/actions.py`
**Problem:** `os.path.join(self.project_root, params["file"])` does not validate that the resolved path stays within `project_root`. An input of `../../etc/passwd` escapes the project boundary.

**Fix:**
```python
resolved = os.path.realpath(os.path.join(self.project_root, params["file"]))
if not resolved.startswith(os.path.realpath(self.project_root) + os.sep):
    raise PermissionError(f"Path escapes project root: {params['file']}")
```

Apply this pattern to every method in `ActionHandler` that resolves a file path: `_handle_edit`, `_handle_create`, `_handle_delete`.

**Assigned To:** Backend_Engineer
**Acceptance:** No path outside `project_root` can be read, written, or deleted via ActionHandler, verified by test.

### 2.2 Hardcoded Project Names

**Locations:**
- `adt_core/sdd/tasks.py:22` — `"adt-framework"` in `_save_tasks()`
- `adt_center/api/dttp_routes.py` — `"adt-framework"` in `/api/dttp/status`

**Fix:** Accept project name as a constructor/config parameter. Never embed it in source code.

- `TaskManager.__init__` should accept `project_name: str` parameter
- `dttp_routes.py` should read project name from `current_app.config`

**Assigned To:** Backend_Engineer
**Acceptance:** `grep -r "adt-framework" adt_core/ adt_center/ adt_sdk/` returns zero results.

### 2.3 Hardcoded UI Values

**Location:** `adt_center/templates/ads.html`
**Problem:** Agent names (CLAUDE, GEMINI) and action types are hardcoded in filter dropdowns.

**Fix:** Populate filter options from the ADS data. The dashboard route should pass distinct agent names and action types extracted from actual events.

**Assigned To:** Backend_Engineer + Frontend_Engineer
**Acceptance:** Adding a new agent (e.g., "COPILOT") to the ADS automatically appears in the filter dropdown without code changes.

### 2.4 Duplicated Hash Function

**Locations:**
- `adt_core/ads/logger.py` — `_calculate_hash()`
- `adt_core/ads/integrity.py` — `_calculate_hash()`

**Problem:** Identical function in two files. If one is changed without the other, the hash chain breaks silently.

**Fix:** Extract to a shared module:
```
adt_core/ads/crypto.py:
    def calculate_event_hash(event: Dict, prev_hash: str) -> str
    GENESIS_HASH = "0" * 64
```

Both `ADSLogger` and `ADSIntegrity` import from `crypto.py`.

**Assigned To:** Backend_Engineer
**Acceptance:** `_calculate_hash` exists in exactly one location. Logger and integrity verifier produce identical hashes for the same input.

### 2.5 Empty Config Files

**Locations:**
- `config/specs.json` — `{"specs": {}}`
- `config/jurisdictions.json` — `{"jurisdictions": {}}`

**Problem:** The DTTP gateway and spec validator load these at startup. With empty configs, every request is denied (fail-closed is correct) but the framework has no actual governance policy loaded. It is **structurally inert**.

**Fix:** Populate with the governance rules for the ADT Framework project itself (self-governance):

`config/specs.json` must contain entries for SPEC-014 through SPEC-018 with:
- Status (approved/active)
- Authorized roles per spec
- Authorized action types per spec
- Authorized paths per spec

`config/jurisdictions.json` must contain role-path mappings matching `AI_PROTOCOL.md` Section 3:
- Systems_Architect: `_cortex/`, `docs/`
- Backend_Engineer: `adt_core/`, `adt_center/api/`, `adt_center/app.py`
- Frontend_Engineer: `adt_center/templates/`, `adt_center/static/`
- DevOps_Engineer: `ops/`
- Overseer: `_cortex/ads/`

**Assigned To:** Systems_Architect (config is governance data, not code)
**Acceptance:** DTTP gateway can authorize a valid Backend_Engineer request against SPEC-017 and deny an unauthorized cross-jurisdiction attempt.

### 2.6 Path Matching Bypass

**Location:** `adt_core/dttp/jurisdictions.py`
**Problem:** `path.startswith(allowed_path)` is bypassable. `/home/user` matches `/home/user2/secret`.

**Fix:** Normalize paths and ensure boundary matching:
```python
def is_in_jurisdiction(self, role: str, path: str) -> bool:
    normalized = os.path.normpath(path)
    for allowed in self._jurisdictions.get(role, []):
        allowed_norm = os.path.normpath(allowed)
        if normalized == allowed_norm or normalized.startswith(allowed_norm + os.sep):
            return True
    return False
```

Apply the same fix in `adt_core/dttp/policy.py` wherever `startswith()` is used for path authorization.

**Assigned To:** Backend_Engineer
**Acceptance:** Test confirms `/home/user2/file` is NOT matched by jurisdiction rule `/home/user`.

---

## 3. High-Priority Fixes

### 3.1 Stale Policy Cache

**Location:** `adt_core/sdd/validator.py`
**Problem:** Config loaded once at `__init__`, never refreshed. If a spec is approved via the Operational Center, running validators still enforce the old policy.

**Fix:** Reload config on every `is_authorized()` call, or implement a `reload()` method with TTL-based caching (e.g., re-read file if modified since last load using `os.path.getmtime()`).

**Assigned To:** Backend_Engineer

### 3.2 Task File Race Condition

**Location:** `adt_core/sdd/tasks.py`
**Problem:** `_load_tasks()` then `_save_tasks()` with no file locking. Concurrent agents can overwrite each other's status updates.

**Fix:** Use `fcntl.flock()` (same pattern as `ADSLogger`) around the read-modify-write cycle.

**Assigned To:** Backend_Engineer

### 3.3 Session Counting Logic

**Location:** `adt_center/app.py:55-57`
**Problem:** Set difference `session_starts - session_ends` doesn't track paired sessions. If GEMINI starts two sessions and ends one, count is wrong.

**Fix:** Count by matching `session_start`/`session_end` event pairs per agent, using timestamps or event IDs to pair them. Simpler alternative: count `session_start` events that have no corresponding `session_end` with a later timestamp from the same agent.

**Assigned To:** Backend_Engineer

### 3.4 Test Coverage

**Location:** `tests/`
**Problem:** 5 test functions for the entire framework. No negative tests. No security tests.

**Fix:** Minimum required tests:
- **ADS:** empty file, schema validation failure, concurrent writes, hash chain with 100+ events
- **SDD:** missing config, invalid spec ID, unauthorized role, case sensitivity
- **DTTP:** path traversal attempt (must fail), jurisdiction boundary test, stub action handlers
- **Integration:** full agent SDK -> DTTP -> action -> ADS flow over HTTP (prepares for SPEC-019)

Target: minimum 20 test functions covering happy path, error path, and security path.

**Assigned To:** Backend_Engineer

### 3.5 API Input Validation

**Location:** `adt_center/api/ads_routes.py`, `adt_center/api/dttp_routes.py`
**Problem:** No validation on query parameters or POST body fields beyond presence checks.

**Fix:**
- Validate types (params must be dict, rationale must be non-empty string)
- Validate string lengths (max 500 chars for rationale, max 200 for paths)
- Return structured error responses: `{"status": "error", "code": "<ERROR_CODE>", "message": "<details>"}`

**Assigned To:** Backend_Engineer

### 3.6 Add Python Logging

**Location:** All modules
**Problem:** No `logging` module usage. Errors silently swallowed with `pass` or bare `except`.

**Fix:** Add `logger = logging.getLogger(__name__)` to every module. Replace silent `except` blocks with `logger.warning()` or `logger.error()` calls. Never swallow exceptions silently.

**Assigned To:** Backend_Engineer

---

## 4. Implementation Order

Tasks must be completed in this order due to dependencies:

```
Phase A (Security — immediate):
  1. Path traversal fix (2.1)
  2. Path matching fix (2.6)

Phase B (Architecture — before new features):
  3. Extract shared hash utility (2.4)
  4. Remove hardcoded project names (2.2)
  5. Populate config files (2.5)
  6. Dynamic UI values (2.3)

Phase C (Robustness):
  7. Stale policy cache (3.1)
  8. Task file locking (3.2)
  9. Session counting fix (3.3)
  10. Python logging (3.6)
  11. API validation (3.5)

Phase D (Confidence):
  12. Test coverage expansion (3.4)
```

---

## 5. Acceptance Criteria

Phase 1 Hardening is **COMPLETED** when:

1. Zero path traversal vulnerabilities (verified by dedicated security tests)
2. `grep -r "adt-framework" adt_core/ adt_center/ adt_sdk/` returns zero hits
3. Config files contain real governance rules and DTTP can enforce them
4. Hash function exists in exactly one location
5. All tests pass (`pytest tests/ -v` green)
6. Minimum 20 test functions with security and error coverage
7. No silent `except: pass` blocks in any module

---

*"A governance framework that cannot secure itself has no authority to secure others."*
