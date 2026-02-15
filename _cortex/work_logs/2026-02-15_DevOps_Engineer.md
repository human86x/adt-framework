# Work Log - 2026-02-15 - DevOps_Engineer

## Summary
Hardened environment enforcement by making `ADT_SPEC_ID` mandatory in both the Claude pre-tool hook and the ADT Operator Console.

## Changes
- **`adt_sdk/hooks/claude_pretool.py`**: Removed default values for `ADT_ROLE` and `ADT_SPEC_ID`. Added a mandatory check that blocks tool use if these are not set.
- **`adt-console/src/index.html`**: Added an "Active Spec" selector to the New Session dialog.
- **`adt-console/src/js/app.js`**: Implemented `loadSpecs()` to populate the spec selector from the ADT Center API.
- **`adt-console/src/js/sessions.js`**: Updated session creation to include `specId`.
- **`adt-console/src-tauri/src/ipc.rs`**: Extended `CreateSessionRequest` with `spec_id`.
- **`adt-console/src-tauri/src/pty.rs`**: Updated `PersistentSession` and `create_session` to track `spec_id` and inject it as `ADT_SPEC_ID` into spawned PTY environments.
- **`config/jurisdictions.json`**: Updated `DevOps_Engineer` jurisdiction via API to include `adt_sdk/` and `_cortex/work_logs/`.

## Status
- DTTP Service: Running
- ADT Center: Running
- Environment Enforcement: HARDENED
- Mandatory `ADT_SPEC_ID`: ACTIVE

## Next Steps
- Verify Windows build pipeline with new `spec_id` fields.
- Expand `Shatterglass` protocol tests to verify OS-level blocking of Tier 1/2 files for the `agent` user.
