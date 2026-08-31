# SPEC-114 — Intent Alignment and Consent Gates

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE, 2026-08-29)
**Authority:** Operator verbal approval, 2026-08-29 (this session — "draft 114 first", approved alongside SPEC-113 via "2")
**Category:** Governance Infrastructure
**Relates to:** SPEC-113 (DTGP Foundation and Device Import), SPEC-033 (Sovereign Change Requests), SPEC-045 (SCR Authorization Hardening), SPEC-057 (Agent Mailbox), SPEC-115 (planned — Embedded_Engineer and Firmware Actions), SPEC-116 (planned — Deployment Action Drivers)

**Intent:** Give DTGP the "smarts" that turn its plumbing into governance. SPEC-113 built the pipes — how an agent reaches a target and executes an action. SPEC-114 defines what has to be true *before* DTGP is willing to run that action, and how a human is brought into the loop for anything Tier-1. Concretely: a **gate composition engine** that runs an ordered chain of checks per (target_type, action) pair, three concrete gate families — **task-binding**, **artifact compatibility**, **environment alignment** — and a **DTGP Consent SCR** that surfaces a full-chain preview to the operator before any Tier-1 action executes. Also: a signed operator-override path for emergencies where a gate chain is legitimately blocking urgent work.

**Triggering Event:** On 2026-08-29 the operator asked "how do we route and block the flashing if made by mistake" while designing DTGP. The answer wasn't a single gate — it was defence in depth across three orthogonal mistake modes: **wrong target** (agent typoed `_gw_02` for `_gw_01`), **wrong artifact for right target** (esp32 firmware fired at an Arduino, or production firmware fired at a lab device), and **right everything but should have been human-decided** (any state-changing action on a Tier-1 asset). SPEC-113 has no mechanism for any of these; DTGP would obediently execute whatever an agent requested. This spec adds the layer that says no.

**Success Condition:** After this spec ships:
1. DTGP's action endpoint composes a gate chain per (target_type, action) from a declarative registry; each gate returns allow / deny / await-consent; the first deny short-circuits with a structured refusal.
2. Every egress action must reference a `task_id`; the task must explicitly enumerate the target in its `dtgp_targets[]`; missing binding = refusal.
3. Every artifact referenced in an action must have a companion manifest (`<artifact>.manifest.json`) declaring compatibility; wrong device type, wrong pinned device, wrong environment, or SHA-256 mismatch = refusal.
4. Any action on a Tier-1 target creates a **DTGP Consent SCR** whose Console surface shows the full expanded chain — target, transit hops, artifact hash, environment, requesting task and agent — and cannot be bypassed by the requesting agent. Human confirm = action resumes; reject or timeout = action aborts.
5. An operator override path exists for emergencies, itself gated by a Tier-1 SCR with mandatory justification; every override is auditable with severity flag in ADS.
6. Every gate evaluation is auditable in ADS; every refusal names the specific gate that fired and the reason.

---

## 1. Positioning

SPEC-113 built DTGP as a mediator that *can* run actions. SPEC-114 makes DTGP a mediator that *decides whether an action should be run*.

| Layer | Spec | Responsibility |
|---|---|---|
| Plumbing (how) | SPEC-113 | Reach the target. Serialise access. Hold credentials. Log the crossing. |
| Intent alignment (whether) | **SPEC-114** | Task-binding. Artifact compatibility. Environment matching. Human consent for Tier-1. |
| Physical safety (safely) | SPEC-115 | Presence, backup, verify, rollback — specific to firmware actions. |
| Driver breadth (what) | SPEC-116 | SFTP, git push, S3, kubectl, docker push. Their own default gate chains. |

SPEC-114 is the smallest of the four and the most consequential — every action DTGP runs traverses its gate chain. Getting the semantics right on paper before the code is why the operator asked for this draft *before* SPEC-113 is built.

## 2. Scope

### In scope for SPEC-114

- **Gate composition engine** — registry keyed by `(target_type, action)` → ordered list of gate IDs. Configurable per project via `_cortex/dtgp/gate_config.yaml`.
- **Task-binding gate** — extends `_cortex/tasks.json` schema with `dtgp_targets[]`; enforces target-in-task and role-in-task.
- **Artifact manifest schema** — the `<artifact>.manifest.json` companion file DTGP expects. Fields, validation rules, generation approach.
- **Artifact compatibility gate** — target type, pinned device, SHA-256 integrity, presence-of-manifest.
- **Environment alignment gate** — lab / staging / production tags on both target and artifact must match for state-changing actions.
- **DTGP Consent SCR** — new SCR type (`sovereign_dtgp_action`) with a Console surface showing the full expanded chain, artifact hash, and task provenance. Auto-timeout to reject.
- **Operator override path** — emergency bypass gated by `sovereign_dtgp_action_override` SCR with mandatory justification; auditable.
- **ADS event types** for every gate evaluation, consent decision, and override.

### Out of scope for SPEC-114 (deferred)

- **Physical safety gates** (presence, backup, verify, rollback) — SPEC-115.
- **Cryptographic signing** of artifacts (beyond SHA-256 integrity) — future spec.
- **Manifest generation tooling** integrated into build pipelines — SPEC-116 per-driver. This spec defines the schema and ships a minimal `adt artifact manifest` CLI; full CI integration is a driver concern.
- **Multi-party consent** (2 of N operators must approve).
- **Delegated / batch consent** (operator pre-approves a class of actions for a duration).
- **Automated environment promotion** (lab → staging → prod artifact lifecycle).
- **Learning-based gate suggestion** (system suggests tightening a chain after observing near-misses).

## 3. Design

### 3.1 Gate Composition Engine

DTGP's action endpoint (`POST /action` from SPEC-113) is extended to compose a gate chain before executing:

```
def execute_action(request):
    chain = gate_registry.resolve(request.target_type, request.action)
    ctx = build_context(request)
    for gate in chain:
        result = gate.evaluate(request, ctx)
        emit_ads('dtgp_gate_evaluated', {gate_id, decision, ...})
        match result:
            case Allow(): continue
            case Deny(reason): return deny(reason, gate_id)
            case AwaitConsent(scr_id): return pause_for_scr(scr_id, request)
    # all gates passed
    return run_action(request)
```

- **Registry:** Python dict of `(target_type, action) → [gate_id, gate_id, ...]`. Framework ships defaults; per-project `_cortex/dtgp/gate_config.yaml` overrides.
- **Gate interface:** every gate implements `evaluate(request, context) -> GateResult` where `GateResult` is one of `Allow()`, `Deny(reason, structured_data)`, `AwaitConsent(scr_id)`.
- **Short-circuit:** first `Deny` ends the chain with an HTTP 403 to the caller and a `dtgp_action_denied` ADS event.
- **Consent pause:** `AwaitConsent` creates an SCR, returns HTTP 202 with an `scr_id` and a `poll_url`. The caller can poll or subscribe to the SCR's outcome. On approval DTGP resumes from the paused gate onwards; on rejection or timeout it emits `dtgp_action_denied` with reason `consent_denied` or `consent_timeout`.
- **Ordering:** gate authors can declare `depends_on: [gate_id, ...]`; the registry topologically sorts. Cheap gates (task-binding) run before expensive ones (SHA-256 verification of a 4MB firmware).

### 3.2 Task-Binding Gate (Layer 1: structural)

**Purpose:** stop `flash("arduino_mega_lora_gw_02")` when the agent meant `_gw_01`. The task authorises the target, not the agent.

**Schema extension** — `_cortex/tasks.json` task record gains:

```
{
  "task_id": "task_247",
  "spec_ref": "SPEC-008",
  "assigned_role": "Embedded_Engineer",
  "status": "in_progress",
  "dtgp_targets": ["arduino_mega_lora_gw_01"],
  "dtgp_actions": ["flash", "health"]
}
```

- `dtgp_targets` — list of `target_id`s this task is authorised to act on.
- `dtgp_actions` — optional whitelist; if omitted, any action allowed by other gates is fine.

**Gate logic:**
1. Load task by `request.task_id`. Missing → `Deny(no_task_binding)`.
2. If `request.target_id not in task.dtgp_targets` → `Deny(target_not_in_task)`.
3. If `task.dtgp_actions` present and `request.action not in task.dtgp_actions` → `Deny(action_not_in_task)`.
4. If `task.status not in {"in_progress", "approved"}` → `Deny(task_not_active)`.
5. If `task.assigned_role != request.requester_role` → `Deny(role_mismatch)`.
6. Else `Allow`.

**Rationale:** this single gate blocks the majority of "wrong target" mistakes at the API surface, because it forces the mistake to be present in the task metadata (which the operator can see and correct) rather than in ephemeral agent state.

### 3.3 Artifact Manifest Schema

**Location:** every artifact used by a DTGP action has a companion manifest at `<artifact_path>.manifest.json`.

**Schema:**

```json
{
  "artifact_id": "fw_lora_gw_v1.2.3",
  "path": "_cortex/artifacts/fw_lora_gw_v1.2.3.hex",
  "sha256": "4a1b7c9e...",
  "size_bytes": 262144,
  "built_at": "2026-08-29T18:00:00Z",
  "built_by": {
    "spec_ref": "SPEC-008",
    "task_ref": "task_247",
    "agent": "CLAUDE",
    "session_id": "sess_be_20260829_..."
  },
  "compatible_target_types": ["arduino_mega_2560"],
  "target_device_id": "arduino_mega_lora_gw_01",
  "environment": "production",
  "notes": "Free-form operator notes; optional."
}
```

- `sha256`, `compatible_target_types`, `environment`, `built_at` are required. Others optional.
- `target_device_id` when set **pins** the artifact to a single device — even a matching type won't accept a differently-pinned artifact. Optional.
- `environment` values: `lab`, `staging`, `production`.

**Manifest generation:** a minimal CLI `adt artifact manifest <path> --spec SPEC-008 --task task_247 --targets arduino_mega_2560 --env lab` ships with this spec. Per-driver deep integration (avrdude build script auto-writes manifest, GitHub Actions post-build hook, etc.) is SPEC-116 driver territory.

### 3.4 Artifact Compatibility Gate (Layer 2: content)

**Runs when** `request.artifact_ref` is set.

**Gate logic:**
1. Locate `<artifact_path>.manifest.json`. Missing → `Deny(artifact_manifest_missing)`.
2. Load and validate manifest. Malformed → `Deny(artifact_manifest_invalid)`.
3. Compute SHA-256 of artifact file. Mismatch with `manifest.sha256` → `Deny(artifact_integrity_failed)`.
4. If target's `type` not in `manifest.compatible_target_types` → `Deny(artifact_incompatible_type)`.
5. If `manifest.target_device_id` set and `!= request.target_id` → `Deny(artifact_pinned_to_other_device)`.
6. Else `Allow`.

**Rationale:** catches "right device wrong firmware", "corrupted artifact", "artifact intended for a different specific device".

### 3.5 Environment Alignment Gate (Layer 2: content)

**Runs when** the action is state-changing (flag on the action definition: `state_changing: true|false`). Read from action registry.

**Gate logic:**
1. Read `target.environment` from registry. Missing → treat as `lab` with an audit warning.
2. Read `manifest.environment` if artifact present.
3. If both present and unequal → `Deny(environment_mismatch)`.
4. If manifest env is `production` and target env is `lab` → hard `Deny`, no override at gate level (operator override still available via §3.7).
5. Else `Allow`.

**Rationale:** catches the "flashed production firmware onto the bench Arduino" and "pushed lab config to the production server" classes. This is the gate that saves you when everything else lines up but someone grabbed the wrong build.

### 3.6 DTGP Consent SCR (Layer 3: human-in-loop)

**When triggered:** whenever the composed gate chain includes a `consent_gate` — by default when `target.tier == 1` for any state-changing action, and when explicitly configured in `gate_config.yaml` for lower-tier targets.

**Gate logic:**
1. Compose a consent payload (details below).
2. Create an SCR of type `sovereign_dtgp_action`. Persist to the SCR queue.
3. Return `AwaitConsent(scr_id)` from the gate.
4. DTGP puts the action in a paused state (in-memory table + ADS event).
5. Console picks up the SCR from the queue (existing mechanism) and displays the consent surface.
6. Operator clicks Confirm → SCR marked authorized → ADS event `sovereign_hardware_action_authorized` — wait, using consistent naming: `sovereign_dtgp_action_authorized`. DTGP resumes the paused action.
7. Operator clicks Reject or SCR times out (default 10 minutes, per-project configurable) → SCR marked rejected/expired → DTGP terminates action with `consent_denied` or `consent_timeout`.

**Consent payload** (what the Console surface shows):

```
About to: flash
Target:   arduino_mega_lora_gw_01
          type: arduino_mega_2560
          serial: 754323034393518011E1
          tier: 2  environment: production
Via transit:
          pi_gateway_01  (Pi 5, 10.42.0.51, tier: 1)
Artifact: fw_lora_gw_v1.2.3.hex
          sha256: 4a1b7c9e...  size: 262144 bytes
          built: 2026-08-29 18:00 UTC  by SPEC-008 task_247
Task:     task_247 (SPEC-008 - Field Deployment)
Agent:    CLAUDE / Embedded_Engineer / sess_be_...
Reason:   (agent-provided rationale, free-form, mandatory)

              [ Confirm ]     [ Reject ]
```

**Critical properties:**
- The requesting agent CANNOT self-approve. The SCR mechanism ensures approval comes from a different authority (per SPEC-045 SCR Authorization Hardening).
- The consent surface shows the FULL expanded chain, not just the terminal target — so the operator can spot "wait, why is this touching pi_gateway_01 too?".
- Consent is per-action, not per-target — approval for one flash does not authorise a second flash to the same device.
- Timeout is configurable per project via `gate_config.yaml`; default 600 seconds (10 minutes).

### 3.7 Operator Override

Reality: gate chains will occasionally block legitimate work. A build pipeline dies, the manifest never gets written, a fix must ship in five minutes. Without an escape hatch, DTGP becomes a wall the operator learns to route around by shutting DTGP off — which is the worst outcome.

**Override endpoint:** `POST /admin/action/override` on DTGP.

**Body:**
```
{
  "target_id": "arduino_mega_lora_gw_01",
  "action": "flash",
  "artifact_path": "/tmp/hotfix.hex",
  "justification": "Prod outage 2026-08-29 20:15 UTC; build pipeline down; hotfix from off-line rebuild.",
  "acknowledged_bypassed_gates": ["artifact_compatibility", "environment_alignment"]
}
```

**Flow:**
1. Endpoint creates a `sovereign_dtgp_action_override` SCR (a distinct type — heavier scrutiny than regular consent).
2. Operator sees an amber-styled consent surface stating explicitly which gates are being bypassed and requiring re-entering the justification for confirm-by-typing (not just a click).
3. On approval, DTGP runs the action WITHOUT the bypassed gates. Locks and access-path resolution still apply — the override skips intent-alignment, not physical safety.
4. ADS event `dtgp_action_operator_override` emitted with justification, bypassed gates, and outcome.
5. Every override generates an entry in a monthly Overseer audit report (Overseer's SPEC-anchored responsibility — no new work here).

**Overrides never bypass:** access-path resolution, lock acquisition, credential resolution, ADS logging. Override is a semantic escape, not an infrastructure one.

### 3.8 ADS Event Types

Add to `adt_core/ads/schema.py`:

```
INTENT_ALIGNMENT_EVENTS = [
    "dtgp_gate_evaluated",                       # {gate_id, decision, target_id, action, ms}
    "dtgp_task_binding_verified",                # {task_id, target_id, action}
    "dtgp_artifact_manifest_loaded",             # {artifact_id, sha256, target_types}
    "dtgp_artifact_compatibility_verified",      # {artifact_id, target_id}
    "dtgp_environment_verified",                 # {target_env, artifact_env}
    "sovereign_dtgp_action_requested",           # SCR created; payload above
    "sovereign_dtgp_action_authorized",          # Operator confirmed
    "sovereign_dtgp_action_rejected",            # Operator rejected
    "sovereign_dtgp_action_timed_out",           # Timeout, treated as reject
    "sovereign_dtgp_action_override_requested",  # Override SCR created
    "sovereign_dtgp_action_override_authorized", # Override approved
    "dtgp_action_operator_override",             # Override action ran, with bypassed_gates list
]
```

`dtgp_gate_evaluated` is high-volume; gate the emission behind a DEBUG flag in production. All others are always-on.

## 4. Task Breakdown

- task_1: Gate composition engine — registry, resolver, `evaluate → GateResult` interface, action-endpoint integration. **Role:** Backend_Engineer.
- task_2: Task schema extension (`dtgp_targets`, `dtgp_actions`), task-binding gate implementation, migration for existing tasks (nullable fields, no forced backfill). **Role:** Backend_Engineer + Systems_Architect (Architect owns `_cortex/tasks.json` schema).
- task_3: Artifact manifest schema + JSON validator + `adt artifact manifest` CLI (minimal). **Role:** Backend_Engineer + Systems_Architect (schema authority).
- task_4: Artifact compatibility gate + environment alignment gate. **Role:** Backend_Engineer.
- task_5: DTGP Consent SCR — new SCR type in the SCR queue, Console surface (modal with full-chain preview), timeout enforcement, DTGP resume-on-approval. **Role:** Backend_Engineer + Frontend_Engineer.
- task_6: Operator override endpoint + `sovereign_dtgp_action_override` SCR type + Console amber-styled override surface with confirm-by-typing. **Role:** Backend_Engineer + Frontend_Engineer.
- task_7: Default gate chain configuration for the v1 driver set (SSH, USB-serial, HTTP) + `_cortex/dtgp/gate_config.yaml` schema and loader. **Role:** Systems_Architect + Backend_Engineer.
- task_8: `INTENT_ALIGNMENT_EVENTS` registered in `adt_core/ads/schema.py`; emission wired through every gate. **Role:** Backend_Engineer.
- task_9: End-to-end verification — task-binding refusal, artifact-mismatch refusal, environment-mismatch refusal, Tier-1 consent approve path, Tier-1 consent reject path, timeout path, override path. **Role:** DevOps_Engineer.

## 5. Acceptance Criteria

- `POST /action` without `task_id` returns 400 with `error: task_id required`.
- `POST /action` with a `task_id` whose task's `dtgp_targets` does not include the request's target returns 403 with `denied_by: task_binding`, `reason: target_not_in_task`.
- `POST /action` with an artifact whose manifest declares `compatible_target_types: [esp32]` against an `arduino_mega_2560` target returns 403 with `reason: artifact_incompatible_type`.
- `POST /action` with an artifact whose manifest env is `production` against a target with env `lab` returns 403 with `reason: environment_mismatch`.
- Corrupted artifact (bytes SHA-256 != manifest SHA-256) returns 403 with `reason: artifact_integrity_failed`.
- `POST /action` against a Tier-1 target with all other gates passing returns 202 with `scr_id` and `poll_url`; a `sovereign_dtgp_action_requested` ADS event exists; Console displays a consent modal with the full expanded chain, artifact SHA-256, task provenance.
- Operator Confirm on the consent modal → SCR authorized → DTGP resumes action → normal completion; ADS shows `sovereign_dtgp_action_authorized` then `dtgp_action_completed`.
- Operator Reject → SCR rejected → DTGP aborts action; ADS shows `sovereign_dtgp_action_rejected` then `dtgp_action_denied` with `reason: consent_denied`.
- Consent timeout (SCR not answered within configured window, default 600s) → same as reject; ADS reason `consent_timeout`.
- Override endpoint requires a justification longer than 30 characters and requires confirming the justification by re-typing on the override consent surface; approved override runs the action with `dtgp_action_operator_override` ADS event listing `bypassed_gates`.

## 6. Non-Goals

- Cryptographic signature verification on artifacts (beyond SHA-256 integrity).
- Multi-party consent.
- Delegated / batch consent (pre-approve a class of actions for N hours).
- Automated environment promotion pipelines.
- Machine-learned suggestion of tightened gate chains from observation.
- Per-agent trust scoring (agent-A gets fewer consent prompts than agent-B).
- Manifest generation deeply integrated with third-party build systems (SPEC-116 per-driver work).

## 7. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| **Consent fatigue.** Operator sees so many Tier-1 SCRs they start rubber-stamping them. | Tier assignment should be conservative — only devices where a bad action really matters are Tier-1. Console shows recent approval rate per operator; if it approaches 100%, prompt a review. `gate_config.yaml` per-project lets operators tune. |
| **Gate misconfiguration blocks legitimate work.** | Override endpoint is the safety valve. `gate_config.yaml` itself is Tier-1 (SCR to edit). Every override generates an audit entry so patterns of override are visible. |
| **Manifest generation not implemented by build pipeline → all artifact actions blocked.** | Minimal `adt artifact manifest` CLI ships with this spec — operator can hand-generate. Per-driver auto-generation is SPEC-116. Rollout order (§10) ensures the CLI ships before gates are enabled by default. |
| **Timing attack: agent races two flashes to the same target with different task_ids to confuse the gate.** | Gate chain is atomic per action call — task_binding is resolved once, per invocation. Lock manager from SPEC-113 already serialises per target, so the second call waits or fails cleanly. |
| **Malicious agent submits `task_id` referencing a task that authorises everything.** | Task creation itself is governed by SDD — creating a task requires a spec, which requires human approval for Tier-1 assets. If an agent could create arbitrary tasks with arbitrary `dtgp_targets`, that's the vulnerability, not this gate. SPEC-114 assumes task creation is trustworthy (which SPEC-026 / SPEC-045 already enforce). |
| **Consent SCR queue overflow if many Tier-1 actions are requested concurrently.** | SCR queue is bounded per project (existing SPEC-033 behaviour). Overflow returns 429 to caller; agent should back off. Emit `sovereign_dtgp_action_queue_full` ADS event as observability signal. |
| **Operator clicks Confirm without reading the surface.** | Confirm requires an active click on a specific button; consent surface layout puts the target and artifact hash prominently in view. Override surface additionally requires re-typing the justification. Beyond that: this is a training / UX issue no gate can fix — audit trail preserves accountability. |

## 8. Dependencies

- **SPEC-113** — DTGP action endpoint, target / action / artifact model, ADS event conventions.
- **SPEC-033** — Sovereign Change Request queue and lifecycle; extended here with two new SCR types.
- **SPEC-045** — SCR Authorization Hardening; ensures the requesting agent cannot self-approve its own consent SCR.
- **SPEC-057** — Agent Mailbox (optional, useful): DTGP can deliver `consent_denied` or `consent_timeout` back to the requesting agent's inbox rather than requiring it to poll.
- **`_cortex/tasks.json`** — extended with two new optional fields; existing tasks without them fail closed on task_binding (they can't authorise anything through DTGP, which is correct: pre-existing tasks weren't authored with DTGP awareness).

## 9. Follow-On Work (Not This Spec)

- **SPEC-115** — Embedded_Engineer role + four-stage physical-safety flash gate (presence, backup, consent, verify, rollback). Layers on top of SPEC-113 + SPEC-114.
- **SPEC-116** — Deployment action drivers (SFTP, git push, S3, kubectl, docker push) with their own default gate chains and per-driver manifest generation.
- Future: cryptographic signing of artifacts; multi-party consent; delegated / batch consent; automated environment promotion pipelines; per-agent trust adjustments to gate chains.

## 10. Rollout

1. **task_1 + task_2** — gate engine + task-binding gate. Ship with all default chains empty (behaviour unchanged); operators opt in per (target_type, action) via `gate_config.yaml`. First opt-in should be one non-critical target class in a test project.
2. **task_3** — manifest schema + CLI. Independently useful; no gate depends on it yet.
3. **task_4** — artifact + environment gates. Enabled per-project as opted-in.
4. **task_5** — consent flow. Requires SCR queue changes; test carefully in isolation before enabling on Tier-1 targets in a live project.
5. **task_6** — override path. Ships together with task_5 (safety valve must exist before the wall does).
6. **task_7** — default gate chains for v1 drivers. This is the moment gates become default-on for new projects; existing projects opt in.
7. **task_8** — ADS wiring throughout, verified by task_9.
8. **task_9** — E2E verification covers every gate + consent path + override path.
9. Update `MASTER_PLAN.md` to add SPEC-114 as ACTIVE (via SCR — MASTER_PLAN is Tier 1).

---

*"Governance is not just knowing what happened. It is deciding, before it happens, what should be allowed to happen."*
