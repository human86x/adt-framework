// Application controller — initialization, keyboard shortcuts, toasts
// SPEC-021: Main entry point for ADT Operator Console frontend

console.log("ADT Console app.js loaded v2");

// --- Toast Notification Manager ---
const ToastManager = (() => {
  const ICONS = {
    denial: '\u26D4',
    escalation: '\u26A0',
    completion: '\u2705',
    info: '\u2139',
  };

  function show(type, title, message, duration) {
    duration = duration || 5000;
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <span class="toast-icon">${ICONS[type] || ''}</span>
      <div class="toast-body">
        <div class="toast-title">${title}</div>
        <div class="toast-message">${message}</div>
      </div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('toast-exit');
      setTimeout(() => toast.remove(), 200);
    }, duration);
  }

  return { show };
})();

// --- Native Notification Bridge ---
const NativeNotify = (() => {
  async function send(title, body) {
    if (!window.__TAURI__) return;
    try {
      await window.__TAURI__.core.invoke('send_notification', {
        request: { title, body },
      });
    } catch (e) {
      console.warn('Native notification failed:', e);
    }
  }

  return { send };
})();

// --- Tray Status Bridge ---
const TrayBridge = (() => {
  async function updateStatus(status, sessionCount, escalations) {
    if (!window.__TAURI__) return;
    try {
      await window.__TAURI__.core.invoke('update_tray_status', {
        request: {
          status: status,
          sessionCount: sessionCount,
          escalations: escalations,
        },
      });
    } catch (e) {
      console.warn('Tray status update failed:', e);
    }
  }

  // Compute tray status from current state
  function refresh() {
    const sessions = SessionManager.getAll();
    const count = sessions.length;

    // Read escalation count from status bar
    const escText = document.getElementById('status-escalations')?.textContent || '';
    const escMatch = escText.match(/(\d+)/);
    const escalations = escMatch ? parseInt(escMatch[1]) : 0;

    let status = 'idle';
    if (count > 0) {
      if (escalations > 0) {
        status = 'warning';
      } else {
        status = 'nominal';
      }
    }

    updateStatus(status, count, escalations);
  }

  return { updateStatus, refresh };
})();


// --- Shatterglass Bridge (SPEC-027) ---
const ShatterglassBridge = (() => {
  let isReady = false;
  let isEnabled = false;

  async function refresh() {
    if (!window.__TAURI__) return;
    try {
      const status = await window.__TAURI__.core.invoke('get_production_mode');
      isReady = status.ready;
      isEnabled = status.enabled;
      updateUI();
    } catch (e) {
      console.warn('Shatterglass status failed:', e);
    }
  }

  function updateUI() {
    const btn = document.getElementById('btn-shatterglass');
    if (!btn) return;

    if (!isReady) {
      btn.classList.add('disabled');
      btn.title = 'Run setup_shatterglass.sh first';
    } else {
      btn.classList.remove('disabled');
      btn.title = isEnabled ? 'Disable Shatterglass' : 'Enable Shatterglass';
      if (isEnabled) {
        btn.classList.add('active');
        document.body.classList.add('production-mode');
      } else {
        btn.classList.remove('active');
        document.body.classList.remove('production-mode');
      }
    }
  }

  async function toggle() {
    if (!isReady) return;
    const action = isEnabled ? 'disable' : 'enable';
    const warning = isEnabled 
      ? "Disable Shatterglass? New agent sessions will have full file access."
      : "Enable Shatterglass? New agent sessions will run with restricted OS permissions. Existing sessions are not affected.";
    
    if (confirm(warning)) {
      try {
        await window.__TAURI__.core.invoke(`${action}_production_mode`);
        await refresh();
        ToastManager.show(isEnabled ? 'info' : 'completion', 'Shatterglass', `Production mode ${isEnabled ? 'enabled' : 'disabled'}`);
      } catch (e) {
        console.error('Failed to toggle shatterglass:', e);
      }
    }
  }

  return { refresh, toggle };
})();


// --- Governance Panel Manager (delegates to GovernancePanel from governance.js) ---
const GovernanceManager = (() => {
  function toggle() {
    if (DashboardManager.isActive()) DashboardManager.toggle();
    if (PanelManager.isActive()) PanelManager.toggle();
    GovernancePanel.toggle();
  }
  function isActive() { return GovernancePanel.isActive(); }
  function deactivate() { if (isActive()) toggle(); }
  return { toggle, isActive, deactivate };
})();

// --- ADT Panel (iframe) Manager ---
const PanelManager = (() => {
  let active = false;
  const getUrl = () => localStorage.getItem('adt_center_url') || 'http://localhost:5001';

  function toggle() {
    active = !active;
    const view = document.getElementById('adt-panel-view');
    const iframe = document.getElementById('adt-panel-iframe');
    const termArea = document.getElementById('terminal-area');

    if (active) {
      if (DashboardManager.isActive()) DashboardManager.toggle();
      if (GovernanceManager.isActive()) GovernanceManager.toggle();

      // Open in native WebviewWindow — bypasses webkit2gtk iframe bug (REQ-085)
      if (window.__TAURI__) {
        try {
          const { WebviewWindow } = window.__TAURI__.webviewWindow;
          new WebviewWindow('adt-panel', { url: getUrl() });
        } catch (e) {
          console.error('[ADT Panel] WebviewWindow failed:', e);
        }
        active = false;
        const panelBtn = document.getElementById('btn-adt-panel');
        if (panelBtn) panelBtn.classList.remove('active');
        return;
      }

      termArea.classList.add('panel-active');
      view.style.display = '';
      if (iframe.src === 'about:blank' || iframe.src === '') {
        iframe.src = getUrl();
      }
    } else {
      termArea.classList.remove('panel-active');
      view.style.display = 'none';
    }

    const btn = document.getElementById('btn-adt-panel');
    if (btn) btn.classList.toggle('active', active);
  }

  return { toggle, isActive: () => active, deactivate: () => { if (active) toggle(); } };
})();

// --- Remote Access Manager (SPEC-024) ---
const RemoteManager = (() => {
  let isSharing = false;
  let publicUrl = null;
  let childProcess = null;

  async function toggle() {
    if (isSharing) {
      await stop();
    } else {
      await start();
    }
  }

  async function start() {
    if (!window.__TAURI__) {
      ToastManager.show('info', 'Remote Access', 'Sharing only available in native console.');
      return;
    }

    const remoteSpan = document.getElementById('status-remote');
    const dot = remoteSpan.querySelector('.status-dot');
    
    dot.className = 'status-dot dot-yellow';
    remoteSpan.querySelector('.remote-label').textContent = 'Connecting...';

    try {
      // Use the shell plugin to run adt connect share
      const { Command } = window.__TAURI__.shell;
      const command = Command.create('python3', ['adt_core/cli.py', 'connect', 'share', '--yes']);
      
      command.on('close', data => {
        console.log(`Tunnel closed with code ${data.code}`);
        cleanup();
      });

      command.on('error', error => {
        console.error(`Tunnel error: ${error}`);
        ToastManager.show('denial', 'Remote Error', error);
        cleanup();
      });

      // Capture stdout for the URL
      command.stdout.on('data', line => {
        const match = line.match(/https:\/\/[a-zA-Z0-9-]+\.trycloudflare\.com/);
        if (match) {
          publicUrl = match[0];
          onConnected(publicUrl);
        }
      });

      childProcess = await command.spawn();
      isSharing = true;
    } catch (err) {
      console.error('Failed to start tunnel:', err);
      ToastManager.show('denial', 'Remote Error', `Could not start tunnel: ${err}`);
      cleanup();
    }
  }

  function onConnected(url) {
    const remoteSpan = document.getElementById('status-remote');
    remoteSpan.querySelector('.status-dot').className = 'status-dot dot-green';
    remoteSpan.querySelector('.remote-label').textContent = 'Live';
    remoteSpan.title = `Remote URL: ${url} (Click to copy)`;
    
    ToastManager.show('completion', 'Remote Access Live', `URL: ${url}`);
    
    // Copy to clipboard
    navigator.clipboard.writeText(url).catch(() => {});
  }

  async function stop() {
    if (childProcess) {
      await childProcess.kill();
    }
    cleanup();
  }

  function cleanup() {
    isSharing = false;
    publicUrl = null;
    childProcess = null;
    
    const remoteSpan = document.getElementById('status-remote');
    if (remoteSpan) {
      remoteSpan.querySelector('.status-dot').className = 'status-dot dot-grey';
      remoteSpan.querySelector('.remote-label').textContent = 'Go Remote';
      remoteSpan.title = 'Go Remote (Secure Tunnel)';
    }
  }

  return { toggle, isSharing, getUrl: () => publicUrl };
})();

// --- Git Status Manager (SPEC-023) ---
const GitStatusManager = (() => {
  const getUrl = () => localStorage.getItem('adt_center_url') || 'http://localhost:5001';
  let intervalId = null;

  async function refresh() {
    try {
      const res = await fetch(`${getUrl()}/api/git/status`);
      if (!res.ok) throw new Error('Failed to fetch git status');
      const data = await res.json();
      
      const dot = document.getElementById('git-dot');
      const branchSpan = document.getElementById('git-branch');
      const changesSpan = document.getElementById('git-changes');
      
      if (branchSpan) branchSpan.textContent = data.branch || '—';
      if (changesSpan) {
        changesSpan.textContent = data.changes > 0 ? `(${data.changes})` : '';
      }
      
      if (dot) {
        dot.className = `status-dot dot-${data.status === 'clean' ? 'green' : 'yellow'}`;
      }
    } catch (err) {
      console.warn('Git status update failed:', err);
      const branchSpan = document.getElementById('git-branch');
      if (branchSpan) branchSpan.textContent = 'Offline';
    }
  }

  function startPolling(ms = 30000) {
    if (intervalId) clearInterval(intervalId);
    refresh();
    intervalId = setInterval(refresh, ms);
  }

  return { refresh, startPolling };
})();

// --- Main Application ---
(function () {
  'use strict';

  // --- Clock ---
  // --- Build Info ---
  async function loadBuildInfo() {
    // Both files are written by src-tauri/build.rs on every release build.
    // Version pulls from tauri.conf.json so the header never drifts from
    // the actual bundled version. Build time is local (with tz offset).
    try {
      const [tRes, vRes] = await Promise.all([
        fetch('build_time.txt'),
        fetch('version.txt')
      ]);
      if (tRes.ok) {
        const t = (await tRes.text()).trim();
        const el = document.getElementById('build-time');
        if (el) el.textContent = '| Build: ' + t;
      }
      if (vRes.ok) {
        const v = (await vRes.text()).trim();
        const el = document.getElementById('brand-version');
        if (el) el.textContent = 'v' + v;
      }
    } catch (e) {
      console.warn('Failed to load build info', e);
    }
  }
  loadBuildInfo();

  // --- Sandbox toggle (SPEC-105) ---
  // Reflects ~/.adt/console_settings.json::dev_mode. Toggle takes effect on
  // the NEXT new session spawn; existing sessions are unaffected.
  async function refreshSandboxTile() {
    const btn = document.getElementById('btn-sandbox-toggle');
    const dot = document.getElementById('sandbox-dot');
    const lbl = document.getElementById('sandbox-label');
    if (!btn || !window.__TAURI__) return;
    try {
      const s = await window.__TAURI__.core.invoke('get_dev_mode');
      const off = !!s.effective_disabled;
      const envOverride = !!s.env_override;
      if (off) {
        btn.style.background = '#5c1e1e';
        btn.style.borderColor = '#c53030';
        btn.style.color = '#f5c8c8';
        dot.style.background = '#f56565';
        lbl.textContent = envOverride ? 'Sandbox: OFF (env)' : 'Sandbox: OFF';
        btn.title = envOverride
          ? 'ADT_DEV_MODE=1 in env — unset it and restart shell to clear.'
          : 'DEV MODE ACTIVE — agents run unsandboxed. Click to re-enable.';
      } else {
        btn.style.background = '#0d5c33';
        btn.style.borderColor = '#2f9e6e';
        btn.style.color = '#c8e6d3';
        dot.style.background = '#3fb984';
        lbl.textContent = 'Sandbox: ON';
        btn.title = 'SPEC-105 sandbox enforced. Click to enter Dev Mode.';
      }
    } catch (e) {
      console.warn('sandbox status probe failed', e);
    }
  }
  async function toggleSandbox() {
    if (!window.__TAURI__) return;
    try {
      const s = await window.__TAURI__.core.invoke('get_dev_mode');
      // ui_set means the file exists with an explicit dev_mode value.
      // dev_mode holds the current UI intent (true=off, false=on).
      // If the operator has never toggled AND env=1, first click PINS
      // the sandbox ON via the UI file (overriding env).
      const currentDev = !!s.dev_mode;
      const nextDev = !currentDev;
      let msg;
      if (!s.ui_set && s.env_set) {
        msg = nextDev
          ? 'Env ADT_DEV_MODE=1 already has sandbox OFF. Toggle ON in UI too? ' +
            '(no-op; sandbox stays off)'
          : 'Env ADT_DEV_MODE=1 has sandbox OFF. Turn sandbox ON now? ' +
            'The UI setting will OVERRIDE the env var. Sandbox will be ' +
            'enforced on the next new session.';
      } else {
        msg = nextDev
          ? 'Turn Dev Mode ON? Next new session will run UNSANDBOXED.'
          : 'Turn Dev Mode OFF? Next new session will be sandboxed (SPEC-105).';
      }
      if (!confirm(msg)) return;
      await window.__TAURI__.core.invoke('set_dev_mode', { request: { devMode: nextDev } });
      await refreshSandboxTile();
    } catch (e) {
      alert('Failed to toggle sandbox: ' + (e && e.message ? e.message : e));
    }
  }
  const sbBtn = document.getElementById('btn-sandbox-toggle');
  if (sbBtn) sbBtn.addEventListener('click', toggleSandbox);
  refreshSandboxTile();
  // Re-probe every 15s in case another Console instance / a shell edit
  // changes the settings file.
  setInterval(refreshSandboxTile, 15000);

  // --- Clock ---
  function updateClock() {
    const now = new Date();
    const clockEl = document.getElementById('status-clock');
    if (clockEl) {
      clockEl.textContent = now.toISOString().substring(11, 19) + ' UTC';
    }
  }
  setInterval(updateClock, 1000);
  updateClock();

  // --- New Session Dialog ---
  const dialog = document.getElementById('new-session-dialog');
  const form = document.getElementById('new-session-form');
  const agentSelect = document.getElementById('input-agent');
  const customGroup = document.getElementById('custom-command-group');

  async function loadSpecs() {
    const specSelect = document.getElementById('input-spec');
    if (!specSelect) return;
    
    try {
      const centerUrl = localStorage.getItem('adt_center_url') || 'http://localhost:5001';
      const project = document.getElementById('input-project')?.value;
      const url = project ? `${centerUrl}/api/specs?project=${encodeURIComponent(project)}` : `${centerUrl}/api/specs`;
      
      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to fetch specs');
      const data = await res.json();
      const specs = data.specs || [];
      
      specSelect.innerHTML = '';
      specs.forEach(spec => {
        const opt = document.createElement('option');
        opt.value = spec.id;
        // Clean title: SPEC-017: ...
        const title = spec.filename.replace('.md', '').replace(/_/g, ' ');
        opt.textContent = title;
        specSelect.appendChild(opt);
      });
      
      // Try to match active spec from context if available
      const activeSpecText = document.getElementById('ctx-spec')?.textContent;
      if (activeSpecText && activeSpecText !== '—') {
        const match = activeSpecText.match(/SPEC-\d{3}/);
        if (match) specSelect.value = match[0];
      }

    } catch (err) {
      console.error('Error loading specs:', err);
      // Minimal fallback
      if (specSelect.innerHTML === '') {
        specSelect.innerHTML = '<option value="SPEC-017">SPEC-017: ADT Framework Repository</option>';
      }
    }
  }

  async function loadRoles() {
    const roleSelect = document.getElementById('input-role');
    if (!roleSelect) return;

    try {
      const centerUrl = localStorage.getItem('adt_center_url') || 'http://localhost:5001';
      const project = document.getElementById('input-project')?.value;
      if (!project) return;

      const res = await fetch(`${centerUrl}/api/governance/roles?project=${encodeURIComponent(project)}`);
      if (!res.ok) throw new Error('Failed to fetch roles');
      const data = await res.json();
      const roles = data.roles || {};
      
      roleSelect.innerHTML = '';
      Object.keys(roles).forEach(roleName => {
        const opt = document.createElement('option');
        opt.value = roleName;
        // Format role name for display: Systems_Architect -> Systems Architect
        opt.textContent = roleName.replace(/_/g, ' ');
        roleSelect.appendChild(opt);
      });
    } catch (err) {
      console.error('Error loading roles:', err);
      // Fallback to hardcoded defaults if API fails
      roleSelect.innerHTML = `
        <option value="Systems_Architect">Systems Architect</option>
        <option value="Backend_Engineer">Backend Engineer</option>
        <option value="Frontend_Engineer">Frontend Engineer</option>
        <option value="DevOps_Engineer">DevOps Engineer</option>
        <option value="Overseer">Overseer</option>
      `;
    }
  }

  async function loadProjects() {
    const projectSelect = document.getElementById('input-project');
    if (!projectSelect) return;

    try {
      const centerUrl = localStorage.getItem('adt_center_url') || 'http://localhost:5001';
      const [forgeRes, governedRes] = await Promise.all([
        fetch(`${centerUrl}/api/forge`),
        fetch(`${centerUrl}/api/projects`)
      ]);
      
      let projects = {};
      if (forgeRes.ok) {
        const d = await forgeRes.json();
        Object.assign(projects, d.projects || d);
      }
      if (governedRes.ok) {
        const d = await governedRes.json();
        Object.assign(projects, d.projects || d);
      }
      
      const currentValue = projectSelect.value;
      projectSelect.innerHTML = '';
      
      const forgeGroup = document.createElement('optgroup');
      forgeGroup.label = 'Internal Forge';
      
      const governedGroup = document.createElement('optgroup');
      governedGroup.label = 'Governed Projects';

      Object.keys(projects).forEach(name => {
        const p = projects[name];
        const opt = document.createElement('option');
        opt.value = name; // Use name for API filtering
        opt.dataset.path = p.path;
        opt.textContent = `${name} (${p.path})`;
        
        if (p.is_framework || p.project_type === 'forge') {
          forgeGroup.appendChild(opt);
        } else {
          governedGroup.appendChild(opt);
        }
      });

      if (forgeGroup.children.length > 0) projectSelect.appendChild(forgeGroup);
      if (governedGroup.children.length > 0) projectSelect.appendChild(governedGroup);

      if (currentValue && projectSelect.querySelector(`option[value="${currentValue}"]`)) {
        projectSelect.value = currentValue;
      }
    } catch (err) {
      console.error('Error loading projects:', err);
    }
  }

  async function fetchAgyModels() {
    if (window._agyModelsCache) {
      return window._agyModelsCache;
    }
    try {
      const models = await window.__TAURI__.core.invoke('list_agy_models');
      if (Array.isArray(models) && models.length > 0) {
        window._agyModelsCache = models;
        return models;
      }
    } catch (err) {
      console.error('Failed to fetch agy models:', err);
    }
    const fallback = [
      'Claude Sonnet 4.6 (Thinking)',
      'Claude Opus 4.6 (Thinking)',
      'Gemini 3.5 Flash (High)',
      'Gemini 3.1 Pro (High)',
      'GPT-OSS 120B (Medium)'
    ];
    return fallback;
  }

  async function populateAgyModels() {
    const selectEl = document.getElementById('input-agy-model');
    if (!selectEl) return;
    
    selectEl.innerHTML = '<option value="">Loading models...</option>';
    
    const models = await fetchAgyModels();
    selectEl.innerHTML = '';
    models.forEach(model => {
      const opt = document.createElement('option');
      opt.value = model;
      opt.textContent = model;
      selectEl.appendChild(opt);
    });
  }

  function openNewSessionDialog() {
    loadProjects().then(() => {
      loadRoles().then(() => loadSpecs());
    });
    dialog.showModal();
    setTimeout(() => agentSelect.focus(), 50);
    if (agentSelect.value === 'agy') {
      populateAgyModels();
    }
  }

  document.getElementById('btn-new-session').addEventListener('click', openNewSessionDialog);
  document.getElementById('btn-shatterglass').addEventListener('click', () => {
    ShatterglassBridge.toggle();
  });

  // --- SPEC-037: File Request Dialog ---
  const requestDialog = document.getElementById('file-request-dialog');
  const requestForm = document.getElementById('file-request-form');

  if (requestDialog) {
    document.getElementById('btn-file-request')?.addEventListener('click', () => {
      requestDialog.showModal();
    });

    document.getElementById('btn-cancel-request')?.addEventListener('click', () => {
      requestDialog.close();
    });

    requestForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const activeSession = SessionManager.getActive();
      if (!activeSession) {
        ToastManager.show('denial', 'Error', 'No active session to file request from');
        return;
      }

      const payload = {
        from_role: activeSession.role,
        from_agent: activeSession.agent,
        to_role: document.getElementById('request-to-role').value,
        priority: document.getElementById('request-priority').value,
        title: document.getElementById('request-title').value,
        description: document.getElementById('request-description').value,
        project: activeSession.project
      };

      const centerUrl = localStorage.getItem('adt_center_url') || 'http://localhost:5001';
      try {
        const res = await fetch(`${centerUrl}/api/governance/requests`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          const data = await res.json();
          ToastManager.show('completion', 'Request Filed', data.req_id || 'Success');
          requestDialog.close();
          requestForm.reset();
          if (typeof ContextPanel !== 'undefined') ContextPanel.fetchRequests();
        } else {
          const err = await res.json();
          ToastManager.show('denial', 'Failed to file', err.error || 'Unknown error');
        }
      } catch (err) {
        ToastManager.show('denial', 'Error', 'ADT Center unreachable');
      }
    });
  }

  // Reload roles and specs when project changes
  document.getElementById('input-project')?.addEventListener('change', () => {
    loadRoles().then(() => loadSpecs());
  });

  // Sidebar new session button
  const sidebarNewBtn = document.getElementById('btn-new-session-sidebar');
  if (sidebarNewBtn) {
    sidebarNewBtn.addEventListener('click', openNewSessionDialog);
  }

  document.getElementById('btn-cancel-session').addEventListener('click', () => {
    dialog.close();
  });

  agentSelect.addEventListener('change', () => {
    customGroup.style.display = agentSelect.value === 'custom' ? '' : 'none';
    
    // SPEC-034: Agent flags visibility
    const flagsDiv = document.getElementById('agent-flags');
    const yoloFlag = document.getElementById('flag-yolo');
    const skipFlag = document.getElementById('flag-skip-permissions');
    
    if (flagsDiv) {
      const agent = agentSelect.value.toLowerCase();
      if (agent === 'gemini') {
        flagsDiv.style.display = 'block';
        yoloFlag.style.display = 'flex';
        skipFlag.style.display = 'none';
      } else if (agent === 'claude') {
        flagsDiv.style.display = 'block';
        yoloFlag.style.display = 'none';
        skipFlag.style.display = 'flex';
      } else if (agent === 'agy') {
        // SPEC-061 Amendment A: Antigravity harness flags
        flagsDiv.style.display = 'block';
        yoloFlag.style.display = 'none';
        skipFlag.style.display = 'flex'; // --dangerously-skip-permissions required for console ops
        // Show model selector if present
        const modelRow = document.getElementById('flag-agy-model');
        if (modelRow) modelRow.style.display = 'flex';
        populateAgyModels();
      } else {
        flagsDiv.style.display = 'none';
        const modelRow = document.getElementById('flag-agy-model');
        if (modelRow) modelRow.style.display = 'none';
      }
    }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const agent = agentSelect.value;
    const selectedOption = agentSelect.options[agentSelect.selectedIndex];
    const command = selectedOption.dataset.command;
    const role = document.getElementById('input-role').value;
    const specId = document.getElementById('input-spec').value;
    
    // SPEC-034: Fix project NAME vs PATH
    const projectSelect = document.getElementById('input-project');
    const project = projectSelect.value; // Name
    const projectOption = projectSelect.options[projectSelect.selectedIndex];
    const projectPath = projectOption ? projectOption.dataset.path : null;
    
    const customCmd = document.getElementById('input-custom-command').value;

    // SPEC-034: Agent flags
    const flags = {
      yolo: document.getElementById('input-yolo')?.checked || false,
      skipPermissions: document.getElementById('input-skip-permissions')?.checked || false,
      model: agent === 'agy' ? (document.getElementById('input-agy-model')?.value || null) : null,
    };

    dialog.close();
    const session = await SessionManager.create(agent, role, specId, agent === 'custom' ? customCmd : command, project, projectPath, flags);

    // Update tray after session creation
    if (session) TrayBridge.refresh();
  });

  // --- Dashboard button ---
  const _AG = (key, ev, fn) => {
    const act = async () => {
      if (window.ConsoleReadiness && !window.ConsoleReadiness.isReady()) {
        await window.ConsoleReadiness.waitReady({ timeout: 8000 });
      }
      await fn();
    };
    return window.ActionGuard ? window.ActionGuard.run(key, ev.currentTarget, act) : act();
  };

  document.getElementById('btn-dashboard').addEventListener('click', (e) => {
    _AG('dashboard_toggle', e, async () => DashboardManager.toggle());
  });

  document.getElementById('btn-projects').addEventListener('click', (e) => {
    _AG('projects_toggle', e, async () => ProjectLauncher.toggle());
  });

  document.getElementById('btn-governance').addEventListener('click', (e) => {
    _AG('governance_toggle', e, async () => GovernanceManager.toggle());
  });

  document.getElementById('btn-adt-panel').addEventListener('click', (e) => {
    _AG('adt_panel_toggle', e, async () => PanelManager.toggle());
  });

  // SPEC-062 task_350: Spec Map tab (architect direct implementation 2026-06-20)
  const specMapBtn = document.getElementById('btn-spec-map');
  if (specMapBtn) {
    specMapBtn.addEventListener('click', (e) => {
      _AG('spec_map_toggle', e, async () => {
        const view = document.getElementById('spec-map-view');
        if (!view) return;
        const open = view.style.display !== 'none' && view.style.display !== '';
        if (open) {
          if (window.SpecMap && window.SpecMap.hide) window.SpecMap.hide();
          specMapBtn.classList.remove('active');
        } else {
          // Close project launcher before showing spec map
          ProjectLauncher.hide();
          if (window.SpecMap && window.SpecMap.show) window.SpecMap.show();
          if (window.SpecMap && window.SpecMap.init) window.SpecMap.init();
          specMapBtn.classList.add('active');
        }
      });
    });
  }

  const remoteBtn = document.getElementById('status-remote');
  if (remoteBtn) {
    remoteBtn.addEventListener('click', () => {
      RemoteManager.toggle();
    });
  }

  // --- Split view button ---
  const splitBtn = document.getElementById('btn-split');
  if (splitBtn) {
    splitBtn.addEventListener('click', () => {
      document.getElementById('terminal-container').classList.toggle('split-view');
    });
  }

  // --- Forge split-mode exit button (SPEC-062 Amendment: Forge auto-launch) ---
  const forgeSplitExit = document.getElementById('forge-split-exit');
  if (forgeSplitExit) {
    forgeSplitExit.addEventListener('click', () => {
      const area = document.getElementById('terminal-area');
      if (area) area.classList.remove('forge-split-mode');
      // Keep spec map visible (user was watching it); collapse the split so terminal
      // takes normal space. If user wants to hide the map, they can toggle spec-map view.
    });
  }

  // --- Sidebar collapse buttons ---
  const collapseLeftBtn = document.getElementById('btn-collapse-left');
  if (collapseLeftBtn) {
    collapseLeftBtn.addEventListener('click', () => {
      document.getElementById('sidebar-left').classList.toggle('collapsed');
    });
  }

  const collapseRightBtn = document.getElementById('btn-collapse-right');
  if (collapseRightBtn) {
    collapseRightBtn.addEventListener('click', () => {
      document.getElementById('sidebar-right').classList.toggle('collapsed');
    });
  }

  // --- Settings & Shortcuts Overlay ---
  const shortcutsOverlay = document.getElementById('shortcuts-overlay');

  function initOverlayTabs() {
    if (!shortcutsOverlay) return;
    const tabs = shortcutsOverlay.querySelectorAll(".tab-btn");
    tabs.forEach(tab => {
      tab.addEventListener("click", () => {
        tabs.forEach(t => t.classList.remove("active"));
        shortcutsOverlay.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
        
        tab.classList.add("active");
        const contentId = `${tab.dataset.tab}-tab-content`;
        const content = document.getElementById(contentId);
        if (content) content.classList.add("active");
      });
    });
  }

  async function toggleAutostart(enabled) {
    if (!window.__TAURI__) return;
    try {
      await window.__TAURI__.core.invoke("toggle_autostart", { enabled });
    } catch (e) {
      console.warn("Autostart toggle failed:", e);
    }
  }

  function initSettings() {
    const autostart = document.getElementById("setting-autostart");
    const centerUrl = document.getElementById("setting-center-url");
    const dtcpUrl = document.getElementById("setting-dtcp-url");
    
    if (!autostart) return;

    // Load from localStorage
    autostart.checked = localStorage.getItem("adt_autostart") === "true";
    centerUrl.value = localStorage.getItem("adt_center_url") || "http://localhost:5001";
    dtcpUrl.value = localStorage.getItem("adt_dtcp_url") || "http://localhost:5002";
    
    autostart.addEventListener("change", () => {
      localStorage.setItem("adt_autostart", autostart.checked);
      toggleAutostart(autostart.checked);
    });
    
    centerUrl.addEventListener("change", () => {
      localStorage.setItem("adt_center_url", centerUrl.value);
    });

    dtcpUrl.addEventListener("change", () => {
      localStorage.setItem("adt_dtcp_url", dtcpUrl.value);
    });
  }

  function toggleShortcuts() {
    if (!shortcutsOverlay) return;
    shortcutsOverlay.style.display =
      shortcutsOverlay.style.display === 'none' ? '' : 'none';
  }

  const shortcutsBtn = document.getElementById('btn-shortcuts');
  if (shortcutsBtn) {
    shortcutsBtn.addEventListener('click', toggleShortcuts);
  }

  const closeShortcutsBtn = document.getElementById('btn-close-shortcuts');
  if (closeShortcutsBtn) {
    closeShortcutsBtn.addEventListener('click', toggleShortcuts);
  }

  // Close overlay on backdrop click
  if (shortcutsOverlay) {
    shortcutsOverlay.addEventListener('click', (e) => {
      if (e.target === shortcutsOverlay) toggleShortcuts();
    });
  }

  // --- Keyboard Shortcuts ---
  document.addEventListener('keydown', (e) => {
    // Escape: close shortcuts overlay or dialog
    if (e.key === 'Escape') {
      if (shortcutsOverlay && shortcutsOverlay.style.display !== 'none') {
        toggleShortcuts();
        return;
      }
    }

    // ?: Show shortcuts (only when not typing in input)
    if (e.key === '?' && !e.ctrlKey && !e.altKey &&
        !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
      e.preventDefault();
      toggleShortcuts();
      return;
    }

    // Ctrl+N: New session
    if (e.ctrlKey && e.key === 'n') {
      e.preventDefault();
      openNewSessionDialog();
      return;
    }

    // Ctrl+Shift+P: Projects Launcher
    if (e.ctrlKey && e.shiftKey && (e.key === 'P' || e.key === 'p')) {
      e.preventDefault();
      ProjectLauncher.toggle();
      return;
    }

    // Ctrl+W: Close current session
    if (e.ctrlKey && e.key === 'w') {
      e.preventDefault();
      const active = SessionManager.getActive();
      if (active) {
        SessionManager.close(active.id);
        TrayBridge.refresh();
      }
      return;
    }

    // Ctrl+Tab: Next session
    if (e.ctrlKey && e.key === 'Tab') {
      e.preventDefault();
      cycleSession(e.shiftKey ? -1 : 1);
      return;
    }

    // Ctrl+1-5: Switch to session by slot
    if (e.ctrlKey && e.key >= '1' && e.key <= '5') {
      e.preventDefault();
      switchToSlot(parseInt(e.key));
      return;
    }

    // Ctrl+G: Governance toggle
    if (e.ctrlKey && e.key === 'g') {
      e.preventDefault();
      GovernanceManager.toggle();
      return;
    }

    // Ctrl+P: Panel toggle
    if (e.ctrlKey && e.key === 'p') {
      e.preventDefault();
      PanelManager.toggle();
      return;
    }

    // Ctrl+M: Spec Map toggle (SPEC-062 - architect direct implementation 2026-06-20)
    if (e.ctrlKey && (e.key === 'm' || e.key === 'M')) {
      e.preventDefault();
      const btn = document.getElementById('btn-spec-map');
      if (btn) btn.click();
      return;
    }

    // Ctrl+D: Dashboard toggle
    if (e.ctrlKey && e.key === 'd') {
      e.preventDefault();
      DashboardManager.toggle();
      return;
    }

    // Ctrl+B: Toggle left sidebar
    if (e.ctrlKey && e.key === 'b') {
      e.preventDefault();
      document.getElementById('sidebar-left').classList.toggle('collapsed');
      return;
    }

    // Ctrl+I: Toggle right sidebar
    if (e.ctrlKey && e.key === 'i') {
      e.preventDefault();
      document.getElementById('sidebar-right').classList.toggle('collapsed');
      return;
    }

    // Ctrl+\: Split view toggle
    if (e.ctrlKey && e.key === '\\') {
      e.preventDefault();
      document.getElementById('terminal-container').classList.toggle('split-view');
      return;
    }
  });

  function switchToSlot(slot) {
    const all = SessionManager.getAll();
    const idx = slot - 1;
    if (idx < all.length) {
      if (DashboardManager.isActive()) DashboardManager.toggle();
      if (GovernanceManager.isActive()) GovernanceManager.toggle();
      if (PanelManager.isActive()) PanelManager.toggle();
      SessionManager.switchTo(all[idx].id);
    }
  }

  function cycleSession(direction) {
    const all = SessionManager.getAll();
    if (all.length === 0) return;

    if (DashboardManager.isActive()) DashboardManager.toggle();
    if (GovernanceManager.isActive()) GovernanceManager.toggle();
    if (PanelManager.isActive()) PanelManager.toggle();

    const active = SessionManager.getActive();
    const currentIdx = active ? all.findIndex(s => s.id === active.id) : -1;
    const nextIdx = (currentIdx + direction + all.length) % all.length;
    SessionManager.switchTo(all[nextIdx].id);
  }

  // --- Tauri Event Listeners (global shortcuts + tray) ---
  if (window.__TAURI__) {
    // Global shortcut: switch to session by slot number
    window.__TAURI__.event.listen('global-switch-session', (event) => {
      const slot = event.payload;
      if (typeof slot === 'number') {
        switchToSlot(slot);
      }
    });

    // Tray menu: open new session dialog
    window.__TAURI__.event.listen('tray-new-session', () => {
      openNewSessionDialog();
    });

    // ADS updates: refresh tray status + send native notifications for denials
    window.__TAURI__.event.listen('ads-updated', () => {
      TrayBridge.refresh();
    });

    // Panel → Console: spawn orchestrator PTY window when build is triggered from specs.html
    window.__TAURI__.event.listen('spawn-build-orchestrator', async (event) => {
      const { spec_id, build_id, project } = event.payload || {};
      if (!spec_id || !build_id) return;
      try {
        await SessionManager.spawnOrchestratorSession({ spec_id, build_id, triggered_by: 'panel' });
        BuildManager.showBuildProgress(build_id, spec_id);
      } catch (e) {
        console.warn('[BUILD] spawn-build-orchestrator event handler failed:', e);
        ToastManager.show('denial', 'Orchestrator Error', String(e));
      }
    });
  }

  // --- ADS Notification Watcher ---
  // Extends ContextPanel's event detection with native OS notifications
  const _origCheckForNotifiable = ContextPanel._checkForNotifiable;
  let lastNotifiedEventCount = 0;

  function watchForNativeNotifications() {
    if (!window.__TAURI__) return;

    // Poll ADS for denial/escalation events and fire native notifications
    setInterval(async () => {
      try {
        const res = await fetch('http://localhost:5001/api/ads/events');
        if (!res.ok) return;
        const data = await res.json();
        const events = data.events || [];

        if (lastNotifiedEventCount === 0) {
          lastNotifiedEventCount = events.length;
          return;
        }

        const newEvents = events.slice(lastNotifiedEventCount);
        lastNotifiedEventCount = events.length;

        newEvents.forEach(event => {
          const type = event.action_type || '';
          if (type.includes('denied') || type.includes('violation')) {
            NativeNotify.send(
              'DTCP Denial',
              truncateStr(event.description, 100)
            );
            TrayBridge.updateStatus('error', SessionManager.getAll().length, 1);
          } else if (type.includes('escalation') || type.includes('break_glass')) {
            NativeNotify.send(
              'Escalation',
              truncateStr(event.description, 100)
            );
            TrayBridge.updateStatus('warning', SessionManager.getAll().length, 1);
          } else if (type.includes('task_complete')) {
            NativeNotify.send(
              'Task Completed',
              truncateStr(event.description, 100)
            );
          }
        });
      } catch {
        // ADT Center not running
      }
    }, 5000);
  }

  function truncateStr(str, len) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
  }

  // --- SCR Alerts Watcher (SPEC-062 Amendment B) ---
  const SCRAlerts = (() => {
    let pollTimer = null;
    let authRequired = false;
    const getCenterUrl = () => localStorage.getItem("adt_center_url") || "http://localhost:5001";

    function showAuthPrompt() {
      authRequired = true;
      const feed = document.getElementById('ctx-scr-feed');
      const authPrompt = document.getElementById('scr-alerts-auth-prompt');
      if (feed) feed.style.display = 'none';
      if (authPrompt) authPrompt.style.display = 'block';
    }

    function hideAuthPrompt() {
      authRequired = false;
      const feed = document.getElementById('ctx-scr-feed');
      const authPrompt = document.getElementById('scr-alerts-auth-prompt');
      if (feed) feed.style.display = 'block';
      if (authPrompt) authPrompt.style.display = 'none';
    }

    async function fetchAndRender() {
      if (authRequired) return;
      try {
        const res = await fetch(`${getCenterUrl()}/api/governance/sovereign-requests?status=pending`);
        if (res.status === 401) {
          showAuthPrompt();
          return;
        }
        if (!res.ok) return;
        const data = await res.json();
        const requests = data.requests || (Array.isArray(data) ? data : []);
        render(requests);
      } catch (e) {
        console.warn("Failed to fetch SCR alerts", e);
      }
    }

    function render(requests) {
      const countBadge = document.getElementById('count-scr');
      const feed = document.getElementById('ctx-scr-feed');
      if (!countBadge || !feed) return;

      countBadge.textContent = requests.length;

      if (requests.length === 0) {
        feed.innerHTML = '<li class="ctx-empty">No active alerts...</li>';
        return;
      }

      feed.innerHTML = '';
      requests.forEach(req => {
        const li = document.createElement('li');
        li.className = 'tracker-item';
        li.style.borderLeftColor = 'var(--accent-yellow)';
        li.innerHTML = `
          <div class="tracker-header" style="display:flex; justify-content:space-between; margin-bottom:4px;">
            <span style="font-size:10px; font-weight:bold; color:var(--accent-yellow);">SCR: ${req.id || req.req_id}</span>
            <span style="font-size:9px; color:var(--text-muted);">${req.agent || 'Agent'} / ${req.role || 'Role'}</span>
          </div>
          <div class="tracker-body" style="font-size:11px; color:var(--text-secondary); margin-bottom:6px;">
            ${req.description || 'Requesting approval for action.'}
          </div>
          <div class="tracker-actions" style="display:flex; gap:6px;">
            <button class="btn-mini-action approve" data-id="${req.id || req.req_id}" style="background:var(--accent-green); color:#000;">Approve</button>
            <button class="btn-mini-action reject" data-id="${req.id || req.req_id}" style="background:var(--accent-red); color:#fff;">Reject</button>
          </div>
        `;
        feed.appendChild(li);
      });

      feed.querySelectorAll('button.approve').forEach(btn => {
        btn.addEventListener('click', () => handleAction(btn.dataset.id, 'approve'));
      });
      feed.querySelectorAll('button.reject').forEach(btn => {
        btn.addEventListener('click', () => handleAction(btn.dataset.id, 'reject'));
      });
    }

    async function handleAction(reqId, action) {
      // SPEC-045 hardened flow: GET nonce -> PUT /<id> with {action: authorize|reject, nonce}
      const apiAction = (action === 'approve') ? 'authorize' : 'reject';
      try {
        // 1. Acquire single-use nonce
        const nRes = await fetch(`${getCenterUrl()}/api/governance/sovereign-requests/${reqId}/nonce`, {
          method: 'GET',
          credentials: 'include'
        });
        if (nRes.status === 401) {
          showAuthPrompt();
          return;
        }
        if (!nRes.ok) {
          const err = await nRes.json().catch(() => ({error: 'nonce request failed'}));
          if (window.ToastManager) window.ToastManager.show('denial', 'SCR Nonce Failed', err.error || `HTTP ${nRes.status}`);
          return;
        }
        const nonceData = await nRes.json();
        const nonce = nonceData.nonce;

        // 2. PUT with action + nonce
        const body = { action: apiAction, nonce: nonce };
        if (action === 'reject') body.reason = 'Rejected via Console sidebar';
        const res = await fetch(`${getCenterUrl()}/api/governance/sovereign-requests/${reqId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(body)
        });
        if (res.status === 401) {
          showAuthPrompt();
          return;
        }
        if (res.ok) {
          if (window.ToastManager) window.ToastManager.show('completion', 'SCR Updated', `SCR ${reqId} ${action}d`);
          fetchAndRender();
        } else {
          const err = await res.json().catch(() => ({}));
          if (window.ToastManager) window.ToastManager.show('denial', 'SCR Action Failed', err.error || `HTTP ${res.status}`);
        }
      } catch (e) {
        if (window.ToastManager) window.ToastManager.show('denial', 'Error', `Failed to ${action} SCR: ${e.message || e}`);
      }
    }

    function init() {
      const section = document.getElementById('section-scr-alerts');
      if (section) section.style.display = 'block';

      const authBtn = document.getElementById('scr-alerts-auth-btn');
      if (authBtn) {
        authBtn.addEventListener('click', () => {
          hideAuthPrompt();
          if (!PanelManager.isActive()) {
            PanelManager.toggle();
          }
        });
      }

      fetchAndRender();

      if (window.__TAURI__) {
        window.__TAURI__.event.listen('ads-updated', () => {
          fetchAndRender();
        });
      }

      pollTimer = setInterval(fetchAndRender, 30000);
    }

    return { init, fetchAndRender };
  })();

  // --- Initialize ---
  // SPEC-073: register init tasks with ConsoleReadiness so the global bar reflects real progress.
  const CR = window.ConsoleReadiness;
  if (CR) {
    CR.begin('session_restore', 'Restoring sessions');
    CR.begin('governance_bootstrap', 'Loading governance state');
    CR.begin('agy_auth_probe', 'Checking agy auth');
    CR.begin('spec_map_init', 'Initialising spec map');
  }

  initOverlayTabs();
  initSettings();
  ProjectLauncher.init();
  GuideSystem.init();
  ContextPanel.initWatchers();
  SCRAlerts.init();

  SessionManager.restore().then(() => {
    if (CR) CR.end('session_restore');
    if (SessionManager.getAll().length === 0) {
      ProjectLauncher.toggle();
    }
  }).catch(() => { if (CR) CR.end('session_restore'); });

  // Best-effort: mark the other tasks done shortly after DOM boot completes.
  // Individual modules can call end() earlier if they finish sooner.
  setTimeout(() => {
    if (!CR) return;
    if (typeof GovernancePanel !== 'undefined') CR.end('governance_bootstrap');
    if (window.SpecMap) CR.end('spec_map_init');
    // agy probe is genuinely long-running; give it its own 8s window
    setTimeout(() => CR.end('agy_auth_probe'), 5000);
  }, 1200);

  SessionManager.updateStatusBar();
  GitStatusManager.startPolling();
  TrayBridge.refresh();
  ShatterglassBridge.refresh();
  watchForNativeNotifications();

  // Periodic uptime refresh
  setInterval(() => {
    const active = SessionManager.getActive();
    if (active && active.startTime) {
      ContextPanel.updateUptime(active);
    }
  }, 30000);
})();

// === SPEC-062 Amendment E: Pending Specs sidebar module ===
window.PendingSpecsAlerts = (function() {
  let pollTimer = null;
  const getCenterUrl = () => localStorage.getItem('adt_center_url') || 'http://localhost:5001';

  async function fetchAndRender() {
    try {
      const project = (window.SpecMap && window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
      const res = await fetch(`${getCenterUrl()}/api/specs?project=${encodeURIComponent(project)}`);
      if (!res.ok) return;
      const data = await res.json();
      const list = (data && data.specs) ? data.specs : (Array.isArray(data) ? data : []);
      const pending = list.filter(s => {
        const st = (s.status || '').toLowerCase();
        return st === 'draft' || st === 'pending' || st === 'proposed';
      });
      render(pending);
    } catch(e) { console.warn('PendingSpecsAlerts fetch failed:', e); }
  }

  function render(specs) {
    const sec = document.getElementById('section-pending-specs');
    const badge = document.getElementById('count-pending-specs');
    const feed = document.getElementById('ctx-pending-specs-feed');
    if (!sec || !badge || !feed) return;
    sec.style.display = 'block';
    badge.textContent = specs.length;
    if (specs.length === 0) {
      feed.innerHTML = '<li class="ctx-empty">No specs awaiting approval...</li>';
      return;
    }
    feed.innerHTML = '';
    specs.forEach(s => {
      const li = document.createElement('li');
      li.className = 'tracker-item';
      li.style.borderLeftColor = 'var(--accent-yellow)';
      const sid = s.spec_id || s.id || '';
      const title = (s.title || '').replace(/</g, '&lt;');
      const status = s.status || 'draft';
      li.innerHTML =
        '<div class="tracker-header" style="display:flex; justify-content:space-between; margin-bottom:4px;">' +
        '  <strong>' + sid + '</strong>' +
        '  <span style="font-size:9px; opacity:0.7;">' + status + '</span>' +
        '</div>' +
        '<div style="font-size:11px; color:var(--text-secondary); margin-bottom:6px;">' + title + '</div>' +
        '<div style="display:flex; gap:6px;">' +
        '  <button class="ps-view" data-id="' + sid + '" style="background:#1f6feb; color:#fff; border:1px solid #1f6feb; padding:4px 10px; border-radius:4px; font-size:11px; cursor:pointer;">View</button>' +
        '  <button class="ps-open-map" data-id="' + sid + '" style="background:#21262d; color:#e6e6e6; border:1px solid #30363d; padding:4px 10px; border-radius:4px; font-size:11px; cursor:pointer;">Open Map</button>' +
        '</div>';
      feed.appendChild(li);
    });
    feed.querySelectorAll('button.ps-view').forEach(b => {
      b.addEventListener('click', () => {
        const sid = b.dataset.id;
        // Navigate to Governance > Specs tab. Try several known affordances.
        const gp = (typeof GovernancePanel !== 'undefined') ? GovernancePanel : window.GovernancePanel;
        if (gp && gp.switchTab) {
          try { gp.switchTab('specs'); } catch(_) {}
        }
        const govBtn = document.getElementById('btn-governance');
        if (govBtn) govBtn.click();
        window._lastViewedSpec = sid;
        if (window.ToastManager) window.ToastManager.show('info', 'Spec Selected', sid + ' - check Specs tab');
      });
    });
    feed.querySelectorAll('button.ps-open-map').forEach(b => {
      b.addEventListener('click', () => {
        const sid = b.dataset.id;
        // Switch to the Spec Map view and load the spec
        const smBtn = document.getElementById('btn-spec-map') || document.querySelector('[data-tab="spec-map"]') || document.querySelector('[data-target="spec-map"]');
        if (smBtn) smBtn.click();
        if (window.SpecMap && window.SpecMap.fetchAndRender) {
          window.SpecMap.state = window.SpecMap.state || {};
          window.SpecMap.state.currentSpecId = sid;
          window.SpecMap.state.lastFetchKey = null;
          setTimeout(() => window.SpecMap.fetchAndRender(sid), 50);
        }
        if (window.ToastManager) window.ToastManager.show('info', 'Opening Map', sid);
      });
    });
  }

  function init() {
    const refreshBtn = document.getElementById('btn-pending-specs-refresh');
    if (refreshBtn) refreshBtn.addEventListener('click', fetchAndRender);
    fetchAndRender();
    if (window.__TAURI__) {
      try { window.__TAURI__.event.listen('ads-updated', fetchAndRender); } catch(_) {}
    }
    pollTimer = setInterval(fetchAndRender, 30000);
  }

  return { init: init, fetchAndRender: fetchAndRender };
})();

// Auto-init when DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => window.PendingSpecsAlerts.init());
} else {
  setTimeout(() => window.PendingSpecsAlerts.init(), 100);
}
