# SPEC-081: Project Knowledge Reuse + Warm-up Bundle

**Status:** APPROVED (2026-08-08, Systems_Architect self-approval — Tier-3 Operational, no SCR required)
**Author:** Systems_Architect (CLAUDE)
**Date:** 2026-08-08
**Tier:** Operational
**Priority:** HIGH — enables "second wish takes 10 min instead of 3 hours" story + demo-friendly speed
**Complements:** SPEC-067 (Forge Wizard), SPEC-080 (Standards Inheritance), SPEC-072/075 (Intent Classification)

**Intent:** Two complementary features that make the framework faster WITHOUT fabricating any events or corrupting the audit trail: (a) a **warm-up bundle** that pre-loads models, classifiers, caches, and connections so operator clicks land instantly; (b) a **project knowledge reuse** system that lets the operator fork a new project from a similar prior one — real workers run in verify-first mode instead of inventing from scratch. Every ADS event fired is real; every worker decision is real; the only thing eliminated is redundant invention.

**Triggering Event:** 2026-08-08 operator design conversation during demo prep: "if there are 4-5 solar system projects hanging in there the system should prefer the latest one" + earlier "we could add a shortcut system that uses aquired knowlage from a selected project". Operator explicitly rejected a fake-replay approach ("its a misleading feature") — this spec is the honest, real-work alternative.

**Success Condition:**
1. Warm-up: opening the Forge Wizard after adt-center start shows the standards catalog and template list within 200 ms (was ~450 ms cold /api/projects + ~200 ms /api/mrr/library_stats), and MRR intent classification completes in ≤5 s on a fresh wish (was ~35 s cold-load).
2. Reuse: after two prior "solar system" projects exist, forging a NEW similar wish (>70 % fingerprint match) shows the operator a top-3 ranked picker with the most-recently-touched match highlighted; on "Fork from it" click, the new project boots with copied specs + tasks tagged `reused_from` + `verify_status: pending`.
3. Verify-mode Architect worker runs on the pre-populated tree, emits `spec_verified_from_reuse` (or `spec_edited_from_reuse` / `spec_dropped_from_reuse` / `spec_added_new`) events — real decisions on real specs, no fabricated activity.
4. Full audit trail: every reused artifact carries a `reused_from` field; grep on `_cortex/ads/events.jsonl` shows the verify events distinctly from fresh-forge events.

---

## 1. Warm-up bundle (Part A)

### 1.1 Extend `agy_warmkeep.sh`
Already probes agy every 20 min. Extend:
- On startup, additionally do one `curl -s http://localhost:5001/api/mrr/library_stats > /dev/null` to warm the MRR endpoint.
- Log to `/tmp/agy_warmkeep.log` as before.

### 1.2 adt-center startup pre-init
In `adt_center/app.py` `create_app` (or wherever startup hooks live), after startup fsck:
- Pre-import `adt_core.standards.intent_matcher` (module-level heavy imports done once)
- Pre-fetch project registry once and cache in-process (5-min TTL)
- Pre-fetch templates list + standards catalog (5-min TTL)
- Log INFO: `"warmup pre-init: matcher loaded, registry cached, catalog cached"`

### 1.3 Frontend cache
`launcher.js` `openForgeWizard()` currently hits `/api/projects`, `/api/mrr/library_stats`, etc. every open. Cache these in-memory for the wizard's lifetime (already partially done for catalog) — extend to project registry.

## 2. Fingerprinting (Part B.1)

New module `adt_core/reuse/fingerprint.py`:

- `compute_fingerprint(wish_text) -> {"tokens": [...], "hash": "..."}` — normalise wish (lowercase, strip punctuation, remove stopwords) → keyword set → SHA-256 for quick equality + full token set for Jaccard similarity.
- `similarity(fp_a, fp_b) -> float` — Jaccard on token sets (intersection / union).

Fingerprints stored at `_cortex/ops/project_fingerprints.jsonl` — one line per project:
```json
{"project_name": "solar_system_1786032782", "fingerprint_hash": "...", "tokens": [...], "wish_preview": "3D solar system with hand tracking...", "last_touched": "2026-08-08T10:30:00Z", "spec_count": 4, "task_count": 27}
```

- **Auto-index** on forge completion: `POST /api/governance/forge/<session_id>/finalize` (or the existing forge_complete handler) appends a new fingerprint entry.
- **Backfill** script `_cortex/ops/backfill_fingerprints.py` — one-time, walks `/home/human/Projects/*` looking for `_cortex/ops/forge_brief.json`, computes + appends.

## 3. Similar-projects API (Part B.2)

New endpoint `POST /api/governance/forge/similar_projects`:
- Body: `{"wish": "operator's wish text"}`
- Response: `{"matches": [{"project_name":"...", "similarity": 0.78, "last_touched_iso": "...", "spec_count": 4, "task_count": 27, "wish_preview": "..."}, ...] }` (top 5, above 0.35 similarity threshold)
- Sort by combined score: `0.4 * recency_weight + 0.6 * similarity_score` where `recency_weight = exp(-days_since_last_touched / 30)` (7-day half-life)
- Frontend calls this on wizard Next button (after wish is filled) or on Confirm-Standards click, so operator sees the picker before committing to a real forge.

## 4. Wizard match picker (Part B.3, Frontend)

`launcher.js` — new screen between Screen-2 and forge submit:
- Fetches `/api/governance/forge/similar_projects` with the operator's wish.
- If ≥1 match with similarity ≥0.70, renders a picker screen with top-3 as radio options + badges (🥇/🥈/🥉 with match %, last-touched, spec/task counts).
- Radio-1 pre-selected. Buttons:
  - **"Fork from selected"** → calls new `/fork_from` endpoint below, then continues to normal forge-progress screen
  - **"Forge fresh (no fork)"** → skips the fork and continues to normal forge as today
- If no match ≥0.70, screen is skipped entirely (transparent to operator).

## 5. Fork endpoint (Part B.4)

`POST /api/governance/forge/<forge_session_id>/fork_from`:
- Body: `{"source_project_name": "solar_system_1786032782"}`
- Copies from source project into the new project (already scaffolded):
  - Every `_cortex/specs/*.md` — added to target with header tag `**Reused from:** <source> (verify_status: pending)`
  - `_cortex/tasks.json` tasks — every task copied with `reused_from_task: <original_id>`, `verify_status: "pending"`, `status: "ready_for_verify"` (new status distinct from `ready`)
- Emits ADS: `fork_initiated {source, target, spec_count, task_count}` — one event, real, auditable.
- Response: `{"forked_from": "...", "specs_copied": N, "tasks_copied": M}`
- Immediately after: proceed to Architect verify-mode spawn.

## 6. Architect verify-mode prompt (Part B.5)

New file `adt_center/api/forge_prompts/architect_verify.md`:
- Worker is given a project already populated with copied specs.
- For each child spec in numerical order:
  - Read the reused spec + read the NEW project's SPEC-001 Vision (regenerated from operator's wish).
  - Emit one of four events with a one-sentence rationale:
    - `spec_verified_from_reuse` — spec fully applies to new wish, no change
    - `spec_edited_from_reuse` — spec applies but needs minor edits (make them, then emit)
    - `spec_dropped_from_reuse` — spec doesn't apply to new wish (delete file + tasks tagged with its `spec_ref`)
    - `spec_added_new` — new wish demands a spec the source didn't have (create via `POST /api/specs` normally)
- Standards inheritance still runs on any spec_added_new per SPEC-080 §4.4.

## 7. Verify-mode build (deferred to Full)

Per operator design conversation — Full-scope, not MVP. Placeholder:
- On build of a spec with `reused_from`, workers should ATTEMPT to re-run source's tests before rebuilding. If tests pass on the copied code, mark tasks `verified_via_test_reuse` (real event, real test outcome, no fabrication). If tests fail, fall back to normal build.
- Requires tasks to carry test-command hints; deferred until we have a stable test-command convention across templates.

## 8. Anti-fabrication guarantees (governance)

**This spec MUST NOT introduce any fake-event emission path.** Enforcement:
- Every ADS event fired by reuse code paths uses a distinct action_type prefix so they're separable in the ledger: `fork_initiated`, `spec_verified_from_reuse`, `spec_edited_from_reuse`, `spec_dropped_from_reuse`, `spec_added_new`, `task_verified_from_reuse` (Full).
- `_cortex/ops/lint_worker_prompts.py` (REQ-125) extended to flag any code that emits standard events (e.g. `task_completed`, `build_worker_spawned`) from a reuse path — those must go through real worker paths, never synthetic.
- Code review checklist: no `threading.Thread` in reuse code (except for genuine background verifiers whose events are real).

## 9. Affected paths

| Path | Role | Change |
|---|---|---|
| `_cortex/ops/agy_warmkeep.sh` | Ops | §1.1 — one-line MRR-endpoint warmup on startup |
| `adt_center/app.py` | Backend | §1.2 — startup pre-init hooks |
| `adt-console/src/js/launcher.js` | Frontend | §1.3 registry cache + §4 match picker screen + fork trigger |
| `adt_core/reuse/fingerprint.py` (new) | Backend | §2 |
| `_cortex/ops/backfill_fingerprints.py` (new) | Ops | §2 |
| `_cortex/ops/project_fingerprints.jsonl` (new, generated) | Data | §2 |
| `adt_center/api/governance_routes.py` | Backend | §3 similar_projects endpoint + §5 fork_from endpoint + hook into forge_complete for auto-index |
| `adt_center/api/forge_prompts/architect_verify.md` (new) | Backend | §6 verify-mode prompt |
| `_cortex/ops/lint_worker_prompts.py` | Ops | §8 anti-fabrication lint extension |
| Tests: `tests/test_spec_081_reuse_e2e.py` (new) | Tests | see §10 |

## 10. Acceptance

- Warm-up: fresh adt-center start → `/api/mrr/library_stats` responds ≤50 ms (was ~200 ms cold-load); `/api/projects` ≤50 ms (was ~450 ms).
- Backfill: script produces one fingerprint entry per project under `/home/human/Projects/*` with a `forge_brief.json`.
- Similar-projects API: given two solar-system projects (>70 % match) with different last-touched timestamps, returns them ranked by the combined score.
- Wizard picker: shows top-3 with correct badges + radio-1 pre-selected.
- Fork: after clicking "Fork from selected", new project's `_cortex/specs/` contains copied files with `**Reused from:**` header; `_cortex/tasks.json` contains copies with `reused_from_task` + `verify_status: "pending"` + `status: "ready_for_verify"`.
- Verify-mode worker: for one verify run over a copied spec tree, ADS shows a mix of `spec_verified_from_reuse` / `spec_edited_from_reuse` / `spec_dropped_from_reuse` / `spec_added_new` events — never a fake `task_completed` or `build_worker_spawned`.
- Anti-fabrication lint: `python3 _cortex/ops/lint_worker_prompts.py` returns rc=0 on the shipped code.

## 11. Out of scope (this spec)

* Test-reuse automated build verification (§7 — Full, later spec).
* LLM-embedding fingerprints (Jaccard-on-tokens is enough for demo; embeddings later).
* Fork within a project (branching a spec within same project) — different feature.
* Cross-machine reuse (fingerprints only local for now).

---

*"Fast because we don't reinvent, honest because every event is real."*
