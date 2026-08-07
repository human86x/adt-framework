# SPEC-080: Intrinsic Standards Inheritance from MRR Match

**Status:** DRAFT — awaits SCR-004 approval for the AI_PROTOCOL amendment
**Author:** Systems_Architect (CLAUDE)
**Date:** 2026-08-05
**Tier:** Constitutional — modifies AI_PROTOCOL §4 (Capability Governance); Tier-1 sovereign; requires SCR
**Priority:** P0 — this is the framework's "governance is intrinsic, not an overlay" principle in operational form
**Complements / Amends:** SPEC-046 (Standards Governance Layer), SPEC-067 (Forge Wizard), SPEC-072 (Intent Matcher), SPEC-075 (LLM Classifier)
**Discovered via:** 2026-08-05 operator directive after Systems_Architect erroneously embedded "align with world-wide standards" language into SPEC-079's template payload. Correct operator observation: standards enforcement belongs in the framework's rule set, not in operator input.

**Intent:** Codify that every `suggested_rr_ids` produced by the MRR / intent classifier is automatically promoted to a mandatory `standards_refs[]` entry on the resulting SPEC-001 (Vision) and inherited by every child spec as hard acceptance criteria. Non-compliance requires an explicit SCR. Never a silent skip. Never a "where applicable" hedge. Never something the operator or template author needs to remember to type.

**Triggering Event:** 2026-08-05 -- operator reviewing SPEC-079 (Solar System template) noticed the Architect had written "Aligns with relevant world-wide standards where applicable" into the operator-facing payload. Correct operator response: standards should be an intrinsic ADT rule, not typed into every wish. The framework's whole thesis (per AI_PROTOCOL §1.1: *"Governance is an intrinsic system property, not an external overlay."*) forbids externalising standards enforcement into operator input.

**Success Condition:** After this spec lands and SCR-004 is approved, a fresh forge run on ANY template (SPEC-077 AR Art, SPEC-079 Solar System, or any operator's own wish) produces a SPEC-001_VISION.md whose `standards_refs[]` field is populated automatically from the MRR classifier's `suggested_rr_ids` -- with no operator input mentioning standards, no template payload enumerating standards, and no worker discretion to skip. Every child spec created in Phase B inherits those `standards_refs[]` verbatim and gains one observable `acceptance_criteria` entry per standard. Waiving a standard requires an explicit `SCR-STANDARD-WAIVER-<spec_id>-<rr_id>`; silent skip is a Tier-2 constitutional violation the verifier fails.

---

## 1. The rule

**When the MRR / intent classifier fires on a wish and returns `suggested_rr_ids: [RR-N1, RR-N2, ...]`:**

1. **Vision inheritance (Phase A).** The forge Architect worker reads the ADS `intent_match_completed` (and/or `intent_classification_completed`) event, extracts `suggested_rr_ids`, and MUST write each as a `standards_refs[]` entry on `SPEC-001_VISION.md` with status `MANDATORY`. A vision spec without inherited `standards_refs` -- when the classifier produced any -- is a governance violation.

2. **Child inheritance (Phase B).** Every child spec MUST include the parent's `standards_refs[]` in its own `standards_refs[]`, PLUS an `acceptance_criteria` entry for EACH inherited standard, phrased as an observable check (e.g. `"WCAG 2.2 AA compliance: axe-core reports zero critical / serious violations against the rendered app"`).

3. **Waiver protocol.** If a child spec cannot satisfy an inherited standard, it MUST file an `SCR-STANDARD-WAIVER-<spec_id>-<rr_id>` before it can be marked complete. The SCR body states the specific reason (technical impossibility, scope, cost) and any mitigation. Silent skip is a Tier-2 constitutional violation.

4. **Template payload prohibition.** Forge template payloads (`FORGE_TEMPLATES` in `launcher.js`) MUST NOT include standards enumeration in `constraints`, `success`, `out`, or elsewhere. Standards are a framework concern, injected via MRR match at forge time. See REQ-123.

5. **Verifier hook.** The build verifier (SPEC-062-F) MUST fail a spec whose `standards_refs[]` are declared but whose task tree contains no acceptance-criterion-verification tasks for those refs. This closes the "declared but never checked" loophole.

## 2. AI_PROTOCOL amendment (Tier-1 sovereign — requires SCR-004)

Insert a new subsection **§4.4 Standards Inheritance** in `_cortex/AI_PROTOCOL.md`:

> **§4.4 Standards Inheritance.**
>
> Every technical work stream in a governed project inherits the standards identified by the framework's MRR / intent classifier at forge time. The mechanism:
>
> (a) The MRR classifier's `suggested_rr_ids` on a wish are promoted to mandatory `standards_refs[]` on the Vision spec.
> (b) Every child spec inherits the Vision's `standards_refs[]` and adds one observable `acceptance_criteria` entry per standard.
> (c) A standard can only be waived via an SCR of the form `SCR-STANDARD-WAIVER-<spec_id>-<rr_id>` that names the specific reason and any mitigation. Silent skip is a Tier-2 constitutional violation.
> (d) Template payloads and other operator-facing inputs MUST NOT enumerate standards. Standards enforcement is framework territory, not operator territory.
>
> Rationale: governance is an intrinsic system property (§1.1). Requiring operators or template authors to remember to type "align with WCAG, glTF, WebGL, IAU…" into their inputs externalises what the framework must enforce automatically.

## 3. Forge Architect prompt amendment

Edit `adt_center/api/forge_prompts/architect.md` — extend **Phase A** with:

> **Phase A.5 — Read and Inherit Standards.**
>
> Before writing any content into `SPEC-001_VISION.md`:
>
> 1. `curl -s "http://localhost:5001/api/ads/events?project=<project>&type=intent_match_completed&limit=1"` OR `?type=intent_classification_completed&limit=1` — whichever fired for this forge run.
> 2. Extract `action_data.suggested_rr_ids` (an array like `["RR-008","RR-012",...]`).
> 3. Write these into SPEC-001's frontmatter as `standards_refs: [<list>]` with status `MANDATORY_INHERITED_FROM_MRR`.
> 4. Emit a `standards_inherited` ADS event with `{spec_id: "SPEC-001", rr_ids: [...], source: "mrr_auto_inheritance"}`.
>
> If the classifier fired but returned an empty `suggested_rr_ids`, still emit the `standards_inherited` event with `rr_ids: []` — governance requires the event trail even for the empty case.

Extend **Phase B** with:

> **Phase B.5 — Propagate Standards to Children.**
>
> For each child spec you create via POST /api/specs:
>
> 1. Include the Vision's inherited `standards_refs[]` verbatim in the child's `standards_refs` field.
> 2. For each inherited `RR-N`, add one `acceptance_criteria` entry phrased as an observable check specific to that child's scope. Example: for a rendering-layer child with RR-021 (accessibility inherited), the acceptance criterion might be `"axe-core CI run reports zero critical / serious violations against src/renderer.html"`.
> 3. If for a specific child a standard is genuinely inapplicable AND unwaivable-by-implementation, do NOT silently drop it — file an SCR named `SCR-STANDARD-WAIVER-<child_spec_id>-<rr_id>` with the cause. This is rare; most standards apply to most children.

## 4. Amendments needed

| File | Amendment | Authority |
|---|---|---|
| `_cortex/AI_PROTOCOL.md` | Insert §4.4 (see §2) | SCR-004 (Tier-1 sovereign) — file with operator authority |
| `adt_center/api/forge_prompts/architect.md` | Insert Phase A.5 + Phase B.5 (see §3) | Backend jurisdiction — operator override applies to this batch |
| `_cortex/specs/SPEC-046_STANDARDS_GOVERNANCE_LAYER.md` | Reference §4.4 as the operational rule; note that manual `standards_refs` is superseded by MRR auto-inheritance | Architect jurisdiction |
| Every existing forge template payload (`launcher.js`) | Audit + strip any standards enumeration | Frontend + Architect (REQ-123) |

## 5. Acceptance criteria

1. Amendment §4.4 is present in AI_PROTOCOL.md, backed by an approved SCR.
2. `adt_center/api/forge_prompts/architect.md` Phase A.5 + B.5 are present and referenced.
3. A fresh forge run on ANY template produces a SPEC-001 whose `standards_refs[]` matches the ADS `intent_match_completed.suggested_rr_ids` verbatim.
4. Every child spec created by that forge inherits those `standards_refs[]` and has one `acceptance_criteria` entry per standard.
5. No forge template payload (present or future) contains a standards enumeration in `constraints` / `success` / `out`. (Enforced by REQ-123 as a review checkpoint.)
6. Build verifier (SPEC-062-F) fails a spec that declares `standards_refs[]` but has no acceptance-criterion-verification tasks.

## 6. Rollout

1. Draft SCR-004 (this batch) to amend AI_PROTOCOL.md §4.4 — operator approves.
2. Once approved, apply the amendment.
3. Edit forge Architect prompt (this batch — Backend under operator override).
4. Add REQ-123 (this batch — Architect).
5. Audit existing template payloads for smuggled standards enumeration — batch-remove.
6. Next forge run onwards enjoys intrinsic inheritance.

## 7. Cross-spec impact

* **SPEC-046** — this spec supersedes SPEC-046's opt-in `standards_refs` pattern with mandatory MRR auto-inheritance.
* **SPEC-062-F** — verifier gains a new failure mode (see §5.6).
* **SPEC-067** — forge wizard is unaffected structurally; behavioural change comes via prompt amendment.
* **SPEC-072 / SPEC-075** — classifiers now emit the load-bearing event; unchanged otherwise.
* **REQ-111** — MRR broad-match + logging (already implemented in prior batch) is the prerequisite this spec builds on.

---

*"If the operator has to type 'be compliant', the framework has already failed."*
