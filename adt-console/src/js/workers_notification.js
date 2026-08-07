// SPEC-078 Part D (REQ-121): Worker Interactive-Input Notification
//
// Polls /api/workers/awaiting_input every 3s. On non-empty response, renders
// a persistent floating banner (bottom-right) listing each paused worker with:
//   - prompt type / hint
//   - "Copy URL" (when there's an OAuth URL)
//   - "I've completed auth -- Resume"
//   - "Cancel worker"
//
// Sits alongside the existing auth badge; independent of it because a worker
// can be paused for reasons other than expired global auth (password, TOTP...).
(function () {
  const POLL_MS = 3000;
  const CENTER = () =>
    (window.SpecMap && window.SpecMap.getCenterUrl && window.SpecMap.getCenterUrl()) ||
    localStorage.getItem('adt_center_url') ||
    'http://localhost:5001';

  const CONTAINER_ID = 'adt-workers-awaiting-panel';

  function ensureContainer() {
    let el = document.getElementById(CONTAINER_ID);
    if (el) return el;
    el = document.createElement('div');
    el.id = CONTAINER_ID;
    el.style.cssText = [
      'position:fixed',
      'bottom:16px',
      'right:16px',
      'z-index:1200',
      'max-width:420px',
      'font-family:system-ui,sans-serif',
      'pointer-events:none' // panel is a wrapper; cards enable events themselves
    ].join(';');
    document.body.appendChild(el);
    return el;
  }

  function copyToClipboard(text) {
    try {
      navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } catch (_) {}
      ta.remove();
      return true;
    }
  }

  function fmtAge(sec) {
    if (sec < 60) return `${sec}s`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m`;
    return `${Math.floor(sec / 3600)}h`;
  }

  function renderCard(w) {
    const card = document.createElement('div');
    card.style.cssText = [
      'background:#0d1117',
      'border:2px solid #f0883e',
      'border-radius:10px',
      'padding:14px 16px',
      'margin-top:10px',
      'color:#e6edf3',
      'box-shadow:0 6px 20px rgba(0,0,0,0.6)',
      'pointer-events:auto'
    ].join(';');

    const title = document.createElement('div');
    title.style.cssText = 'font-weight:700;color:#f0883e;margin-bottom:6px;font-size:14px';
    title.textContent = `Worker awaiting operator input (${w.prompt_type || 'unknown'})`;
    card.appendChild(title);

    const meta = document.createElement('div');
    meta.style.cssText = 'font-size:11px;color:#8b949e;margin-bottom:8px';
    const bits = [];
    if (w.spawned_by_spec) bits.push(w.spawned_by_spec);
    if (w.project) bits.push(w.project);
    if (w.role) bits.push(w.role);
    bits.push(`paused ${fmtAge(w.age_sec || 0)}`);
    if (w.state && w.state !== 'paused') bits.push(w.state);
    meta.textContent = bits.join(' | ');
    card.appendChild(meta);

    if (w.hint) {
      const hint = document.createElement('div');
      hint.style.cssText = 'font-size:12px;color:#c9d1d9;margin-bottom:8px;line-height:1.4';
      hint.textContent = w.hint;
      card.appendChild(hint);
    }

    if (w.prompt_url) {
      const urlBox = document.createElement('div');
      urlBox.style.cssText = 'font-size:11px;background:#161b22;border:1px solid #30363d;padding:6px 8px;border-radius:4px;word-break:break-all;margin-bottom:8px;font-family:monospace';
      urlBox.textContent = w.prompt_url;
      card.appendChild(urlBox);
    } else if (w.matched_line) {
      const lineBox = document.createElement('div');
      lineBox.style.cssText = 'font-size:11px;background:#161b22;border:1px solid #30363d;padding:6px 8px;border-radius:4px;word-break:break-all;margin-bottom:8px;font-family:monospace';
      lineBox.textContent = w.matched_line;
      card.appendChild(lineBox);
    }

    const buttons = document.createElement('div');
    buttons.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap';

    if (w.prompt_url) {
      const b = document.createElement('button');
      b.textContent = 'Copy URL';
      b.style.cssText = 'padding:6px 10px;background:#21262d;border:1px solid #30363d;color:#e6e6e6;border-radius:5px;cursor:pointer;font-size:12px';
      b.onclick = () => {
        copyToClipboard(w.prompt_url);
        b.textContent = 'Copied!';
        setTimeout(() => (b.textContent = 'Copy URL'), 1500);
      };
      buttons.appendChild(b);

      // Also offer opening the URL directly (browser handles it).
      const bOpen = document.createElement('button');
      bOpen.textContent = 'Open';
      bOpen.style.cssText = 'padding:6px 10px;background:#21262d;border:1px solid #30363d;color:#e6e6e6;border-radius:5px;cursor:pointer;font-size:12px';
      bOpen.onclick = () => { try { window.open(w.prompt_url, '_blank'); } catch (_) {} };
      buttons.appendChild(bOpen);
    }

    const bResume = document.createElement('button');
    bResume.textContent = "I've completed auth - Resume";
    bResume.style.cssText = 'padding:6px 10px;background:#238636;border:none;color:#fff;border-radius:5px;cursor:pointer;font-size:12px;font-weight:600';
    bResume.onclick = async () => {
      bResume.disabled = true;
      bResume.textContent = 'Resuming...';
      try {
        const r = await fetch(`${CENTER()}/api/workers/${encodeURIComponent(w.worker_id)}/resume`, { method: 'POST' });
        if (r.ok) {
          card.remove();
        } else {
          const body = await r.text();
          bResume.disabled = false;
          bResume.textContent = 'Retry Resume';
          console.warn('worker resume failed', r.status, body);
        }
      } catch (e) {
        bResume.disabled = false;
        bResume.textContent = 'Retry Resume';
        console.error('worker resume error', e);
      }
    };
    buttons.appendChild(bResume);

    const bCancel = document.createElement('button');
    bCancel.textContent = 'Cancel worker';
    bCancel.style.cssText = 'padding:6px 10px;background:#21262d;border:1px solid #da3633;color:#f85149;border-radius:5px;cursor:pointer;font-size:12px';
    bCancel.onclick = async () => {
      if (!confirm(`Cancel worker ${w.worker_id}?`)) return;
      bCancel.disabled = true;
      try {
        await fetch(`${CENTER()}/api/workers/${encodeURIComponent(w.worker_id)}/cancel`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason: 'operator_cancelled_from_console' })
        });
        card.remove();
      } catch (e) {
        bCancel.disabled = false;
        console.error('worker cancel error', e);
      }
    };
    buttons.appendChild(bCancel);

    card.appendChild(buttons);
    card.dataset.workerId = w.worker_id;
    return card;
  }

  function render(workers) {
    const container = ensureContainer();
    // Diff render: only add/remove cards, don't blow away existing state.
    const existing = new Map();
    Array.from(container.children).forEach((c) => {
      if (c.dataset && c.dataset.workerId) existing.set(c.dataset.workerId, c);
    });
    const seen = new Set();
    workers.forEach((w) => {
      seen.add(w.worker_id);
      if (existing.has(w.worker_id)) {
        // Keep the existing card so the operator's in-progress interaction isn't lost.
        return;
      }
      container.appendChild(renderCard(w));
    });
    // Remove cards for workers no longer present.
    existing.forEach((card, id) => {
      if (!seen.has(id)) card.remove();
    });
  }

  async function poll() {
    try {
      const r = await fetch(`${CENTER()}/api/workers/awaiting_input`);
      if (!r.ok) return;
      const data = await r.json();
      render(data.workers || []);
    } catch (_) {
      // ignore transient errors
    } finally {
      setTimeout(poll, POLL_MS);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', poll);
  } else {
    poll();
  }
})();
