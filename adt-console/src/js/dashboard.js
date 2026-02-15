// Dashboard mode — overview grid of all agent sessions
// SPEC-021 Phase D: Dashboard view with session cards and stats

const DashboardManager = (() => {
  let isDashboardActive = false;

  function toggle() {
    isDashboardActive = !isDashboardActive;
    const terminalArea = document.getElementById('terminal-area');
    const dashView = document.getElementById('dashboard-view');
    const termContainer = document.getElementById('terminal-container');
    const emptyState = document.getElementById('empty-state');

    if (isDashboardActive) {
      const sessions = SessionManager.getAll();
      if (sessions.length === 0) {
        isDashboardActive = false;
        ToastManager.show('info', 'Dashboard', 'No sessions to display');
        return;
      }

      render(sessions);
      termContainer.style.display = 'none';
      emptyState.style.display = 'none';
      dashView.style.display = '';
    } else {
      dashView.style.display = 'none';
      termContainer.style.display = '';

      const active = SessionManager.getActive();
      if (active) {
        SessionManager.switchTo(active.id);
      } else {
        emptyState.style.display = '';
      }
    }
  }

  function render(sessions) {
    const grid = document.getElementById('dashboard-grid');
    const statsEl = document.getElementById('dashboard-stats');
    grid.innerHTML = '';

    // Stats header
    if (statsEl) {
      const agentCounts = {};
      sessions.forEach(s => {
        agentCounts[s.agent] = (agentCounts[s.agent] || 0) + 1;
      });

      const agentSummary = Object.entries(agentCounts)
        .map(([agent, count]) => `${agent.toUpperCase()}: ${count}`)
        .join(' | ');

      statsEl.innerHTML = `
        <span class="dashboard-stat">Active: <span class="stat-value">${sessions.length}</span></span>
        <span class="dashboard-stat">${agentSummary}</span>
      `;
    }

    sessions.forEach(session => {
      const card = document.createElement('div');
      card.className = 'dashboard-card';

      const roleShort = session.role
        .replace('_Engineer', '')
        .replace('Systems_', 'Sys_');

      const uptime = getSessionUptime(session);

      card.innerHTML = `
        <div class="card-header" style="border-left: 3px solid ${session.color}">
          <div>
            <span class="card-agent" style="color:${session.color}">${session.agent.toUpperCase()}</span>
            <span class="card-role">${roleShort}</span>
          </div>
          <span style="font-size:10px; color:var(--text-muted);">${uptime}</span>
        </div>
        <div class="card-body" id="mini-term-${session.id}">
          <div style="padding:8px; font-size:11px; color:var(--text-muted); font-family:monospace;">
            ${session.role}<br>
            Session: ${session.id}
          </div>
        </div>
        <div class="card-task">
          <span class="task-id" id="card-task-${session.id}">Loading...</span>
        </div>
      `;

      card.addEventListener('click', () => {
        toggle();
        SessionManager.switchTo(session.id);
      });

      grid.appendChild(card);

      // Fetch task for this session's role
      fetchCardTask(session);
    });
  }

  function getSessionUptime(session) {
    if (!session.startTime) return '--';
    const elapsed = Date.now() - session.startTime;
    const mins = Math.floor(elapsed / 60000);
    const hours = Math.floor(mins / 60);
    const m = mins % 60;
    return hours > 0 ? `${hours}h ${m}m` : `${m}m`;
  }

  async function fetchCardTask(session) {
    const el = document.getElementById(`card-task-${session.id}`);
    if (!el) return;

    try {
      const res = await fetch('http://localhost:5001/api/tasks');
      if (!res.ok) {
        el.textContent = 'No data';
        return;
      }
      const data = await res.json();
      const tasks = data.tasks || [];

      const activeTask = tasks.find(t =>
        (t.status === 'in_progress' || t.status === 'pending') &&
        t.assigned_to?.includes(session.role)
      );

      if (activeTask) {
        el.innerHTML = `<span class="task-id">${activeTask.id}</span> ${activeTask.title}`;
      } else {
        el.textContent = 'No active task';
      }
    } catch {
      el.textContent = 'Offline';
    }
  }

  return { toggle, isActive: () => isDashboardActive };
})();
