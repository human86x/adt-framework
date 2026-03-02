# DevOps Engineer Work Log: 2026-03-02

## Task: REQ-034 Fix PTY Spawning and Sandbox Mounts

*   **Objective:** Robustify `pty.rs` by using absolute paths for system binaries and improving framework root detection.
*   **Actions:**
    *   Updated `get_framework_root` in `adt-console/src-tauri/src/pty.rs` to prioritize `ADT_FRAMEWORK_ROOT`, check for existence, and provide robust fallbacks (standard home path, executable directory traversal).
    *   Changed `has_bubblewrap` to use absolute path `/usr/bin/bwrap` and existence check.
    *   Updated `has_user_namespaces` to use absolute path `/usr/bin/unshare`.
    *   Updated `build_unshare_script` to use absolute paths for all internal commands (`/usr/bin/mount`, `/usr/bin/mkdir`, `/usr/bin/test`, `/usr/sbin/pivot_root`, `/usr/bin/umount`).
    *   Verified that `/usr/local/bin` is already included in sandbox mounts.
*   **Fixes for SPEC-037:**
    *   Updated `adt_sdk/hooks/gemini_pretool.py` and `adt_sdk/hooks/claude_pretool.py` to prioritize `ADT_SPEC_ID` environment variable over the `active_spec.txt` file, allowing per-call spec overrides.
*   **Verification:**
    *   Ran `cargo check` in `adt-console/src-tauri/` - PASSED.
    *   Ran `cargo test pty::tests` - PASSED (7 tests).
*   **Status Update:**
    *   Marked **REQ-034** as COMPLETED via ADT CLI.
    *   Verified **REQ-022** (absolute hook paths) is already handled by current code and registry state. Marked COMPLETED.
*   **Git Sync:** Committed and pushed changes to `origin/feature/spec-021-operator-console`.

The PTY spawner and sandboxing mechanism are now more robust against environment variations.
