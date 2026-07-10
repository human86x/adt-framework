// adt-console/src/js/mirror_monitor.js
window.MirrorMonitor = {
  panel: null,
  pollTimer: null,
  eventTimer: null,
  noContentCount: 0,
  eventSince: 0,
  state: {
    peer_id: null,
    session_id: null,
    collector_url: null,  // OUR local adt_center — what we poll for frames
    peer_url: null,        // Paul's adt_center URL — for event log proxy
    peer_project: 'adt-framework',
    minimized: false,
    x: null,
    y: null
  },
  statusData: {
    polling: false,
    frames_shown: 0,
    last_frame_age_ms: null
  },

  init() {
    if (this.panel) return;

    try {
      const saved = localStorage.getItem('adt_mirror_monitor_state');
      if (saved) {
        const s = JSON.parse(saved);
        if (s.x !== undefined) this.state.x = s.x;
        if (s.y !== undefined) this.state.y = s.y;
        if (s.minimized !== undefined) this.state.minimized = s.minimized;
      }
    } catch(e){}

    const div = document.createElement('div');
    div.id = 'mirror-monitor-panel';
    div.style.cssText = 'position:fixed;z-index:9999;width:340px;background:#1e1e1e;border:2px solid var(--accent-amber,#ffc107);border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,0.5);display:none;overflow:hidden;';

    if (this.state.x !== null && this.state.y !== null) {
      div.style.left = this.state.x + 'px';
      div.style.top = this.state.y + 'px';
    } else {
      div.style.right = '20px';
      div.style.top = '60px';
    }

    div.innerHTML = `
      <div class="mm-header" style="background:#333;padding:4px 8px;cursor:move;display:flex;justify-content:space-between;align-items:center;user-select:none;">
        <div style="font-size:12px;font-weight:bold;color:#ddd;"><span style="margin-right:4px;">🔎</span>Peer: <span id="mm-peer-id">--</span></div>
        <div style="display:flex;gap:6px;">
          <button id="mm-btn-expand" style="background:none;border:none;color:#ccc;cursor:pointer;font-size:12px;" title="expand">⤢</button>
          <button id="mm-btn-minimize" style="background:none;border:none;color:#ccc;cursor:pointer;font-size:12px;" title="minimize">–</button>
          <button id="mm-btn-close" style="background:none;border:none;color:#ccc;cursor:pointer;font-size:12px;" title="close">×</button>
        </div>
      </div>
      <div id="mm-content" style="${this.state.minimized ? 'display:none;' : ''}">
        <div style="width:100%;height:185px;background:#000;position:relative;">
          <img id="mm-image" style="width:100%;height:100%;object-fit:contain;display:none;" />
          <div id="mm-overlay" style="position:absolute;top:0;left:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#888;font-size:12px;text-align:center;padding:10px;">Waiting for peer screen...</div>
        </div>
        <div id="mm-status-strip" style="height:14px;background:#222;font-size:9px;color:#aaa;line-height:14px;padding:0 4px;display:flex;justify-content:space-between;">
          <span id="mm-capture-status">capture: --</span>
          <span>Frame age: <span id="mm-frame-age">--</span></span>
        </div>
        <div style="background:#1a1a2e;border-top:1px solid #333;">
          <div style="font-size:10px;font-weight:bold;color:#8b949e;padding:3px 6px;border-bottom:1px solid #333;display:flex;justify-content:space-between;align-items:center;">
            <span>📋 Peer Events</span>
            <span id="mm-event-status" style="font-size:9px;color:#555;">connecting...</span>
          </div>
          <div id="mm-events-log" style="height:140px;overflow-y:auto;font-size:9px;font-family:monospace;color:#b0b0b0;padding:2px 4px;line-height:1.4;"></div>
        </div>
      </div>
    `;

    document.body.appendChild(div);
    this.panel = div;
    if (this.state.peer_id) {
      div.querySelector('#mm-peer-id').textContent = this.state.peer_id;
    }

    div.querySelector('#mm-btn-expand').onclick = () => this.expand();
    div.querySelector('#mm-btn-minimize').onclick = () => this.minimize();
    div.querySelector('#mm-btn-close').onclick = () => this.hide();

    const header = div.querySelector('.mm-header');
    let isDragging = false, startX, startY, initialX, initialY;
    header.onmousedown = (e) => {
      if (e.target.tagName === 'BUTTON') return;
      isDragging = true;
      startX = e.clientX; startY = e.clientY;
      const rect = div.getBoundingClientRect();
      initialX = rect.left; initialY = rect.top;
      div.style.right = 'auto';
    };
    window.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      div.style.left = (initialX + e.clientX - startX) + 'px';
      div.style.top  = (initialY + e.clientY - startY) + 'px';
    });
    window.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        this.state.x = parseInt(div.style.left);
        this.state.y = parseInt(div.style.top);
        this.saveState();
      }
    });
  },

  saveState() {
    localStorage.setItem('adt_mirror_monitor_state', JSON.stringify({
      minimized: this.state.minimized,
      x: this.state.x,
      y: this.state.y,
    }));
  },

  setPeer({peer_id, session_id, collector_url, peer_url, peer_project}) {
    this.state.peer_id      = peer_id;
    this.state.session_id   = session_id;
    this.state.collector_url = collector_url;
    if (peer_url)     this.state.peer_url     = peer_url;
    if (peer_project) this.state.peer_project = peer_project;
    this.eventSince = 0;
    if (this.panel) {
      this.panel.querySelector('#mm-peer-id').textContent = peer_id || 'unknown';
    }
  },

  show() {
    this.init();
    if (this.panel) this.panel.style.display = 'block';
    this.statusData.polling = true;
    this.noContentCount = 0;
    this.poll();
    this.pollEvents();
  },

  hide() {
    if (this.panel) this.panel.style.display = 'none';
    this.statusData.polling = false;
    clearTimeout(this.pollTimer);
    clearTimeout(this.eventTimer);
  },

  minimize() {
    this.state.minimized = true;
    if (this.panel) this.panel.querySelector('#mm-content').style.display = 'none';
    this.saveState();
  },

  expand() {
    this.state.minimized = false;
    if (this.panel) this.panel.querySelector('#mm-content').style.display = 'block';
    this.saveState();
  },

  status() { return this.statusData; },

  _centerUrl() {
    return (this.state.collector_url || '').replace(/\/$/, '') || 'http://localhost:5001';
  },

  async poll() {
    if (!this.statusData.polling) return;

    if (this.state.peer_id && this.state.session_id) {
      try {
        // Use absolute URL — relative paths don't resolve in Tauri webview
        const base = this._centerUrl();
        const url = `${base}/api/mirror/frame/latest?peer_id=${encodeURIComponent(this.state.peer_id)}&session_id=${encodeURIComponent(this.state.session_id)}&_t=${Date.now()}`;
        const res = await fetch(url);

        if (res.status === 200) {
          this.noContentCount = 0;
          const blob = await res.blob();
          const imgUrl = URL.createObjectURL(blob);
          const imgEl = this.panel.querySelector('#mm-image');
          const overlayEl = this.panel.querySelector('#mm-overlay');
          const ageEl = this.panel.querySelector('#mm-frame-age');
          const stripEl = this.panel.querySelector('#mm-status-strip');

          if (imgEl.src) URL.revokeObjectURL(imgEl.src);
          imgEl.src = imgUrl;
          imgEl.style.display = 'block';
          overlayEl.style.display = 'none';
          this.statusData.frames_shown++;

          const ageMs = res.headers.get('X-Frame-Age-Ms');
          const ts = res.headers.get('X-Frame-Ts');
          let ageS = ageMs ? parseInt(ageMs) / 1000 : (ts ? (Date.now() - parseFloat(ts) * 1000) / 1000 : null);

          if (ageS !== null) {
            ageEl.textContent = ageS.toFixed(1) + ' s';
            this.statusData.last_frame_age_ms = ageS * 1000;
            stripEl.style.color = ageS < 3 ? '#4caf50' : ageS < 10 ? '#ffeb3b' : '#f44336';
          } else {
            ageEl.textContent = 'unknown';
          }

        } else if (res.status === 204) {
          this.noContentCount++;
          if (this.noContentCount >= 15) {
            const imgEl = this.panel.querySelector('#mm-image');
            const overlayEl = this.panel.querySelector('#mm-overlay');
            imgEl.style.display = 'none';
            overlayEl.style.display = 'flex';
            overlayEl.textContent = 'No frames received — is capture running on peer?';
            this.statusData.polling = false;
            return;
          }
        }
      } catch (err) {
        console.error('MirrorMonitor poll error:', err);
      }
    }

    this.pollTimer = setTimeout(() => this.poll(), 2000);
  },

  async pollEvents() {
    if (!this.panel) return;
    const evLog = this.panel.querySelector('#mm-events-log');
    const statusEl = this.panel.querySelector('#mm-event-status');
    if (!evLog) return;

    const peerUrl  = this.state.peer_url;
    const projName = this.state.peer_project || 'adt-framework';
    const base     = this._centerUrl();

    if (!peerUrl) {
      if (statusEl) statusEl.textContent = 'no peer URL';
      this.eventTimer = setTimeout(() => this.pollEvents(), 5000);
      return;
    }

    try {
      // Proxy through our adt_center to bypass Tauri CSP
      const remoteEvUrl = `${peerUrl}/api/ads/events?limit=30&offset=0`;
      const proxyUrl = `${base}/api/mirror/peer_proxy?url=${encodeURIComponent(remoteEvUrl)}`;
      const r = await fetch(proxyUrl);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const events = await r.json();
      if (statusEl) statusEl.textContent = `${events.length} events`;

      if (Array.isArray(events) && events.length) {
        const frag = events.slice(-25).map(ev => {
          const ts    = (ev.ts || '').substring(11, 19);
          const agent = (ev.agent || ev.role || '?').substring(0, 12);
          const atype = (ev.action_type || '?').substring(0, 22);
          const color = ev.escalation ? '#ff5555' : ev.authorized === false ? '#ffaa00' : '#7bd88f';
          return `<div style="border-bottom:1px solid #222;padding:1px 0;"><span style="color:#555;">${ts}</span> <span style="color:#58a6ff;">${agent}</span> <span style="color:${color};">${atype}</span></div>`;
        }).join('');
        evLog.innerHTML = frag;
        evLog.scrollTop = evLog.scrollHeight;
      }
    } catch (e) {
      if (statusEl) statusEl.textContent = 'error: ' + e.message.substring(0, 30);
    }

    this.eventTimer = setTimeout(() => this.pollEvents(), 3000);
  },
};
