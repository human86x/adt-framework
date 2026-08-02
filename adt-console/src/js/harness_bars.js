// SPEC-062-H: per-harness quota/activity strip in the topbar. Polls every 5s.
(function () {
  const POLL_MS = 5000;
  // Must use 'localhost' not 127.0.0.1 — the Tauri CSP whitelists only
  // http://localhost:5001, so a 127.0.0.1 URL is silently blocked.
  const CENTER = () =>
    (window.SpecMap && window.SpecMap.getCenterUrl && window.SpecMap.getCenterUrl()) ||
    'http://localhost:5001';

  function ensureContainer() {
    let host = document.getElementById('harness-bars');
    if (host) return host;
    const brand = document.querySelector('#topbar .topbar-brand');
    if (!brand) return null;
    host = document.createElement('div');
    host.id = 'harness-bars';
    host.style.cssText =
      'display:inline-flex;align-items:center;gap:6px;margin-left:12px;';
    brand.appendChild(host);
    return host;
  }

  function pillFor(h) {
    const el = document.createElement('div');
    el.className = 'harness-pill';
    el.dataset.name = h.name;
    el.title = `${h.label} — ${h.usage_label}${h.detail ? ' · ' + h.detail : ''}`;
    el.style.cssText =
      'display:inline-flex;align-items:center;gap:6px;padding:3px 8px;'
      + 'background:#21262d;border:1px solid #30363d;border-radius:12px;'
      + 'font-size:10px;line-height:1;color:#c9d1d9;min-width:118px;'
      + 'height:20px;box-sizing:border-box;';
    el.innerHTML = `
      <span class="hp-dot" style="width:6px;height:6px;border-radius:50%;flex:0 0 6px"></span>
      <span class="hp-name" style="font-weight:600;flex:0 0 auto"></span>
      <span class="hp-bar" style="flex:1 1 auto;height:5px;background:#0d1117;border-radius:3px;overflow:hidden;position:relative">
        <span class="hp-fill" style="position:absolute;left:0;top:0;bottom:0;width:0;background:#3fb950;transition:width 0.4s"></span>
      </span>
      <span class="hp-label" style="font-size:9px;opacity:0.75;flex:0 0 auto;white-space:nowrap"></span>
    `;
    return el;
  }

  function colorFor(h) {
    if (!h.auth_ok) return '#f85149';
    if (h.usage_pct >= 90) return '#f85149';
    if (h.usage_pct >= 70) return '#d29922';
    if (h.active) return '#3fb950';
    return '#6e7681';
  }

  function render(host, data) {
    const list = (data && data.harnesses) || [];
    const seen = new Set();
    list.forEach(h => {
      seen.add(h.name);
      let el = host.querySelector(`.harness-pill[data-name="${h.name}"]`);
      if (!el) { el = pillFor(h); host.appendChild(el); }
      el.title = `${h.label} — ${h.usage_label}${h.detail ? ' · ' + h.detail : ''}`;
      const c = colorFor(h);
      el.querySelector('.hp-dot').style.background = c;
      el.querySelector('.hp-fill').style.background = c;
      el.querySelector('.hp-fill').style.width = `${Math.max(0, Math.min(100, h.usage_pct || 0))}%`;
      el.querySelector('.hp-name').textContent = h.label;
      el.querySelector('.hp-label').textContent = h.usage_label || '';
      el.style.opacity = h.auth_ok ? '1' : '0.72';
    });
    host.querySelectorAll('.harness-pill').forEach(el => {
      if (!seen.has(el.dataset.name)) el.remove();
    });
  }

  // SPEC-076-B: map harness to quota bucket
  // Antigravity + Gemini CLI use Google Gemini bucket. Claude uses non-Gemini bucket.
  const _bucketOf = name => {
    if (name === 'agy' || name === 'gemini' || name === 'antigravity') return 'gemini';
    if (name === 'claude' || name === 'codex' || name === 'openai') return 'nongemini';
    return 'gemini';
  };

  function _fmtCountdown(iso) {
    if (!iso) return '';
    const d = new Date(iso).getTime() - Date.now();
    if (d <= 0) return '';
    const s = Math.floor(d / 1000);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${ss}s`;
    return `${ss}s`;
  }

  let _lastQuota = { buckets: {} };

  function applyQuotaOverlay(host) {
    // For each pill, if its bucket is exhausted, override colour + bar + label
    host.querySelectorAll('.harness-pill').forEach(el => {
      const bkt = _bucketOf(el.dataset.name);
      const bstate = _lastQuota.buckets && _lastQuota.buckets[bkt];
      if (bstate && bstate.state === 'exhausted') {
        const countdown = _fmtCountdown(bstate.resets_at);
        el.querySelector('.hp-dot').style.background = '#f85149';
        // Exhausted = EMPTY bar (operator's semantic — resource remaining, not used)
        el.querySelector('.hp-fill').style.width = '0%';
        el.querySelector('.hp-fill').style.background = '#f85149';
        el.querySelector('.hp-label').textContent = countdown ? `QUOTA · ${countdown}` : 'QUOTA HIT';
        el.querySelector('.hp-label').style.color = '#f85149';
        el.querySelector('.hp-label').style.opacity = '1';
        el.style.borderColor = '#f85149';
        el.title = `${el.dataset.name} — ${bkt} bucket EXHAUSTED, resets at ${bstate.resets_at || 'unknown'}`;
      } else {
        el.querySelector('.hp-label').style.color = '';
        el.style.borderColor = '#30363d';
      }
    });
  }

  async function tick() {
    const host = ensureContainer();
    if (!host) return;
    try {
      const [rH, rQ] = await Promise.all([
        fetch(`${CENTER()}/api/harnesses/status`, { cache: 'no-store' }),
        fetch(`${CENTER()}/api/agy/state`, { cache: 'no-store' })
      ]);
      if (rH.ok) render(host, await rH.json());
      if (rQ.ok) {
        const q = await rQ.json();
        _lastQuota = (q && q.quota) || { buckets: {} };
      }
      applyQuotaOverlay(host);
    } catch (_) { /* backend down — leave last state visible */ }
  }

  // Refresh countdown labels every second (state only refetched on POLL_MS)
  function tickCountdown() {
    const host = document.getElementById('harness-bars');
    if (host) applyQuotaOverlay(host);
  }

  function start() {
    tick();
    setInterval(tick, POLL_MS);
    setInterval(tickCountdown, 1000);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else { start(); }
})();
