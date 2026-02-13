// Application controller — initialization, keyboard shortcuts, toasts
// SPEC-021: Main entry point for ADT Operator Console frontend

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


// --- Governance Panel Manager (delegates to GovernancePanel from governance.js) ---
const GovernanceManager = (() => {
  function toggle() {
    if (DashboardManager.isActive()) DashboardManager.toggle();
    GovernancePanel.toggle();
  }
  function isActive() { return GovernancePanel.isActive(); }
  function deactivate() { if (isActive()) toggle(); }
  return { toggle, isActive, deactivate };
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
// --- Main Application ---
(function () {
  'use strict';

  // --- Clock ---
  function updateClock() {
    const now = new Date();
    document.getElementById('status-clock').textContent =
      now.toISOString().substring(11, 19) + ' UTC';
  }
  setInterval(updateClock, 1000);
  updateClock();

  // --- New Session Dialog ---
  const dialog = document.getElementById('new-session-dialog');
  const form = document.getElementById('new-session-form');
  const agentSelect = document.getElementById('input-agent');
  const customGroup = document.getElementById('custom-command-group');

  function openNewSessionDialog() {
    dialog.showModal();
  }

  document.getElementById('btn-new-session').addEventListener('click', openNewSessionDialog);

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
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const agent = agentSelect.value;
    const selectedOption = agentSelect.options[agentSelect.selectedIndex];
    const command = selectedOption.dataset.command;
    const role = document.getElementById('input-role').value;
    const project = document.getElementById('input-project').value;
    const customCmd = document.getElementById('input-custom-command').value;

    dialog.close();
    const session = await SessionManager.create(agent, role, agent === 'custom' ? customCmd : command, project);

    // Update tray after session creation
    if (session) TrayBridge.refresh();
  });

  // --- Dashboard button ---
  document.getElementById('btn-dashboard').addEventListener('click', () => {
    DashboardManager.toggle();
  });

  document.getElementById('btn-governance').addEventListener('click', () => {
    GovernanceManager.toggle();
  });

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
    const dttpUrl = document.getElementById("setting-dttp-url");
    
    if (!autostart) return;

    // Load from localStorage
    autostart.checked = localStorage.getItem("adt_autostart") === "true";
    centerUrl.value = localStorage.getItem("adt_center_url") || "http://localhost:5001";
    dttpUrl.value = localStorage.getItem("adt_dttp_url") || "http://localhost:5002";
    
    autostart.addEventListener("change", () => {
      localStorage.setItem("adt_autostart", autostart.checked);
      toggleAutostart(autostart.checked);
    });
    
    centerUrl.addEventListener("change", () => {
      localStorage.setItem("adt_center_url", centerUrl.value);
    });

    dttpUrl.addEventListener("change", () => {
      localStorage.setItem("adt_dttp_url", dttpUrl.value);
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
      SessionManager.switchTo(all[idx].id);
    }
  }

  function cycleSession(direction) {
    const all = SessionManager.getAll();
    if (all.length === 0) return;

    if (DashboardManager.isActive()) DashboardManager.toggle();
      if (GovernanceManager.isActive()) GovernanceManager.toggle();

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
              'DTTP Denial',
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

  // --- Initialize ---
  initOverlayTabs();
  initSettings();
  ContextPanel.initWatchers();
  SessionManager.restore();
  SessionManager.updateStatusBar();
  TrayBridge.refresh();
  watchForNativeNotifications();

  // Periodic uptime refresh
  setInterval(() => {
    const active = SessionManager.getActive();
    if (active && active.startTime) {
      ContextPanel.updateUptime(active);
    }
  }, 30000);
})();