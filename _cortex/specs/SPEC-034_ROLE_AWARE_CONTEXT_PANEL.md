# SPEC-034: Role-Aware Context Panel

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE)
**Date:** 2026-02-23
**Related Specs:** SPEC-021 (Operator Console), SPEC-028 (Hive Tracker Panel)

---

## 1. Problem Statement

The Operator Console right-side Context Panel (Hive Tracker) displays **all** requests and tasks regardless of which session/role is active. When an operator switches between sessions (e.g., Backend_Engineer -> Frontend_Engineer), the panel content does not change. This defeats the purpose of role-based session awareness.

### Specific Issues

1. **Requests** (`fetchRequests()` in `context.js:52-88`): Fetches all requests from `GET /api/governance/requests` with zero role filtering. Every session sees every REQ regardless of the `To:` field.

2. **Tasks To-Do/Completed**: Fetches all tasks then filters client-side (`context.js:200-203`). Works but is inefficient -- sends all 128+ tasks over the wire when only 5-10 may be relevant.

3. **Backend**: `GET /api/governance/requests` does not support role filtering. The markdown parser in `governance_routes.py` does not extract the `To:` or `From:` fields from `requests.md`.

---

## 2. Solution

### 2.1 Backend: Parse Request Metadata (Backend_Engineer)

Update the requests markdown parser in `adt_center/api/governance_routes.py` to extract structured fields from each request entry:

- `to` -- target role (from `**To:**` line)
- `from_role` -- originating role (parsed from `**From:**` line, e.g., "Backend_Engineer" from "Backend_Engineer (CLAUDE)")

Add `?role=` query parameter to `GET /api/governance/requests`:
- When `?role=X` is provided, return only requests where `to` contains `X` OR `from_role` contains `X`
- Without the parameter, return all (backward compatible)

### 2.2 Backend: Tasks endpoint (Backend_Engineer)

The `GET /api/tasks` endpoint already supports `?assigned_to=` filtering via `TaskManager.list_tasks()`. No backend change needed for tasks -- just frontend usage.

### 2.3 Frontend: Role-Aware Fetching (Frontend_Engineer)

Update `adt-console/src/js/context.js`:

**`fetchRequests()`** (line 52):
- Read `currentSession.role`
- Append `&role=` to the API URL when a role is set
- Show requests addressed TO or FROM the active role
- Add a small toggle/link "Show all" that removes the filter

**`fetchTaskData()`** (line 162):
- Append `&assigned_to=` to the API URL using `session.role`
- Remove the client-side filter on lines 200-203 (backend handles it)
- Keep the active task detection logic (lines 174-184) as-is since it already checks role

### 2.4 Visual Indicator

When the panel is filtered by role, show a subtle label at the top of the context panel:
```
[Showing: Backend_Engineer]
```
This makes it obvious the view is scoped. Clicking it toggles to "All roles".

---

## 3. Files Modified

| File | Role | Change |
|------|------|--------|
| `adt_center/api/governance_routes.py` | Backend_Engineer | Parse To/From fields, add `?role=` to requests endpoint |
| `adt-console/src/js/context.js` | Frontend_Engineer | Pass role to API calls, add filter indicator/toggle |

---

## 4. Acceptance Criteria

1. Switch to a Backend_Engineer session -- panel shows only requests addressed to/from Backend_Engineer and tasks assigned to Backend_Engineer
2. Switch to a Frontend_Engineer session -- panel updates to show that role's requests and tasks
3. "Show all" toggle displays unfiltered view
4. Sessions without a role set show all data (backward compatible)
5. API endpoints remain backward compatible (no role param = all data)

---

## 5. Task Breakdown

- **task_129**: Backend_Engineer -- Parse `To:`/`From:` fields in requests markdown parser, add `?role=` filter to `GET /api/governance/requests`
- **task_130**: Frontend_Engineer -- Update `context.js` to pass role to both API calls, add filter indicator and toggle

---

## 6. Additional Fixes: Session Creation Bugs

### 6.1 Bug: Project NAME passed as CWD instead of PATH

**Root cause chain:**
1. `app.js:393` -- `opt.value = name` stores project NAME in dropdown value
2. `app.js:450` -- `const project = document.getElementById('input-project').value` reads NAME
3. `sessions.js:67` -- `cwd: project || null` passes NAME as CWD to Rust backend
4. `pty.rs:235-237` -- `cmd.cwd(path)` gets an invalid directory, PTY inherits parent CWD
5. `pty.rs:271-273` -- `CLAUDE_PROJECT_DIR` / `GEMINI_PROJECT_DIR` env vars set to NAME not PATH

**Fix (Frontend_Engineer):** On form submit in `app.js`, read `selectedOption.dataset.path` instead of `.value` for the CWD. Keep `.value` (name) for API filtering. Pass both `project` (name) and `projectPath` (path) to SessionManager.create(). Update `sessions.js` to use the path for `cwd`.

### 6.2 Bug: Hooks use relative paths, fail when CWD is wrong

**Affected files:**
- `.gemini/settings.json:9` -- `python3 adt_sdk/hooks/gemini_pretool.py`
- `.claude/settings.local.json:18` -- `python3 adt_sdk/hooks/claude_pretool.py`

**Fix (DevOps_Engineer):** Update both hook configs to use absolute paths. The `adt init` command should also write absolute paths when installing hooks for external projects.

### 6.3 Feature: Agent permission bypass checkboxes

Add checkboxes to the session creation dialog:
- **Gemini:** "YOLO mode" -- appends `--yolo` to the gemini launch command
- **Claude:** "Skip permissions" -- appends `--dangerously-skip-permissions` to the claude launch command

These are conditionally visible based on the selected agent type.

**Fix (Frontend_Engineer):** Add checkboxes to the session form in `app.js`. Show/hide based on agent dropdown value. Append flags to command in `sessions.js` before passing to IPC.

---

## 7. Extended Task Breakdown

- **task_131**: Frontend_Engineer -- Fix CWD: read `dataset.path` from project dropdown on form submit, pass as `cwd` to SessionManager. Keep name for API filtering.
- **task_132**: DevOps_Engineer -- Fix hook paths: update `.gemini/settings.json` and `.claude/settings.local.json` to use absolute paths. Update `adt init` hook installation to write absolute paths.
- **task_133**: Frontend_Engineer -- Add agent flag checkboxes (--yolo, --dangerously-skip-permissions) to session creation dialog, conditionally visible by agent type.
