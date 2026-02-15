// Governance Panel — Task Board, Hierarchy View, Delegation Tree
// SPEC-003: ADT Operational Dashboard (Hierarchy + Delegation)
// SPEC-013: ADT Panel UI Refinements (Collapsible tasks, spec icons, auto-scroll)

const GovernancePanel = (() => {
  const API_URL = () => localStorage.getItem('adt_center_url') || 'http://localhost:5001';
  let isActive = false;
  let currentTab = 'taskboard';
  let cachedTasks = [];
  let cachedSpecs = [];
  let cachedEvents = [];
  let cachedPhases = [];
  let matrixFilter = null;

  // --- Toggle Panel ---
  function toggle() {
    isActive = !isActive;
    const termArea = document.getElementById('terminal-area');
    const govPanel = document.getElementById('governance-view');

    if (isActive) {
      termArea.classList.add('governance-active');
      govPanel.style.display = '';
      refresh();
    } else {
      termArea.classList.remove('governance-active');
      govPanel.style.display = 'none';
    }

    const btn = document.getElementById('btn-governance');
    if (btn) btn.classList.toggle('active', isActive);
  }

  function isActiveState() { return isActive; }

  // --- Data Fetching ---
  async function fetchAll() {
    const url = API_URL();
    const [tasksRes, specsRes, eventsRes] = await Promise.allSettled([
      fetch(`${url}/api/tasks`).then(r => r.ok ? r.json() : null),
      fetch(`${url}/api/specs`).then(r => r.ok ? r.json() : null),
      fetch(`${url}/api/ads/events`).then(r => r.ok ? r.json() : null),
    ]);

    cachedTasks = tasksRes.status === 'fulfilled' && tasksRes.value
      ? (tasksRes.value.tasks || []) : [];
    cachedSpecs = specsRes.status === 'fulfilled' && specsRes.value
      ? (specsRes.value.specs || []) : [];
    const evData = eventsRes.status === 'fulfilled' ? eventsRes.value : null;
    cachedEvents = evData ? (Array.isArray(evData) ? evData : (evData.events || [])) : [];

    await fetchPhases();
  }

  async function fetchPhases() {
    if (window.__TAURI__) {
      try {
        const raw = await window.__TAURI__.core.invoke('read_project_file', {
          path: '_cortex/phases.json'
        });
        if (raw) {
          const data = JSON.parse(raw);
          cachedPhases = data.phases || [];
          return;
        }
      } catch { /* fallback */ }
    }
    cachedPhases = buildDefaultPhases();
  }

  function buildDefaultPhases() {
    return [
      { id: '1', name: 'Core Engines', status: 'completed',
        specs: ['SPEC-014', 'SPEC-015', 'SPEC-016', 'SPEC-017'] },
      { id: '1.5', name: 'Hardening + Service Extraction', status: 'active',
        specs: ['SPEC-018', 'SPEC-019', 'SPEC-020'] },
      { id: '2', name: 'Operator Console', status: 'active',
        specs: ['SPEC-021', 'SPEC-013', 'SPEC-003'] },
      { id: '3', name: 'Production & Distribution', status: 'planned',
        specs: ['SPEC-022', 'SPEC-023', 'SPEC-024'] },
    ];
  }

  // --- Refresh ---
  async function refresh() {
    if (!isActive) return;
    try {
      await fetchAll();
      renderTab(currentTab);
    } catch {
      document.getElementById('gov-content').innerHTML =
        '<div class="gov-offline">ADT Center API offline</div>';
    }
  }

  // --- Tab Switching ---
  function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('#governance-view .gov-tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    renderTab(tab);
  }

  function renderTab(tab) {
    const content = document.getElementById('gov-content');
    switch (tab) {
      case 'taskboard': renderTaskBoard(content); break;
      case 'hierarchy': renderHierarchy(content); break;
      case 'delegation': renderDelegation(content); break;
    }
  }

  // ============================
  // TASK BOARD (SPEC-003 + SPEC-013)
  // ============================
  function renderTaskBoard(container) {
    const pending = cachedTasks.filter(t => t.status === 'pending');
    const inProgress = cachedTasks.filter(t => t.status === 'in_progress');
    const completed = cachedTasks.filter(t => t.status === 'completed');

    // SPEC-013: Group completed tasks by role
    const completedByRole = {};
    completed.forEach(t => {
      const role = t.assigned_to || 'Unassigned';
      if (!completedByRole[role]) completedByRole[role] = [];
      completedByRole[role].push(t);
    });

    container.innerHTML = `
      <div class="taskboard">
        <div class="taskboard-column">
          <div class="column-header pending-header">
            <span>Pending</span>
            <span class="column-count">${pending.length}</span>
          </div>
          <div class="column-cards">${pending.map(renderTaskCard).join('')}</div>
        </div>
        <div class="taskboard-column">
          <div class="column-header progress-header">
            <span>In Progress</span>
            <span class="column-count">${inProgress.length}</span>
          </div>
          <div class="column-cards">${inProgress.map(renderTaskCard).join('')}</div>
        </div>
        <div class="taskboard-column">
          <div class="column-header completed-header">
            <span>Completed</span>
            <span class="column-count">${completed.length}</span>
          </div>
          <div class="column-cards">
            ${Object.entries(completedByRole).map(([role, tasks]) => `
              <div class="role-group">
                <button class="role-group-toggle" onclick="GovernancePanel._toggleGroup(this)">
                  <span class="toggle-icon">&#9654;</span>
                  <span class="role-group-name ${getRoleClass(role)}">${formatRole(role)}</span>
                  <span class="role-group-count">${tasks.length}</span>
                </button>
                <div class="role-group-cards collapsed">
                  ${tasks.map(renderTaskCard).join('')}
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    `;
  }

  function renderTaskCard(task) {
    const priorityClass = task.priority || '';
    const roleClass = getRoleClass(task.assigned_to || '');
    const specBadge = task.spec_ref ? `<span class="card-spec">${task.spec_ref}</span>` : '';
    const delegationBadge = task.delegation
      ? `<span class="card-delegated">by ${task.delegation.delegated_by?.role || '?'}` +
        `${task.delegation.delegated_by?.agent ? ' (' + task.delegation.delegated_by.agent + ')' : ''}</span>`
      : '';
    const blockedBadge = task.depends_on?.length
      ? `<span class="card-blocked">blocked by ${task.depends_on.join(', ')}</span>`
      : '';

    return `
      <div class="task-card ${priorityClass}" title="${(task.description || task.title || '').replace(/"/g, '&quot;')}" onclick="GovernancePanel._showTaskDetail('${task.id}')">
        <div class="task-card-header">
          <span class="task-card-id">${task.id}</span>
          ${specBadge}
        </div>
        <div class="task-card-title">${task.title}</div>
        <div class="task-card-meta">
          <span class="${roleClass}">@${formatRole(task.assigned_to || 'Unassigned')}</span>
          ${delegationBadge}
        </div>
        ${blockedBadge}
      </div>
    `;
  }

  // ============================
  // HIERARCHY VIEW (SPEC-003)
  // ============================
  function renderHierarchy(container) {
    let html = '<div class="hierarchy-tree">';
    html += '<div class="hier-root">ADT Framework</div>';

    cachedPhases.forEach(phase => {
      const phaseSpecs = phase.specs || [];
      const phaseTasks = cachedTasks.filter(t => phaseSpecs.includes(t.spec_ref));
      const phaseCompleted = phaseTasks.filter(t => t.status === 'completed').length;
      const phaseTotal = phaseTasks.length;
      const phaseProgress = phaseTotal > 0 ? Math.round((phaseCompleted / phaseTotal) * 100) : 0;
      const phaseStatusClass = phase.status === 'completed' ? 'completed'
        : phase.status === 'active' ? 'active' : 'planned';

      html += `
        <div class="hier-phase">
          <button class="hier-toggle" onclick="GovernancePanel._toggleHier(this)">
            <span class="toggle-icon">&#9660;</span>
            <span class="hier-phase-label ${phaseStatusClass}">Phase ${phase.id}: ${phase.name}</span>
            <div class="progress-bar-container">
              <div class="progress-bar" style="width:${phaseProgress}%"></div>
            </div>
            <span class="hier-count">${phaseCompleted}/${phaseTotal}</span>
          </button>
          <div class="hier-children">
      `;

      phaseSpecs.forEach(specRef => {
        const spec = cachedSpecs.find(s => s.id === specRef);
        const specTasks = cachedTasks.filter(t => t.spec_ref === specRef);
        const specCompleted = specTasks.filter(t => t.status === 'completed').length;
        const specTotal = specTasks.length;
        const specProgress = specTotal > 0 ? Math.round((specCompleted / specTotal) * 100) : 0;

        // SPEC-013: Spec status icons
        const specStatus = spec?.status || 'UNKNOWN';
        const specIcon = specStatus === 'APPROVED'
          ? '<span class="spec-icon approved" title="Approved">&#10003;</span>'
          : specStatus === 'DRAFT'
          ? '<span class="spec-icon draft" title="Draft">&#9679;</span>'
          : '<span class="spec-icon pending" title="Pending">&#9711;</span>';

        const specName = spec
          ? (spec.filename || spec.id || specRef).replace('.md', '').replace(/^SPEC-\d+_/, '').replace(/_/g, ' ')
          : specRef;

        html += `
          <div class="hier-spec">
            <button class="hier-toggle" onclick="GovernancePanel._toggleHier(this)">
              <span class="toggle-icon">&#9654;</span>
              ${specIcon}
              <span class="hier-spec-label">${specRef}</span>
              <span class="hier-spec-name">${specName}</span>
              ${specTotal > 0 ? `
                <div class="progress-bar-container small">
                  <div class="progress-bar" style="width:${specProgress}%"></div>
                </div>
                <span class="hier-count">${specCompleted}/${specTotal}</span>
              ` : ''}
            </button>
            <div class="hier-children collapsed">
        `;

        specTasks.forEach(task => {
          const statusIcon = task.status === 'completed'
            ? '<span class="task-status-icon done">&#10003;</span>'
            : task.status === 'in_progress'
            ? '<span class="task-status-icon progress">&#9654;</span>'
            : task.depends_on?.some(dep => cachedTasks.find(d => d.id === dep)?.status !== 'completed')
              ? '<span class="task-status-icon blocked">!</span>'
              : '<span class="task-status-icon pending">&#9711;</span>';

          html += `
            <div class="hier-task ${task.status}" onclick="GovernancePanel._showTaskDetail('${task.id}')">
              ${statusIcon}
              <span class="hier-task-id">${task.id}</span>
              <span class="hier-task-title">${task.title}</span>
              <span class="hier-task-role ${getRoleClass(task.assigned_to || '')}">${formatRole(task.assigned_to || '')}</span>
            </div>
          `;
        });

        html += '</div></div>';
      });

      html += '</div></div>';
    });

    html += '</div>';
    container.innerHTML = html;
  }

  // ============================
  // DELEGATION TREE + MATRIX (SPEC-003)
  // ============================
  function renderDelegation(container) {
    container.innerHTML = `
      <div class="delegation-layout">
        <div class="delegation-tree-panel">
          <div class="delegation-tree-header">Delegation Tree</div>
          <div id="deleg-tree" class="delegation-tree-content"></div>
        </div>
        <div class="delegation-matrix-panel">
          <div class="delegation-matrix-header">Summary Matrix</div>
          <div id="deleg-matrix" class="delegation-matrix-content"></div>
        </div>
      </div>
    `;

    renderDelegationTree();
    renderSummaryMatrix();
  }

  function renderDelegationTree() {
    const tree = document.getElementById('deleg-tree');
    if (!tree) return;

    // Group tasks by spec
    const tasksBySpec = {};
    cachedTasks.forEach(t => {
      const spec = t.spec_ref || 'No Spec';
      if (!tasksBySpec[spec]) tasksBySpec[spec] = [];
      tasksBySpec[spec].push(t);
    });

    let html = '';
    Object.entries(tasksBySpec).forEach(([specRef, tasks]) => {
      const spec = cachedSpecs.find(s => s.id === specRef);
      const specName = spec
        ? (spec.filename || spec.id || specRef).replace('.md', '').replace(/^SPEC-\d+_/, '').replace(/_/g, ' ')
        : specRef;

      // Group tasks by delegated-to role
      const byRole = {};
      tasks.forEach(t => {
        const role = t.delegation?.delegated_to?.role || t.assigned_to || 'Unassigned';
        if (!byRole[role]) byRole[role] = [];
        byRole[role].push(t);
      });

      // Apply matrix filter
      const filteredRoles = matrixFilter
        ? Object.entries(byRole).filter(([role]) => role === matrixFilter.role)
        : Object.entries(byRole);

      if (matrixFilter && filteredRoles.length === 0) return;

      html += `
        <div class="deleg-spec-node">
          <button class="deleg-toggle" onclick="GovernancePanel._toggleHier(this)">
            <span class="toggle-icon">&#9660;</span>
            <span class="deleg-spec-ref">${specRef}</span>
            <span class="deleg-spec-name">${specName}</span>
          </button>
          <div class="deleg-children">
      `;

      const firstTask = tasks[0];
      const delegator = firstTask?.delegation?.delegated_by
        || { role: 'Systems_Architect', agent: 'CLAUDE' };
      html += '<div class="deleg-creator">Created by: ' + delegator.role + ' (' + (delegator.agent || '?') + ')</div>';

      filteredRoles.forEach(([role, roleTasks]) => {
        const filtered = matrixFilter?.agent
          ? roleTasks.filter(t => {
              const agent = t.delegation?.delegated_to?.agent || t.delegation?.delegated_by?.agent || '';
              return agent.toUpperCase() === matrixFilter.agent.toUpperCase();
            })
          : roleTasks;

        if (filtered.length === 0) return;

        html += `
          <div class="deleg-role-node">
            <div class="deleg-role-label ${getRoleClass(role)}">&#8594; ${role}</div>
            <div class="deleg-role-tasks">
        `;

        filtered.forEach(task => {
          const statusIcon = task.status === 'completed' ? '[v]'
            : task.status === 'in_progress' ? '[>]'
            : task.depends_on?.some(dep => cachedTasks.find(d => d.id === dep)?.status !== 'completed')
              ? '[!]' : '[ ]';

          const statusClass = task.status === 'completed' ? 'done'
            : task.status === 'in_progress' ? 'progress' : 'pending';

          const agentTag = task.delegation?.delegated_to?.agent
            ? '<span class="deleg-agent-tag">' + task.delegation.delegated_to.agent + '</span>' : '';

          html += `
            <div class="deleg-task-node ${statusClass}" onclick="GovernancePanel._showTaskDetail('${task.id}')" title="${(task.description || task.title || '').replace(/"/g, '&quot;')}">
              <span class="deleg-status">${statusIcon}</span>
              <span class="deleg-task-id">${task.id}:</span>
              <span class="deleg-task-title">${task.title}</span>
              ${agentTag}
              <span class="deleg-task-status-label">${task.status.toUpperCase()}</span>
            </div>
          `;

          if (task.depends_on?.length) {
            html += '<div class="deleg-blocked-by">blocked by: ' + task.depends_on.join(', ') + '</div>';
          }
        });

        html += '</div></div>';
      });

      html += '</div></div>';
    });

    if (!html) {
      html = '<div class="gov-empty">No delegation data available</div>';
    }

    tree.innerHTML = html;
  }

  function renderSummaryMatrix() {
    const matrix = document.getElementById('deleg-matrix');
    if (!matrix) return;

    const roles = ['Systems_Architect', 'Backend_Engineer', 'Frontend_Engineer', 'DevOps_Engineer', 'Overseer'];
    const agents = ['CLAUDE', 'GEMINI'];

    const counts = {};
    const breakdowns = {};
    roles.forEach(role => {
      counts[role] = {};
      breakdowns[role] = {};
      agents.forEach(agent => {
        counts[role][agent] = 0;
        breakdowns[role][agent] = { completed: 0, in_progress: 0, pending: 0 };
      });
      counts[role]['UNASSIGNED'] = 0;
      breakdowns[role]['UNASSIGNED'] = { completed: 0, in_progress: 0, pending: 0 };
    });

    cachedTasks.forEach(task => {
      const role = task.assigned_to || task.delegation?.delegated_to?.role;
      if (!role || !counts[role]) return;

      const agent = task.delegation?.delegated_to?.agent
        || task.delegation?.delegated_by?.agent
        || 'UNASSIGNED';
      const bucket = agents.includes(agent.toUpperCase()) ? agent.toUpperCase() : 'UNASSIGNED';

      counts[role][bucket]++;
      const status = task.status || 'pending';
      if (breakdowns[role][bucket][status] !== undefined) {
        breakdowns[role][bucket][status]++;
      }
    });

    let html = '<table class="matrix-table"><thead><tr><th></th>';
    agents.forEach(a => { html += '<th>' + a + '</th>'; });
    html += '<th>N/A</th></tr></thead><tbody>';

    roles.forEach(role => {
      html += '<tr><td class="matrix-role ' + getRoleClass(role) + '">' + formatRole(role) + '</td>';
      [...agents, 'UNASSIGNED'].forEach(agent => {
        const count = counts[role][agent] || 0;
        const bd = breakdowns[role][agent];
        const colorClass = count === 0 ? 'matrix-empty'
          : count < 3 ? 'matrix-green'
          : count < 6 ? 'matrix-yellow'
          : 'matrix-red';

        const isFiltered = matrixFilter?.role === role
          && (matrixFilter?.agent || 'UNASSIGNED') === agent;

        const tooltip = bd.completed + ' done, ' + bd.in_progress + ' active, ' + bd.pending + ' pending';

        html += '<td class="matrix-cell ' + colorClass + (isFiltered ? ' matrix-active' : '') + '"'
          + ' title="' + tooltip + '"'
          + ' onclick="GovernancePanel._filterMatrix(\'' + role + '\', \'' + agent + '\')">'
          + count + '</td>';
      });
      html += '</tr>';
    });

    html += '</tbody></table>';

    if (matrixFilter) {
      html += '<button class="matrix-clear" onclick="GovernancePanel._clearFilter()">Clear filter</button>';
    }

    matrix.innerHTML = html;
  }

  // --- Task Detail Modal ---
  function showTaskDetail(taskId) {
    const task = cachedTasks.find(t => t.id === taskId);
    if (!task) return;

    const taskEvents = cachedEvents.filter(e =>
      (e.action_data && e.action_data.task_id === taskId) ||
      (e.description && e.description.includes(taskId))
    ).slice(-10).reverse();

    const overlay = document.createElement('div');
    overlay.className = 'task-detail-overlay';
    overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };

    let modalHtml = '<div class="task-detail-modal">';
    modalHtml += '<div class="task-detail-header">';
    modalHtml += '<h3>' + task.id + ': ' + task.title + '</h3>';
    modalHtml += '<button onclick="this.closest(\'.task-detail-overlay\').remove()" class="shortcuts-close">&times;</button>';
    modalHtml += '</div>';
    modalHtml += '<div class="task-detail-body">';
    modalHtml += '<div class="task-detail-row"><strong>Status:</strong> <span class="task-status-badge ' + task.status + '">' + task.status.toUpperCase() + '</span></div>';
    modalHtml += '<div class="task-detail-row"><strong>Priority:</strong> ' + (task.priority || '--') + '</div>';
    modalHtml += '<div class="task-detail-row"><strong>Spec:</strong> ' + (task.spec_ref || '--') + '</div>';
    modalHtml += '<div class="task-detail-row"><strong>Assigned to:</strong> ' + (task.assigned_to || '--') + '</div>';
    if (task.delegation) {
      modalHtml += '<div class="task-detail-row"><strong>Delegated by:</strong> '
        + (task.delegation.delegated_by?.role || '?')
        + ' (' + (task.delegation.delegated_by?.agent || '?') + ')</div>';
    }
    if (task.depends_on?.length) {
      modalHtml += '<div class="task-detail-row"><strong>Depends on:</strong> ' + task.depends_on.join(', ') + '</div>';
    }
    modalHtml += '<div class="task-detail-desc">' + (task.description || 'No description') + '</div>';

    if (taskEvents.length > 0) {
      modalHtml += '<h4>ADS History</h4><ul class="task-detail-events">';
      taskEvents.forEach(e => {
        modalHtml += '<li>';
        modalHtml += '<span class="event-type ' + getEventTypeClass(e.action_type) + '">' + e.action_type + '</span>';
        modalHtml += '<span class="event-time">' + (e.ts ? new Date(e.ts).toLocaleString() : '') + '</span>';
        modalHtml += '<div>' + truncate(e.description, 120) + '</div>';
        modalHtml += '</li>';
      });
      modalHtml += '</ul>';
    } else {
      modalHtml += '<p class="gov-empty">No ADS events for this task</p>';
    }

    modalHtml += '</div></div>';
    overlay.innerHTML = modalHtml;
    document.body.appendChild(overlay);
  }

  // --- Utility ---
  function getRoleClass(role) {
    if (role.includes('Architect')) return 'role-architect';
    if (role.includes('Backend')) return 'role-backend';
    if (role.includes('Frontend')) return 'role-frontend';
    if (role.includes('DevOps')) return 'role-devops';
    if (role.includes('Overseer')) return 'role-overseer';
    return '';
  }

  function formatRole(role) {
    return (role || 'Unassigned')
      .replace('_Engineer', '')
      .replace('Systems_', 'Sys_');
  }

  function getEventTypeClass(actionType) {
    if (!actionType) return '';
    if (actionType.includes('complete') || actionType.includes('success')) return 'completion';
    if (actionType.includes('denied') || actionType.includes('violation')) return 'denial';
    if (actionType.includes('escalation') || actionType.includes('break_glass')) return 'escalation';
    return '';
  }

  function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
  }

  // --- Exposed for onclick handlers ---
  function _toggleGroup(btn) {
    var cards = btn.nextElementSibling;
    var icon = btn.querySelector('.toggle-icon');
    cards.classList.toggle('collapsed');
    icon.innerHTML = cards.classList.contains('collapsed') ? '&#9654;' : '&#9660;';
  }

  function _toggleHier(btn) {
    var children = btn.nextElementSibling;
    if (!children) return;
    var icon = btn.querySelector('.toggle-icon');
    children.classList.toggle('collapsed');
    icon.innerHTML = children.classList.contains('collapsed') ? '&#9654;' : '&#9660;';
  }

  function _filterMatrix(role, agent) {
    if (matrixFilter && matrixFilter.role === role && (matrixFilter.agent || 'UNASSIGNED') === agent) {
      matrixFilter = null;
    } else {
      matrixFilter = { role: role, agent: agent === 'UNASSIGNED' ? null : agent };
    }
    renderDelegationTree();
    renderSummaryMatrix();
  }

  function _clearFilter() {
    matrixFilter = null;
    renderDelegationTree();
    renderSummaryMatrix();
  }

  function _showTaskDetail(taskId) { showTaskDetail(taskId); }

  return {
    toggle: toggle,
    isActive: isActiveState,
    refresh: refresh,
    switchTab: switchTab,
    _toggleGroup: _toggleGroup,
    _toggleHier: _toggleHier,
    _filterMatrix: _filterMatrix,
    _clearFilter: _clearFilter,
    _showTaskDetail: _showTaskDetail,
  };
})();
