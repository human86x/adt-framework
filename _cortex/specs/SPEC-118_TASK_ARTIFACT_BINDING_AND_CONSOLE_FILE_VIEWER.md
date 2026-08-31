# SPEC-118 — Task-Artifact Binding & In-Console File Viewer/Editor

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE, 2026-08-31)
**Authority:** Operator verbal approval, 2026-08-31 (this session — "1. code mirror. 2 read only by defaults if needed edited. 3. file binding code view anotations in one go" then "go")
**Category:** Governance Infrastructure
**Version target:** v0.4.2 (feature release; still pre-v0.5.0 which is reserved for DTGP debut)
**Relates to:** SPEC-055 (Build Orchestration), SPEC-057 (Agent Mailbox), SPEC-105 (Worker Namespace Sandbox / Reconciler), SPEC-111 (Spec Map Filtering), SPEC-117 (Reconciler Completion Verification Hardening — TRUST-CRITICAL)

**Intent:** Close the loop between "task marked complete" and "operator can inspect the actual code". Bind every task to the files it produced, expose those files in the Console via an embedded CodeMirror 6 viewer/editor, and let the operator annotate specific lines so the next agent working on that file sees the note. Companion to SPEC-117: the evidence gate tests *whether an artifact exists*; this spec puts *human eyes on the artifact contents* and provides an inline correction surface.

**Triggering Event:** On 2026-08-31 the operator asked to bind Console tasks to real files so a click on a task surfaces the files it touched, opens them in an internal viewer, and (when needed) an editor. The goal named explicitly: verify agents' work in real time and flag specific code regions for the next agent. This becomes especially important once DTGP (SPEC-113) lands and IoT-firmware development produces hardware-affecting artifacts — the operator wants a "super easy navigatable and optimized hardware development environment" surrounding those flows. SPEC-118 is the software plumbing that flow depends on.

**Success Condition:** After this spec ships:
1. Every task in the Console detail panel shows a "Bound Files" list derived from `acceptance_criteria.artifacts[]`, worker-execution-window mtimes, and the SPEC-105 reconciler's `allowed_files` list — each tagged with its source.
2. Clicking a bound file opens it in a CodeMirror 6 viewer with syntax highlighting for the languages ADT projects actually use (Python, Rust, JS/TS, Markdown, JSON, YAML, TOML, C/C++, plain text).
3. An "Edit" toggle enables saving changes back through a governed backend endpoint that routes writes through DTCP for logging.
4. Optimistic-concurrency SHA-256 check prevents the operator from clobbering agent-written content that changed between load and save.
5. Operator can click the CodeMirror gutter to attach a line-annotation, stored in `<project>/_cortex/annotations.jsonl`.
6. When an agent is dispatched via SPEC-057 mailbox to work on a file that has open annotations, the mailbox `context.file_annotations[]` includes them so the agent sees the operator's notes before starting.
7. Every operator file-edit and annotation emits an ADS event so the audit trail captures human-in-the-loop corrections.

---

## 1. Positioning

SPEC-117 answered "was work produced?" — file exists on disk, sha256 matches, gate passed. SPEC-118 answers "*what* was produced, and is it correct?" — human eyes on the actual code, correction surface if it isn't.

| Spec | Role in the trust chain |
|---|---|
| SPEC-055 | Orchestrator dispatches worker to a task. |
| SPEC-105 | Sandbox + reconciler landing files under DTCP authority. |
| SPEC-057 | Mailbox delivering context to agents. |
| SPEC-117 | Reconciler evidence gate — refuses phantom completions. |
| **SPEC-118** | **Console binds task → files → viewer/editor → operator annotation → next agent.** |

The whole point of ADT is external orchestration with human authority preserved. SPEC-118 gives that authority a workbench.

## 2. Scope

### In scope

- Derived `bound_files` field on task records, computed from three sources (declared, detected, reconciler-landed).
- Backend endpoint to enumerate bound files per task.
- Backend endpoint to read file contents (GET) and write them (PUT) under DTCP-routed authority with SHA-256 optimistic-concurrency.
- Backend endpoints for annotations (POST / GET), backed by `<project>/_cortex/annotations.jsonl`.
- CodeMirror 6 vendored into `adt-console/src/vendor/codemirror6/` with language packs for Python, Rust, JS/TS, Markdown, JSON, YAML, TOML, C/C++, plain text.
- Console UI:
  - Task detail panel gains a "Bound Files" section with source badges.
  - File click opens a CodeMirror viewer panel.
  - Read-only by default. "Edit" button toggles editing. Save button PUTs.
  - Line-gutter click opens an annotation input; annotations render as gutter markers.
- SPEC-057 mailbox integration: annotations for a target file are attached to the next agent context that touches that file.
- New ADS event types for binding computation, file edits, and annotation lifecycle.

### Out of scope

- **Full IDE features.** No integrated terminal, no build system, no debugger, no run-configuration. This is a viewer + editor + annotator, not VS Code.
- **Real-time collaborative editing** (Google Docs style) between multiple operators.
- **Agent-authored annotations** back to the operator ("agent flags: operator input needed on line 42"). Reserved for follow-on.
- **Multi-file refactoring / project-wide find-replace.** Single-file only.
- **Git-integrated diff views** (blame, cross-commit compare). "Current on disk vs. last-agent-modified" is enough for v1.
- **Binary file rendering** (images, compiled artifacts). Refuse to render; offer download-only.
- **Files above a hard size cap** (default 5 MB). Refuse to render; log why.
- **Resolved-state on annotations.** All annotations are open in v1; resolution flow is a follow-on.

## 3. Design

### 3.1 Task ↔ File Binding

Every task gains a derived `bound_files` list on GET. Not stored redundantly on disk — computed at request time and cached only in the response (Console re-fetches when it opens the task detail).

Each entry: `{path, source, exists, size, mtime, sha256_short, is_binary, is_over_size_cap}`.

**Sources (an entry may carry more than one; UI shows them all):**

- **`declared`** — from `task.acceptance_criteria.artifacts[]`. Absolute source of truth for what the spec author intended.
- **`detected`** — files whose mtime falls inside the worker's execution window (`[build_worker_spawned.ts, build_worker_*.ts + grace]`). Broader net; catches everything the worker touched, including files not listed in the spec.
- **`reconciler_landed`** — from the SPEC-105 reconciler's `allowed_files` list on `_rec_summary`. Files DTCP explicitly permitted through overlay reconciliation.

**Derivation algorithm** (in a new `adt_core/sdd/task_bindings.py`):

```
def compute_bound_files(task, project_root, ads_events):
    declared  = extract_artifact_paths(task.acceptance_criteria)
    window    = find_worker_window(ads_events, task.task_id)
    detected  = scan_mtimes_in_window(project_root, window)
    landed    = extract_allowed_files(ads_events, task.task_id)
    return merge_by_path(declared, detected, landed, project_root)
```

Merge: same path from multiple sources becomes one entry with `source: ["declared", "detected"]`.

Filter: exclude `.log`, `.pyc`, `__pycache__/`, common transient paths. Configurable via `_cortex/config/task_bindings_ignore.txt`.

### 3.2 Backend File Endpoints

All under adt-center, all project-scoped, all routing writes through DTCP.

- `GET /api/projects/<project_name>/task/<task_id>/bound-files`
  - Response: `{task_id, bound_files: [entry, ...], computed_at}`.

- `GET /api/projects/<project_name>/file?path=<rel_path>`
  - Response: `{path, content, size, mtime, sha256, mime_hint, line_count, is_binary}`.
  - Path traversal protection: resolve `<project_root>/<rel_path>`, verify the resolved path starts with `<project_root>/`, refuse otherwise.
  - Size cap: 5 MB (configurable). Larger → 413 with `{error: "too_large_to_view", size, cap}`.
  - Binary detection: if first 1024 bytes contain a NUL byte → 415 with `{error: "binary_file", download_url}`.

- `PUT /api/projects/<project_name>/file`
  - Body: `{path, content, previous_sha256, task_ref}`.
  - Optimistic concurrency: compute current sha256; if `previous_sha256` mismatches → 409 with `{error: "sha256_mismatch", current_sha256, current_content_or_diff}`. Operator resolves and re-submits.
  - Routes the write through DTCP — the operator's session_id becomes the write-authority principal; refusal from DTCP surfaces as 403.
  - On success: emit `operator_file_edit` ADS event (see §3.6). Response includes new sha256.

- `POST /api/projects/<project_name>/annotations`
  - Body: `{path, line_start, line_end, note, task_ref?}`.
  - Appends to `<project>/_cortex/annotations.jsonl`. One JSON per line.
  - Returns the annotation record with a generated `id`.
  - Emits `operator_annotation_added`.

- `GET /api/projects/<project_name>/annotations?path=<rel>&task_id=<id>`
  - Returns `{annotations: [...]}` filtered by path and optionally task.

### 3.3 CodeMirror 6 Vendoring

CodeMirror 6 is modular. Bundle at build-time into a single vendored file:

- **Location:** `adt-console/src/vendor/codemirror6/codemirror.bundle.js` + `codemirror.bundle.css`.
- **Modules included:**
  - `@codemirror/state`, `@codemirror/view` (core)
  - `@codemirror/lang-python`, `@codemirror/lang-rust`, `@codemirror/lang-javascript`, `@codemirror/lang-markdown`, `@codemirror/lang-json`, `@codemirror/lang-yaml`, `@codemirror/lang-cpp`
  - `@codemirror/theme-one-dark` (matches Console dark theme)
  - `@codemirror/basic-setup` (line numbers, gutter, search)
- **Vendoring process:** one-time. DevOps runs `npm install` in a scratch dir, uses `esbuild` to bundle to a single ESM file, commits the resulting bundle. No CDN references anywhere (Tauri CSP would block them).
- **Estimated size:** ~250 KB minified. Acceptable.

TOML syntax is not first-party in CodeMirror 6; use the generic bracket-highlight fallback or ship `@codemirror/legacy-modes/mode/toml`. Same for plain text (no language extension needed).

### 3.4 Edit Mode + Save Flow

- Viewer opens **read-only** on file click. Explicit "Edit" button in the panel header toggles editing.
- Save button appears once editing enabled. Click → PUT with `previous_sha256` from the initial GET.
- **Conflict handling:** on 409, open a diff pane showing current-on-disk vs. operator's local edits, three action buttons: `[Reload disk copy]` (discard operator edits), `[Force overwrite]` (submit again without previous_sha256), `[Merge manually]` (operator hand-merges in the viewer). All three route through DTCP and emit ADS.
- **Unsaved changes indicator:** dot on the tab title when the buffer is dirty. Prompt on close if dirty.

### 3.5 Annotations

- **Storage:** `<project>/_cortex/annotations.jsonl`. Append-only. One JSON per line.
- **Schema:**
  ```json
  {
    "id": "ann_20260831_193000_ab12",
    "ts": "2026-08-31T19:30:00Z",
    "path": "adt_core/dtgp/vault.py",
    "line_start": 42,
    "line_end": 42,
    "note": "This key derivation drops the salt; needs review.",
    "author": "operator",
    "session_id": "sess_...",
    "task_ref": "task_205"
  }
  ```
- **Rendering:** CodeMirror gutter shows a small dot on annotated lines. Hover reveals the note. Click reveals full detail with `[Edit]` and (v1.1) `[Resolve]` buttons.
- **Delivery to agents (mailbox integration):**
  - When the SPEC-057 mailbox composes a message for an agent whose task lists a bound_file with open annotations, the mailbox `context.file_annotations = [...]` array is populated with all open annotations for those files.
  - Agent sees "operator has open annotations on these files: [...]" as part of its startup context.
  - Every delivery emits `annotation_delivered_to_agent` ADS event so the trail is auditable.

### 3.6 New ADS Event Types

Add to `adt_core/ads/schema.py`:

```
TASK_BINDING_EVENTS = [
    "task_bound_files_computed",       # {task_id, count, sources_breakdown}
    "operator_file_read",              # {path, size, session_id, task_ref} - throttled per session
    "operator_file_edit",              # {path, size_before, size_after, sha256_before, sha256_after, task_ref}
    "operator_file_edit_conflict",     # {path, current_sha256, operator_previous_sha256, resolution}
    "operator_annotation_added",       # {annotation_id, path, line_start, line_end, note_length, task_ref}
    "annotation_delivered_to_agent",   # {annotation_id, agent_session_id, delivery_channel}
]
```

Throttling on `operator_file_read`: at most one per unique (session_id, path) per 5 minutes. Prevents log spam from re-scrolls.

## 4. Task Breakdown

- task_1: `adt_core/sdd/task_bindings.py` — the derivation logic (declared + detected + reconciler-landed → merged bound_files). Includes ignore-list handling. **Role:** Backend_Engineer.
- task_2: `GET /api/projects/<name>/task/<id>/bound-files` endpoint in `adt_center/api/governance_routes.py`. **Role:** Backend_Engineer.
- task_3: `GET /api/projects/<name>/file` and `PUT /api/projects/<name>/file` endpoints. Path-traversal protection, size cap, binary detection, SHA-256 optimistic concurrency, DTCP-routed writes. **Role:** Backend_Engineer.
- task_4: `POST` and `GET` annotation endpoints; `_cortex/annotations.jsonl` append/read. **Role:** Backend_Engineer.
- task_5: Vendor CodeMirror 6 bundle into `adt-console/src/vendor/codemirror6/`. One-time bundling step + commit of the bundle files. **Role:** DevOps_Engineer + Frontend_Engineer.
- task_6: Console UI — task detail panel gains "Bound Files" list with source badges. File click opens the viewer panel. **Role:** Frontend_Engineer.
- task_7: CodeMirror viewer panel — read-only rendering with syntax highlighting per language, line numbers, dark theme. **Role:** Frontend_Engineer.
- task_8: Edit mode toggle + save button + conflict resolution UI (diff pane on 409). **Role:** Frontend_Engineer.
- task_9: Annotation UI — click gutter to add, render existing annotations as markers, hover to preview, click to detail. **Role:** Frontend_Engineer.
- task_10: SPEC-057 mailbox integration — inject open annotations into `context.file_annotations` for agents whose next task touches annotated files. **Role:** Backend_Engineer.
- task_11: Register `TASK_BINDING_EVENTS` in `adt_core/ads/schema.py`. Emit from all backend paths. **Role:** Backend_Engineer.
- task_12: End-to-end verification. Complete a task via a small fixture worker, open task in Console, verify bound files show correctly, open a file, edit + save (verify conflict path too), add an annotation, dispatch an agent to that file, verify agent receives the annotation. **Role:** DevOps_Engineer.

## 5. Acceptance Criteria

- `GET /api/projects/adt-framework/task/<real_task_id>/bound-files` returns at least the declared artifacts for a task that has them.
- `GET /api/projects/adt-framework/file?path=adt_core/dtgp/vault.py` returns 200 with the file content, correct size, and sha256; `?path=../../etc/passwd` returns 403.
- `PUT /api/projects/<name>/file` with a valid `previous_sha256` succeeds and emits `operator_file_edit`; with an out-of-date `previous_sha256` returns 409 with a `current_sha256` and content preview.
- Console task detail panel shows a "Bound Files" section for any task with acceptance_criteria.artifacts or a worker execution window.
- Clicking a bound file opens a CodeMirror viewer with syntax highlighting matching the file's extension (Python → py highlight, Markdown → md, etc.).
- Clicking "Edit" turns the viewer editable; changes are saved via PUT with correct SHA-256.
- Clicking a gutter line and entering an annotation appends a JSON record to `<project>/_cortex/annotations.jsonl` and emits `operator_annotation_added`.
- Dispatching a SPEC-057 mailbox message to an agent whose target task has an annotated bound file includes the annotation in `context.file_annotations`, and emits `annotation_delivered_to_agent`.
- Files larger than 5 MB return 413 with a friendly error; binary files return 415.
- Bundle size for CodeMirror 6 vendored bundle is under 400 KB minified + gzipped.

## 6. Non-Goals (recap)

- Full IDE. Multi-file operations. Real-time collab. Agent-authored annotations. Git-integrated blame/diff. Resolved-annotations flow (v1.1).

## 7. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| **Path traversal via crafted `?path=` string.** | Resolve to absolute path and verify prefix match against project_root. Reject on mismatch. Unit test covers `..`, symlinks, absolute paths, URL-encoded traversals. |
| **Operator clobbers agent's in-progress work.** | SHA-256 optimistic concurrency — server rejects PUT if the file has changed since the read. Conflict UI shows current-on-disk vs. operator edits. |
| **Large files crash CodeMirror.** | Hard cap (default 5 MB) at the backend. Refuse-to-render at API level; the client never receives the payload. |
| **Binary files rendered as garbage text.** | NUL-byte detection in first 1024 bytes. Refuse with 415; offer download-only link. |
| **CodeMirror bundle blocked by Tauri CSP.** | Vendored locally under `adt-console/src/vendor/codemirror6/`. No CDN references anywhere. |
| **Annotations grow unbounded in a long-lived project.** | Append-only for v1. Follow-on introduces resolved-state and archival compaction. Format is JSONL so tail-based reads scale. |
| **Agent receives too many annotations per delivery.** | Cap at 20 most-recent annotations per file in `context.file_annotations`. Log truncation on the ADS event. |
| **Operator edits create silent divergence from the spec's acceptance_criteria.** | Every `operator_file_edit` is ADS-logged with `task_ref`. Subsequent SPEC-117 reruns for that task will re-verify against the acceptance_criteria; if the operator edit invalidated the criteria, the task moves back to `failed` (correct outcome — the ledger stays honest). |
| **DTCP refuses the write because the operator's session lacks jurisdiction.** | Operator's own session runs under the `Overseer` role by default in the Console — Overseer has broad audit authority. If the write path is Sovereign (Tier-1), the operator is routed through an SCR flow instead of a direct write. Enforcement inherits from existing DTCP policy — no new bypass. |

## 8. Dependencies

- **SPEC-057** — Agent Mailbox. Task_10 hooks into its message composition to inject `context.file_annotations`.
- **SPEC-105** — Reconciler `allowed_files` list. One of the three binding sources.
- **SPEC-117** — Provides `head_sha_at_spawn` + evidence-window semantics that make "detected files in window" computable.
- **DTCP** — All file writes route through DTCP. No file write happens outside its authority.
- **CodeMirror 6** — External dependency, vendored at build time. Version pinned in the vendoring script.

## 9. Follow-On Work

- **v1.1: Resolved annotations.** Operator marks an annotation resolved; agent's next delivery only includes unresolved ones. UI shows resolved marks distinctly.
- **v1.2: Agent-authored annotations.** Agent flags "need operator input on line X" from within its task; UI surfaces it to the operator.
- **Diff view.** Side-by-side current-on-disk vs. state-at-task-spawn.
- **Multi-file annotations dashboard.** Overview of all open annotations across the project.
- **Console file search.** Grep-across-bound-files for a task.

## 10. Rollout

1. **task_1 + task_11** — binding logic module + schema events. No behavior change externally; enables downstream tasks.
2. **task_2** — bound-files endpoint. Independently testable via curl.
3. **task_3 + task_4** — file GET/PUT + annotations endpoints. Full API surface before Console touches it.
4. **task_5** — CodeMirror vendoring. Ship the bundle files as a discrete commit.
5. **task_6 + task_7** — Console file list + viewer.
6. **task_8** — Edit + save.
7. **task_9** — Annotation UI.
8. **task_10** — Mailbox integration for annotation delivery.
9. **task_12** — E2E verification with a real fixture.
10. Version bump to **v0.4.2** (feature release). Release notes headline: "Task-file binding + inline viewer/editor + annotations for human-in-the-loop code review."
11. Then SPEC-113 (DTGP) begins the v0.5.0 track.

---

*"Ledgers say what happened. Files say what's there. Governance requires both, and the operator's eye between them."*
