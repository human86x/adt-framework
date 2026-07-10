// SPEC-069 (extension): Mirror Mode — echoes every operator action from this
// console to a peer console (Paul's machine) so what I do lands there too.
//
//  - Toggle via topbar 🔁 button OR MirrorMode.toggle()
//  - Peer URL / peer home / peer user are configured via a small prompt on
//    first enable, then persisted to localStorage.
//  - Text inputs are debounced (300ms) and mirrored with path translation
//    (my home → peer home, my user → peer user) so typed paths remain valid
//    on the peer file system.
//  - Every mirrored action fires a matching remote command; remote.js on the
//    peer side executes + highlights it, so Paul sees exactly what's being
//    pressed as it happens.
(function () {
  const STORAGE_KEY = 'adt_mirror_config';
  const STATE_KEY = 'adt_mirror_active';
  const DEBOUNCE_MS = 300;
  const inputDebounces = new Map();

  function loadConfig() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch { return {}; }
  }
  function saveConfig(c) { localStorage.setItem(STORAGE_KEY, JSON.stringify(c)); }
  function loadActive() { return localStorage.getItem(STATE_KEY) === '1'; }
  function saveActive(v) { localStorage.setItem(STATE_KEY, v ? '1' : '0'); }

  const cfg = Object.assign({
    peer_url: '',              // e.g. http://100.78.107.46:5001
    peer_home: '/home/pauls',  // peer OS home
    peer_user: 'pauls',        // peer OS user
    my_home: '/home/human',    // my OS home for reverse-translation
    my_user: 'human',
    my_external_url: '',       // MY adt_center URL as seen from peer (e.g. http://100.x.x.x:5001)
    project: '*',              // peer project (or '*' for whatever they've open)
    peer_project: 'adt-framework', // peer's project name for event log
    session_id: '*',           // peer session (or '*')
  }, loadConfig());

  let ACTIVE = loadActive();
  let heartbeatTimer = null;

  function startHeartbeat() {
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    heartbeatTimer = setInterval(() => {
      if (ACTIVE) send('mirror_heartbeat', 'peer', {
        from: cfg.my_user || 'operator',
        ts: Date.now(),
      });
    }, 15000);
    // Fire one immediately when turning on
    if (ACTIVE) send('mirror_heartbeat', 'peer', { from: cfg.my_user || 'operator', ts: Date.now() });
  }
  function stopHeartbeat() {
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
    // One-shot "off" ping
    send('mirror_off', 'peer', {});
  }

  // Text transform on outgoing text: swap my paths/user for peer paths/user.
  function translate(text) {
    if (typeof text !== 'string' || !text) return text;
    let out = text;
    if (cfg.my_home && cfg.peer_home) {
      out = out.split(cfg.my_home).join(cfg.peer_home);
    }
    // Only translate user when it appears alone (not e.g. "humanoid").
    if (cfg.my_user && cfg.peer_user) {
      out = out.replace(new RegExp(`\\b${cfg.my_user}\\b`, 'g'), cfg.peer_user);
    }
    return out;
  }

  // Per-command state: cmd_id -> {el, ts, kind, timeoutId}
  const _pendingAcks = new Map();
  let _ackSince = 0;
  let _ackPoll = null;
  let _cmdCounter = 0;

  function _myAckUrl() {
    // Ack URL points back at MY adt_center — the peer POSTs to it after
    // executing the mirrored command. Uses same origin as centerUrl().
    return (window.SpecMap && window.SpecMap.getCenterUrl)
      ? (window.SpecMap.getCenterUrl().replace(/\/$/,'') + '/api/mirror/ack')
      : 'http://localhost:5001/api/mirror/ack';
  }

  function _makeCmdId() {
    _cmdCounter += 1;
    return (cfg.my_user || 'op') + '_' + Date.now() + '_' + _cmdCounter;
  }

  // Highlight my source element with a status badge:
  //   'sent'    yellow → pending peer ack
  //   'ok'      green  → peer executed successfully
  //   'fail'    red    → peer reported failure
  //   'timeout' orange → no ack in 5s
  function _paintSource(el, kind, label) {
    if (!el) return;
    const colors = { sent: '#f0d000', ok: '#7bd88f', fail: '#ff5555', timeout: '#ff9900' };
    const color = colors[kind] || '#8b949e';
    el.style.transition = 'box-shadow 0.15s ease';
    el.style.boxShadow = `0 0 0 3px ${color}, 0 0 16px ${color}`;
    // Floating tag
    const existing = el._mirrorTag;
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
    const tag = document.createElement('div');
    tag.textContent = label;
    tag.style.cssText = `position:fixed;background:${color};color:#000;font-weight:700;font-size:10px;padding:2px 6px;border-radius:3px;z-index:99999;pointer-events:none;box-shadow:0 2px 6px rgba(0,0,0,0.5)`;
    const rect = el.getBoundingClientRect();
    tag.style.top = (rect.bottom + 4) + 'px';
    tag.style.left = rect.left + 'px';
    document.body.appendChild(tag);
    el._mirrorTag = tag;
    if (kind === 'ok' || kind === 'fail' || kind === 'timeout') {
      // Fade the highlight after 1.5s
      setTimeout(() => {
        el.style.boxShadow = '';
        if (tag.parentNode) tag.parentNode.removeChild(tag);
      }, 1800);
    }
  }

  async function _pollAcks() {
    if (!ACTIVE) return;
    try {
      const url = (window.SpecMap && window.SpecMap.getCenterUrl)
        ? window.SpecMap.getCenterUrl().replace(/\/$/,'') + `/api/mirror/acks?since=${_ackSince}`
        : `http://localhost:5001/api/mirror/acks?since=${_ackSince}`;
      const r = await fetch(url);
      if (!r.ok) return;
      const d = await r.json();
      _ackSince = d.highest_seq || _ackSince;
      for (const ack of (d.acks || [])) {
        const p = _pendingAcks.get(ack.cmd_id);
        if (!p) continue;
        if (p.timeoutId) clearTimeout(p.timeoutId);
        const ok = /^ok\b/.test(String(ack.outcome || ''));
        _paintSource(p.el, ok ? 'ok' : 'fail', ok ? `✓ ${p.command} @ peer` : `✗ ${ack.outcome || 'no_target'}`);
        _pendingAcks.delete(ack.cmd_id);
      }
    } catch (e) { /* swallow */ }
  }

  function _startAckPoll() {
    if (_ackPoll) return;
    _ackPoll = setInterval(_pollAcks, 500);
  }
  function _stopAckPoll() {
    if (_ackPoll) { clearInterval(_ackPoll); _ackPoll = null; }
  }

  async function send(command, target, params, sourceEl) {
    if (!cfg.peer_url) return;
    if (!ACTIVE && command !== 'mirror_off' && command !== 'mirror_capture_stop') return;
    // Skip tracking for background pings
    const isHeartbeat = command === 'mirror_heartbeat' || command === 'mirror_off';
    const cmd_id = isHeartbeat ? null : _makeCmdId();
    const payload = {
      project: cfg.project || '*',
      session_id: cfg.session_id || '*',
      command,
      target,
      params: Object.assign({}, params || {}, cmd_id ? { cmd_id, ack_url: _myAckUrl() } : {}),
      from_operator: 'mirror:' + (cfg.my_user || 'unknown'),
    };
    if (cmd_id && sourceEl) {
      _paintSource(sourceEl, 'sent', '→ mirroring');
      const timeoutId = setTimeout(() => {
        if (_pendingAcks.has(cmd_id)) {
          _paintSource(sourceEl, 'timeout', '⚠ no ack from peer');
          _pendingAcks.delete(cmd_id);
        }
      }, 5000);
      _pendingAcks.set(cmd_id, { el: sourceEl, ts: Date.now(), command, timeoutId });
    }
    try {
      await fetch(`${cfg.peer_url}/api/remote/commands`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true,
      });
    } catch (e) { /* swallow */ }
  }

  // Map a click target to a remote command. Reuses the same classifier idea
  // as telemetry.js but produces command NAMES that remote.js can execute.
  function commandForClick(el) {
    if (!el) return null;
    let cur = el;
    while (cur && cur !== document.body) {
      const id = cur.id || '';
      if (id === 'btn-projects')     return { command: 'open_projects', target: id };
      if (id === 'btn-spec-map')     return { command: 'open_spec_map', target: id };
      if (id === 'btn-governance')   return { command: 'open_governance', target: id };
      if (id === 'btn-adt-panel')    return { command: 'open_adt_panel', target: id };
      if (id === 'btn-dashboard')    return { command: 'open_dashboard', target: id };
      if (id === 'btn-new-session' || id === 'btn-new-session-sidebar') return { command: 'new_session', target: id };
      if (id === 'btn-split')        return { command: 'toggle_split', target: id };
      if (id === 'sm-intents-badge') return { command: 'open_intents', target: id };
      if (id === 'sm-btn-cci')       return { command: 'open_change_request', target: id };
      if (id === 'sm-btn-launch')    return { command: 'launch_app', target: id };
      if (id === 'sm-btn-approve')   return { command: 'sm_approve', target: id };
      if (id === 'sm-btn-build')     return { command: 'sm_build', target: id };
      if (id === 'sm-btn-stop')      return { command: 'sm_stop', target: id };
      // Generic click via id if the element has one
      if (cur.tagName === 'BUTTON' && id) return { command: 'click', target: id };
      // Wizard next/back
      if (id === 'btn-wiz-next')    return { command: 'click', target: id };
      if (id === 'btn-wiz-back')    return { command: 'click', target: id };
      if (id === 'btn-wiz-forge')   return { command: 'click', target: id };
      cur = cur.parentElement;
    }
    return null;
  }

  // Global click mirror
  document.addEventListener('click', (e) => {
    if (!ACTIVE) return;
    const c = commandForClick(e.target);
    if (c) send(c.command, c.target, null, e.target.closest('button') || e.target);
  }, true);

  // Input mirror — debounced, only for elements with an id
  function mirrorInput(el) {
    if (!ACTIVE || !el || !el.id) return;
    const prev = inputDebounces.get(el.id);
    if (prev) clearTimeout(prev);
    inputDebounces.set(el.id, setTimeout(() => {
      inputDebounces.delete(el.id);
      const tag = el.tagName;
      if (tag === 'INPUT') {
        if (el.type === 'checkbox' || el.type === 'radio') {
          send('set_checked', el.id, { checked: !!el.checked }, el);
        } else {
          send('set_input', el.id, { value: translate(el.value) }, el);
        }
      } else if (tag === 'TEXTAREA') {
        send('set_input', el.id, { value: translate(el.value) }, el);
      } else if (tag === 'SELECT') {
        send('set_select', el.id, { value: translate(el.value) }, el);
      }
    }, DEBOUNCE_MS));
  }
  document.addEventListener('input', (e) => mirrorInput(e.target), true);
  document.addEventListener('change', (e) => {
    const el = e.target;
    if (el && el.tagName === 'SELECT') mirrorInput(el);
    else if (el && (el.type === 'checkbox' || el.type === 'radio')) mirrorInput(el);
  }, true);

  // UI: toggle button in topbar, tooltip shows peer url
  function updateBadge() {
    const b = document.getElementById('btn-mirror');
    if (!b) return;
    b.style.background = ACTIVE ? '#238636' : '#21262d';
    b.style.color = ACTIVE ? '#fff' : '#c9d1d9';
    b.title = ACTIVE
      ? `Mirror ON → ${cfg.peer_url || '(no peer!)'}  (user=${cfg.peer_user}, home=${cfg.peer_home})`
      : 'Mirror OFF (click to enable — echoes your clicks + inputs to peer console)';
    b.textContent = ACTIVE ? '🔁 ON' : '🔁';
  }

  function configureFlow() {
    const url = prompt('Peer adt_center URL (e.g. http://100.78.107.46:5001)', cfg.peer_url || 'http://100.78.107.46:5001');
    if (!url) return false;
    const home = prompt('Peer HOME (e.g. /home/pauls)', cfg.peer_home || '/home/pauls');
    if (!home) return false;
    const user = prompt('Peer user (e.g. pauls)', cfg.peer_user || 'pauls');
    if (!user) return false;
    const myExt = prompt('YOUR adt_center URL as seen from peer (Tailscale IP, e.g. http://100.x.x.x:5001)\nLeave blank to auto-detect (may not work behind NAT)', cfg.my_external_url || '') || '';
    const project = prompt("Peer project name (or '*' for whatever they open)", cfg.project || '*') || '*';
    cfg.peer_url = url.replace(/\/$/,'');
    cfg.peer_home = home.replace(/\/$/,'');
    cfg.peer_user = user;
    cfg.my_external_url = myExt.replace(/\/$/,'');
    cfg.project = project;
    saveConfig(cfg);
    return true;
  }

  window.MirrorMode = {
    toggle() {
      if (!ACTIVE && !cfg.peer_url) {
        if (!configureFlow()) return;
      }
      ACTIVE = !ACTIVE;
      saveActive(ACTIVE);
      updateBadge();
      if (ACTIVE) {
        startHeartbeat(); _startAckPoll();
        const localUrl = (window.SpecMap && window.SpecMap.getCenterUrl) ? window.SpecMap.getCenterUrl().replace(/\/$/,'') : 'http://localhost:5001';
        // collectorUrl is where Paul's capture service sends frames TO — must be reachable from Paul's machine
        const collectorUrl = cfg.my_external_url || localUrl;
        send('mirror_capture_start', 'peer', { collector_url: collectorUrl, peer_id: cfg.peer_user, session_id: cfg.session_id || '*' });
        if (window.MirrorMonitor) {
          window.MirrorMonitor.setPeer({
            peer_id: cfg.peer_user,
            session_id: cfg.session_id || '*',
            collector_url: localUrl,  // OUR local server — what the monitor polls for frames
            peer_url: cfg.peer_url,   // Paul's adt_center — for event log proxy
            peer_project: cfg.peer_project || 'adt-framework',
          });
          window.MirrorMonitor.show();
        }
      } else { 
        send('mirror_capture_stop', 'peer', {});
        stopHeartbeat(); _stopAckPoll(); 
        if (window.MirrorMonitor) window.MirrorMonitor.hide();
      }
      if (window.ToastManager) window.ToastManager.show(ACTIVE ? 'info' : 'denial',
        ACTIVE ? '🔁 Mirror ON' : '🔁 Mirror OFF',
        ACTIVE ? `Echoing to ${cfg.peer_url}` : 'Local only');
    },
    configure() { configureFlow(); updateBadge(); },
    status() { return { active: ACTIVE, config: cfg }; },
    setPeer(newCfg) { Object.assign(cfg, newCfg); saveConfig(cfg); updateBadge(); },
  };

  document.addEventListener('DOMContentLoaded', () => {
    updateBadge();
    const b = document.getElementById('btn-mirror');
    if (b) {
      b.addEventListener('click', (e) => {
        if (e.shiftKey) window.MirrorMode.configure();
        else window.MirrorMode.toggle();
      });
    }
  });
})();
