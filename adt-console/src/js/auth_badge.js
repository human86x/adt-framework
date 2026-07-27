// SPEC-062 (operator-requested): persistent agy auth state UI + in-Console login flow
(function() {
  const POLL_MS = 5000;
  const CENTER = () => (window.SpecMap && window.SpecMap.getCenterUrl && window.SpecMap.getCenterUrl()) ||
                       (localStorage.getItem('adt_center_url')) || 'http://localhost:5001';

  function paint(state) {
    const dot = document.getElementById('agy-auth-dot');
    const label = document.getElementById('agy-auth-label');
    const badge = document.getElementById('agy-auth-badge');
    if (!dot || !label || !badge) return;
    if (state && state.ok) {
      dot.style.background = '#2e7d32';
      _renderAuthBrokenBanner(state); label.textContent = state.identity ? `agy: ${state.identity}` : 'agy: authed';
      badge.style.borderColor = '#2e7d32';
      badge.title = `agy authenticated. Last check: ${new Date(state.last_check_at * 1000).toLocaleTimeString()}. Click to re-login.`;
    } else {
      dot.style.background = '#c62828';
      label.textContent = 'agy: not authed';
      badge.style.borderColor = '#c62828';
      _renderAuthBrokenBanner(state); badge.title = `agy not authed${state && state.error ? ': ' + state.error : ''}. Click to log in.`;
    }
  }

  async function poll(force) {
    try {
      const url = `${CENTER()}/api/agy/state${force ? '?force=1' : ''}`;
      const r = await fetch(url);
      if (r.ok) paint(await r.json());
    } catch(_) {}
  }

  function openLoginModal() {
    // Reuse the wizard modal styles if possible
    let backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:1099';
    let modal = document.createElement('div');
    modal.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#0d1117;border:2px solid #6B7FD7;border-radius:12px;padding:30px;width:520px;max-height:88vh;overflow-y:auto;z-index:1100;color:#e6edf3;box-shadow:0 20px 50px rgba(0,0,0,0.8)';
    modal.innerHTML = `
      <h2 style="margin-top:0;color:#6B7FD7;text-align:center">agy Authentication</h2>
      <p style="color:#8b949e">When agy tokens expire or the keyring loses session, all subprocess agy spawns fail silently (you've seen the OAuth tabs the workers can't auth from).</p>
      <p style="color:#8b949e">Click <strong>Open Login Terminal</strong> below to spawn an agy session inside the Console. agy will print an OAuth URL, your browser opens, you complete login, you paste the code back — then close that PTY tab. All future agy spawns will use the refreshed keyring tokens.</p>
      <div style="margin-top:18px;padding:10px;border:1px solid #30363d;border-radius:6px;background:#161b22;font-size:12px">
        <strong>Status:</strong> <span id="agy-login-current-state">(loading…)</span>
      </div>
      <div style="margin-top:20px;display:flex;gap:8px;justify-content:flex-end">
        <button id="agy-login-recheck" style="padding:8px 16px;background:#21262d;border:1px solid #30363d;color:#e6e6e6;border-radius:6px;cursor:pointer">Recheck (no login)</button>
        <button id="agy-login-open-pty" style="padding:8px 16px;background:#1f6feb;border:none;color:#fff;border-radius:6px;cursor:pointer">Open Login Terminal</button>
        <button id="agy-login-close" style="padding:8px 16px;background:#21262d;border:1px solid #30363d;color:#e6e6e6;border-radius:6px;cursor:pointer">Close</button>
      </div>
    `;
    document.body.appendChild(backdrop);
    document.body.appendChild(modal);
    const teardown = () => { backdrop.remove(); modal.remove(); };
    backdrop.onclick = teardown;
    document.getElementById('agy-login-close').onclick = teardown;
    // Show current state in modal
    fetch(`${CENTER()}/api/agy/state?force=1`).then(r => r.ok ? r.json() : null).then(s => {
      const el = document.getElementById('agy-login-current-state');
      if (!el) return;
      if (s && s.ok) {
        el.innerHTML = `<span style="color:#2e7d32">✓ authenticated</span>${s.identity ? ' as ' + s.identity : ''}`;
      } else {
        el.innerHTML = `<span style="color:#c62828">✗ not authenticated</span>${s && s.error ? '<br><small>' + s.error + '</small>' : ''}`;
      }
    });
    document.getElementById('agy-login-recheck').onclick = async () => {
      const btn = document.getElementById('agy-login-recheck');
      btn.disabled = true; btn.textContent = "Checking…";
      try {
        const r = await fetch(`${CENTER()}/api/agy/state?force=1`);
        const s = r.ok ? await r.json() : null;
        paint(s);
        if (s && s.ok) {
          alert(`agy is authenticated.${s.identity ? ' (' + s.identity + ')' : ''}`);
          teardown();
          return;
        } else {
          alert(`Still not authenticated.\n${s && s.error ? s.error : ''}\n\nTry "Open Login Terminal" and complete OAuth in your browser.`);
        }
      } catch(e) { alert('Recheck failed: ' + e.message); }
      btn.disabled = false; btn.textContent = "Recheck (no login)";
    };
    document.getElementById('agy-login-open-pty').onclick = () => {
      // Spawn a new agy interactive session via the existing SessionManager
      if (window.SessionManager && typeof window.SessionManager.newSession === "function") {
        try {
          window.SessionManager.newSession({ agent: "agy", role: "Architect", interactive: true });
          teardown();
          // Re-poll auth status every 10s while the user is logging in
          let attempts = 0;
          const iv = setInterval(async () => {
            attempts += 1;
            await poll(true);
            const dot = document.getElementById('agy-auth-dot');
            if (dot && dot.style.background.includes('46, 125, 50')) { // matched #2e7d32
              clearInterval(iv);
              return;
            }
            if (attempts >= 30) clearInterval(iv); // 5 min cap
          }, 10000);
        } catch(e) {
          alert("Couldn't open Login Terminal automatically.\n\nManual: open a system terminal, run `agy`, complete OAuth, then click Recheck.");
        }
      } else {
        alert("Console session manager unavailable.\n\nManual login: open a system terminal, run `agy`, complete the OAuth flow in your browser, then click Recheck.");
      }
    };
  }

  function init() {
    const badge = document.getElementById('agy-auth-badge');
    if (badge && !badge.dataset.bound) {
      badge.dataset.bound = "true";
      badge.addEventListener('click', openLoginModal);
    }
    poll(false);
    setInterval(() => poll(false), POLL_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();


// SPEC-062-H: when auth is broken, show a persistent banner with a
let _authBrokenFailCount = 0;
function _renderAuthBrokenBanner(state) {
  let banner = document.getElementById('auth-broken-banner');
  if (!state || state.ok) {
    _authBrokenFailCount = 0;
    if (banner) banner.remove();
    return;
  }
  _authBrokenFailCount++;
  if (_authBrokenFailCount < 2 && !banner) return;
  if (banner) return;

  // REQ-104 fix (SPEC-071 follow-up): banner sits ABOVE the topbar as a normal
  // block element so it never covers the Projects / Spec Map / Governance /
  // ADT Panel buttons. Previously position:fixed;top:0 overlaid the topbar.
  banner = document.createElement('div');
  banner.id = 'auth-broken-banner';
  banner.style.cssText = 'position:relative;z-index:9997;'
    + 'background:linear-gradient(90deg,#c62828,#ff5555,#c62828);'
    + 'color:#fff;text-align:center;padding:6px 16px;font-weight:700;font-size:13px;'
    + 'box-shadow:0 2px 12px rgba(198,40,40,0.6);'
    + 'animation:auth-broken-pulse 2s infinite;'
    + 'display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap;';
  banner.innerHTML = '<span>⚠ agy auth broken — builds will fail.</span>'
    + '<button id="auth-broken-recheck" style="background:#fff;color:#c62828;border:none;'
    + 'padding:3px 10px;border-radius:4px;font-weight:800;cursor:pointer">Recheck</button>'
    + '<button id="auth-broken-launch" style="background:rgba(0,0,0,0.25);color:#fff;border:1px solid rgba(255,255,255,0.4);'
    + 'padding:3px 10px;border-radius:4px;font-weight:700;cursor:pointer">Open Login Terminal</button>';
  // Insert BEFORE the topbar so it pushes everything down naturally.
  document.body.insertBefore(banner, document.body.firstChild);
  const style = document.createElement('style');
  style.textContent = '@keyframes auth-broken-pulse{0%,100%{opacity:1}50%{opacity:0.88}}';
  document.head.appendChild(style);

  // Recheck: force probe — clears banner immediately if auth is already OK (e.g. user just authenticated externally)
  const recheckBtn = document.getElementById('auth-broken-recheck');
  if (recheckBtn) recheckBtn.addEventListener('click', async () => {
    recheckBtn.disabled = true; recheckBtn.textContent = 'Checking…';
    try {
      const r = await fetch(`${CENTER()}/api/agy/state?force=1`);
      const s = r.ok ? await r.json() : null;
      if (s) paint(s);
      if (s && s.ok) {
        // Auth is fine — banner already removed by paint()
        if (window.ToastManager) window.ToastManager.show('info', '✓ agy authed', 'Authentication confirmed — banner cleared.');
      } else {
        recheckBtn.disabled = false; recheckBtn.textContent = 'Recheck';
        if (window.ToastManager) window.ToastManager.show('denial', 'Still not authed', (s && s.error) || 'Run `agy` in a terminal to authenticate.');
      }
    } catch (e) {
      recheckBtn.disabled = false; recheckBtn.textContent = 'Recheck';
    }
  });

  const launchBtn = document.getElementById('auth-broken-launch');
  if (launchBtn) launchBtn.addEventListener('click', async () => {
    launchBtn.disabled = true; launchBtn.textContent = 'Launching…';
    try {
      const r = await fetch(`${CENTER()}/api/agy/reauth_launch`, { method: 'POST' });
      const d = await r.json().catch(() => ({}));
      if (r.ok) {
        launchBtn.textContent = 'Terminal launched — complete OAuth there';
        if (window.ToastManager) window.ToastManager.show('info',
          '🖥 agy terminal launched',
          'Complete OAuth in the new terminal window. Banner auto-hides once auth resolves.');
      } else {
        launchBtn.disabled = false; launchBtn.textContent = 'Open Login Terminal';
        if (window.ToastManager) window.ToastManager.show('denial',
          'Launch failed', d.error || 'no terminal available');
      }
    } catch (e) {
      launchBtn.disabled = false; launchBtn.textContent = 'Open Login Terminal';
    }
  });
}
