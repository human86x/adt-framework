# SPEC-075: LLM-Backed Intent Classification Agent

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE)
**Created:** 2026-07-26
**Target Milestone:** v0.4.0
**Jurisdiction:** Backend_Engineer (`adt_core/standards/`, `adt_center/api/`), Frontend_Engineer (`adt-console/src/js/launcher.js`), Systems_Architect (`_cortex/prompts/`, `config/intent_index.json`)
**Depends On:** SPEC-072 (Intent-Driven Governance Assurance), SPEC-046 (Standards Governance), SPEC-067 (Forge Wizard)
**Supersedes (partial):** SPEC-072 §3.1 `intent_matcher.py` keyword-only classifier — retained as fallback tier

**Intent:** Replace SPEC-072's brittle 20-line keyword lookup with a real classifier — an LLM agent that reads the operator's Forge wish, reasons across the whole Rationalised Rule (RR) catalog + standards excerpts, and returns the RRs it thinks apply. The classifier auto-adopts its picks into the Forge wizard as pre-checked chips; the operator retains final authority to uncheck any before submit. This makes MRR enforcement actually reach cases like "habit tracker → personal-data storage → right-to-erasure applies," which the keyword matcher silently missed on 2026-07-26.

**Triggering Event:** habit_tracker_1785072584 forge (2026-07-26 14:58 UTC): the wish "A daily habit tracker where users define habits, check them off each day, and view a heatmap of streak history" clearly implies personal-data storage under GDPR Art. 4(1) and triggers right-to-erasure obligations (Art. 17), storage limitation (Art. 5(1)(e)), and ISO/IEC 42001 lifecycle-data provisions. SPEC-072's keyword matcher returned `matched_domains: []` and `baseline_rr_ids: []` — zero MRRs flagged. Operator caught the miss manually and asked "am I right that this needs privacy handling?" That question should never need to be asked.

**Success Condition:**
(a) For a corpus of ≥20 seed wishes covering health, finance, communication, media, dev-tools, IoT, education, personal-data-storage, and gaming, the classifier's recall of the "gold" RR set (curated by SA) is ≥ 0.80.
(b) The Forge wizard's Screen 2 renders every classifier-picked RR pre-checked, with a rationale tooltip explaining why the classifier picked it — operator can uncheck before submit.
(c) Every classification run emits `intent_classification_started` and `intent_classification_completed` events to project ADS with `{engine, model, prompt_version, latency_ms, matched_rrs, confidence, rationales, provenance: "llm_classifier_v1"}` — no silent runs.
(d) If the LLM is unreachable / times out / returns malformed JSON, the classifier degrades to SPEC-072 keyword matching and emits `intent_classification_fallback` — the wizard never blocks on classifier failure.
(e) The classifier prompt template lives at `_cortex/prompts/intent_classifier.md` under Tier-1 sovereign protection; any change requires an SCR.
(f) An operator can inspect any past classification's full reasoning trace via `GET /api/governance/intent/classifications/<run_id>` — audit-grade evidence.

---

## 1. Problem

SPEC-072 §3.1 defines `match_intent_domain(intent_text) → (matched_domains, baseline_rr_ids)` as substring-scan against `config/intent_index.json`. Two structural failures:

1. **Coverage is a keyword bingo.** `intent_index.json` currently has 2 domains. Even a fully populated 30-domain index would miss any wish phrased outside the exact keyword list — "system to remember what I did each day" does not contain "journal" or "track", but is a journaling app.
2. **Recall on data-classification is near zero.** The habit-tracker wish stores personal data. GDPR/ISO applies. Keyword matcher scored `[]`. Operators cannot rely on it.

The system pretends to reason ("Intent-Driven Governance Assurance Engine") but does string matching. This spec closes that gap.

---

## 2. Architecture

### 2.1 Two-tier pipeline

```
Forge wish
   │
   ▼
Tier 1: intent_matcher.py (SPEC-072 keyword) ─┐
                                              │  union of
Tier 2: intent_classifier_llm.py (SPEC-075) ──┤  matched RRs
                                              │  (deduplicated)
                                              ▼
                                    Forge wizard Screen 2:
                                    RRs pre-checked with rationales
                                    Operator can uncheck
                                              │
                                              ▼
                                     Submit → selected_rr_ids
```

Tier 1 stays for cheap keyword hits (health, payment) — always cheap, always available.
Tier 2 adds semantic reasoning + rationale — where the real value lives.

### 2.2 New module: `adt_core/standards/intent_classifier_llm.py`

```python
def classify_intent(
    wish: str,
    users: str,
    success_v1: str,
    project_name: str,
    engine: str = "gemini-3.1-pro-high",   # or "claude-sonnet-4-6"
    prompt_version: str = "v1",
    timeout_s: int = 20,
) -> ClassificationResult:
    """
    Returns:
      ClassificationResult(
        run_id: str,
        engine: str,
        model: str,
        prompt_version: str,
        latency_ms: int,
        matched_domains: list[str],
        recommended_rrs: list[RecommendedRR],   # {id, rationale, confidence}
        data_classifications: list[str],         # e.g. ["personal_data", "health_related"]
        suggested_erasure_requirements: list[str],
        overall_confidence: float,               # 0.0 - 1.0
        raw_response: str,                       # for audit
        fallback_reason: Optional[str],
      )
    Raises never — always returns a result. On any error returns a fallback
    ClassificationResult with matched from Tier 1 and fallback_reason set.
    """
```

Model selection: `gemini-3.1-pro-high` (default) via the existing `agy` binary; alternative `claude-sonnet-4-6` via Anthropic SDK. Chosen for structured JSON compliance + reasoning quality. Model is a config value; not hard-coded.

### 2.3 Prompt template (`_cortex/prompts/intent_classifier.md`)

Tier-1 sovereign. Structure:

```
SYSTEM: You are the ADT Intent Classifier. Given a Forge wish, classify what
domains and Rationalised Rules apply. Return STRICT JSON matching the schema
below — no prose, no markdown.

TOOLS: You have read-only visibility of:
- The domain index: {intent_index_json}
- The full RR catalog: {rr_catalog_json} (id, title, text, derived_from, scope)
- Standards excerpts: {standards_summary}

TASK:
Read the wish + acceptance criteria below. Identify:
1. Domains the app inhabits (from the index or novel).
2. RRs from the catalog that legitimately apply — err on the side of INCLUSION
   for privacy, security, and human-rights RRs (recall > precision).
3. Data classifications the app implicitly performs (personal_data,
   health_related, financial, biometric, communications, location, etc.).
4. Erasure requirements the app must expose to end users.
5. Your confidence in the overall classification (0.0-1.0).

For EACH recommended RR, include a one-sentence RATIONALE citing the specific
wish content that triggered it. Rationales are shown to the operator.

WISH:
{wish}

USERS:
{users}

SUCCESS V1:
{success_v1}

RESPOND with:
{
  "matched_domains": ["..."],
  "recommended_rrs": [{"id": "RR-XXX", "rationale": "...", "confidence": 0.0-1.0}, ...],
  "data_classifications": ["..."],
  "suggested_erasure_requirements": ["..."],
  "overall_confidence": 0.0-1.0
}
```

Version is bumped in the frontmatter for every change; historical prompts kept for reproducibility of past classifications.

### 2.4 New endpoint: `POST /api/governance/intent/classify`

Request:
```json
{ "wish": "...", "users": "...", "success_v1": "...", "project": "adt-framework", "engine": "gemini-3.1-pro-high" }
```
Response (200):
```json
{
  "run_id": "cls_20260726_142312_abcd",
  "matched_domains": ["personal_data", "wellbeing", "quantified_self"],
  "recommended_rrs": [
    {"id": "RR-008", "rationale": "Wish stores per-user habit completion — personal data under GDPR.", "confidence": 0.94},
    {"id": "RR-017", "rationale": "Streak history is a behavioural profile requiring storage limitation.", "confidence": 0.88}
  ],
  "data_classifications": ["personal_data", "behavioural_profile"],
  "suggested_erasure_requirements": ["User-initiated purge of all habit data (single action, no confirmation delay)"],
  "overall_confidence": 0.91,
  "engine": "gemini-3.1-pro-high",
  "prompt_version": "v1",
  "latency_ms": 3421,
  "fallback_reason": null
}
```

Response (200, fallback):
```json
{
  "run_id": "cls_...",
  "matched_domains": [...from keyword matcher...],
  "recommended_rrs": [],
  "data_classifications": [],
  "overall_confidence": 0.0,
  "fallback_reason": "gemini timeout after 20s",
  "engine": "keyword_fallback",
  "prompt_version": "spec072_v1"
}
```

Never returns 5xx unless the request body is malformed.

### 2.5 New endpoint: `GET /api/governance/intent/classifications/<run_id>`

Returns the full stored trace for audit: prompt hash, model, raw LLM response, timings, matched RRs with rationales. Backed by `_cortex/standards/intent_classifications.jsonl`.

### 2.6 Forge wizard integration (Screen 2 modification)

When the wizard opens Screen 2 and the operator has already filled the wish on Screen 1:

1. Fire `POST /api/governance/intent/classify` in the background.
2. Show a **classifier chip** near the "Standards to anchor" section: `[⟳] Classifier analysing… (5.3s)` with live elapsed timer.
3. When response arrives:
   - Render each `recommended_rr` as **pre-checked** in the RR list.
   - Each pre-checked RR gets a small badge: `AUTO` with hover-tooltip = rationale string.
   - Above the RR list, render a "Data Classifications Detected" strip: `[personal_data] [behavioural_profile]` — coloured chips.
   - Above the wizard-actions row, render a "Suggested Erasure Requirements" callout — surfaces the erasure obligations directly to the operator so they can add them to the vision spec.
4. If the operator unchecks an AUTO-picked RR, log `intent_classification_operator_override` with `{run_id, rr_id, reason: optional_prompt}` — feedback signal for future prompt tuning.
5. On submit, `selected_rr_ids` = union of operator-checked chips (whether AUTO or manual).

### 2.7 ADS events

| Event | When | action_data |
|---|---|---|
| `intent_classification_started` | POST /classify received | `{run_id, engine, prompt_version}` |
| `intent_classification_completed` | LLM returned valid JSON | `{run_id, matched_domains, recommended_rrs, data_classifications, latency_ms, confidence}` |
| `intent_classification_fallback` | LLM error, using keyword tier | `{run_id, fallback_reason, engine_attempted, keyword_matched_domains}` |
| `intent_classification_operator_override` | Operator unchecked an AUTO RR | `{run_id, rr_id, override_reason}` |

All emit to **project ADS**, not framework ADS.

### 2.8 Storage

- `_cortex/standards/intent_classifications.jsonl` (per project): append-only ledger of full classification traces.
- `_cortex/prompts/intent_classifier.md` (framework only): Tier-1 sovereign prompt template.
- `config/intent_index.json` (framework only): retained; used by keyword fallback tier.

---

## 3. Governance of the Classifier Itself

The classifier IS an AI agent making governance-relevant decisions. It is itself subject to ADT:

1. **Sovereign prompt.** Any prompt change requires SCR.
2. **Model pinning.** The `engine` field in every ADS event is mandatory — you can always identify which model produced which recommendation.
3. **Version pinning.** `prompt_version` is required on every classification; changes bump the version.
4. **Human authority always wins.** Operator can uncheck any AUTO pick without justification (though a reason is prompted for feedback capture). Operator can also add manual RRs the classifier missed.
5. **No auto-blocking.** The classifier's `overall_confidence` never blocks a forge; it only informs. Blocking is an operator or Overseer decision, not the classifier's.
6. **Auditability.** Every classification's full raw LLM response is stored — three months minimum retention. Overseer can replay any decision from the trace.
7. **Recursive traceability.** The `intent_classifier.md` prompt template's own construction is spec-driven (this spec, SPEC-075).

---

## 4. Acceptance Criteria

1. `POST /api/governance/intent/classify` with the habit_tracker wish returns ≥3 recommended RRs including at least one privacy/personal-data RR, and `data_classifications` contains `personal_data`.
2. Classifier response arrives at the Forge wizard in ≤10 s p95 (Gemini 3.1 Pro high); operator sees pre-checked chips with rationales before submit becomes clickable.
3. On `agy` timeout / model unreachable, the wizard shows a subtle fallback banner ("Classifier offline — using keyword tier") and still lets the operator submit.
4. `intent_classification_completed` event is written to project ADS for every non-fallback run; `intent_classification_fallback` for every fallback.
5. Full raw LLM response retrievable via `GET /api/governance/intent/classifications/<run_id>`.
6. Prompt template lives at `_cortex/prompts/intent_classifier.md` and is denied modification without SCR.
7. Regression test suite: 20 seed wishes with gold RR sets; classifier recall ≥ 0.80, precision ≥ 0.65. Runs in CI on prompt changes.

---

## 5. Implementation Sequencing (proposed)

1. **BE #1** — `intent_classifier_llm.py` skeleton with agy backend + strict-JSON parsing + timeout + keyword fallback path. Ship endpoint returning fallback-only responses.
2. **SA #1** — write `_cortex/prompts/intent_classifier.md` v1; commit RR catalog snapshot generator.
3. **BE #2** — wire LLM call, ADS logging, JSONL persistence, retrieval endpoint.
4. **FE #1** — wizard Screen 2: async classifier chip + pre-checked AUTO RRs + rationale tooltip + Data Classifications strip + Erasure Requirements callout + override capture.
5. **SA #2** — regression seed corpus (20 wishes + gold RRs) + eval harness; iterate prompt to hit ≥ 0.80 recall.
6. **Overseer** — one-time audit of first 10 real classifications; confirm no false positives systematically leaking non-applicable RRs.

Sequenced so operators get value at step 4 even if step 5 is still being tuned.

---

## 6. Out of Scope / Follow-ups

- Fine-tuning a small model on ADT-specific data (SPEC-076 candidate).
- Vector-store RAG over standards clauses (SPEC-076 alt).
- Multi-model ensemble / voting.
- Classifier confidence thresholds that gate Forge submit — this would be a policy decision, not a mechanical one; defer until we have real production signal.

---

*"A classifier that fails silently is a governance surface pretending to exist."*
