# SPEC-074: Forge Live Genesis Stream

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE)
**Created:** 2026-07-26
**Target Milestone:** v0.4.0
**Jurisdiction:** Backend_Engineer (`adt_center/api/`), Frontend_Engineer (`adt-console/src/js/launcher.js`)
**Depends On:** SPEC-067 (Forge Wizard), SPEC-072 (Intent-Driven Governance Assurance), SPEC-073 (Console Loading States)
**Complements:** SPEC-075 (LLM-Backed Intent Classification)

**Intent:** Replace the black-box synchronous `POST /api/governance/forge` with a live, phase-by-phase stream so the operator sees each server-side step start and finish in real time — including the SPEC-075 intent classifier's reasoning as it happens. Kill the "shady background stuff" complaint at the source: nothing important the framework does should happen without the operator being able to watch it.

**Triggering Event:** Operator report 2026-07-26 during habit_tracker_1785072584 forge: "once pressed, the full real time log should appear for the user to track, if mrr agent kicks in, all should be shown to the user!!!!! no shady background stuff... as we cant debug if we dont see." SPEC-073 shipped a client-side placeholder (rc62 genesis screen) but the actual phase transitions are still invisible until the whole POST returns 5-15s later.

**Success Condition:**
(a) Clicking "Forge Application" opens a Server-Sent Events connection that emits at least one event per phase (init_project, start_dtcp, register_intent, intent_classification_started/completed, forge_brief_written, worker_spawned, worker_stdout_line*, forge_session_created) within 100 ms of the phase actually running.
(b) The Forge wizard's live-log panel updates as each event arrives — no polling, no client-side guessing.
(c) A network drop or LLM stall never leaves the operator without feedback: heartbeat events every 2 s while the stream is idle.
(d) The stream terminates cleanly with `forge_session_created` (success) or `forge_failed` (error) — both carry `session_id` and a machine-readable `phase_timings` object for post-mortem.
(e) All emitted events are also persisted to the project ADS as `forge_phase_*` events — the stream is a UI convenience, ADS is the durable record.
(f) An operator reloading the wizard mid-forge can reattach to the same session and see the phase history up to now (via `GET /api/governance/forge/<session_id>/genesis_stream`).

---

## 1. Problem

`api_forge_project` (`adt_center/api/governance_routes.py:233`) runs 6-8 synchronous steps and only returns when they're all done. During that window (5-15 s empirically, longer once SPEC-075 LLM classifier is wired in) the client sees:

- rc61 and earlier: disabled "Forging..." button, no feedback
- rc62+: SPEC-073 client-side genesis screen with a spinner + phase list + elapsed timer — honest but static (client cannot know which server phase is currently executing)

Static phase list + spinner is a lie by omission. The operator wants to see the actual sequence, especially the SPEC-075 classifier's chosen RRs and rationale as they land — not learn about them retroactively on the Forge Complete screen.

## 2. Non-Goals

- No new persistence layer. Events use ADS.
- No new protocol. Server-Sent Events over HTTP — the simplest streaming primitive that survives the panel bridge and Tauri's fetch.
- No LLM-token-level streaming (that's SPEC-075 §6 out-of-scope). Phase-level granularity is sufficient.

## 3. Architecture

### 3.1 New endpoint: `POST /api/governance/forge/stream`

Same request body as `POST /api/governance/forge`. Response is `text/event-stream`:

```
event: phase_started
data: {"phase":"init_project","started_at":"2026-07-26T15:23:11.123Z","seq":1}

event: phase_completed
data: {"phase":"init_project","duration_ms":842,"outcome":"success","seq":2}

event: phase_started
data: {"phase":"intent_classification","engine":"gemini-3.1-pro-high","seq":3}

event: intent_classification_partial
data: {"matched_domains":["personal_data","wellbeing"],"seq":4}

event: intent_classification_partial
data: {"recommended_rr":{"id":"RR-008","rationale":"Wish stores per-user habit completion — personal data under GDPR.","confidence":0.94},"seq":5}

event: phase_completed
data: {"phase":"intent_classification","duration_ms":3421,"outcome":"success","seq":6}

... more phases ...

event: forge_session_created
data: {"forge_session_id":"sess_...","project_name":"...","phase_timings":{...},"seq":N}
```

### 3.2 Heartbeat

If no event has been emitted for 2 s, server sends:
```
event: heartbeat
data: {"pending_phase":"worker_spawn","elapsed_ms":8213}
```

Keeps the connection open through any middlebox and reassures the client the server is alive.

### 3.3 Reattach: `GET /api/governance/forge/<session_id>/genesis_stream`

Replays the phase-event history up to now, then continues live if the session is still in progress. Reads from the persisted ADS ledger — no in-memory buffer needed for reattach.

### 3.4 Panel bridge compatibility

`ops/panel_bridge.py` currently buffers full responses before forwarding. For SSE it must be modified to relay bytes as they arrive (no buffering, no timeout on read once headers indicate `Content-Type: text/event-stream`). This unblocks all future SSE endpoints, not just this one.

### 3.5 Frontend integration (`launcher.js`)

Replace `submitForge`'s single `fetch` with an `EventSource`:

```js
const es = new EventSource(`${getCenterUrl()}/api/governance/forge/stream?_body=${encodeURIComponent(JSON.stringify(body))}`);
// (POST-body-in-query workaround for EventSource, or use fetch+ReadableStream for real POST)
es.addEventListener('phase_started', e => appendPhaseRow(JSON.parse(e.data)));
es.addEventListener('phase_completed', e => markPhaseDone(JSON.parse(e.data)));
es.addEventListener('intent_classification_partial', e => appendClassifierChip(JSON.parse(e.data)));
es.addEventListener('forge_session_created', e => { transitionToLiveLog(JSON.parse(e.data)); es.close(); });
es.addEventListener('forge_failed', e => { showGenesisError(JSON.parse(e.data)); es.close(); });
es.onerror = () => showGenesisError('stream lost');
```

Genesis screen rows go from static "&#8226; phase name" to actively-animated: pending → in-progress (spinner) → done (checkmark + elapsed).

## 4. ADS Persistence

Every stream event is mirrored to project ADS as `forge_phase_started` / `forge_phase_completed` / `forge_phase_failed` with `action_data.phase` and `action_data.seq`. This means:

1. Stream events survive network loss (reattach reads from ADS).
2. Post-mortem: exact phase timings queryable via ADS filters.
3. Overseer can audit forge sessions from ledger alone.

## 5. Acceptance Criteria

1. `POST /api/governance/forge/stream` with the habit_tracker request body emits ≥6 phase events before `forge_session_created`.
2. Wizard's live-log panel animates each phase transition within 100 ms of the SSE event arriving.
3. Killing the network (temporary iptables drop) for 5 s causes the wizard to show a "reconnecting..." chip and successfully reattach via `/genesis_stream` when the network returns.
4. Every stream event is present in project ADS with matching `seq` numbers — no drops.
5. When SPEC-075 is live: `intent_classification_partial` events carry each recommended RR as it is picked, and the wizard renders pre-checked chips in real time (not batch after LLM completes).
6. Panel bridge relays SSE without buffering — verified by matching client-observed event timestamps to server-emitted timestamps within 200 ms.

## 6. Migration & Backward Compatibility

- Legacy `POST /api/governance/forge` (non-stream) remains for scripting / curl users. Marked deprecated after this ships.
- Frontend switches to stream endpoint via a config flag `ADT_FORGE_STREAM=1` for one release cycle; then becomes default.
- No breaking change to `forge_brief.json` schema or `POST /forge` response.

## 7. Out of Scope / Follow-ups

- LLM-token-level streaming inside `intent_classification` phase (SPEC-075 §6).
- Cross-session multiplexing of streams (one operator watching multiple simultaneous forges).
- Push over WebSocket instead of SSE (SSE is intentionally simpler; add WS only if requirements demand bidirectional).

---

*"If it happens on the server and the operator can't see it, it didn't happen — it hid."*
