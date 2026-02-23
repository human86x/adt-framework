# Overseer Audit Procedure: Self-Governance Integrity

**Version:** 1.0
**Status:** DRAFT
**Owner:** Overseer
**References:** SPEC-020, AI_PROTOCOL.md

---

## 1. Overview

As the Overseer, your role is to ensure the integrity of the ADT Framework's governance. This document defines the procedures for auditing elevated events: **Tier 2 (Constitutional) modifications** and **Break-Glass interventions**.

These events represent the highest level of risk to the system, as they involve modifications to the enforcement logic itself or bypassing the enforcement gateway entirely.

---

## 2. Auditing Tier 2 (Constitutional) Modifications

Tier 2 modifications are changes to the core enforcement code (e.g., `gateway.py`, `policy.py`). They are authorized through DTTP but require elevated justification.

### 2.1 Identification

Identify Tier 2 events in the ADS (`_cortex/ads/events.jsonl`) by searching for:
- `action_type`: `tier2_authorized`
- `tier`: 2
- `escalation`: true (if denied)

### 2.2 Review Checklist

For every `tier2_authorized` event, verify:

1.  **Spec Authorization:** Does the referenced spec explicitly list the modified file (not a directory wildcard)?
2.  **Justification:** Is the `tier2_justification` field present and reasonable? Does it explain *why* the enforcement logic needed to change?
3.  **Scope:** Was the change minimal? (Check `git diff` for the relevant commit if available).
4.  **Integrity:** Is the event correctly hashed and chained to the previous event?

### 2.3 Escalation

If a Tier 2 modification appears suspicious, unauthorized, or over-broad, you must **escalate to the Human** immediately and log the concern as an `audit_violation` event.

---

## 3. Auditing Break-Glass Interventions

Break-Glass is a manual intervention by the Human to repair the framework when DTTP is non-functional.

### 3.1 Identification

Identify Break-Glass events by searching for:
- `agent`: `HUMAN`
- `action_type`: `break_glass`
- `role`: `sovereign`

### 3.2 Review Checklist

When a Break-Glass event is detected, perform the following audit:

1.  **Sovereign Check:** Is the `agent` field `HUMAN`? If the agent is `CLAUDE` or `GEMINI`, this is a **CRITICAL VIOLATION** unless accompanied by a `delegate_agent` note and explicit human instruction.
2.  **Event Presence:** Is the event logged in the ADS? (If the Human fixed the system but forgot to log, remind them to do so).
2.  **Rationale:** Does the `description` or `reason` explain what was broken and why manual intervention was required?
3.  **Chain Integrity:** Does the hash chain remain valid? If the Human's manual edit broke the chain, the Overseer must use the healing tools to repair it.
4.  **Minimal Fix:** Verify that only the necessary files were modified to restore functionality. Check `files_modified` against the actual state of the repo.
5.  **Collateral Changes:** Ensure no Tier 3 (regular) features were snuck into the break-glass session. Break-glass is for repair, not feature development.

### 3.3 Audit Log

After completing the review, log your findings:

```json
{
  "event_id": "evt_YYYYMMDD_HHMMSS_audit",
  "ts": "<ISO8601>",
  "agent": "GEMINI",
  "role": "Overseer",
  "action_type": "break_glass_audit",
  "description": "Audit of break-glass event <ID>. Status: VERIFIED/DISPUTED.",
  "spec_ref": "SPEC-020",
  "authorized": true
}
```

---

## 4. Auditing Tier 1 (Sovereign) Violations

Tier 1 violations occur when an agent attempts to modify human-only configuration files. These are always denied by DTTP.

### 4.1 Identification

Identify Tier 1 violations by searching for:
- `action_type`: `sovereign_path_violation`
- `escalation`: true

### 4.2 Action

1.  **Identify the Source:** Which agent and role attempted the violation?
2.  **Analyze the Spec:** Was the agent following a spec that incorrectly targeted a Tier 1 path, or was it a "hallucination" or intentional bypass attempt?
3.  **Remediate:** If the spec is at fault, inform the Systems_Architect to fix the spec. If the agent is malfunctioning, report to the Human.

---

## 5. Tools

- `adt_core/ads/query.py`: Use this to filter and find elevated events.
- `adt_core/ads/integrity.py`: Use this to verify the hash chain integrity.
- `adt_core/ads/healer.py`: Use this to reconstruct the hash chain if it is broken (Historical Integrity Reset).
- `git diff`: Use this to inspect the actual code changes associated with an event.

---

*"Trust but verify. The framework enforces, but the Overseer audits."*
