# SPEC-020: Self-Governance Integrity

**Status:** APPROVED
**Priority:** CRITICAL
**Owner:** Systems_Architect + Human
**Created:** 2026-02-07
**References:** SPEC-014, SPEC-018, SPEC-019, AI_PROTOCOL.md Section 3
**Triggered By:** Architectural analysis of self-governance loop during SPEC-019 design

---

## 1. Purpose

The ADT Framework governs itself by its own principles. DTTP enforces governance on the codebase, including its own source code. This creates a self-referential loop with three failure modes:

1. **Constitution tampering** -- An agent modifies the governance config files, granting itself arbitrary permissions.
2. **Enforcement deadlock** -- DTTP is down and no agent can submit the fix through the governance pathway.
3. **Authorized self-corruption** -- A legitimately authorized agent submits code that guts the enforcement logic.

This spec defines the protections that close the self-governance loop without creating deadlocks or requiring blind trust.

### 1.1 The Paradox

> If DTTP governs all code changes, and DTTP's own code can be changed, then DTTP must govern changes to itself. But if DTTP is compromised or down, it cannot govern anything -- including its own repair.

The resolution: **the human is the root of trust, not the framework.** The framework enforces the human's decisions structurally, but the human retains the ability to intervene directly when the structure itself needs repair.

### 1.2 Analogy

A constitution defines how laws are made. But amending the constitution requires a higher bar than passing a law. And if the entire government collapses, the people (the sovereign) reconstitute it directly.

In ADT:
- **Regular code** = legislation (governed by DTTP under approved specs)
- **Enforcement code** = the constitution (requires elevated authorization)
- **Governance config** = the founding charter (human-only, never agent-modifiable)
- **Break-glass** = the sovereign reconstituting governance after collapse

---

## 2. Protected Path Classification

All paths in the ADT Framework are classified into three tiers:

### 2.1 Tier 1: Sovereign (Human-Only)

These paths define the rules of governance. They are **never modifiable through DTTP**. Any DTTP request targeting a Tier 1 path must be rejected with reason `sovereign_path_violation`, regardless of role, spec, or authorization.

| Path | Contents | Rationale |
|------|----------|-----------|
| `config/specs.json` | Spec authorization rules | Defines what specs authorize -- modifying this IS modifying all permissions |
| `config/jurisdictions.json` | Role-path jurisdiction map | Defines who can touch what -- modifying this IS modifying all boundaries |
| `config/dttp.json` | DTTP service configuration | Defines how enforcement runs -- modifying this IS modifying enforcement |
| `_cortex/AI_PROTOCOL.md` | Master governance protocol | The prime directive and role definitions |
| `_cortex/MASTER_PLAN.md` | Strategic plan and spec registry | Defines what gets built and in what order |

**Enforcement:** DTTP gateway must check resolved paths against a hardcoded sovereign path list **before** any spec/jurisdiction validation. This check cannot be configured away because it is not read from config -- it is compiled into the gateway.

**Human modification:** The human edits these files directly using their OS-level access. Changes should be logged to the ADS manually or via a dedicated human-action logging tool (not through DTTP).

### 2.2 Tier 2: Constitutional (Elevated Authorization)

These paths contain the enforcement logic itself. They are modifiable through DTTP but require a **dedicated hardening spec** (like SPEC-018) that explicitly names the file being changed. General-purpose specs (like SPEC-017 "build the framework") do NOT authorize changes to Tier 2 paths.

| Path | Contents | Rationale |
|------|----------|-----------|
| `adt_core/dttp/gateway.py` | Request validation and execution orchestration | Core enforcement logic |
| `adt_core/dttp/policy.py` | Fail-closed policy engine | Authorization decision maker |
| `adt_core/dttp/service.py` | Standalone service wrapper | HTTP entry point to enforcement |
| `adt_core/ads/logger.py` | Atomic event logger with hash chain | Audit trail integrity |
| `adt_core/ads/integrity.py` | Hash chain verification | Tamper detection |
| `adt_core/ads/crypto.py` | Shared hash utilities (per SPEC-018) | Cryptographic foundation |

**Enforcement:** DTTP gateway checks if the target path is Tier 2. If so, it requires:

1. The authorizing spec must be in status `APPROVED` (not just `ACTIVE`)
2. The spec must explicitly list the Tier 2 file in its authorized paths (not a directory wildcard)
3. The spec `action_data` must include field `tier2_justification` explaining why enforcement code needs modification
4. The action is logged with elevated flag `"tier": 2` in the ADS event

**Practical effect:** A Backend_Engineer can edit `adt_core/dttp/actions.py` (Tier 3, regular code) under SPEC-018 normally. But editing `adt_core/dttp/gateway.py` (Tier 2) requires SPEC-018 to explicitly name that file, and the ADS event is flagged for Overseer review.

### 2.3 Tier 3: Regular (Standard Authorization)

All other paths. Governed by standard DTTP validation: spec approved, role authorized, jurisdiction match, action type permitted.

This includes:
- `adt_core/dttp/actions.py` -- action handlers (not enforcement logic)
- `adt_core/dttp/jurisdictions.py` -- jurisdiction loader (reads config, doesn't make policy)
- `adt_core/sdd/*` -- spec registry, validator, task manager
- `adt_core/ads/query.py` -- read-only query interface
- `adt_core/ads/schema.py` -- event schema (validation, not enforcement)
- `adt_center/*` -- Operational Center (UI, routes)
- `adt_sdk/*` -- Agent SDK
- `tests/*` -- Test suite
- `docs/*` -- Documentation

---

## 3. Break-Glass Procedure

### 3.1 When to Invoke

Break-glass is invoked when DTTP cannot process requests and agent-driven repair is impossible. Triggers:

- DTTP service crashes and cannot restart
- DTTP rejects all requests due to a policy bug (total lockout)
- A Tier 2 file is corrupted and DTTP behavior is incorrect
- Config file is malformed and DTTP fails to load policy

### 3.2 Procedure

**Step 1: Human identifies the failure.**
The human observes that DTTP is non-functional (service down, all requests denied, incorrect behavior).

**Step 2: Human fixes directly.**
The human edits files using their OS-level access (user `human` has full permissions). No DTTP request is needed -- the human is the sovereign.

**Step 3: Human logs the intervention.**
After fixing, the human appends a break-glass event to the ADS:

```json
{
  "event_id": "evt_YYYYMMDD_HHMMSS_breakglass",
  "ts": "<ISO8601>",
  "agent": "HUMAN",
  "role": "sovereign",
  "action_type": "break_glass",
  "description": "Manual intervention: <what was fixed and why>",
  "spec_ref": "SPEC-020",
  "authorized": true,
  "tier": 1,
  "files_modified": ["<list of files touched>"],
  "reason": "<what triggered the break-glass>"
}
```

**Step 4: Human restarts DTTP.**
```bash
python -m adt_core.dttp.service --port 5002
```

**Step 5: Overseer reviews.**
The next Overseer session must verify:
- The break-glass event is logged in ADS
- The hash chain remains valid (or is repaired)
- The fix is minimal and addresses only the failure
- No unauthorized changes were made alongside the fix

### 3.3 Constraints

- Break-glass is for **repair only**, not for bypassing governance on regular work
- The human should not use break-glass to implement features -- only to restore DTTP functionality
- Every break-glass event is subject to Overseer audit
- If break-glass is invoked more than twice in 30 days, a SPEC should be written to address the root cause

---

## 4. Anti-Self-Modification Rules

### 4.1 Request-Time Validation

When DTTP receives a request, the gateway adds the following checks **in order, before existing validation**:

```
CHECK 1: Sovereign path?
  → If target path resolves to a Tier 1 path: DENY immediately
  → Reason: "sovereign_path_violation"
  → Log with tier: 1, escalation: true

CHECK 2: Constitutional path?
  → If target path resolves to a Tier 2 path:
    → Require spec explicitly lists this file (not directory)
    → Require tier2_justification in request
    → If either missing: DENY
    → Reason: "tier2_authorization_required"
    → If approved: log with tier: 2

CHECK 3: Standard validation (existing)
  → Spec approved? Role authorized? Jurisdiction match? Action type permitted?
  → Proceed as current DTTP logic
```

### 4.2 Hardcoded vs. Configured

The Tier 1 (sovereign) path list is **hardcoded in the gateway source code**, not read from config. This prevents the circular vulnerability where an agent modifies the config to remove a path from protection, then modifies that path.

```python
# gateway.py -- HARDCODED, not configurable
SOVEREIGN_PATHS = [
    "config/specs.json",
    "config/jurisdictions.json",
    "config/dttp.json",
    "_cortex/AI_PROTOCOL.md",
    "_cortex/MASTER_PLAN.md",
]
```

The Tier 2 (constitutional) path list is **also hardcoded**, for the same reason:

```python
# gateway.py -- HARDCODED, not configurable
CONSTITUTIONAL_PATHS = [
    "adt_core/dttp/gateway.py",
    "adt_core/dttp/policy.py",
    "adt_core/dttp/service.py",
    "adt_core/ads/logger.py",
    "adt_core/ads/integrity.py",
    "adt_core/ads/crypto.py",
]
```

To modify these lists, a developer must modify `gateway.py` -- which is itself a Tier 2 path, requiring elevated authorization. This creates the correct recursive protection: you need elevated permission to change the list of things that need elevated permission.

### 4.3 The Root Trust Anchor

The ultimate protection is not software -- it is the OS permission model from SPEC-014:

- In production, `gateway.py` is owned by `human`, readable by `dttp`, not writable by `agent`
- An agent cannot modify `gateway.py` directly (OS prevents it)
- An agent can only request DTTP to modify it (which triggers Tier 2 checks)
- The human can always modify it directly (sovereign authority)

The chain of trust:
```
Human (sovereign, OS root of trust)
  └── gateway.py (Tier 2, hardcoded sovereign paths)
        └── SOVEREIGN_PATHS list (Tier 1, immune to DTTP)
              └── specs.json, jurisdictions.json (define all other permissions)
                    └── All Tier 3 paths (standard governance)
```

---

## 5. ADS Event Extensions

### 5.1 Tier Field

All DTTP events gain an optional `tier` field:

```json
{
  "tier": 1,  // 1 = sovereign violation (always denied)
              // 2 = constitutional (elevated authorization)
              // 3 = regular (standard, default if omitted)
}
```

### 5.2 New Action Types

| Action Type | Meaning |
|-------------|---------|
| `sovereign_path_violation` | Agent attempted to modify a Tier 1 path. Always denied. |
| `tier2_authorized` | Agent modification of Tier 2 path was approved under elevated spec. |
| `tier2_denied` | Agent modification of Tier 2 path was denied (missing justification or spec). |
| `break_glass` | Human manual intervention to repair governance infrastructure. |
| `break_glass_audit` | Overseer review of a break-glass event. |

### 5.3 Escalation

All Tier 1 violations and Tier 2 denials set `"escalation": true` in the ADS event. The Overseer role must review these within their next session.

---

## 6. Implementation Tasks

| Task | Description | Assigned To | Depends On |
|------|-------------|-------------|------------|
| task_014 | Add sovereign path check to `gateway.py` -- hardcoded SOVEREIGN_PATHS list, checked before all other validation | Backend_Engineer | SPEC-018 Phase A |
| task_015 | Add constitutional path check to `gateway.py` -- hardcoded CONSTITUTIONAL_PATHS list, require explicit file listing in spec and tier2_justification | Backend_Engineer | task_014 |
| task_016 | Extend ADS event schema with `tier` field and new action types | Backend_Engineer | task_014 |
| task_017 | Write tests -- sovereign path rejection, Tier 2 elevation, break-glass logging, path list immutability | Backend_Engineer | task_014, task_015, task_016 |
| task_018 | Overseer audit procedure -- document how to review break-glass and Tier 2 events | Systems_Architect | task_016 |

---

## 7. Acceptance Criteria

SPEC-020 is **COMPLETED** when:

1. `POST /request` targeting `config/specs.json` returns `403` with reason `sovereign_path_violation` regardless of role or spec
2. `POST /request` targeting `config/jurisdictions.json` returns `403` with reason `sovereign_path_violation` regardless of role or spec
3. `POST /request` targeting `adt_core/dttp/gateway.py` requires explicit file listing in the authorizing spec and `tier2_justification` in the request
4. SOVEREIGN_PATHS and CONSTITUTIONAL_PATHS are hardcoded in source, not read from config
5. Break-glass events can be appended to ADS with `agent: "HUMAN"` and `action_type: "break_glass"`
6. All Tier 1 violations and Tier 2 denials produce ADS events with `escalation: true`
7. Tests verify that removing a path from SOVEREIGN_PATHS requires modifying a Tier 2 file (recursive protection)

---

## 8. What This Does NOT Do

- **Does not prevent the human from doing anything.** The human is the sovereign. This spec protects against agent self-modification, not human error.
- **Does not make DTTP infallible.** Bugs can still occur. Break-glass exists for this reason.
- **Does not prevent all social engineering.** An agent could ask the human to approve a spec that weakens governance. The human must exercise judgement. The framework can enforce structure, not intent.
- **Does not replace code review.** Tier 2 changes should still be reviewed by the human before the spec is approved. The framework enforces the gate, not the quality of what passes through it.

---

*"The framework governs itself, but the human governs the framework. This is not a contradiction -- it is the design."*

---

## 9. Amendment B: ADS Role Name Normalization (REQ-016)

**Author:** CLAUDE (Systems_Architect)
**Date:** 2026-02-18
**Status:** APPROVED by Human 2026-02-18
**Triggered By:** REQ-016 (Overseer/Gemini) -- inconsistent role casing in ADS events linked to hash chain instability

---

### 9.1 Problem

ADS events contain a free-text `role` field. Different agents and hooks produce
inconsistent casing:

```
"role": "DevOps_Engineer"     # From hive activation / active_role.txt
"role": "devops_engineer"     # From env var set manually
"role": "Backend_Engineer"    # From hook default
"role": "backend_engineer"    # From Gemini CLI
```

This causes two problems:

1. **Hash chain fragility:** The `role` field is included in the hash
   calculation. `DevOps_Engineer` and `devops_engineer` produce different
   hashes. If a chain is computed expecting one casing and an event arrives
   with the other, verification fails.

2. **Query inconsistency:** Filtering ADS events by role (e.g., in the
   Console context panel or Hive Tracker) produces incomplete results when
   the same logical role appears under multiple casings.

### 9.2 Solution: Canonical Role Names with Validation

#### 9.2.1 Canonical Role Registry

The ADS schema maintains a list of canonical role names, sourced from
`config/jurisdictions.json` at startup. For the framework (forge), the
canonical roles are:

```
Systems_Architect
Backend_Engineer
Frontend_Engineer
DevOps_Engineer
Overseer
```

For external governed projects, canonical roles are whatever is defined in
that project's `config/jurisdictions.json`.

#### 9.2.2 Normalization in ADSEventSchema

`ADSEventSchema.create_event()` normalizes the `role` field before creating
the event dict. Normalization is case-insensitive matching against the
canonical list:

```python
# In schema.py

CANONICAL_ROLES = None  # Loaded at startup from jurisdictions.json

@staticmethod
def normalize_role(role: str) -> str:
    """Normalize role name to canonical casing.
    
    Matches case-insensitively against canonical roles.
    If no match found, returns the input unchanged (for forward
    compatibility with new roles).
    """
    if ADSEventSchema.CANONICAL_ROLES is None:
        return role  # Not yet initialized, pass through
    for canonical in ADSEventSchema.CANONICAL_ROLES:
        if role.lower() == canonical.lower():
            return canonical
    return role  # Unknown role, pass through unchanged
```

The normalization runs inside `create_event()`:

```python
@staticmethod
def create_event(event_id, agent, role, action_type, ...):
    role = ADSEventSchema.normalize_role(role)
    # ... rest of event creation
```

#### 9.2.3 Validation in ADSEventSchema.validate()

Add optional strict validation that warns (but does not reject) when a role
name does not match any canonical role:

```python
@staticmethod
def validate(event_data):
    # ... existing checks ...
    
    # Role normalization check (warning, not rejection)
    if ADSEventSchema.CANONICAL_ROLES:
        role = event_data.get("role", "")
        if role.lower() not in [r.lower() for r in ADSEventSchema.CANONICAL_ROLES]:
            logger.warning(f"ADS: Unknown role '{role}' not in canonical list")
    
    return True
```

#### 9.2.4 Initialization

The canonical role list is loaded once at service startup:

```python
# In service.py or app.py startup
import json
jurisdictions_path = os.path.join(project_root, "config", "jurisdictions.json")
with open(jurisdictions_path) as f:
    jur = json.load(f)
ADSEventSchema.CANONICAL_ROLES = list(jur.get("jurisdictions", {}).keys())
```

#### 9.2.5 Hook Normalization

The hooks (`claude_pretool.py`, `gemini_pretool.py`) also normalize role
names before sending DTTP requests. They read the canonical list from the
project's `config/jurisdictions.json`:

```python
# In hook startup
def get_canonical_role(role, project_dir):
    """Normalize role against project's jurisdiction config."""
    jur_path = os.path.join(project_dir, "config", "jurisdictions.json")
    if os.path.exists(jur_path):
        with open(jur_path) as f:
            jur = json.load(f)
        for canonical in jur.get("jurisdictions", {}).keys():
            if role.lower() == canonical.lower():
                return canonical
    return role
```

### 9.3 Agent Field Normalization

The `agent` field has the same inconsistency: `CLAUDE` vs `claude`,
`GEMINI` vs `gemini`. Apply the same normalization:

```python
CANONICAL_AGENTS = ["CLAUDE", "GEMINI", "HUMAN"]

@staticmethod
def normalize_agent(agent: str) -> str:
    for canonical in ADSEventSchema.CANONICAL_AGENTS:
        if agent.upper() == canonical:
            return canonical
    return agent.upper()  # Default: uppercase unknown agents
```

### 9.4 Files to Modify

| File | Change |
|------|--------|
| `adt_core/ads/schema.py` | Add `CANONICAL_ROLES`, `CANONICAL_AGENTS`, `normalize_role()`, `normalize_agent()`. Apply in `create_event()`. |
| `adt_core/dttp/service.py` | Load canonical roles from `jurisdictions.json` at startup, set `ADSEventSchema.CANONICAL_ROLES`. |
| `adt_center/app.py` | Same initialization at Center startup. |
| `adt_sdk/hooks/claude_pretool.py` | Add `get_canonical_role()`, normalize before DTTP request. |
| `adt_sdk/hooks/gemini_pretool.py` | Same normalization. |

### 9.5 Backward Compatibility

- Existing ADS events with inconsistent casing are NOT retroactively fixed
  (that would break the hash chain).
- Normalization applies only to new events going forward.
- The hash chain remains valid because each event's hash is computed from
  its own content -- past events with `devops_engineer` keep their hashes,
  future events will use `DevOps_Engineer`.
- Unknown role names pass through unchanged (forward compatible with new
  roles added to jurisdictions.json).

### 9.6 Acceptance Criteria

- [ ] `ADSEventSchema.create_event(role="devops_engineer")` produces event with `"role": "DevOps_Engineer"`
- [ ] `ADSEventSchema.create_event(agent="gemini")` produces event with `"agent": "GEMINI"`
- [ ] Canonical roles loaded from `jurisdictions.json` at DTTP and Center startup
- [ ] Hooks normalize role before sending DTTP request
- [ ] Unknown roles pass through without error (warning logged)
- [ ] Existing ADS events with old casing remain valid (no retroactive changes)
