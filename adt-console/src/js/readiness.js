// SPEC-073: Console Loading States & Action Guards
// Loaded FIRST in index.html — before any module that may call begin/end.
// See _cortex/specs/SPEC-073_CONSOLE_LOADING_STATES_AND_ACTION_GUARDS.md
(function () {
  const _tasks = new Map();          // key -> { label, startedAt, endedAt|null }
  const _listeners = new Set();
  let _readyEmitted = false;

  function _emit() {
    const snap = pending();
    _listeners.forEach(fn => { try { fn(snap); } catch(_){} });
    _render();
    _checkReady();
  }

  function begin(key, label) {
    if (_tasks.has(key) && !_tasks.get(key).endedAt) return;   // already open
    _tasks.set(key, { label: label || key, startedAt: Date.now(), endedAt: null });
    _emit();
  }

  function end(key) {
    const t = _tasks.get(key);
    if (!t || t.endedAt) return;
    t.endedAt = Date.now();
    _emit();
  }

  function pending() {
    const out = [];
    _tasks.forEach((t, k) => { if (!t.endedAt) out.push({ key: k, label: t.label, elapsedMs: Date.now() - t.startedAt }); });
    return out;
  }

  function isReady() { return pending().length === 0; }

  function waitReady({ timeout = 8000 } = {}) {
    if (isReady()) return Promise.resolve(true);
    return new Promise((resolve) => {
      const deadline = Date.now() + timeout;
      const off = onChange(() => {
        if (isReady()) { off(); resolve(true); }
        else if (Date.now() > deadline) { off(); resolve(false); }
      });
    });
  }

  function onChange(fn) { _listeners.add(fn); return () => _listeners.delete(fn); }

  function _render() {
    const bar = document.getElementById('console-readiness-bar');
    const fill = document.getElementById('console-readiness-fill');
    const label = document.getElementById('console-readiness-label');
    if (!bar || !fill || !label) return;

    const total = _tasks.size;
    const done = Array.from(_tasks.values()).filter(t => t.endedAt).length;
    const pct = total === 0 ? 100 : Math.round((done / total) * 100);
    const snap = pending();

    if (snap.length === 0) {
      // Fade out then hide
      fill.style.width = '100%';
      setTimeout(() => { if (isReady()) bar.style.display = 'none'; }, 400);
      label.textContent = 'Ready';
    } else {
      bar.style.display = 'block';
      fill.style.width = pct + '%';
      const cur = snap[0];
      label.textContent = `${cur.label} (${snap.length} pending, ${pct}%)`;
      label.title = snap.map(p => `• ${p.label} (${(p.elapsedMs/1000).toFixed(1)}s)`).join('\n');
    }
  }

  function _checkReady() {
    const nowReady = isReady() && _tasks.size > 0;
    if (nowReady && !_readyEmitted) {
      _readyEmitted = true;
      _logConsoleReady();
    }
  }

  function _logConsoleReady() {
    try {
      const centerUrl = (window.SpecMap && window.SpecMap.getCenterUrl)
        ? window.SpecMap.getCenterUrl()
        : (localStorage.getItem('adt_center_url') || 'http://localhost:5001');
      const tasksArr = Array.from(_tasks.entries()).map(([k, t]) => ({
        key: k, label: t.label, elapsedMs: (t.endedAt || Date.now()) - t.startedAt
      }));
      const durationMs = tasksArr.reduce((m, t) => Math.max(m, t.elapsedMs), 0);
      const body = JSON.stringify({
        session_id: window.__ADT_TELEMETRY_SESSION_ID || (window.Telemetry && window.Telemetry.sessionId) || 'unknown',
        action: 'console_ready',
        target: 'console',
        action_data: { duration_ms: durationMs, tasks: tasksArr },
        metadata: { duration_ms: durationMs, tasks: tasksArr }
      });
      fetch(`${centerUrl}/api/telemetry/action?project=adt-framework`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true
      }).catch(() => {});
    } catch (_) {}
  }

  // 15-second watchdog for stalled readiness tasks
  setTimeout(() => {
    const stalled = pending();
    if (stalled.length > 0) {
      console.warn('[ConsoleReadiness] Stalled tasks detected after 15s:', stalled);
      try {
        const centerUrl = (window.SpecMap && window.SpecMap.getCenterUrl)
          ? window.SpecMap.getCenterUrl()
          : (localStorage.getItem('adt_center_url') || 'http://localhost:5001');
        const body = JSON.stringify({
          session_id: window.__ADT_TELEMETRY_SESSION_ID || (window.Telemetry && window.Telemetry.sessionId) || 'unknown',
          action: 'readiness_stall',
          target: 'console',
          action_data: { stalled_tasks: stalled },
          metadata: { stalled_tasks: stalled }
        });
        fetch(`${centerUrl}/api/telemetry/action?project=adt-framework`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true
        }).catch(() => {});
      } catch (_) {}
    }
  }, 15000);

  // ---------------- ActionGuard: per-button single-flight + busy state ----
  const _busy = new Set();

  async function guardRun(actionKey, buttonEl, asyncFn) {
    if (_busy.has(actionKey)) return false;
    _busy.add(actionKey);
    const prev = buttonEl && { disabled: buttonEl.disabled, html: buttonEl.innerHTML };
    if (buttonEl) {
      buttonEl.disabled = true;
      buttonEl.dataset.busy = '1';
    }
    try {
      await asyncFn();
      return true;
    } catch (err) {
      console.warn('[ActionGuard]', actionKey, 'failed:', err);
      return false;
    } finally {
      _busy.delete(actionKey);
      if (buttonEl) {
        buttonEl.disabled = prev.disabled;
        delete buttonEl.dataset.busy;
      }
    }
  }

  window.ConsoleReadiness = { begin, end, pending, isReady, waitReady, onChange };
  window.ActionGuard = { run: guardRun, isBusy: (k) => _busy.has(k) };

  // Prime a synthetic "boot" task so the bar is visible from the very first
  // paint; ended once DOMContentLoaded settles and all currently registered
  // tasks have had a chance to register themselves.
  begin('console_boot', 'Booting Console');
  const _bootEnd = () => setTimeout(() => end('console_boot'), 250);
  if (document.readyState === 'complete' || document.readyState === 'interactive') _bootEnd();
  else document.addEventListener('DOMContentLoaded', _bootEnd);
})();


// REQ-113 (Paul WSL analysis): global fetch guard + SafePoll to prevent
// duplicate in-flight polls from piling up when backend slows.
(function () {
  // 1. Wrap global fetch: add a default AbortController with 20s timeout
  // to any request that doesn't already provide a signal. Fixes the
  // "webview connection pool exhausted → UI freeze" pattern.
  if (window.__ADT_FETCH_GUARD_INSTALLED) return;
  window.__ADT_FETCH_GUARD_INSTALLED = true;
  const _origFetch = window.fetch.bind(window);
  window.fetch = function(input, init) {
    init = init || {};
    if (!init.signal) {
      const ac = new AbortController();
      init.signal = ac.signal;
      // REQ-113 rc69: bumped 20s → 60s to cover the LLM intent classifier
      // (25-45s p95). Still catches truly hung requests. Callers that need
      // longer can pass their own signal to bypass this guard.
      setTimeout(() => { try { ac.abort(); } catch(_) {} }, 60000);
    }
    return _origFetch(input, init);
  };

  // 2. SafePoll: setInterval that skips ticks while a previous tick is still
  // running. Prevents duplicate-request storms.
  window.SafePoll = {
    _guards: new Map(),  // key -> { running, id }
    register(key, intervalMs, fn) {
      this.cancel(key);
      const state = { running: false };
      const id = setInterval(async () => {
        if (state.running) return;
        state.running = true;
        try { await fn(); }
        catch (e) { console.warn('[SafePoll:'+key+']', e); }
        finally { state.running = false; }
      }, intervalMs);
      state.id = id;
      this._guards.set(key, state);
      return id;
    },
    cancel(key) {
      const g = this._guards.get(key);
      if (g && g.id) { clearInterval(g.id); this._guards.delete(key); }
    }
  };
})();
