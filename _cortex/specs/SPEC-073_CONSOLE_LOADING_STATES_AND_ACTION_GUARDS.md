# SPEC-073: Console Loading States & Action Guards

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE)
**Created:** 2026-07-26
**Target Milestone:** v0.4.0
**Jurisdiction:** Frontend_Engineer (`adt-console/src/`)
**Depends On:** SPEC-021 (Operator Console), SPEC-032 (Project Launcher), SPEC-062 (Spec Map)

**Intent:** Make the Console honest about when it is ready. The operator must never be left guessing whether a click was ignored, is being processed, or triggered a race — every asynchronous open must produce a visible in-progress signal, and the topbar must reflect whether the app is done initializing.

**Triggering Event:** Operator report, 2026-07-26 (CEV-CONSOLE-INIT-SILENT): "when it appears that all was loaded it still thinking so when pressing on the buttons like app forge it just doesn't do anything but then it starts to open multiple appforges resetting the previous one." Observed after SPEC-072 build (rc60/rc61). Reproduces on cold Console start on the local WSL host and lab-center Pi.

**Success Condition:** (a) On cold start, a top-of-viewport progress bar is visible within 100 ms of first paint and hides only when every registered init task has ended. (b) Double-clicking any wizard-opening button during the warmup window produces exactly one wizard modal — verified by `document.querySelectorAll('.wizard-modal').length === 1`. (c) Every registered click that fires while its target is initializing shows a per-button busy spinner and lands exactly once. (d) `window.ConsoleReadiness.pending()` returns `[]` before any topbar button can report "clickable but silent." (e) ADS receives one `console_ready` event per session with `duration_ms` and per-task timings.

---

## 1. Problem

Operator report (2026-07-26):

> "Until all of the ADT Console is fully loaded so we can open specs and start the app forge — it takes time, and when it appears that all was loaded it still thinking so when pressing on the buttons like app forge it just doesn't do anything but then it starts to open multiple appforges resetting the previous one."

Two distinct failure modes visible to the operator:

1. **Silent warmup window.** The DOM paints in ~500 ms but several async initializers keep running for another 2–8 s (session restore, adopted-RR fetch, agy auth probe, project registry, SpecMap dataset, jurisdiction rules). Clicks during that window either no-op or produce partial state — the operator cannot see the difference between "app is thinking" and "app is broken."
2. **Double-open racing.** Clicking `Forge Application` (or any wizard-opening button) twice in quick succession spawns two wizard modals; the second one wipes the first one's `currentWizard` reference in `launcher.js:429`, so any in-flight fetch bound to the first wizard writes into a detached DOM. Same class of bug affects Projects, Spec Map, Governance, ADT Panel toggles.

---

## 2. Goals

1. Operator sees a **global readiness indicator** from window open until the console is safe to drive.
2. Every button that triggers an async open shows a **per-button busy state** during initialization and refuses further clicks until the target is ready.
3. Wizard opens are **single-flight**: a second click while a wizard is spawning is a no-op, not a second wizard.

## 3. Non-Goals

* No skeleton screens for individual panels (out of scope; addressed later if needed).
* No backend changes. No new endpoints.
* No new dependencies. Pure vanilla JS + CSS.

---

## 4. Architecture

### 4.1 `ConsoleReadiness` module (new: `adt-console/src/js/readiness.js`)

A tiny global registry loaded before all other modules that call `document.getElementById` on startup:

```js
window.ConsoleReadiness = {
  _tasks: new Map(),       // key -> { label, startedAt, done }
  _listeners: new Set(),

  begin(key, label) { /* register + emit change */ },
  end(key)          { /* mark done + emit change */ },
  isReady()         { /* true iff all tasks done */ },
  pending()         { /* Array of {key, label, elapsedMs} */ },
  onChange(fn)      { /* subscribe */ }
};
```

**Critical init tasks** that must call `begin` / `end`:

| Key | Owner | Label |
|---|---|---|
| `session_restore` | `sessions.js` | "Restoring sessions" |
| `project_launcher_init` | `launcher.js` | "Loading project registry" |
| `governance_bootstrap` | `governance.js` | "Loading governance state" |
| `spec_map_init` | `spec_map.js` | "Initialising spec map" |
| `agy_auth_probe` | `auth_badge.js` | "Checking agy auth" |
| `ads_reducer_prime` | `ads_reducer.js` | "Priming event ledger" |

Any module may register additional keys; the readiness bar reflects the union.

### 4.2 Global progress bar

Fixed 3 px bar at top of viewport (below `#topbar`), rendered in `index.html`:

```html
<div id="console-readiness-bar" style="display:none;position:fixed;top:48px;left:0;right:0;height:3px;z-index:9999;background:#161b22">
  <div id="console-readiness-fill" style="height:100%;width:0%;background:linear-gradient(90deg,#58a6ff,#a5d6ff);transition:width 250ms ease"></div>
  <div id="console-readiness-label" style="position:absolute;top:6px;right:12px;font-size:10px;color:#8b949e;background:rgba(13,17,23,0.85);padding:2px 8px;border-radius:3px"></div>
</div>
```

Behaviour:
* Shown when at least one task is pending; hidden otherwise.
* Fill width = `(done / total)` for tasks registered since page load.
* Label = current task's `label`; on hover shows the full pending list.
* Fade-out over 400 ms once `isReady()` becomes true; then `display:none`.

### 4.3 Per-action busy guard (`ActionGuard`)

Also in `readiness.js`:

```js
window.ActionGuard = {
  _busy: new Set(),

  async run(actionKey, buttonEl, asyncFn) {
    if (this._busy.has(actionKey)) return;   // single-flight: drop the second click
    this._busy.add(actionKey);
    const prev = buttonEl && { disabled: buttonEl.disabled, html: buttonEl.innerHTML };
    if (buttonEl) {
      buttonEl.disabled = true;
      buttonEl.dataset.busy = "1";
    }
    try { await asyncFn(); }
    finally {
      this._busy.delete(actionKey);
      if (buttonEl) {
        buttonEl.disabled = prev.disabled;
        delete buttonEl.dataset.busy;
      }
    }
  }
};
```

CSS for busy buttons (in `console.css`):

```css
button[data-busy="1"] {
  opacity: 0.6;
  cursor: progress;
  position: relative;
}
button[data-busy="1"]::after {
  content: "";
  position: absolute; inset: 0; margin: auto;
  width: 12px; height: 12px;
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: adt-spin 0.6s linear infinite;
}
@keyframes adt-spin { to { transform: rotate(360deg); } }
```

### 4.4 Wiring the topbar buttons

In `app.js`, wrap each async-opening handler:

```js
document.getElementById('btn-projects').addEventListener('click', (e) => {
  ActionGuard.run('projects_toggle', e.currentTarget, async () => {
    if (!window.ConsoleReadiness.isReady()) {
      await window.ConsoleReadiness.waitReady({ timeout: 8000 });
    }
    await ProjectLauncher.toggle();
  });
});
```

Same wrapping for `btn-spec-map`, `btn-governance`, `btn-adt-panel`, `btn-dashboard`, `card-forge-app`, `card-create-project`, `card-import-project`.

### 4.5 Wizard single-flight

`ProjectLauncher` gains an internal `_opening` flag:

```js
function openForgeWizard() {
  if (currentWizard || _opening) return;    // second click during spawn: drop
  _opening = true;
  try { showForgeScreen1(); } finally { _opening = false; }
}
```

Analogous guard in `openCreateWizard`, `openImportWizard`.

---

## 5. Acceptance Criteria

1. On cold Console start, the top progress bar is visible within 100 ms of first paint and stays until every registered task ends.
2. Double-clicking `Forge Application` during the warmup window produces **exactly one** wizard modal (verified by `document.querySelectorAll('.wizard-modal').length === 1`).
3. Clicking `Projects` before ProjectLauncher init completes results in the button showing the busy spinner, the click landing exactly once, and the launcher opening after init resolves.
4. `window.ConsoleReadiness.pending()` returns `[]` before any topbar button reports itself "clickable but silent."
5. ADS receives one `console_ready` event when all init tasks complete, with `action_data.duration_ms` and `action_data.tasks` = array of `{key, elapsedMs}`.
6. No regression: `node --check` clean on all modified JS files.

---

## 6. Implementation Notes for Frontend_Engineer

* Load `readiness.js` **first** in `index.html`, before any module that might call `begin/end`.
* `end()` must be called in `finally` blocks — a rejected fetch that never ends its task will freeze the bar at partial progress.
* Buttons already using `.dataset.busy` for other reasons: audit before shipping.
* Consider a 15 s watchdog that emits `readiness_stall` to ADS if a task hasn't ended — a stuck init is a diagnostic signal, not a silent failure.

## 7. Out of Scope (Follow-ups)

* Retry UI for stalled init tasks.
* Per-panel skeleton screens.
* Backend readiness probe (would let the bar show more than just frontend state).

---

*"An action the operator can't see is an action they'll repeat."*
