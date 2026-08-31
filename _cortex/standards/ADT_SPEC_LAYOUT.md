# ADT Standard — Specification Layout

**Standard ID:** ADT-SPEC-LAYOUT
**Status:** BINDING
**Version:** 1.0
**Effective:** 2026-08-29
**Applies to:** ADT itself and every governed project (scaffolded or imported).
**Owner:** Systems_Architect (ADT Framework)
**Authority:** SPEC-110 (Governed Project Standards Propagation)

> This file is authoritative. It is copied into every governed project's
> `_cortex/standards/` by the framework's scaffold and import pipelines.
> Do not edit in-project — edit the source in the ADT Framework repository
> and let propagation refresh it.

---

## 1. Purpose

Define the one canonical layout for specification files (`SPEC-*.md`) inside
any governed project's `_cortex/specs/` directory, so that:

- ADT's `SpecRegistry` (`adt_core/sdd/registry.py`) can discover every spec.
- Every agent — Claude, Gemini, Antigravity, or any future harness — resolves
  spec IDs to the same file, without ambiguity.
- Cross-project tooling (spec map, forge, task graph, standards inheritance)
  can address a spec by its ID alone.

## 2. Canonical Location

All specification files live at the top level of:

```
<project_root>/_cortex/specs/
```

**Subdirectories under `_cortex/specs/` are FORBIDDEN.** The registry scans
this directory non-recursively. Any spec placed in a subfolder is invisible
to ADT and therefore ungoverned.

If discipline grouping is desired (Hardware, Software, Firmware, DevOps,
etc.), express it as a `**Category:**` metadata line inside each spec file
(see section 4), not as a directory.

## 3. Filename Rules

Two shapes are permitted, and only two:

| Shape | Example |
|---|---|
| Primary spec | `SPEC-NNN_TITLE_IN_SNAKE_CAPS.md` |
| Amendment    | `SPEC-NNN_AMENDMENT_X_TITLE_IN_SNAKE_CAPS.md` |

Rules:

- `NNN` is a zero-padded integer, monotonically allocated per project.
- `TITLE_IN_SNAKE_CAPS` is uppercase words joined by `_` — human-readable,
  no punctuation other than `_`.
- `X` for amendments is a single uppercase letter or letter+digit
  (`A`, `B`, `C`, ..., `C1`, `H`), assigned in the order the amendment is
  added.
- Extensions other than `.md` are not recognised.
- Filenames that do not begin with `SPEC-` are ignored by the registry
  and MUST NOT be used to hold specification content.

## 4. Required and Optional Metadata

Each spec file's header block MUST include:

- `# <Title>` — a level-1 markdown heading as the first non-blank line.
- `**Status:** <STATE>` — one of: `DRAFT`, `ACTIVE`, `APPROVED`,
  `COMPLETED`, `DEPRECATED`, `SUPERSEDED`.
- `**Intent:** <one-line business purpose>` — the "why" in a single line.

Each spec file's header block MAY include:

- `**Category:** <free string>` — discipline grouping (e.g. `Hardware`,
  `Software`, `Firmware`, `DevOps`, `Quality`). Used by UI for filtering.
- `**Author:**`, `**Authority:**`, `**Relates to:**`, `**Supersedes:**`,
  `**Standards refs:**` — free-form provenance and cross-references.

## 5. Identity and Uniqueness

- The **spec ID** is derived from the filename. `SpecRegistry._extract_spec_id`
  yields `SPEC-NNN` for a primary spec and `SPEC-NNN-X` for an amendment.
- Every spec ID MUST be unique across `_cortex/specs/`. Because the layout
  is flat, two files with the same `SPEC-NNN` and no amendment suffix
  create a collision the registry will silently resolve to whichever file
  `os.listdir` yields last — which is undefined behaviour and MUST be
  treated as a defect.
- Amendments are the sanctioned way to attach follow-on content to an
  existing spec without renumbering.

## 6. Migration from Non-Canonical Layouts

A project imported with specs in subfolders is non-compliant. The migration
playbook is:

1. **Inventory.** List every `SPEC-*.md` under `_cortex/specs/**`. Group by
   numeric ID. Report duplicates.
2. **Resolve collisions.** For each duplicate ID, either renumber the
   loser to the next free `SPEC-NNN`, or fold it as an amendment
   (`SPEC-NNN_AMENDMENT_A_<TITLE>.md`). Human sign-off is required per
   pair before any file moves.
3. **Encode category.** For every spec whose subfolder carried semantic
   meaning, insert a `**Category:** <SubfolderName>` line in the header
   before moving.
4. **Flatten.** Move every spec to `_cortex/specs/` (top level). Delete
   the now-empty subfolders.
5. **Verify.** Restart adt-center or reload the project in the Console.
   Confirm the registry returns the full spec count.
6. **Log.** Emit an ADS `spec_layout_migrated` event with
   `{files_moved, ids_renumbered, amendments_created, categories_encoded}`.
   Commit as a single migration.

## 7. Enforcement

- The registry (`adt_core/sdd/registry.py`) is the enforcement point for
  discovery. Any spec outside this standard is invisible and therefore
  ungoverned.
- Attempts to introduce subdirectories under `_cortex/specs/` SHOULD be
  rejected at review time. There is no runtime block today; that is a
  candidate for a future check.

## 8. Rationale

Governance requires stable, deterministic identity for every spec.
A flat layout eliminates cross-folder collision ambiguity, keeps the
registry cheap and predictable, and gives every downstream consumer
(Console, forge, task graph, standards inheritance, ADS event references)
a single unambiguous ID to key on. Grouping metadata is preserved on the
spec itself, where it can travel with the artefact and be indexed
independently of filesystem structure.

---

*"Layout is the shape of identity. Keep it flat, keep it addressable."*
