# SPEC-044: DTTP -> DTCP Terminology Migration

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE)
**Date:** 2026-04-25
**Approver:** Human Collaborator (G), authorising on behalf of the Architect (Paul Sheridan, email 2026-04-21)
**Milestone:** v0.4.x (Hardening)
**Priority:** HIGH
**Related Specs:** SPEC-014 (DTTP Implementation), SPEC-019 (DTTP Standalone Service), SPEC-026 (DTTP Governance Configurator), SPEC-017 (Framework Repository)

---

## 1. Executive Summary

The protocol historically named **Digital Transformation Transfer Protocol (DTTP)** is being renamed to **Digital Transformation Control Protocol (DTCP)**. The word *Transfer* no longer reflects the architecture; the protocol's role within ADT is **execution and enforcement**, not transfer. This spec governs the coordinated, multi-tier, multi-role rename across the entire framework.

This is a **terminological** migration. The protocol's behaviour, on-the-wire semantics, and ledger contents are unchanged. Historical ADS events retain `dttp_*` action types verbatim (the SHA-256 chain is immutable); only **new** code, configuration, documentation, and event types adopt `dtcp_*`.

## 2. Authority (Architect Directive)

Email from Paul Sheridan (Architect), 2026-04-21, 10:20 AM, subject "Digital Transformation Control Protocol (DTCP)":

> The term "Transfer" in DTTP no longer reflects the ADT architecture, and DTCP better represents its role as a control and enforcement layer, particularly in doitrt.com. I propose replacing it with:
>
> "The Digital Transformation Control Protocol (DTCP), the execution and enforcement layer within ADT, enforces this boundary in real time by rejecting any operation that is not explicitly authorised by human-defined specifications."
>
> If you agree, could you please update all occurrences of DTTP in GitHub and align the documentation with a more technically accurate description, for example:
>
> "The Digital Transformation Control Protocol (DTCP) is the execution and enforcement layer within ADT. It operates as a privilege-separated enforcement gateway that validates all system and AI-initiated actions in real time against human-defined specifications, role-based jurisdictions, and tiered governance protections. Unauthorized actions are denied at execution time rather than logged post hoc."

The longer paragraph becomes the canonical definition in `AI_PROTOCOL.md`.

## 3. Scope

### 3.1 In scope

- Rename module directory `adt_core/dttp/` -> `adt_core/dtcp/`
- Rename Python files: `tests/test_dttp*.py` -> `tests/test_dtcp*.py`, `adt_sdk/hooks/dttp_request.py` -> `dtcp_request.py`
- Rename templates: `adt_center/templates/dttp.html` -> `dtcp.html`
- Rename API blueprint module: `adt_center/api/dttp_routes.py` -> `dtcp_routes.py`, with HTTP route prefix change `/dttp` -> `/dtcp`
- Rename config: `config/dttp.json` -> `config/dtcp.json` (Tier-1 SCR required)
- Rename service unit: `_cortex/ops/adt-dttp.service` -> `adt-dtcp.service`; PyInstaller spec `ops/windows/dttp_service.spec` -> `dtcp_service.spec`
- Refactor all internal imports, identifiers, environment variables (`DTTP_URL` -> `DTCP_URL`), comments, log strings
- Update `AI_PROTOCOL.md`, `MASTER_PLAN.md`, `requests.md` (Tier-1 SCRs for the first two)
- Update all open / draft specs that mention DTTP (SPEC-038/039/040/041/042/043 and any others)
- Update Tauri Rust references (`adt-console/src-tauri/src/{main,pty,ipc}.rs`)
- Update Frontend JS (`adt-console/src/js/*.js`) and `index.html`

### 3.2 Explicitly out of scope

- **Historical ADS events:** the immutable hashed ledger keeps `dttp_*` action types as written. Re-keying breaks the SHA-256 chain.
- **Historical work logs and completed specs:** preserve the historical record. Files like `_cortex/work_logs/2026-02-09_systems_architect.md` and SPEC-014/019/026 keep their original DTTP wording. Add an editorial header note: *"Pre-SPEC-044 terminology: DTTP = DTCP."* Filenames are NOT renamed for completed specs.
- **External properties** (doitrt.com, etc.): Paul's email mentions doitrt.com - that is outside this repo. Out of scope; flagged to whoever owns it.
- **The `WSL/adt-framework-build/` snapshot:** appears to be a build artefact / mirror, not the live tree. Excluded from this spec.

## 4. Phased Migration Plan

Phases run **sequentially**. Each phase has explicit completion criteria; do not start the next phase until the current one is verified.

### Phase A - Architect bootstrap (Sovereign + Spec-Registry)

**Owner:** Systems_Architect

A1. **SCR-A1 - Register SPEC-044 in `config/specs.json`** (Tier-1). This is the bootstrap; without it, no role can act under SPEC-044's authority. Entry to add (immediately after `"SPEC-043"` block):

```json
"SPEC-044": {
  "title": "DTTP -> DTCP Terminology Migration",
  "status": "active",
  "roles": [
    "Systems_Architect",
    "Backend_Engineer",
    "Frontend_Engineer",
    "DevOps_Engineer",
    "Overseer"
  ],
  "action_types": ["edit", "patch", "create", "delete", "rename"],
  "paths": [
    "_cortex/",
    "adt_core/",
    "adt_sdk/",
    "adt_center/",
    "adt-console/src/",
    "adt-console/src-tauri/",
    "tests/",
    "ops/",
    "config/",
    "README.md",
    "notes.md"
  ]
}
```

A2. **SCR-A2 - Update `AI_PROTOCOL.md`** (Tier-1): replace the DTTP definition with Paul's canonical paragraph (Section 2 above). Bump version to v2.3, date 2026-04-25, add a Section 6 line: *"DTCP supersedes the prior DTTP terminology (SPEC-044). DTCP and DTTP refer to the same protocol; new code uses DTCP."*

A3. **SCR-A3 - Update `MASTER_PLAN.md`** (Tier-1): add SPEC-044 row to Section 5 Active Specifications.

A4. Update `_cortex/requests.md` (Tier-3) with REQ entries handing off Phases B, C, D, E to Backend, DevOps, Frontend, and shared roles.

**Phase A complete when:** SPEC-044 is registered in `config/specs.json`, AI_PROTOCOL.md is at v2.3, MASTER_PLAN lists SPEC-044, all three SCRs are authorised.

### Phase B - Backend core rename (Tier-2)

**Owner:** Backend_Engineer

B1. **Create `adt_core/dtcp/` as the canonical module.** Copy each file from `adt_core/dttp/`, rewriting internal identifiers (`DTTP*`, `DTTP_URL`, log strings) to their DTCP equivalents. Keep import paths internal-consistent.

B2. **Convert `adt_core/dttp/` into a deprecation shim** - each file becomes a one-line re-export:

```python
# adt_core/dttp/gateway.py - DEPRECATED, re-exports from dtcp
import warnings
warnings.warn("adt_core.dttp is deprecated; import from adt_core.dtcp (SPEC-044)", DeprecationWarning, stacklevel=2)
from adt_core.dtcp.gateway import *  # noqa: F401,F403
```

The shim exists for **one release only** and is removed in Phase F.

B3. Update `adt_sdk/`: rename `hooks/dttp_request.py` -> `hooks/dtcp_request.py`; update imports and identifiers in `client.py`, `decorators.py`, `hooks/claude_pretool.py`, `hooks/gemini_pretool.py`. Environment variable `DTTP_URL` -> `DTCP_URL` with backwards-compat fallback (`os.environ.get("DTCP_URL") or os.environ.get("DTTP_URL")`).

B4. Update `adt_center/api/`: rename `dttp_routes.py` -> `dtcp_routes.py`, update blueprint name and registration in `app.py`. Add HTTP redirect `/dttp/* -> /dtcp/*` (308 Permanent Redirect) for one release.

B5. **New ADS action types**: from this point forward, new events use `dtcp_*` (e.g. `dtcp_request_validated`, `dtcp_denied`). The Overseer must NOT rewrite historical `dttp_*` events. Add a one-time `protocol_renamed` event recording the cutover (event_id naming convention unchanged).

**Phase B complete when:** all tests under `tests/` pass against the new `adt_core/dtcp/` module; the shim issues a warning when imported; the SDK uses DTCP names internally; `/dtcp/*` API routes respond and `/dttp/*` redirects.

### Phase C - DevOps configuration & desktop (Tier-1 + Tier-3)

**Owner:** DevOps_Engineer

C1. **SCR-C1 - `config/dttp.json` -> `config/dtcp.json`** (Tier-1). Same content, renamed key. Code in `adt_core/dtcp/config.py` reads new path; falls back to old for one release.

C2. Update Tauri Rust source: `adt-console/src-tauri/src/{main,pty,ipc}.rs` - identifier and log-string updates only; no behavioural change.

C3. Rename systemd unit `_cortex/ops/adt-dttp.service` -> `adt-dtcp.service`; update PyInstaller spec `ops/windows/dttp_service.spec` -> `dtcp_service.spec`. Update `install.sh`, `console.sh`, and any docs referencing service names.

C4. Log paths: new logs write to `dtcp*.log`. Existing `dttp*.log` files are NOT renamed (historical artefacts). Update logrotate / rotation config to cover both for one release.

**Phase C complete when:** services start under the new names; config loads from new path; AppImage and Windows builds reference DTCP.

### Phase D - Frontend rename (Tier-3)

**Owner:** Frontend_Engineer

D1. Rename `adt_center/templates/dttp.html` -> `dtcp.html`; update `base.html` nav link and any `url_for('dttp_...')` -> `url_for('dtcp_...')`. Update `dashboard.html`, `governance.html`, `about.html`, `projects.html`.

D2. Update Tauri/console JS: `adt-console/src/js/{app,context,launcher,guide}.js` and `index.html` - identifier renames, displayed copy ("DTTP Gateway" -> "DTCP Gateway"), tooltips.

D3. Page titles, badges, navigation copy. The displayed acronym is **DTCP** with the expansion "Digital Transformation Control Protocol".

**Phase D complete when:** the Operator Console and ADT Panel render no "DTTP" strings to the user; `/dtcp` page loads; old `/dttp` URL redirects.

### Phase E - Tests & internal scripts (Tier-3)

**Owner:** Backend_Engineer (lead), with Systems_Architect coordination

E1. Rename test files: `tests/test_dttp.py` -> `tests/test_dtcp.py`, `tests/test_dttp_service.py` -> `tests/test_dtcp_service.py`, `tests/test_dttp_sandboxing.py` -> `tests/test_dtcp_sandboxing.py`. Update fixture and mock identifiers.

E2. Update `_cortex/ops/*.py` scripts that mention DTTP (logging helpers, migration scripts). `_cortex/ops/dttp*.log` files: leave as historical record.

E3. Update top-level `README.md` and `notes.md` (Tier-3) with the new terminology. Use Paul's canonical paragraph for the DTCP definition.

**Phase E complete when:** `pytest` runs green under new file names; no live-code references to the `DTTP_` env var or `dttp` module remain (excluding shim and historical artefacts).

### Phase F - Shim removal & cleanup

**Owner:** Backend_Engineer + Systems_Architect

F1. Delete `adt_core/dttp/` shim once a full release cycle has passed since Phase B and ADS shows zero `DeprecationWarning` events for the shim.

F2. Remove `DTTP_URL` env-var fallback in SDK.

F3. Remove `/dttp/*` HTTP redirect.

F4. Drop `config/dttp.json` fallback path.

F5. Update completed specs (SPEC-014, SPEC-019, SPEC-026) with editorial header note linking to SPEC-044; do **not** rewrite historical content.

**Phase F complete when:** `grep -r 'DTTP\|dttp' . --exclude-dir=.git --exclude-dir=WSL --exclude-dir=__pycache__` returns only: (a) historical work logs, (b) completed specs with editorial notes, (c) historical ADS events, (d) historical `*.log` files. No live code or current docs.

## 5. Implementation Tasks

| Task | Phase | Role | Description |
|------|-------|------|-------------|
| task_231 | A1 | Systems_Architect | Submit SCR to add SPEC-044 entry to `config/specs.json` |
| task_232 | A2 | Systems_Architect | Submit SCR to update `AI_PROTOCOL.md` to v2.3 with DTCP definition |
| task_233 | A3 | Systems_Architect | Submit SCR to update `MASTER_PLAN.md` Section 5 with SPEC-044 row |
| task_234 | B1+B2 | Backend_Engineer | Create `adt_core/dtcp/` canonical module; convert `adt_core/dttp/` to deprecation shim |
| task_235 | B3+B4 | Backend_Engineer | Migrate `adt_sdk/` and `adt_center/api/` to DTCP names; add `/dttp -> /dtcp` redirect; emit `protocol_renamed` ADS event |
| task_236 | C1-C4 | DevOps_Engineer | SCR for `config/dttp.json -> config/dtcp.json`; rename service units, PyInstaller spec, install scripts; update Tauri Rust identifiers |
| task_237 | D1-D3 | Frontend_Engineer | Rename templates, update Console JS and Panel pages, swap displayed terminology to DTCP |
| task_238 | E1-E3 | Backend_Engineer | Rename test files, update internal ops scripts, update top-level README/notes |
| task_239 | F1-F4 | Backend_Engineer | Phase F shim removal (gated on one release cycle, zero deprecation events) |
| task_240 | F5 | Systems_Architect | Phase F editorial notes on SPEC-014/019/026; close SPEC-044 |

## 6. Acceptance Criteria

1. The framework runs end-to-end with **no functional regressions** at every phase boundary.
2. The Operator Console and ADT Panel render **zero** "DTTP" strings in the UI after Phase D.
3. The ADS ledger remains **unbroken**: SHA-256 chain validates from the genesis event to head, with `dttp_*` events untouched and `dtcp_*` events appended cleanly.
4. `import adt_core.dttp` continues to work during Phases B-E (with `DeprecationWarning`); fails with `ModuleNotFoundError` after Phase F.
5. `AI_PROTOCOL.md` v2.3 contains Paul's canonical DTCP definition verbatim.
6. The Phase F grep produces **only** the four allowed historical-artefact categories.

## 7. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Atomic directory rename breaks every import in one commit | Shim approach (B2) keeps both names live during transition |
| Tier-1 SCRs blocked or delayed | Phase A is single-Architect, single-Human; runs first; remaining phases can begin in parallel only after A completes |
| ADS chain corruption from event-type rewrite | Explicitly prohibited in Section 3.2; only **new** events use `dtcp_*` |
| In-flight specs (SPEC-038-043) reference DTTP | Each owner updates their spec text as part of their own phase work; not a separate task |
| `config/dttp.json` rename loses runtime config | C1 keeps fallback for one release |
| External integrations using `DTTP_URL` env var break | B3 keeps env-var fallback for one release |
| Historical work logs / completed specs lose context | Section 3.2: not renamed in place; editorial header notes added in Phase F |
| Hash-chain confusion when reading mixed `dttp_*`/`dtcp_*` events | Phase B5 emits a single `protocol_renamed` marker event that tooling can use as the cutover anchor |

## 8. Sequencing Constraint

```
Phase A (SA, sovereign)
   |__ must complete before any other phase
Phase B (Backend, Tier-2)
   |__ must complete before Phase E test renames
   |__ may proceed in parallel with Phase C and Phase D after A
Phase C (DevOps), Phase D (Frontend) - parallelisable after A
Phase E (Tests + scripts) - after B
Phase F (Cleanup) - after one release cycle past B; final pass
```

## 9. Cross-Reference

This spec creates the cross-role REQ entries in `_cortex/requests.md`: **REQ-051** (Backend, Phase B+E), **REQ-052** (DevOps, Phase C), **REQ-053** (Frontend, Phase D), **REQ-054** (Phase F coordination with Backend + Overseer).

---

*"The protocol's name now matches what the protocol does."* - SPEC-044
