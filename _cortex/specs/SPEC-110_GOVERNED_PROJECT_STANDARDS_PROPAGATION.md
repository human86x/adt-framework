# SPEC-110 — Governed Project Standards Propagation

**Status:** DRAFT
**Author:** Systems_Architect (CLAUDE, 2026-08-29)
**Authority:** Operator approval, 2026-08-29 (this session)
**Category:** Governance Infrastructure
**Relates to:** SPEC-031 (External Project Governance), SPEC-063 (Project Bootstrap Scaffold), SPEC-046 (Standards Governance Layer)

**Intent:** Ensure every governed project — ADT itself, every scaffolded project, and every imported project — carries the same set of ADT canonical standards, so that any agent summoned in any project operates from identical rules without having to be told them per-session.

**Triggering Event:** On 2026-08-29 the operator imported `oceanpulse_phase_two` into the ADT Console. Its specs were invisible because the project used a non-canonical layout (subfolders under `_cortex/specs/`). There was no in-project standards document defining the canonical layout, so neither the operator nor OceanPulse's own agents had a source of truth to point at. The gap is not the missing feature in OceanPulse — it is that ADT's own canonical rules do not travel with the projects it governs.

**Success Condition:** After this spec ships:
1. A freshly scaffolded project contains every `ADT_*.md` file that exists in the framework's `_cortex/standards/`.
2. An existing project imported via the Console gains those same files on import (or via an explicit `sync-standards` action).
3. Every `/hive-*` skill reads `_cortex/standards/ADT_*.md` at summon time and includes the list in its `session_start` ADS event.
4. An ADS event `standards_propagated` is emitted on every copy, listing the files and the target project.

---

## 1. Overview

ADT authors canonical standards (starting with `ADT_SPEC_LAYOUT.md`) in its own `_cortex/standards/` directory. Today those standards do not reach the projects ADT governs, so external projects can drift into non-canonical shapes without any in-project artefact to correct them.

This spec establishes three connected mechanisms:

- **Author (Architect).** A conventional home for canonical standards in the framework repo: `_cortex/standards/ADT_*.md`, with the `ADT_` prefix reserving the namespace for framework-authoritative documents.
- **Propagate (Backend + Frontend).** Scaffold-time copy into new projects and import-time / on-demand sync into existing projects.
- **Load (DevOps).** Summon-time reads in `/hive-*` skills so every agent starts with knowledge of the standards that govern its jurisdiction.

## 2. Scope

### In scope

- The `_cortex/standards/ADT_*.md` naming convention as the propagation set.
- Modifications to `adt_center/services/intent_auto_forge.py` and `_cortex/templates/project_bootstrap/` to copy the standards during scaffold.
- A new endpoint on `adt_center/api/` (e.g. `POST /api/projects/<id>/sync-standards`) plus a Console action to trigger it manually or automatically at import.
- Additions to `/hive-*` skills (in `.claude/skills/` and the equivalent Gemini/Antigravity locations) to enumerate and read standards at summon.
- A new ADS event type `standards_propagated`.

### Out of scope

- Bidirectional sync. Standards flow framework → project only. In-project edits to `ADT_*.md` are discouraged and will be overwritten by the next propagation.
- Compliance-standard JSONs (`COBIT-2019.json`, `EU-AI-ACT-2024.json`, `COMPANY-CODEX.json`). Those are governed by SPEC-046 and remain project-scoped.
- Retroactive migration of existing projects' spec layouts. That is per-project migration work (see the OceanPulse migration message associated with this session).

## 3. Design

### 3.1 Naming and Namespace

- Framework-authoritative standards MUST use the prefix `ADT_` and the extension `.md`, and live at the top level of `<framework_repo>/_cortex/standards/`.
- Every file matching `_cortex/standards/ADT_*.md` in the framework repo is a member of the propagation set.
- Project-local standards (non-framework) MUST NOT use the `ADT_` prefix, so the namespaces remain unambiguous.

### 3.2 Scaffold-Time Copy

- At project scaffold (`intent_auto_forge.py` and the SPEC-063 bootstrap path), after the target `_cortex/` skeleton is created, copy every file from the framework's `_cortex/standards/ADT_*.md` into the new project's `_cortex/standards/`.
- Overwrite is the default. Standards are read-only in-project.
- Emit one `standards_propagated` ADS event per scaffold, with `action_data = {project_path, files_copied[], source: "scaffold"}`.

### 3.3 Import-Time and On-Demand Sync

- New endpoint: `POST /api/projects/<project_id>/sync-standards`.
- Behaviour: same file copy as scaffold, but into an existing project's `_cortex/standards/`. Missing files are added; existing files with a byte-different framework source are overwritten. Files unique to the project (non-`ADT_` prefix, or `ADT_*.md` no longer in the framework) are left untouched.
- Console UX: on successful import of an external project, automatically call this endpoint and surface the result. Also expose a manual "Sync ADT Standards" button on the project detail page for later refreshes.
- Emit one `standards_propagated` ADS event per call, with `action_data = {project_path, files_copied[], files_skipped[], source: "import" | "manual"}`.

### 3.4 Summon-Time Read

- Each `/hive-*` skill (all roles), after loading `AI_PROTOCOL.md`, MUST glob `_cortex/standards/ADT_*.md` and read every match.
- The `session_start` ADS event MUST include `action_data.standards_loaded = ["ADT_SPEC_LAYOUT.md", ...]`.
- The skill scripts already run inline in the agent's context, so this is a bootstrap-checklist edit, not a new hook.

### 3.5 New ADS Event Type

Add to `adt_core/ads/schema.py`:

```
STANDARDS_PROPAGATION_EVENTS = [
    "standards_propagated",
]
```

Payload contract:

```
{
  "action_type": "standards_propagated",
  "spec_ref": "SPEC-110",
  "action_data": {
    "project_path": "<absolute path>",
    "source": "scaffold" | "import" | "manual",
    "files_copied": ["ADT_SPEC_LAYOUT.md", ...],
    "files_skipped": [],
    "framework_commit": "<short SHA if available>"
  }
}
```

## 4. Task Breakdown

- task_1: Author `_cortex/standards/ADT_SPEC_LAYOUT.md`. **Role:** Systems_Architect. **Status:** COMPLETED (this session).
- task_2: Add scaffold-time copy of `_cortex/standards/ADT_*.md` into new projects, in `intent_auto_forge.py` and the SPEC-063 bootstrap path. **Role:** Backend_Engineer.
- task_3: Implement `POST /api/projects/<id>/sync-standards` and the corresponding Console action (auto-fire on import, manual button on project detail). **Role:** Backend_Engineer + Frontend_Engineer.
- task_4: Register the `standards_propagated` event type in `adt_core/ads/schema.py` and emit it from every propagation site. **Role:** Backend_Engineer.
- task_5: Update `/hive-architect`, `/hive-backend`, `/hive-frontend`, `/hive-devops`, `/hive-overseer` skills (and their Gemini equivalents in `.gemini/`) to read `_cortex/standards/ADT_*.md` at summon and log `standards_loaded` in `session_start`. **Role:** DevOps_Engineer.
- task_6: Add integration verification — scaffold a throwaway project, confirm `ADT_SPEC_LAYOUT.md` lands in it; import an existing project without the standard, run sync, confirm the file appears and an ADS event is emitted. **Role:** DevOps_Engineer.

## 5. Acceptance Criteria

- A fresh scaffold produces `<new_project>/_cortex/standards/ADT_SPEC_LAYOUT.md` byte-identical to the framework source.
- The Console shows a "Sync ADT Standards" action on every external project; invoking it copies missing files.
- Import of an external project without `ADT_SPEC_LAYOUT.md` results in the file being present after import completes.
- An ADS query for `action_type = "standards_propagated"` returns one row per scaffold / import / manual sync.
- A `/hive-<role>` invocation in any governed project emits a `session_start` event whose `action_data.standards_loaded` includes every `ADT_*.md` present in that project's `_cortex/standards/`.
- If a project has zero `ADT_*.md` files, the agent surfaces a warning in its startup announcement and stops before executing any task.

## 6. Non-Goals

- Two-way sync. Do not implement upload of project standards back to the framework.
- Enforcement of the spec layout at write time. Discovery-side enforcement (registry non-recursion) is the only enforcement in v1.
- Versioning or diffing of standards documents. Overwrite is the model. Version history lives in the framework's git log.

## 7. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Overwriting a project's local edits to an `ADT_*.md` file. | Reserve the `ADT_` prefix for framework-authoritative content; document in each standard's header that it is read-only in-project. Log skipped files if a checksum mismatch is detected outside the propagation source. |
| Propagation runs during scaffold before the target `_cortex/standards/` directory exists. | Copy step MUST create the target directory if absent. |
| Skill drift — one harness loads standards, another does not. | task_5 covers Claude AND Gemini/Antigravity skill locations; verification in task_6 must exercise at least one Claude and one Gemini summon. |
| Framework `_cortex/standards/` grows unbounded with non-`ADT_` files. | Propagation set is filtered to `ADT_*.md`; other files (compliance JSONs, drafts) are ignored. |

## 8. Dependencies

- **SPEC-031** — External Project Governance (defines what "governed project" means).
- **SPEC-063** — Project Bootstrap Scaffold (defines the scaffold pipeline touched by task_2).
- **SPEC-046** — Standards Governance Layer (already handles compliance-standard JSONs; SPEC-110 is complementary, not overlapping).
- **AI_PROTOCOL.md** — the summon-time-read hook in task_5 is an extension of the initialisation sequence defined here.

## 9. Rollout

1. Land task_1 (this file's sibling standard). Available immediately in the framework repo.
2. Land tasks 2–5 in a single feature branch; verify via task_6 in a throwaway project.
3. Re-run sync-standards against every currently-registered external project as a one-shot migration; log a `standards_propagated` event per project.
4. Update `MASTER_PLAN.md` to reference SPEC-110 as ACTIVE.

---

*"The framework's rules must travel with the projects it governs, or those projects will drift out from under it."*
