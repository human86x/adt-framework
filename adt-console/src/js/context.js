// Context panel — live governance data for current session
// SPEC-021: Pull from ADT Center API + local file watchers

const ContextPanel = (() => {
  const getCenterUrl = () => localStorage.getItem("adt_center_url") || "http://localhost:5001";
  let currentSession = null;
  let escalationCount = 0;
  let pollInterval = null;
  let allSpecs = {};

  async function update(session) {
    currentSession = session;

    document.getElementById('ctx-role').textContent = session.role || '--';

    const agentEl = document.getElementById('ctx-agent');
    agentEl.textContent = session.agent?.toUpperCase() || '--';
    agentEl.style.color = session.color || 'var(--text-primary)';

    document.getElementById('ctx-task').textContent = 'Connecting...';
    document.getElementById('ctx-task-priority').textContent = '';
    document.getElementById('ctx-task-priority').className = 'ctx-priority';
    document.getElementById('ctx-spec').textContent = '--';
    document.getElementById('ctx-event-count').textContent = '';

    if (session.startTime) {
      updateUptime(session);
    }

    await fetchSpecs();
    await fetchTaskData(session);
    await fetchADSEvents(session);
    await fetchRequests();
    await fetchDelegations();
    await fetchDTTPStatus();

    // If Tauri, try reading local files as fallback
    if (window.__TAURI__) {
      fetchLocalData(session);
    }
  }

  function updateUptime(session) {
    const elapsed = Date.now() - session.startTime;
    const mins = Math.floor(elapsed / 60000);
    const hours = Math.floor(mins / 60);
    const m = mins % 60;
    document.getElementById('ctx-uptime').textContent =
      hours > 0 ? `${hours}h ${m}m` : `${m}m`;
  }

  async function fetchRequests() {
    try {
      const res = await fetch(`${getCenterUrl()}/api/governance/requests`);
      if (!res.ok) return;
      const data = await res.json();
      const requests = data.requests || [];
      
      const countEl = document.getElementById('count-requests');
      if (countEl) countEl.textContent = requests.length;
      
      const container = document.getElementById('ctx-requests-list');
      if (!container) return;
      container.innerHTML = '';
      
      if (requests.length === 0) {
        container.innerHTML = '<li class="ctx-empty">No requests</li>';
        return;
      }
      
      requests.reverse().slice(0, 10).forEach(req => {
        const li = document.createElement('li');
        li.className = 'tracker-item';
        const statusClass = req.status.toLowerCase().includes('complete') ? 'badge-completed' : 'badge-pending';
        li.innerHTML = `
          <div class="tracker-header">
            <strong>${req.id}</strong>
            <span class="badge-adt ${statusClass}">${req.status}</span>
          </div>
          <div class="tracker-body" style="font-size: 10px;">${truncate(req.summary, 100)}</div>
          <div class="ctx-meta">From: ${req.author}</div>
        `;
        container.appendChild(li);
      });
    } catch {}
  }

  async function fetchDelegations() {
    try {
      const res = await fetch(`${getCenterUrl()}/api/governance/delegations`);
      if (!res.ok) return;
      const data = await res.json();
      const delegations = data.delegations || [];
      
      // Filter for delegations sent BY current role or targeting current role
      const sent = delegations.filter(d => d.from === currentSession?.role);
      
      const countEl = document.getElementById('count-sent');
      if (countEl) countEl.textContent = sent.length;
      
      const container = document.getElementById('ctx-tasks-sent');
      if (!container) return;
      container.innerHTML = '';
      
      if (sent.length === 0) {
        container.innerHTML = '<li class="ctx-empty">No delegations sent</li>';
        return;
      }
      
      // Show latest activity first
      sent.reverse().slice(0, 10).forEach(d => {
        const li = document.createElement('li');
        li.className = 'tracker-item';
        const actionLabel = d.action.replace('task_', '').replace('_', ' ');
        li.innerHTML = `
          <div class="tracker-header">
            <strong>${d.task_id}</strong>
            <span class="text-adt-accent" style="font-size: 9px;">\u2192 ${d.to.replace('_', ' ')}</span>
          </div>
          <div class="ctx-meta">${actionLabel.toUpperCase()}</div>
          <div class="ctx-meta" style="opacity: 0.6;">${d.ts ? new Date(d.ts).toLocaleTimeString() : ''}</div>
        `;
        container.appendChild(li);
      });
    } catch {}
  }

  async function fetchSpecs() {
    try {
      const res = await fetch(`${getCenterUrl()}/api/specs`);
      if (!res.ok) return;
      const data = await res.json();
      allSpecs = data.specs || {};
    } catch {
      // ADT Center may be offline
      if (window.__TAURI__) {
        try {
          const specsJson = await window.__TAURI__.core.invoke('read_project_file', {
            path: 'config/specs.json'
          });
          if (specsJson) {
            const data = JSON.parse(specsJson);
            allSpecs = data.specs || {};
          }
        } catch {}
      }
    }
  }

  async function fetchTaskData(session) {
    try {
      const res = await fetch(`${getCenterUrl()}/api/tasks`);
      if (!res.ok) return;
      const data = await res.json();

      const tasks = data.tasks || [];

      // Find active task for this role
      const activeTask = tasks.find(t =>
        t.status === 'in_progress' &&
        t.assigned_to?.includes(session.role)
      ) || tasks.find(t =>
        t.status === 'pending' &&
        t.assigned_to?.includes(session.role) &&
        (!t.depends_on || t.depends_on.every(dep =>
          tasks.find(d => d.id === dep)?.status === 'completed'
        ))
      );

      if (activeTask) {
        document.getElementById('ctx-task').innerHTML = `
          <strong class="ctx-task-id">${activeTask.id}</strong>
          <span class="ctx-value-decoded">${activeTask.title}</span>
        `;
        
        const spec = allSpecs[activeTask.spec_ref];
        const specTitle = spec?.title || 'Unknown Spec';
        document.getElementById('ctx-spec').innerHTML = `
          <strong class="ctx-spec-ref">${activeTask.spec_ref}</strong>
          <span class="ctx-value-decoded">${specTitle}</span>
        `;

        // Update To-Do list (Pending or In Progress for this role)
        const todoTasks = tasks.filter(t => 
          (t.status === 'in_progress' || t.status === 'pending') && 
          t.assigned_to?.includes(session.role)
        );
        document.getElementById('count-todo').textContent = todoTasks.length;
        const todoContainer = document.getElementById('ctx-tasks-todo');
        if (todoContainer) {
          todoContainer.innerHTML = '';
          if (todoTasks.length === 0) {
            todoContainer.innerHTML = '<li class="ctx-empty">All tasks done</li>';
          } else {
            todoTasks.slice(0, 10).forEach(t => {
              const li = document.createElement('li');
              li.className = 'tracker-item';
              li.innerHTML = `
                <div class="tracker-header">
                  <strong>${t.id}</strong>
                  <span class="badge-adt badge-${t.status.replace('_', '-')}">${t.status.replace('_', ' ')}</span>
                </div>
                <div class="tracker-body">${t.title}</div>
              `;
              todoContainer.appendChild(li);
            });
          }
        }

        updatePreflight(session, activeTask, specTitle);
        renderDelegation(activeTask, session);
      } else {
        document.getElementById('ctx-task').textContent = '--';
        document.getElementById('ctx-spec').textContent = '--';
        document.getElementById('count-todo').textContent = '0';
        updatePreflight(session, null);
        renderDelegation(null, session);
      }

      // Render completed tasks — for this role
      const completedTasks = tasks.filter(t => 
        t.status === 'completed' && 
        t.assigned_to?.includes(session.role)
      ).reverse();

      const countCompletedEl = document.getElementById('count-completed');
      if (countCompletedEl) countCompletedEl.textContent = completedTasks.length;

      const completedContainer = document.getElementById('ctx-tasks-completed');
      if (completedContainer) {
        completedContainer.innerHTML = '';
        if (completedTasks.length === 0) {
          completedContainer.innerHTML = '<li class="ctx-empty">No completions</li>';
        } else {
          completedTasks.slice(0, 10).forEach(t => {
            const li = document.createElement('li');
            li.className = 'tracker-item';
            li.innerHTML = `
              <div class="tracker-header">
                <strong>${t.id}</strong>
                <span class="badge-adt badge-completed">DONE</span>
              </div>
              <div class="tracker-body">${t.title}</div>
              ${t.evidence ? `<div class="ctx-meta" style="font-size:9px; opacity:0.7;">Ev: ${truncate(t.evidence, 40)}</div>` : ''}
            `;
            completedContainer.appendChild(li);
          });
        }
      }

      // Update dashboard stats
      const totalCompleted = tasks.filter(t => t.status === 'completed').length;
      updateDashboardStats(totalCompleted, tasks.length);
      
      const remoteDot = document.getElementById("ctx-remote-status");
      if (remoteDot) {
        remoteDot.className = "status-dot dot-green";
        remoteDot.title = "ADT Center: Online";
      }
    } catch (e) {
      console.error("fetchTaskData error:", e);
      // ADT Center not running -- show offline state
      const remoteDot = document.getElementById("ctx-remote-status");
      if (remoteDot) {
        remoteDot.className = "status-dot dot-red";
        remoteDot.title = "ADT Center: Offline";
      }
      document.getElementById('ctx-task').textContent = 'API offline';
      updatePreflight(session, null);
      renderDelegation(null, session);
    }
  }

  async function fetchLocalData(session) {
    // Tauri fallback: read local files via IPC when ADT Center is offline
    try {
      const tasksJson = await window.__TAURI__.core.invoke('read_project_file', {
        path: '_cortex/tasks.json'
      });
      if (tasksJson) {
        const data = JSON.parse(tasksJson);
        const tasks = data.tasks || [];
        const activeTask = tasks.find(t =>
          t.status !== 'completed' &&
          t.assigned_to?.includes(session.role) &&
          (!t.depends_on || t.depends_on.every(dep =>
            tasks.find(d => d.id === dep)?.status === 'completed'
          ))
        );
        if (activeTask) {
          document.getElementById('ctx-task').innerHTML = `
            <strong>${activeTask.id}</strong>
            <span class="ctx-value-decoded">${activeTask.title}</span>
          `;
          
          const specTitle = allSpecs[activeTask.spec_ref]?.title || '';
          document.getElementById('ctx-spec').innerHTML = `
            <strong>${activeTask.spec_ref}</strong>
            <span class="ctx-value-decoded">${specTitle}</span>
          `;

          const priorityEl = document.getElementById('ctx-task-priority');
          if (activeTask.priority) {
            priorityEl.textContent = activeTask.priority.toUpperCase();
            priorityEl.className = 'ctx-priority ' + activeTask.priority;
          }
          renderDelegation(activeTask, session);
          updatePreflight(session, activeTask);
        }
        
        // Local completed tasks
        const completedTasks = tasks.filter(t => 
          t.status === 'completed' && 
          t.assigned_to?.includes(session.role)
        ).reverse().slice(0, 5);

        const completedContainer = document.getElementById('ctx-tasks-completed');
        if (completedContainer) {
          completedContainer.innerHTML = '';
          completedTasks.forEach(t => {
            const li = document.createElement('li');
            li.innerHTML = `<span>${t.id}: ${t.title}</span>`;
            completedContainer.appendChild(li);
          });
        }
        const completed = tasks.filter(t => t.status === 'completed').length;
        updateDashboardStats(completed, tasks.length);
      }
    } catch {
      // read_project_file IPC may not exist yet
    }

    try {
      const eventsRaw = await window.__TAURI__.core.invoke('read_project_file', {
        path: '_cortex/ads/events.jsonl'
      });
      if (eventsRaw) {
        const lines = eventsRaw.trim().split('\n').filter(l => l.trim());
        const allEvents = lines.map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
        const agentEvents = allEvents
          .filter(e => e.agent?.toLowerCase() === session.agent?.toLowerCase())
          .slice(-10)
          .reverse();
        renderADSFeed(agentEvents);
        updateADSCount(allEvents.length);
        document.getElementById('ctx-event-count').textContent =
          agentEvents.length + ' agent events';
      }
    } catch {
      // read_project_file IPC may not exist yet
    }
  }

  function updatePreflight(session, task, specTitle = null) {
    const statusEl = document.querySelector('#ctx-preflight .preflight-status');
    const labelEl = document.querySelector('#ctx-preflight .preflight-label');
    const detailsEl = document.getElementById('ctx-alignment-details');

    if (!session) {
      statusEl.className = 'preflight-status';
      labelEl.textContent = 'Alignment: Offline';
      detailsEl.textContent = '';
      return;
    }

    if (!task) {
      statusEl.className = 'preflight-status warning';
      labelEl.textContent = 'Alignment: No Task';
      detailsEl.textContent = 'Awaiting task assignment';
      return;
    }

    // Alignment check: Role matches task, Spec matches task
    const roleMatch = task.assigned_to?.includes(session.role);
    const specMatch = task.spec_ref && task.spec_ref !== '--';
    
    // In a real implementation, we would check the agent's actual environment
    // variables (ADT_ROLE, ADT_SPEC_ID) reported via PTY.
    
    if (roleMatch && specMatch) {
      statusEl.className = 'preflight-status nominal';
      labelEl.textContent = 'Alignment: Nominal';
      detailsEl.textContent = specTitle ? `Active on ${task.spec_ref}: ${specTitle}` : `Ready for ${task.spec_ref}`;
    } else {
      statusEl.className = 'preflight-status error';
      labelEl.textContent = 'Alignment: Mismatch';
      detailsEl.textContent = 'Role/Spec discrepancy detected';
    }
  }

  function renderDelegation(task, session) {
    const container = document.getElementById('ctx-delegation');
    container.innerHTML = '';

    if (!task) {
      container.innerHTML = '<span class="ctx-meta">No active task</span>';
      return;
    }

    const specTitle = allSpecs[task.spec_ref]?.title || '';

    // Build delegation chain: Spec -> Role -> Task
    const items = [
      { label: 'Spec', value: task.spec_ref || '--', extra: specTitle, color: 'var(--accent-purple)' },
      { label: 'Role', value: session.role, color: session.color || 'var(--accent-blue)' },
      { label: 'Task', value: task.id, extra: task.title, color: 'var(--text-primary)' },
    ];

    // If task has delegation metadata, show delegator
    if (task.delegation) {
      const d = task.delegation;
      items.splice(1, 0, {
        label: 'By',
        value: `${d.delegated_by.role} (${d.delegated_by.agent})`,
        color: 'var(--text-secondary)',
      });
    }

    items.forEach((item, i) => {
      const el = document.createElement('div');
      el.className = 'delegation-item';
      el.innerHTML = `
        <div style="display:flex; align-items:center; gap:6px;">
          <strong style="color:var(--text-muted); min-width:35px; font-size:10px;">${item.label}</strong> 
          <span style="color:${item.color}">${item.value}</span>
        </div>
        ${item.extra ? `<div class="ctx-meta" style="margin-left:41px">${item.extra}</div>` : ''}
      `;
      container.appendChild(el);

      if (i < items.length - 1) {
        const arrow = document.createElement('div');
        arrow.style.cssText = 'color:var(--text-muted); font-size:10px; margin-left:12px; margin-top:-2px; margin-bottom:2px;';
        arrow.textContent = '\u2193';
        container.appendChild(arrow);
      }
    });
  }

  async function fetchADSEvents(session) {
    try {
      const res = await fetch(`${getCenterUrl()}/api/ads/events`);
      if (!res.ok) return;
      const data = await res.json();

      // Handle both list and object response formats
      const allEvents = Array.isArray(data) ? data : (data.events || []);
      const agentEvents = allEvents
        .filter(e => e.agent?.toLowerCase() === session.agent?.toLowerCase())
        .slice(-10)
        .reverse();

      renderADSFeed(agentEvents);
      updateADSCount(allEvents.length);

      // Count this session's events
      const countEl = document.getElementById('ctx-event-count');
      countEl.textContent = `${agentEvents.length} agent events`;

      // Count escalations
      escalationCount = allEvents.filter(e =>
        e.action_type?.includes('escalation') ||
        e.action_type?.includes('break_glass') ||
        e.action_type?.includes('violation')
      ).length;
      updateEscalationDisplay();

      // Fire toasts for denials/escalations
      checkForNotifiableEvents(allEvents);
    } catch {
      // ADT Center not running -- local fallback handled by fetchLocalData
    }
  }

  async function fetchRoleRequests(session) {
    try {
      const res = await fetch(`${getCenterUrl()}/api/ads/events`);
      if (!res.ok) return;
      const allEvents = await res.json();
      
      const list = Array.isArray(allEvents) ? allEvents : (allEvents.events || []);
      
      // Filter for delegation events targeting this role
      const requests = list.filter(e => 
        e.action_type === 'delegate_task' && 
        e.description.includes(session.role)
      ).slice(-5).reverse();
      
      const container = document.getElementById('ctx-role-requests');
      container.innerHTML = '';
      
      if (requests.length === 0) {
        container.innerHTML = '<li style="color:var(--text-muted)">No pending requests</li>';
        return;
      }
      
      requests.forEach(req => {
        const li = document.createElement('li');
        li.innerHTML = `
          ${req.description}
          <span class="request-meta">From ${req.role} | ${req.spec_ref}</span>
        `;
        container.appendChild(li);
      });
    } catch {
      // ADT Center may not be running
    }
  }

  let lastKnownEventCount = 0;

  function checkForNotifiableEvents(events) {
    if (lastKnownEventCount === 0) {
      lastKnownEventCount = events.length;
      return;
    }

    const newEvents = events.slice(lastKnownEventCount);
    lastKnownEventCount = events.length;

    newEvents.forEach(event => {
      if (event.action_type?.includes('denied') || event.action_type?.includes('violation')) {
        ToastManager.show('denial', 'DENIED', truncate(event.description, 80));
      } else if (event.action_type?.includes('escalation') || event.action_type?.includes('break_glass')) {
        ToastManager.show('escalation', 'ESCALATION', truncate(event.description, 80));
      } else if (event.action_type?.includes('task_complete')) {
        ToastManager.show('completion', 'Completed', truncate(event.description, 80));
      }
    });
  }

  function renderADSFeed(events) {
    const feed = document.getElementById('ctx-ads-feed');
    feed.innerHTML = '';

    if (events.length === 0) {
      feed.innerHTML = '<li style="color:var(--text-muted)">No events</li>';
      return;
    }

    events.forEach(event => {
      const li = document.createElement('li');
      const typeClass = getEventTypeClass(event.action_type);
      const time = event.ts ? new Date(event.ts).toLocaleTimeString('en-US', { hour12: false, minute: '2-digit', second: '2-digit' }) : '';
      li.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span class="event-type ${typeClass}" style="font-size:9px; font-weight:800;">${event.action_type.toUpperCase()}</span>
          <span style="color:var(--text-muted); font-size:10px;">${time}</span>
        </div>
        <div style="margin-top:2px; line-height:1.2;">${truncate(event.description, 100)}</div>
        <div class="ctx-meta" style="font-size:9px; opacity:0.7;">${event.spec_ref || ''}</div>
      `;
      li.title = event.description || '';
      feed.appendChild(li);
    });
  }

  function getEventTypeClass(actionType) {
    if (!actionType) return '';
    if (actionType.includes('complete') || actionType.includes('success')) return 'completion';
    if (actionType.includes('denied') || actionType.includes('violation')) return 'denial';
    if (actionType.includes('escalation') || actionType.includes('break_glass')) return 'escalation';
    if (actionType.includes('session')) return 'session';
    return '';
  }

  function updateADSCount(count) {
    document.getElementById('status-ads').innerHTML =
      `<span class="status-dot dot-green"></span> ADS: ${count} events`;
    const badge = document.getElementById('ctx-ads-count');
    if (badge) badge.textContent = count;
  }

  function updateEscalationDisplay() {
    const el = document.getElementById('status-escalations');
    el.textContent = `Escalations: ${escalationCount}`;
    if (escalationCount > 0) {
      el.classList.add('has-escalations');
    } else {
      el.classList.remove('has-escalations');
    }
  }

  function updateDashboardStats(completed, total) {
    const statsEl = document.getElementById('dashboard-stats');
    if (statsEl) {
      statsEl.innerHTML = `
        <span class="dashboard-stat">Tasks: <span class="stat-value">${completed}/${total}</span></span>
      `;
    }
  }

  async function fetchDTTPStatus() {
    try {
      const res = await fetch(`${getCenterUrl()}/dttp/status`);
      if (!res.ok) {
        document.getElementById('status-dttp').innerHTML =
          '<span class="status-dot dot-grey"></span> DTTP: offline';
        return;
      }
      const data = await res.json();
      document.getElementById('status-dttp').innerHTML =
        `<span class="status-dot dot-green"></span> DTTP: ${data.status || 'active'}`;
    } catch {
      document.getElementById('status-dttp').innerHTML =
        '<span class="status-dot dot-grey"></span> DTTP: --';
    }
  }

  function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
  }

  // Listen for file watcher events from Rust backend
  function initWatchers() {
    if (window.__TAURI__) {
      window.__TAURI__.event.listen('ads-updated', () => {
        if (currentSession) {
          fetchADSEvents(currentSession);
          fetchRoleRequests(currentSession);
          fetchDelegations();
        }
      });

      window.__TAURI__.event.listen('tasks-updated', () => {
        if (currentSession) fetchTaskData(currentSession);
      });

      window.__TAURI__.event.listen('requests-updated', () => {
        fetchRequests();
      });
    }

    // Browser fallback: poll every 10s
    pollInterval = setInterval(() => {
      if (currentSession) {
        fetchADSEvents(currentSession);
        fetchTaskData(currentSession);
        fetchRoleRequests(currentSession);
        fetchDelegations();
        fetchRequests();
        fetchDTTPStatus();
      }
    }, 10000);
  }

  return { update, initWatchers, updateUptime };
})();