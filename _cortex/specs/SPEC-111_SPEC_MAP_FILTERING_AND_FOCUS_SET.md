# SPEC-111 — Spec Map Filtering and Focus Set

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE, 2026-08-29)
**Authority:** Operator verbal approval, 2026-08-29 (this session — "yes build that spec")
**Category:** Governance Infrastructure
**Relates to:** SPEC-021 (Operator Console), SPEC-110 (Governed Project Standards Propagation), SPEC-046 (Standards Governance Layer)

**Intent:** Give operators a low-friction way to keep only the specs they are actively working on visible in the Console's Spec Map dropdown, and to hide specs a given role cannot act on, so Spec Map navigation stays fast as project spec counts grow into the dozens or hundreds.

**Triggering Event:** On 2026-08-29 the operator imported `oceanpulse_phase_two` into the ADT Console. The project brought ~47 specs, most of them non-software from a code-oriented agent's perspective (Hardware, Firmware, Quality, Phase2_Commercial), and many already COMPLETED. All of them landed in a single flat dropdown with no filtering, making Spec Map navigation unusable for focused work.

**Success Condition:** After this spec ships:
1. `SpecRegistry` parses `**Category:**` from spec headers and exposes it on the list_specs payload.
2. Every governed project has (or can bootstrap) `_cortex/spec_map.json` capturing role-to-category mapping, a per-project focus set, and a hide-status list.
3. The Console Spec Map dropdown auto-filters by the active role's category list and by the hide-status defaults; three header toggles override each layer.
4. First open of a project without `spec_map.json` triggers a one-time Bootstrap Wizard that populates role-to-category from a checkbox matrix over the categories actually present in that project.
5. A Manage Focus panel lets the operator curate the focus set and edit the role-to-category mapping at any time.
6. Every write to `spec_map.json` emits an ADS event.

---

## 1. Overview

Spec Map is the operator's primary spec-navigation surface. Today it lists every spec the registry returns, in ID order, with no filtering by relevance, role, status, or attention. That works for a repo like ADT itself (curated, single-discipline) and breaks the moment a project like OceanPulse arrives with mixed disciplines and a long tail of completed work.

This spec introduces a small per-project manifest plus three complementary filter layers, keyed off metadata the framework can already read (status) or is about to read (category, as of SPEC-110's `ADT_SPEC_LAYOUT`).

## 2. Scope

### In scope

- Registry extension to parse `**Category:**` and include it in `list_specs()` output.
- New per-project manifest `_cortex/spec_map.json` with a defined schema.
- REST endpoints on `adt_center/api/` for reading and updating the manifest.
- Console dropdown filter logic driven by the manifest and three header toggles.
- Bootstrap Wizard modal that runs once per project (or on demand).
- Manage Focus panel accessible from the Spec Map dropdown at any time.
- Two new ADS event types.

### Out of scope

- **Role vocabulary extension.** Adding hardware/firmware/QA/etc. roles is a separate concern (see §9 follow-on note). SPEC-111 works with the roles ADT already defines.
- **Server-side enforcement of the filter.** The dropdown is a UI convenience. Agents can still request any spec by ID via the API.
- **Persisting focus set per user or per session.** Focus is per project, one shared list.
- **Two-way sync of focus set across concurrent Console instances.** Last-write-wins is acceptable; the ADS event carries the previous hash for audit.

## 3. Design

### 3.1 Registry Extension

- Add `_parse_category(path)` to `adt_core/sdd/registry.py`, matching `**Category:**\s*(.*)` in the first ~2000 chars, mirroring the existing `_parse_intent` helper.
- Include the parsed value as `category: str | null` in every dict returned by `list_specs()` and `get_spec_detail()`.
- Behaviour when absent: `null`. No default synthesised.

### 3.2 Manifest Schema (`_cortex/spec_map.json`)

```json
{
  "version": 1,
  "role_categories": {
    "Backend_Engineer":  ["Software", "DevOps"],
    "Frontend_Engineer": ["Software", "UI"],
    "Systems_Architect": [],
    "DevOps_Engineer":   ["DevOps", "Infrastructure"],
    "Overseer":          []
  },
  "focus_set": [],
  "hide_statuses": ["COMPLETED", "DEPRECATED", "SUPERSEDED"],
  "last_bootstrapped_at": null,
  "last_updated_by": null,
  "last_updated_at": null
}
```

Semantics:

- `role_categories[<role>]` — allowed categories for that role.
  - Empty array: no category filter, all categories shown (plus a soft warning in the dropdown header that no filter is configured).
  - Missing key: same as empty array.
- `focus_set` — explicit list of spec IDs.
  - Empty: show everything that passes the auto-filters.
  - Non-empty: show only these; overrides `hide_statuses` and `role_categories` (an operator who deliberately focuses a completed spec wants to see it).
- `hide_statuses` — list of `Status:` values to hide unless the "Show completed" toggle is on. Default `["COMPLETED", "DEPRECATED", "SUPERSEDED"]`.
- `last_bootstrapped_at` — ISO8601 timestamp; `null` triggers the Bootstrap Wizard on next project open.
- `last_updated_*` — provenance for the ADS event and Manage Focus panel display.

Tier 3 (Operational). No SCR required to edit.

### 3.3 Filter Logic (in priority order)

Applied by the Console after receiving the raw spec list:

1. Load all specs from `GET /api/specs`.
2. **If `focus_set` non-empty** → keep only specs whose ID is in `focus_set`. Return.
3. Otherwise:
   1. Drop specs whose `status` is in `hide_statuses`. (**Skip** if "Show completed" toggle on.)
   2. Drop specs whose `category` is not in `role_categories[<active_role>]`. (**Skip** if "Show all categories" toggle on, or if `role_categories[<active_role>]` is empty.) Specs with `category == null` always pass this filter.
   3. Return.

Master override: **"Show all specs"** toggle bypasses steps 2 and 3 entirely and returns the raw list.

### 3.4 Bootstrap Wizard

**Trigger:** Console opens a project whose `_cortex/spec_map.json` is missing OR whose `last_bootstrapped_at` is `null`.

**UI:** A single modal.

- Title: "Route this project's specs to roles"
- Body: a checkbox matrix.
  - Rows: the unique `Category` values found in this project's specs, plus one row labelled `(uncategorized)` if any spec has `category == null`.
  - Columns: the role names loaded from `_cortex/jurisdictions.json`.
  - Cells: checkboxes, initial state all unchecked.
  - Presets under the matrix:
    - "Assign all to all" — check every cell (roles see everything).
    - "Auto-guess by name" — heuristic: any category containing "software", "code", "backend", "frontend", "api", "ui", "server", "ops", "devops" → check for `Backend_Engineer`, `Frontend_Engineer`, `DevOps_Engineer` per keyword match. Everything else uncthecked. Operator adjusts.
- Footer:
  - "Save & continue" — writes `role_categories` and `last_bootstrapped_at`. Emits `spec_map_bootstrap_completed` ADS event.
  - "Configure later" — closes without writing. Wizard reappears on next open until Saved. Note in header: "Filtering disabled until roles are configured."

The wizard also constructs and writes a default `hide_statuses` value if the manifest didn't exist.

### 3.5 Manage Focus Panel

Accessible from a gear icon in the Spec Map dropdown header, and also linked from the (uncategorized) row of the Bootstrap Wizard.

Three sections:

- **Focus set.** Table of every spec with a checkbox column. Ticked rows are in `focus_set`. Batch actions: "Focus only ACTIVE", "Focus only APPROVED", "Clear focus". Save on button press.
- **Role → Category mapping.** The same matrix as the Bootstrap Wizard, re-editable. Save on button press.
- **Uncategorized specs.** Any spec with `category == null` is listed with an inline text input. Typing a category and hitting Enter edits the spec file's header (adds `**Category:** <value>` under the existing metadata block). This is a Tier 3 spec edit and does NOT require an SCR. Emits `spec_edited` ADS event. Included in v1; can be deferred to v1.1 if scope pressure appears at implementation time.

### 3.6 REST Endpoints

- `GET  /api/projects/<project_id>/spec-map` — returns current manifest, or a fully-defaulted manifest if the file doesn't exist.
- `PUT  /api/projects/<project_id>/spec-map` — replaces the whole manifest. Server validates shape, writes atomically, emits `spec_map_updated` ADS event with `{prev_hash, next_hash, changed_keys[]}`.
- Optional convenience: `PATCH /api/projects/<project_id>/spec-map/focus-set` — for the common "toggle one spec in focus" action.

### 3.7 ADS Event Types

Add to `adt_core/ads/schema.py`:

```
SPEC_MAP_EVENTS = [
    "spec_map_bootstrap_completed",   # {project_path, roles_configured[], categories_seen[]}
    "spec_map_updated",               # {project_path, changed_keys[], prev_hash, next_hash}
]
```

## 4. Task Breakdown

- task_1: Extend `SpecRegistry` to parse `**Category:**` and include it in `list_specs()` and `get_spec_detail()`. **Role:** Backend_Engineer.
- task_2: Add `_cortex/spec_map.json` default template. Implement `GET` / `PUT` endpoints in `adt_center/api/`. Validate shape server-side. **Role:** Backend_Engineer.
- task_3: Register the two SPEC-111 event types in `adt_core/ads/schema.py` and emit them from the manifest write path. **Role:** Backend_Engineer.
- task_4: Implement dropdown filter logic in `adt-console/src/js/spec_map.js`: three header toggles ([Show completed], [Show all categories], [Show all specs]), focus-set precedence, role-based category filter, "no filter configured" soft warning. **Role:** Frontend_Engineer.
- task_5: Implement Bootstrap Wizard modal: matrix over categories × roles, "Assign all to all" and "Auto-guess by name" presets, save/skip. **Role:** Frontend_Engineer.
- task_6: Implement Manage Focus panel: focus checkboxes with batch actions, editable role matrix, inline category editor for uncategorized specs. **Role:** Frontend_Engineer.
- task_7: End-to-end verification. Fresh-import a project with mixed categories. Confirm wizard fires, save writes correct manifest, dropdown obeys role/status/focus, ADS events fire on each write. **Role:** DevOps_Engineer.

## 5. Acceptance Criteria

- `SpecRegistry.list_specs()` returns `category: str | null` for every spec.
- On first Console open of a project without `spec_map.json`, the Bootstrap Wizard modal appears. On save, `_cortex/spec_map.json` exists with correct `role_categories` and non-null `last_bootstrapped_at`.
- With `role_categories["Backend_Engineer"] = ["Software"]` and Backend active, the dropdown shows only specs whose `category == "Software"` OR whose `category` is null.
- Default `hide_statuses` hides COMPLETED specs. Toggling "Show completed" re-exposes them.
- `focus_set = ["SPEC-007", "SPEC-025"]` makes the dropdown show exactly those two specs regardless of status or role.
- A role with empty `role_categories[role]` shows all specs, plus a header warning "no category filter configured for this role — configure in Manage Focus".
- Every `PUT /api/projects/<id>/spec-map` emits one `spec_map_updated` ADS event with `changed_keys` populated.
- Setting a category via the Manage Focus inline editor writes `**Category:** <value>` into the spec file and emits a `spec_edited` event.

## 6. Non-Goals

- Role vocabulary extension (`Hardware_Engineer`, `Firmware_Engineer`, etc.).
- Per-user or per-session focus sets.
- Server-side filter enforcement — the filter is a UI convenience, not a permission.
- Multi-user real-time sync of manifest edits.

## 7. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Category typos in freeform strings silently exclude specs from the wrong role. | The Manage Focus panel surfaces the unique category set for the project; operator can spot typos. Consider a "categories in use vs categories mapped" diff view in v1.1. |
| Operator skips the Bootstrap Wizard and later wonders why the filter is not working. | Soft-warning banner in the dropdown header whenever `role_categories[<active_role>]` is empty, linking to Manage Focus. |
| Focus set becomes stale as specs complete and new ones arrive. | Batch action "Clear focus" is one click; "Focus only ACTIVE" recomputes from current status. |
| Concurrent edits from multiple Console instances overwrite each other. | Whole-document PUT with last-write-wins. ADS event carries `prev_hash` and `next_hash` so audit can reconstruct the sequence. Not a data-loss risk beyond the manifest itself. |
| Uncategorized specs pass every category filter and dilute the "clean" view. | Manage Focus panel highlights uncategorized specs with the inline editor; operator can categorize them in-panel without leaving the flow. |

## 8. Dependencies

- **SPEC-021** — Operator Console (defines the Spec Map surface being extended).
- **SPEC-110** — Governed Project Standards Propagation (introduces `ADT_SPEC_LAYOUT.md` which defines the `**Category:**` field this spec consumes). SPEC-111 does not block on SPEC-110 landing — it can read categories the moment they appear in spec headers.
- **`_cortex/jurisdictions.json`** — source of truth for the role list used in the Bootstrap Wizard matrix.

## 9. Follow-On Work (Not This Spec)

**SPEC-112 candidate — Role Vocabulary Extension.** ADT's role set today (`Systems_Architect`, `Backend_Engineer`, `Frontend_Engineer`, `DevOps_Engineer`, `Overseer`) doesn't cover disciplines like `Hardware_Engineer` or `Firmware_Engineer`. SPEC-111 lets the operator hide hardware specs from code-agent dropdowns, but it doesn't let an agent *act* on them. Extending the role vocabulary — per-project role declarations with their own jurisdictions — is the natural next step. Log this now so it isn't lost.

## 10. Rollout

1. **task_1** (registry) — backwards compatible, lands independently.
2. **task_2 + task_3** — manifest schema + endpoints + event types, single feature branch.
3. **task_4 + task_5 + task_6** — Console UI, single feature branch, gated behind the manifest work.
4. **task_7** — verification on a throwaway project fixture with mixed categories and statuses.
5. Update `MASTER_PLAN.md` to reference SPEC-111 as ACTIVE (via SCR — MASTER_PLAN is Tier 1).

---

*"A map that shows everything shows nothing. Focus is a first-class governance surface."*
