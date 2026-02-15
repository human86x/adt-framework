// Session management — create, switch, close agent sessions
// SPEC-021: Session lifecycle with ADT role/agent identity

const SessionManager = (() => {
  const sessions = new Map();
  let activeSessionId = null;

  
  const ROLE_CLASSES = {
    'Systems_Architect': 'role-architect',
    'Backend_Engineer': 'role-backend',
    'Frontend_Engineer': 'role-frontend',
    'DevOps_Engineer': 'role-devops',
    'Overseer': 'role-overseer'
  };

  const AGENT_COLORS = {
    claude: '#6B7FD7',
    gemini: '#4CAF50',
    custom: '#bc8cff',
  };

  const AGENT_COMMANDS = {
    claude: 'claude',
    gemini: 'gemini',
    custom: 'bash',
  };

  const DEFAULT_SHELL = '/bin/bash';

  async function create(agent, role, specId, customCommand, project) {
    let command = customCommand || AGENT_COMMANDS[agent] || DEFAULT_SHELL;
    let args = [];

    // Special handling for Gemini: use -i for immediate summoning and add --yolo
    // We check agent.toLowerCase() to catch both 'gemini' and custom 'gemini' commands
    if (agent.toLowerCase() === 'gemini' || command === 'gemini') {
      command = 'gemini';
      args = ['-i', `/summon ${role.toLowerCase()}`, '--yolo'];
    } else if (agent.toLowerCase() === 'claude' || command === 'claude') {
      command = 'claude';
      const roleSuffix = role.replace('_Engineer', '').replace('Systems_', '').toLowerCase();
      args = [`/hive-${roleSuffix}`];
    } else if (command.includes(' ')) {
      const parts = command.split(' ');
      command = parts[0];
      args = parts.slice(1);
    }

    const color = AGENT_COLORS[agent] || AGENT_COLORS.custom;

    // Get terminal size from a default
    const size = { cols: 120, rows: 30 };

    let sessionInfo;

    if (window.__TAURI__) {
      try {
        sessionInfo = await window.__TAURI__.core.invoke('create_session', {
          request: {
            agent: agent,
            role: role,
            spec_id: specId,
            command: command,
            args: args,
            cwd: project || null,
            cols: size.cols,
            rows: size.rows,
          }
        });
      } catch (err) {
        console.error('Failed to create session:', err);
        ToastManager.show('denial', 'Session Error', `Failed to spawn ${agent}: ${err}`);
        return null;
      }
    } else {
      // Browser fallback — no real PTY, demo mode
      sessionInfo = {
        id: `session_${Date.now()}`,
        agent: agent,
        role: role,
        spec_id: specId,
        command: command,
        cwd: project,
        alive: true,
      };
    }

    const session = {
      ...sessionInfo,
      color: color,
      startTime: Date.now(),
    };

    sessions.set(session.id, session);

    // Create terminal
    const term = TerminalManager.create(session.id);

    if (!window.__TAURI__) {
      // Browser fallback — show info message and start simulation
      term.write(`\x1b[36mADT Console — Browser Mode (Demo)\x1b[0m\r\n`);
      term.write(`Agent: ${agent} | Role: ${role}\r\n`);
      term.write(`\x1b[90mPTY not available in browser. Simulating activity...\x1b[0m\r\n\r\n`);
      
      startDemoSimulation(session, term);
    }

    // Update UI
    renderTab(session);
    renderSidebarEntry(session);
    switchTo(session.id);
    updateStatusBar();

    return session;
  }

  function startDemoSimulation(session, term) {
    const lines = [
      `Initializing ${session.agent} for ${session.role}...`,
      `Connecting to ADT Center at http://localhost:5001...`,
      `[SUCCESS] Connection established.`,
      `Fetching latest tasks from tasks.json...`,
      `[INFO] Active task found: ${session.role} assignments.`,
      `Loading MASTER_PLAN.md...`,
      `Checking _cortex/ads/events.jsonl integrity...`,
      `[OK] Integrity chain valid.`,
      `Ready for operator instructions.`,
      `$ `
    ];

    let i = 0;
    const interval = setInterval(() => {
      if (!sessions.has(session.id)) {
        clearInterval(interval);
        return;
      }
      if (i < lines.length) {
        term.write(lines[i] + (i < lines.length - 1 ? '\r\n' : ''));
        i++;
      } else {
        // Random "activity" logs
        if (Math.random() > 0.8) {
          term.write(`\r\n\x1b[90m[${new Date().toISOString().substring(11, 19)}] Automated health check pass.\x1b[0m\r\n$ `);
        }
      }
    }, 800);
  }

  function switchTo(sessionId) {
    activeSessionId = sessionId;
    TerminalManager.show(sessionId);

    // Explicitly sync resize on switch to ensure correct terminal rendering
    const size = TerminalManager.getSize(sessionId);
    if (window.__TAURI__ && size) {
      window.__TAURI__.core.invoke('resize_session', {
        sessionId: sessionId,
        cols: size.cols,
        rows: size.rows,
      }).catch(() => {});
    }

    // Update tab active state
    document.querySelectorAll('.session-tab').forEach(tab => {
      tab.classList.toggle('active', tab.dataset.sessionId === sessionId);
    });

    // Update sidebar active state
    document.querySelectorAll('#session-list li').forEach(li => {
      li.classList.toggle('active', li.dataset.sessionId === sessionId);
    });

    // Update context panel
    const session = sessions.get(sessionId);
    if (session) {
      ContextPanel.update(session);
    }

    // Hide empty state
    document.getElementById('empty-state').style.display = 'none';
  }

  async function close(sessionId) {
    if (window.__TAURI__) {
      try {
        await window.__TAURI__.core.invoke('close_session', {
          request: { sessionId: sessionId }
        });
      } catch (err) {
        console.error('Failed to close session:', err);
      }
    }

    TerminalManager.destroy(sessionId);
    sessions.delete(sessionId);

    // Remove UI elements
    document.querySelector(`.session-tab[data-session-id="${sessionId}"]`)?.remove();
    document.querySelector(`#session-list li[data-session-id="${sessionId}"]`)?.remove();

    // Switch to another session or show empty state
    if (activeSessionId === sessionId) {
      const remaining = Array.from(sessions.keys());
      if (remaining.length > 0) {
        switchTo(remaining[remaining.length - 1]);
      } else {
        activeSessionId = null;
        document.getElementById('empty-state').style.display = '';
      }
    }

    updateStatusBar();
  }

  const AGENT_SYMBOLS = {
    claude: '\u263E', // Crescent Moon (blue/purple vibe)
    gemini: '\u263D', // First Quarter Moon (green/teal vibe)
    custom: '\u2328', // Keyboard
  };

  function renderTab(session) {
    const tabsContainer = document.getElementById('session-tabs');
    const tab = document.createElement('button');
    tab.className = 'session-tab';
    tab.dataset.sessionId = session.id;

    const symbol = AGENT_SYMBOLS[session.agent.toLowerCase()] || AGENT_SYMBOLS.custom;
    const roleShort = session.role.replace('_Engineer', '').replace('Systems_', '');
    const roleClass = ROLE_CLASSES[session.role] || '';
    tab.innerHTML = `
      <span class="tab-indicator" style="background:${session.color}"></span>
      <span class="${roleClass}" style="font-weight:700;margin-right:4px">${roleShort}</span>
      <span class="agent-badge" style="color:${session.color}">${session.agent.toUpperCase()}</span>
      <button class="tab-close" title="Close">&times;</button>
    `;

    tab.addEventListener('click', (e) => {
      if (e.target.classList.contains('tab-close')) {
        close(session.id);
      } else {
        switchTo(session.id);
      }
    });

    tabsContainer.appendChild(tab);
  }

  function renderSidebarEntry(session) {
    const list = document.getElementById('session-list');
    const li = document.createElement('li');
    li.dataset.sessionId = session.id;
    const roleClass = ROLE_CLASSES[session.role] || '';
    li.innerHTML = `
      <span class="session-role ${roleClass}">${session.role}</span>
      <span class="session-agent">
        <span class="tab-symbol" style="color:${session.color};font-size:10px">${AGENT_SYMBOLS[session.agent.toLowerCase()] || ''}</span>
        ${session.agent.toUpperCase()}
      </span>
      <span class="session-status">active</span>
    `;
    li.addEventListener('click', () => switchTo(session.id));
    list.appendChild(li);
  }

  function updateStatusBar() {
    document.getElementById('status-sessions').textContent = `Sessions: ${sessions.size}`;
  }

  function getActive() {
    return activeSessionId ? sessions.get(activeSessionId) : null;
  }

  function getAll() {
    return Array.from(sessions.values());
  }

  async function restore() {
    if (!window.__TAURI__) return;

    try {
      const activeSessions = await window.__TAURI__.core.invoke("list_sessions");
      for (const info of activeSessions) {
        if (!sessions.has(info.id)) {
          const color = AGENT_COLORS[info.agent.toLowerCase()] || AGENT_COLORS.custom;
          const session = {
            ...info,
            color: color,
            startTime: Date.now(),
          };
          sessions.set(session.id, session);
          TerminalManager.create(session.id);
          renderTab(session);
          renderSidebarEntry(session);
        }
      }

      if (sessions.size > 0 && !activeSessionId) {
        const lastSessionId = Array.from(sessions.keys()).pop();
        switchTo(lastSessionId);
      }
      updateStatusBar();
    } catch (err) {
      console.error("Failed to restore sessions:", err);
    }
  }

  return { create, switchTo, close, getActive, getAll, updateStatusBar, restore };
})();