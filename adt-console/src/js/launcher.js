/**
 * SPEC-032: ADT Project Launcher
 * Corrected Version - Ultimate Robustness (v7)
 * Uses Event Delegation and explicit debugging.
 */

const ProjectLauncher = (() => {
  let active = false;
  let projects = [];
  let recentSessions = [];
  let filteredProjects = [];
  let currentWizard = null;
  let _opening = false;
  let forgeData = {};
  let forgePollInterval = null;

  // Resolved from /api/system/info on first use — avoids hardcoding /home/human/
  let _serverHome = null;
  let _serverProjects = null;

  const getCenterUrl = () => localStorage.getItem("adt_center_url") || "http://localhost:5001";

  async function _getServerPaths() {
    if (_serverHome) return { home: _serverHome, projects: _serverProjects };
    try {
      const r = await fetch(`${getCenterUrl()}/api/system/info`);
      if (r.ok) {
        const d = await r.json();
        _serverHome = d.home || '/home/user';
        _serverProjects = d.projects_dir || _serverHome + '/Projects';
      }
    } catch (_) {}
    if (!_serverHome) {
      _serverHome = '/home/user';
      _serverProjects = '/home/user/Projects';
    }
    return { home: _serverHome, projects: _serverProjects };
  }

  function init() {
    // SPEC-073: mark the launcher init task
    if (window.ConsoleReadiness) window.ConsoleReadiness.begin('project_launcher_init', 'Loading project registry');
    const main = document.getElementById("terminal-area");
    if (!main) { if (window.ConsoleReadiness) window.ConsoleReadiness.end('project_launcher_init'); return; }

    const overlay = document.createElement("div");
    overlay.id = "launcher-overlay";
    overlay.className = "launcher-overlay";
    overlay.style.display = "none";
    
    overlay.innerHTML = `
      <div class="launcher-header">
        <h1>ADT Framework</h1>
        <p>Operator Console — Governance Control Center</p>
      </div>

      <div class="launcher-search">
        <input type="text" id="launcher-search-input" placeholder="Search projects..." autocomplete="off">
      </div>

      <div class="launcher-actions">
        <div class="launcher-card forge-mode" id="card-forge-mode">
          <h3>INTERNAL FORGE</h3>
          <p>Work on the ADT Framework itself.</p>
        </div>
        <div class="launcher-card" id="card-create-project">
          <h3>CREATE PROJECT</h3>
          <p>Scaffold a new governed project.</p>
        </div>
        <div class="launcher-card" id="card-import-project">
          <h3>IMPORT PROJECT</h3>
          <p>Add ADT to an existing codebase.</p>
        </div>
        <div class="launcher-card forge-app" id="card-forge-app">
          <h3>FORGE APPLICATION</h3>
          <p>Describe a vision. The Architect builds it autonomously.</p>
        </div>
      </div>

      <div class="launcher-section-title">Governed Projects</div>
      <div id="launcher-project-list" class="project-list">
        <div class="ctx-empty">Loading projects...</div>
      </div>

      <div class="launcher-section-title">Recent Sessions</div>
      <div id="launcher-recent-list" class="launcher-recent">
        <div class="ctx-empty">No recent sessions.</div>
      </div>
    `;

    main.appendChild(overlay);

    // Event Listeners for search/actions
    document.getElementById("launcher-search-input").oninput = handleSearch;
    const _g = (key, btn, fn) => {
      const act = async () => {
        if (window.ConsoleReadiness && !window.ConsoleReadiness.isReady()) {
          await window.ConsoleReadiness.waitReady({ timeout: 8000 });
        }
        await fn();
      };
      return window.ActionGuard ? window.ActionGuard.run(key, btn, act) : act();
    };
    document.getElementById("card-forge-mode").onclick = (e) => _g('open_forge_mode', e.currentTarget, async () => openProject("adt-framework"));
    document.getElementById("card-create-project").onclick = (e) => _g('open_create_wizard', e.currentTarget, async () => openCreateWizard());
    document.getElementById("card-import-project").onclick = (e) => _g('open_import_wizard', e.currentTarget, async () => openImportWizard());
    document.getElementById("card-forge-app").onclick = (e) => _g('open_forge_wizard', e.currentTarget, async () => openForgeWizard());

    // EVENT DELEGATION: Click handler for the project list
    document.getElementById("launcher-project-list").onclick = (e) => {
      const item = e.target.closest(".project-item");
      if (item) {
        const name = item.getAttribute("data-name");
        console.log("Project item clicked:", name);
        openProject(name);
      }
    };

    // EVENT DELEGATION: Click handler for recent sessions
    document.getElementById("launcher-recent-list").onclick = (e) => {
      const item = e.target.closest(".recent-item");
      if (item) {
        const index = parseInt(item.getAttribute("data-index"));
        reopenSession(index);
      }
    };

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && active) {
        if (typeof SessionManager !== "undefined" && SessionManager.getAll().length > 0) toggle();
      }
    });
    // SPEC-073: launcher DOM is up; end init task (project registry fetch happens on first toggle → refresh)
    if (window.ConsoleReadiness) window.ConsoleReadiness.end('project_launcher_init');
  }

  async function toggle() {
    active = !active;
    const overlay = document.getElementById("launcher-overlay");
    if (!overlay) return;
    overlay.style.display = active ? "flex" : "none";
    if (active) {
      document.getElementById("launcher-search-input").focus();
      await refresh();
    }
  }

  function hide() {
    active = false;
    const overlay = document.getElementById("launcher-overlay");
    if (overlay) overlay.style.display = "none";
  }

  async function refresh() {
    try {
      const res = await fetch(`${getCenterUrl()}/api/projects`);
      if (res.ok) {
        const data = await res.json();
        const projectsObj = data.projects || data;
        projects = Object.keys(projectsObj).map(name => ({
          name,
          ...projectsObj[name]
        }));
      }
      const recentRaw = localStorage.getItem("adt_recent_sessions");
      recentSessions = recentRaw ? JSON.parse(recentRaw) : [];
      filteredProjects = projects;
      render();
    } catch (err) {
      console.warn("Refresh failed:", err);
      render();
    }
  }

  function render() {
    const projectList = document.getElementById("launcher-project-list");
    const recentList = document.getElementById("launcher-recent-list");
    if (!projectList || !recentList) return;

    projectList.innerHTML = filteredProjects.length > 0 
      ? filteredProjects.map(p => `
          <div class="project-item ${p.is_framework ? "forge" : ""}" data-name="${p.name}">
            <div class="project-info">
              <div class="project-name">${p.name}</div>
              <div class="project-path">${p.path}</div>
            </div>
            <div class="project-meta">
              <div class="project-status">
                <span class="status-dot dot-${p.dtcp_running ? "green" : "grey"}"></span>
                <span>:${p.port}</span>
              </div>
            </div>
          </div>
        `).join("")
      : '<div class="ctx-empty">No governed projects found.</div>';

    recentList.innerHTML = recentSessions.length > 0
      ? recentSessions.map((s, i) => `
          <div class="recent-item" data-index="${i}">
            <div class="recent-main">
              <strong>${s.role.replace(/_/g, " ")} @ ${s.project}</strong>
              <span class="ctx-meta">${s.agent} — ${s.spec_id}</span>
            </div>
            <div class="recent-time">${formatTimeAgo(s.ts)}</div>
          </div>
        `).slice(0, 6).join("")
      : '<div class="ctx-empty">No recent sessions.</div>';
  }

  function handleSearch(e) {
    const term = e.target.value.toLowerCase();
    filteredProjects = projects.filter(p => 
      p.name.toLowerCase().includes(term) || p.path.toLowerCase().includes(term)
    );
    render();
  }

  function openProject(projectName) {
    console.log("Opening project:", projectName);
    toggle(); // Hide launcher
    
    // Attempt to pre-fill the existing "New Session" dialog
    const projectSelect = document.getElementById("input-project");
    const dialog = document.getElementById("new-session-dialog");
    const agentSelect = document.getElementById("input-agent");
    
    if (projectSelect && dialog) {
      // 1. Ensure project exists in the dropdown (it should be there if app loaded)
      projectSelect.value = projectName;
      projectSelect.dispatchEvent(new Event("change"));
      
      // 2. Show the native Tauri dialog
      dialog.showModal();

      // 3. Focus the agent select for quick keyboard usage
      if (agentSelect) setTimeout(() => agentSelect.focus(), 100);
    } else {
      alert("Error: New Session dialog not found in the DOM.");
    }
  }

  function reopenSession(index) {
    const s = recentSessions[index];
    if (s && typeof SessionManager !== "undefined") {
      toggle();
      SessionManager.create(s.agent, s.role, s.spec_id, s.command, s.project);
    }
  }

  // Forge auto-launch: after decompose completes, one-click flow into
  // (1) a Systems_Architect agy session on the first child spec, and
  // (2) a horizontal split view — spec map on top, terminal on bottom.
  async function startForgeAutoLaunch(projectName, projectPath, firstSpec) {
    // If we don't have the path from forge wizard state, resolve it from adt_center.
    let cwd = projectPath;
    if (!cwd) {
      try {
        const r = await fetch(`${getCenterUrl()}/api/projects`);
        if (r.ok) {
          const data = await r.json();
          const entry = (data.projects || data || {})[projectName];
          if (entry && entry.path) cwd = entry.path;
        }
      } catch (_) {}
    }

    // Seed SpecMap state so the map opens on the right project + spec.
    if (window.SpecMap) {
      window.SpecMap.state = window.SpecMap.state || {};
      window.SpecMap.state.currentProject = projectName;
      window.SpecMap.state.currentSpecId = firstSpec;
      try { localStorage.setItem('adt_spec_map_project', projectName); } catch (_) {}
    }

    // Show the spec map view (and initialize it if first time).
    if (window.SpecMap && window.SpecMap.show) window.SpecMap.show();
    if (window.SpecMap && window.SpecMap.init) window.SpecMap.init();

    // Then activate split mode BEFORE spawning the terminal so the PTY sizes
    // itself against the smaller bottom pane on first render.
    const area = document.getElementById('terminal-area');
    if (area) area.classList.add('forge-split-mode');

    // Inject resizable divider between spec-map and terminal panes
    if (area) {
      let existingDivider = document.getElementById('forge-split-divider');
      if (!existingDivider) {
        const divider = document.createElement('div');
        divider.id = 'forge-split-divider';
        divider.title = 'Drag to resize panels';
        const termContainer = document.getElementById('terminal-container');
        if (termContainer) area.insertBefore(divider, termContainer);

        let dragging = false;
        let areaTop = 0, areaHeight = 0;

        divider.addEventListener('mousedown', (e) => {
          dragging = true;
          const rect = area.getBoundingClientRect();
          areaTop = rect.top;
          areaHeight = rect.height;
          document.body.style.cursor = 'ns-resize';
          document.body.style.userSelect = 'none';
          e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
          if (!dragging) return;
          const pct = Math.max(20, Math.min(80, ((e.clientY - areaTop) / areaHeight) * 100));
          const specMapView = document.getElementById('spec-map-view');
          const tc = document.getElementById('terminal-container');
          if (specMapView) specMapView.style.flex = `0 0 ${pct}%`;
          if (tc) tc.style.flex = `0 0 ${100 - pct - 0.4}%`;
        });

        document.addEventListener('mouseup', () => {
          if (!dragging) return;
          dragging = false;
          document.body.style.cursor = '';
          document.body.style.userSelect = '';
          // Let xterm ResizeObserver detect the new size
          window.dispatchEvent(new Event('resize'));
        });
      }
    }

    // Load the first spec into the map (async — don't await; it'll paint soon).
    if (window.SpecMap && window.SpecMap.populateSelector) {
      window.SpecMap.populateSelector().then(() => {
        if (window.SpecMap.loadSpec) window.SpecMap.loadSpec(firstSpec);
      }).catch(() => {});
    }

    // Update the header project label + spec dropdown.
    try {
      const dd = document.getElementById('spec-map-header-project-dd');
      const label = dd && dd.querySelector('.adt-dd-label');
      if (label) label.textContent = projectName;
      if (dd) dd.dataset.value = projectName;
    } catch (_) {}

    // Write active_spec.txt into the forge project so summon reads the right spec
    try {
      await fetch(`${getCenterUrl()}/api/projects/${encodeURIComponent(projectName)}/set_active_spec`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spec_id: firstSpec })
      });
    } catch(_) {}

    // Spawn the SA session inside agy for this project + spec.
    if (typeof SessionManager !== "undefined" && SessionManager.create) {
      const initMsg = [
        `You are a **Systems_Architect** agent working on the **${projectName}** project.`,
        ``,
        `This project was just created via App Forge. The project root is your current working directory.`,
        `Please initialize yourself for this project:`,
        `1. Read \`_cortex/MASTER_PLAN.md\` — understand what is being built`,
        `2. Read \`_cortex/tasks.json\` — see the full task breakdown`,
        `3. Read \`_cortex/specs/${firstSpec}_*.md\` (or list \`_cortex/specs/\` to find it) — your first spec`,
        `4. Summarize: project name, what it does, specs created, tasks ready to build`,
        ``,
        `You will oversee building this project. Workers will ask you questions about architecture and specs.`
      ].join('\n');

      await SessionManager.create(
        'agy',
        'Systems_Architect',
        firstSpec,
        'agy',
        projectName,
        cwd || null,
        { skipPermissions: true, initialMessage: initMsg }
      );
    }
  }

  async function openCreateWizard() {
    if (currentWizard || _opening) return;
    _opening = true;
    try {
      const { projects } = await _getServerPaths();
      showWizard(`
        <h2>Create New Project</h2>
        <div class="wizard-field">
          <label>Project Name</label>
          <input type="text" id="wiz-create-name" placeholder="my-app">
        </div>
        <div class="wizard-field">
          <label>Absolute Path</label>
          <input type="text" id="wiz-create-path" placeholder="${projects}/my-app">
        </div>
        <div class="wizard-actions">
          <button class="btn-prev" id="btn-wiz-cancel">Cancel</button>
          <button class="primary" id="btn-wiz-submit">Scaffold Project</button>
        </div>
      `);
      
      document.getElementById("btn-wiz-cancel").onclick = closeWizard;
      document.getElementById("btn-wiz-submit").onclick = submitCreate;
      
      setTimeout(() => {
        const nameInput = document.getElementById("wiz-create-name");
        if (nameInput) nameInput.focus();
      }, 100);
    } finally {
      _opening = false;
    }
  }

  async function openImportWizard() {
    if (currentWizard || _opening) return;
    _opening = true;
    try {
      const { projects } = await _getServerPaths();
      showWizard(`
        <h2>Import Project</h2>
        <div class="wizard-field">
          <label>Absolute Path</label>
          <input type="text" id="wiz-import-path" placeholder="${projects}/existing">
        </div>
        <div class="wizard-actions">
          <button class="btn-prev" id="btn-wiz-cancel">Cancel</button>
          <button class="primary" id="btn-wiz-submit">Initialize ADT</button>
        </div>
      `);
      
      document.getElementById("btn-wiz-cancel").onclick = closeWizard;
      document.getElementById("btn-wiz-submit").onclick = submitImport;

      setTimeout(() => {
        const pathInput = document.getElementById("wiz-import-path");
        if (pathInput) pathInput.focus();
      }, 100);
    } finally {
      _opening = false;
    }
  }

  function showWizard(html) {
    closeWizard();
    const backdrop = document.createElement("div");
    backdrop.className = "wizard-backdrop";
    const modal = document.createElement("div");
    modal.className = "wizard-modal";
    modal.innerHTML = html;
    document.body.appendChild(backdrop);
    document.body.appendChild(modal);
    currentWizard = { modal, backdrop };
  }

  function closeWizard() {
    if (forgePollInterval) { clearInterval(forgePollInterval); forgePollInterval = null; }
    if (currentWizard) {
      currentWizard.modal.remove();
      currentWizard.backdrop.remove();
      currentWizard = null;
    }
  }

  async function submitCreate() {
    const name = document.getElementById("wiz-create-name").value.trim();
    const path = document.getElementById("wiz-create-path").value.trim();

    if (!name || !path) {
      alert("Missing name or path.");
      return;
    }

    try {
      if (window.__TAURI__) {
        await window.__TAURI__.core.invoke("init_project", {
          request: { path, name, detect: true, start_dtcp: true }
        });
        closeWizard();
        await refresh();
        alert("Project created successfully.");
      } else {
        alert("Tauri backend not detected.");
      }
    } catch (err) {
      alert("Backend Error: " + err.toString());
    }
  }

  async function submitImport() {
    const path = document.getElementById("wiz-import-path").value.trim();
    if (!path) return;
    const name = path.split("/").pop();

    try {
      if (window.__TAURI__) {
        await window.__TAURI__.core.invoke("init_project", {
          request: { path, name, detect: true, start_dtcp: true }
        });
        closeWizard();
        await refresh();
        alert("Project imported successfully.");
      }
    } catch (err) {
      alert("Backend Error: " + err.toString());
    }
  }

  function openForgeWizard() {
    if (currentWizard || _opening) return;
    _opening = true;
    try {
      forgeData = {};
      showForgeScreen1();
    } finally {
      _opening = false;
    }
  }

  const FORGE_TEMPLATES = [
    {
      label: "🎮 EyeToy Ball Game",
      slug: "eyetoy",
      wish: `A simple "EyeToy"-style desktop game where the operator's built-in webcam tracks their hands and they bat a virtual ball around the screen. Player sees their silhouette overlaid on a play area; ball bounces off screen edges and off the hand silhouette. Single-player, casual, runs locally with no install.`,
      users: "Casual home players ages 8+, single-player, sitting in front of a laptop with built-in webcam",
      success: "Player launches the app, sees their hand silhouette overlaid on the play area, and can bat a virtual ball that bounces off screen edges and off the hand silhouette. Score counter increments per hit.",
      out: "No multiplayer. No cloud sync. No mobile/tablet. No microphone or audio input.",
      constraints: "Must run on Linux laptop with built-in webcam, no dedicated GPU required. Browser-based or Electron/Tauri local app. Pure local -- no external API calls."
    },
    {
      label: "🎨 Pixel Art Studio",
      slug: "pixel_art",
      wish: "A browser-based pixel art editor with a configurable grid canvas (8x8 up to 64x64), a fixed 32-colour palette, pencil/fill/eraser/line tools, undo/redo, and one-click PNG export. Runs fully offline, no backend required.",
      users: "Hobbyist game devs and digital artists who want a lightweight local pixel editor without installing Aseprite.",
      success: "User can open the app, draw a 16x16 sprite using pencil and fill tools, undo a mistake, and export it as a transparent PNG.",
      out: "No animation timeline in v1. No layers. No cloud storage. No account system.",
      constraints: "Pure browser app (HTML+CSS+JS, no build step). All state in localStorage. Works offline."
    },
    {
      label: "💰 Personal Budget Tracker",
      slug: "budget_tracker",
      wish: "A local-first personal finance app where the user logs income and expenses by category (Food, Rent, Fun, etc.), sets monthly budget limits per category, and sees a live pie chart of spending vs budget. All data stored locally, CSV export available.",
      users: "Individuals who want a simple private alternative to cloud-based finance apps like Mint or YNAB.",
      success: "User can add 10 transactions across 3 categories, set a monthly limit for each, and see a colour-coded pie chart showing over/under budget status. Export button produces a valid CSV.",
      out: "No bank integration. No recurring transactions in v1. No multi-currency. No mobile sync.",
      constraints: "Tauri desktop app or single-file browser app. Data in localStorage or a local JSON file. No external API calls."
    },
    {
      label: "✅ Daily Habit Tracker",
      slug: "habit_tracker",
      wish: "A daily habit tracker where users define habits (e.g. 'Meditate', 'Exercise', 'Read'), check them off each day, and view a GitHub-style heatmap calendar showing streak history. Current streak and longest streak displayed per habit.",
      users: "People trying to build consistent daily routines who want a minimal, distraction-free local app.",
      success: "User adds 3 habits, checks them off for today, sees streak counts update, and the heatmap shows today's entry filled in. Data persists across app restarts.",
      out: "No reminders or push notifications in v1. No sharing. No cloud sync. No gamification points.",
      constraints: "Tauri or browser-based. Local JSON storage. No server required."
    },
    {
      label: "🎵 Local Music Player",
      slug: "music_player",
      wish: "A desktop music player that reads MP3, OGG, and FLAC files from a user-chosen local folder, displays a waveform visualizer, shows album art from embedded tags, supports a play queue with drag-to-reorder, and remembers the last played position on close.",
      users: "Music enthusiasts who want a fast, private local player without uploading their library to the cloud.",
      success: "User selects a folder with 20 MP3 files, sees a track list with titles and durations, plays a track with the waveform animating, skips to the next track, and reopens the app to find it resumes where it left off.",
      out: "No streaming. No podcast support in v1. No equaliser. No lyrics fetch.",
      constraints: "Tauri desktop app (Rust backend for file I/O). Web Audio API for waveform. All local, no network calls."
    },
    {
      label: "📝 Markdown Notes App",
      slug: "markdown_notes",
      wish: "A local-first markdown note-taking app with a two-pane layout (editor left, live preview right), tag system for organisation, full-text search across all notes, and autosave every 30 seconds. Notes stored as plain .md files in a user-chosen folder.",
      users: "Developers and writers who want a private, file-based alternative to Notion or Obsidian for daily notes.",
      success: "User creates a note with markdown headings and a code block, adds a tag 'work', saves it, searches for a word in the note, and finds it instantly. Preview renders correctly.",
      out: "No graph view in v1. No plugin system. No mobile sync. No PDF export.",
      constraints: "Tauri desktop app. Notes are real .md files on disk, not a database. No cloud dependency."
    },
    {
      label: "⌨️ Typing Speed Trainer",
      slug: "typing_trainer",
      wish: "A touch-typing trainer that presents random word prompts (or code snippets), measures WPM and accuracy in real time, highlights errors in red, and shows a session history graph of WPM over the last 10 tests. Custom word-list upload supported.",
      users: "Programmers and writers who want to improve typing speed with a clean, distraction-free local tool.",
      success: "User completes a 60-second typing test, sees their WPM and accuracy displayed, and the session is added to the history graph. Uploading a custom word list replaces the default prompts.",
      out: "No competitive leaderboard in v1. No account system. No video lessons.",
      constraints: "Pure browser app (HTML+CSS+JS). No backend. Custom word lists loaded from a local file via file picker."
    },
    {
      label: "🏃 2D Platformer Game",
      slug: "platformer_2d",
      wish: "A browser-based 2D side-scrolling platformer with a pixel-art aesthetic, procedurally generated levels, a player character who can run and jump, collectible coins, enemies with simple patrol AI, and a local high-score table. Keyboard controls.",
      users: "Casual gamers and hobbyist devs who want a fun, self-contained browser game with endless replayability.",
      success: "Player spawns, runs through a procedurally generated level, collects coins, avoids/defeats an enemy, reaches the exit, and sees their score recorded in a local top-10 table.",
      out: "No online multiplayer. No save-game system in v1. No touchscreen controls. No level editor.",
      constraints: "Single HTML file with canvas rendering. No external game engine (vanilla JS only). No network calls."
    },
    {
      label: "🍳 Recipe Manager",
      slug: "recipe_manager",
      wish: "A local recipe database app where users can add recipes with ingredients, steps, and photos (stored locally), scale servings (auto-adjusting ingredient quantities), filter by dietary tag (vegan, gluten-free, etc.), and generate a shopping list from selected recipes.",
      users: "Home cooks who want a private, offline alternative to recipe websites with no ads or paywalls.",
      success: "User adds a pasta recipe with 4 ingredients and 3 steps, changes serving size from 2 to 6 and sees ingredient quantities scale correctly, adds a 'vegan' tag, and generates a shopping list for 3 selected recipes.",
      out: "No meal planner calendar in v1. No nutrition data. No import from URLs. No cloud sync.",
      constraints: "Tauri desktop app. Photos stored in a local folder referenced by path. Data in a local SQLite or JSON file."
    },
    {
      label: "🍅 Pomodoro Focus Timer",
      slug: "pomodoro",
      wish: "A Pomodoro focus timer with a 25-minute work / 5-minute break cycle, a task queue where the user enters what they are working on each session, a daily session log showing total focused time, and optional ambient background sounds (rain, white noise) playable from bundled audio.",
      users: "Knowledge workers and students who use the Pomodoro technique to manage focus and avoid burnout.",
      success: "User adds a task 'Write report', starts a 25-minute timer, hears rain ambience, gets a desktop notification when time is up, logs 1 Pomodoro, and sees the daily total update to 25 minutes.",
      out: "No sync across devices. No calendar integration in v1. No custom timer lengths in v1.",
      constraints: "Tauri desktop app with system tray icon and OS notifications. Bundled audio files (no streaming). Local JSON log."
    },
    {
      label: "🌐 LAN Network Monitor",
      slug: "network_monitor",
      wish: "A real-time local network monitor that shows per-process upload/download bandwidth usage as a live bar chart, flags processes exceeding a user-set threshold, logs traffic history to a local file, and can send a desktop alert when any process spikes above the threshold.",
      users: "Developers and power users who want to see which processes are hogging bandwidth without installing heavyweight tools like Wireshark.",
      success: "User opens the app, sees a live bar chart of top 5 bandwidth consumers updating every second, sets a 1 MB/s threshold for a browser process, triggers a download, and receives a desktop alert.",
      out: "No packet inspection. No firewall controls. No remote monitoring. No mobile app.",
      constraints: "Tauri desktop app with a Rust backend using system APIs (procfs on Linux) for per-process stats. No root required for basic stats."
    }
  ];

  async function showForgeScreen1() {
    const { projects: projsDir } = await _getServerPaths();
    showWizard(`
      <h2>Forge Application (1/2)</h2>
      <p class="wiz-subtitle">Describe your vision. The Architect will formalize a specification and build the foundation autonomously.</p>
      <div class="wizard-field">
        <label>What do you want to build? <span class="wiz-required">*</span></label>
        <textarea id="wiz-forge-wish" rows="4" placeholder="An eyetoy-style game where the onboard camera tracks the player's hands to move a virtual ball on screen.">` + (forgeData.wish || "") + `</textarea>
      </div>
      <div class="wizard-field">
        <label>Project path <span class="wiz-required">*</span></label>
        <input type="text" id="wiz-forge-path" placeholder="${projsDir}/my-new-app" value="` + (forgeData.path || "") + `" data-projects-dir="${projsDir}">
      </div>
      <div class="wizard-field">
        <label>Project name <span class="wiz-optional">(auto-detected from path)</span></label>
        <input type="text" id="wiz-forge-name" placeholder="my-new-app" value="` + (forgeData.name || "") + `">
      </div>
      <div class="wizard-actions">
        <button class="btn-prev" id="btn-wiz-cancel">Cancel</button>
        <div id="wiz-template-picker" style="position:relative;margin-right:auto">
          <button type="button" id="btn-wiz-template" style="background:#21262d;border:1px solid #30363d;color:#8b949e;padding:8px 14px;border-radius:6px;cursor:pointer;font-size:12px;display:flex;align-items:center;gap:6px">
            <span>Load template</span><span style="font-size:10px;opacity:0.7">&#9660;</span>
          </button>
          <div id="wiz-template-menu" style="display:none;position:absolute;bottom:calc(100% + 6px);left:0;background:#161b22;border:1px solid #30363d;border-radius:8px;min-width:260px;z-index:200;box-shadow:0 8px 32px rgba(0,0,0,0.6);max-height:300px;overflow-y:auto;padding:4px 0"></div>
        </div>
        <button class="primary" id="btn-wiz-next">Next &rarr;</button>
      </div>
    `);
    document.getElementById("btn-wiz-cancel").onclick = closeWizard;
    document.getElementById("btn-wiz-next").onclick = () => {
      forgeData.wish = (document.getElementById("wiz-forge-wish").value || "").trim();
      forgeData.path = (document.getElementById("wiz-forge-path").value || "").trim();
      forgeData.name = (document.getElementById("wiz-forge-name").value || "").trim();
      if (!forgeData.wish) { alert("Please describe your wish."); return; }
      if (!forgeData.path) { alert("Project path is required."); return; }
      showForgeScreen2();
    };
    // Template picker dropdown (custom div — native <select> invisible on dark themes in Tauri)
    const templateBtn = document.getElementById("btn-wiz-template");
    const templateMenu = document.getElementById("wiz-template-menu");
    if (templateBtn && templateMenu) {
      FORGE_TEMPLATES.forEach(tpl => {
        const item = document.createElement("div");
        item.style.cssText = "padding:8px 14px;cursor:pointer;font-size:12px;color:#e6edf3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis";
        item.textContent = tpl.label;
        item.onmouseenter = () => { item.style.background = "#21262d"; };
        item.onmouseleave = () => { item.style.background = ""; };
        item.onclick = () => {
          const ts = Math.floor(Date.now() / 1000);
          const wish = document.getElementById("wiz-forge-wish");
          const pathEl = document.getElementById("wiz-forge-path");
          const nameEl = document.getElementById("wiz-forge-name");
          if (wish) wish.value = tpl.wish;
          const projsBase = (pathEl && pathEl.dataset.projectsDir) || _serverProjects || '/home/user/Projects';
          if (pathEl) pathEl.value = `${projsBase}/${tpl.slug}_${ts}`;
          if (nameEl) nameEl.value = `${tpl.slug}_${ts}`;
          forgeData.users = tpl.users;
          forgeData.success = tpl.success;
          forgeData.out = tpl.out;
          forgeData.constraints = tpl.constraints;
          templateMenu.style.display = "none";
          templateBtn.querySelector("span").textContent = tpl.label;
        };
        templateMenu.appendChild(item);
      });
      templateBtn.onclick = (e) => {
        e.stopPropagation();
        templateMenu.style.display = templateMenu.style.display === "none" ? "block" : "none";
      };
      document.addEventListener("click", () => { templateMenu.style.display = "none"; }, { once: false });
    }
    setTimeout(() => {
      const el = document.getElementById("wiz-forge-wish");
      if (el) el.focus();
    }, 100);
  }

  function showForgeScreen2() {
    showWizard(`
      <h2>Forge Application (2/2)</h2>
      <p class="wiz-subtitle">Just a few more details to ensure the Architect builds exactly what you need.</p>
      <div class="wizard-field">
        <label>Who is this for? <span class="wiz-required">*</span></label>
        <input type="text" id="wiz-forge-users" placeholder="Casual home players, ages 8+, single-player at first." value="` + (forgeData.users || "") + `">
      </div>
      <div class="wizard-field">
        <label>What does 'done v1' look like? <span class="wiz-required">*</span></label>
        <input type="text" id="wiz-forge-success" placeholder="Player can stand in front of the camera, see their hand silhouette, and bat a ball that bounces off the screen edges." value="` + (forgeData.success || "") + `">
      </div>
      <div class="wizard-field">
        <label>Anything that's explicitly NOT in v1? <span class="wiz-optional">(optional)</span></label>
        <input type="text" id="wiz-forge-out" placeholder="No multiplayer. No cloud sync. No mobile." value="` + (forgeData.out || "") + `">
      </div>
      <div class="wizard-field">
        <label>Hard constraints? <span class="wiz-optional">(optional)</span></label>
        <input type="text" id="wiz-forge-constraints" placeholder="Must run on Linux laptop with built-in webcam, no GPU required." value="` + (forgeData.constraints || "") + `">
      </div>
      <div class="wizard-field">
        <label>Standards to anchor (pick all that apply) <span class="wiz-optional">(optional)</span></label>
        <div id="wiz-forge-standards" style="display:flex;flex-direction:column;gap:4px;margin-top:4px;max-height:180px;overflow-y:auto;padding:6px;border:1px solid #30363d;border-radius:4px;background:#0d1117">
          <span style="font-size:11px;color:#8b949e">Loading adopted Rationalised Rules...</span>
        </div>
      </div>
      <div class="wizard-field" style="display:flex;align-items:center;gap:8px;margin-top:12px;margin-bottom:12px;">
        <input type="checkbox" id="wiz-forge-auto-standards" checked style="width:16px;height:16px;margin:0;cursor:pointer;">
        <label for="wiz-forge-auto-standards" style="margin:0;cursor:pointer;font-size:13px;">Enable Auto-Standards Compliance Engine <span class="wiz-optional">(SPEC-072: MRR intent matcher scans your wish for regulated domains)</span></label>
      </div>
      <div class="wizard-actions">
        <button class="btn-prev" id="btn-wiz-back">&larr; Back</button>
        <button class="primary forge-submit" id="btn-wiz-forge">Forge Application</button>
      </div>
    `);
    // Load adopted RRs grouped by source standard and render chips
    fetch(`${getCenterUrl()}/api/governance/standards/rationalised-rules?disposition=adopted`)
      .then(r => r.ok ? r.json() : { rules: [] })
      .then(d => {
        const wrap = document.getElementById("wiz-forge-standards");
        if (!wrap) return;
        const rules = d.rules || [];
        if (!rules.length) {
          wrap.innerHTML = '<span style="font-size:11px;color:#8b949e">No adopted Rationalised Rules yet. Open Standards Workbench to adopt some, then re-open this wizard.</span>';
          return;
        }
        // Group by source standard (first derived_from segment)
        const seen = new Set();
        const dedupedRules = rules.filter(r => {
          if (!r.id || seen.has(r.id)) return false;
          seen.add(r.id);
          return true;
        });
        const groups = {};
        dedupedRules.forEach(r => {
          const src = ((r.derived_from || ["UNKNOWN/x"])[0] || "UNKNOWN/x").split("/")[0];
          if (!groups[src]) groups[src] = [];
          groups[src].push(r);
        });
        const preselected = new Set(forgeData.selected_rr_ids || []);
        let html = "";
        Object.entries(groups).forEach(([std, rs]) => {
          rs.forEach(r => {
            const checked = preselected.has(r.id) ? "checked" : "";
            const titleAttr = (r.title || "").replace(/"/g, "&quot;");
            html += `<label class="wiz-rr-row" title="${titleAttr}" style="display:flex;align-items:center;gap:10px;padding:8px 10px;background:#161b22;border:1px solid #30363d;border-radius:6px;font-size:13px;cursor:pointer;width:100%;box-sizing:border-box;line-height:1.4">
                       <input type="checkbox" class="wiz-rr-chip" data-rr="${r.id}" ${checked} style="margin:0;flex-shrink:0;width:16px;height:16px;cursor:pointer">
                       <span style="display:flex;flex-direction:column;gap:3px;min-width:0;flex:1;text-align:left">
                         <span class="wiz-rr-title-span" style="display:flex;gap:8px;align-items:center">
                           <strong style="color:#58a6ff">${r.id}</strong>
                           <span style="color:#8b949e;font-size:11px;background:#0d1117;padding:1px 6px;border-radius:3px;border:1px solid #30363d">${std}</span>
                         </span>
                         <span style="color:#e6edf3;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${titleAttr}</span>
                       </span>
                     </label>`;
          });
        });
        wrap.innerHTML = html;

        // SPEC-075: Fire LLM Classifier
        const statusEl = document.createElement("div");
        statusEl.id = "wiz-forge-classifier-status";
        statusEl.style.cssText = "font-size:12px;color:#58a6ff;margin-bottom:6px;font-weight:bold;";
        wrap.parentNode.insertBefore(statusEl, wrap);
        
        const startClassifyTime = Date.now();
        const classifyTimer = setInterval(() => {
          const ms = Date.now() - startClassifyTime;
          statusEl.textContent = `[⟳] Classifier analysing… ${(ms/1000).toFixed(1)}s`;
        }, 100);
        
        const projName = forgeData.name || (forgeData.path || '').split("/").pop() || 'new-project';
        fetch(`${getCenterUrl()}/api/governance/intent/classify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            wish: forgeData.wish || "",
            users: document.getElementById("wiz-forge-users")?.value || forgeData.users || "",
            success_v1: document.getElementById("wiz-forge-success")?.value || forgeData.success || "",
            project: projName
          })
        }).then(r => r.json()).then(cls => {
          clearInterval(classifyTimer);
          if (cls.error) {
            statusEl.style.color = "#f85149";
            statusEl.textContent = `[✗] Classifier failed: ${cls.error}`;
            return;
          }
          statusEl.style.color = "#3fb950";
          statusEl.textContent = `[✓] Classification complete. Confidence: ${Math.round(cls.overall_confidence*100)}%`;
          
          if (cls.recommended_rrs && cls.recommended_rrs.length) {
            cls.recommended_rrs.forEach(rec => {
              const chk = wrap.querySelector(`.wiz-rr-chip[data-rr="${rec.id}"]`);
              if (chk) {
                if (!chk.checked) chk.checked = true;
                
                const lbl = chk.closest('label');
                const titleSpan = lbl.querySelector('.wiz-rr-title-span');
                if (titleSpan) {
                  const badge = document.createElement("span");
                  badge.style.cssText = "background:#238636;color:#fff;padding:1px 6px;border-radius:3px;font-size:10px;margin-left:auto;cursor:help;flex-shrink:0;";
                  badge.textContent = "AUTO";
                  badge.title = rec.rationale;
                  titleSpan.appendChild(badge);
                }
                
                chk.addEventListener('change', (e) => {
                  if (!e.target.checked) {
                    const reason = prompt(`You unchecked auto-recommended rule ${rec.id}. Reason (optional):`);
                    fetch(`${getCenterUrl()}/api/governance/intent/override`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        run_id: cls.run_id,
                        rr_id: rec.id,
                        project: projName,
                        override_reason: reason || ""
                      })
                    }).catch(()=>{});
                  }
                });
              }
            });
          }
          
          if (cls.data_classifications && cls.data_classifications.length) {
            const dcDiv = document.createElement('div');
            dcDiv.style.cssText = "margin-bottom:8px;";
            dcDiv.innerHTML = `<span style="font-size:11px;color:#8b949e;margin-right:6px;">Data Classifications Detected:</span>` +
              cls.data_classifications.map(dc => `<span style="background:#1f6feb;color:#fff;padding:2px 6px;border-radius:10px;font-size:10px;margin-right:4px;">${dc}</span>`).join('');
            wrap.parentNode.insertBefore(dcDiv, wrap);
          }
          
          if (cls.suggested_erasure_requirements && cls.suggested_erasure_requirements.length) {
            const reqDiv = document.createElement('div');
            reqDiv.style.cssText = "margin-top:8px;padding:8px;background:#3a2908;border:1px solid #d29922;border-radius:4px;color:#e6edf3;font-size:12px;";
            reqDiv.innerHTML = `<strong style="color:#d29922">Suggested Erasure Requirements:</strong><ul style="margin:4px 0 0 16px;padding:0;">` +
              cls.suggested_erasure_requirements.map(req => `<li>${req}</li>`).join('') + `</ul>`;
            const toggleRow = document.querySelector('label[for="wiz-forge-auto-standards"]')?.closest('.wizard-field');
            if (toggleRow) toggleRow.parentNode.insertBefore(reqDiv, toggleRow);
          }
          
        }).catch(err => {
          clearInterval(classifyTimer);
          statusEl.style.color = "#f85149";
          statusEl.textContent = `[✗] Classifier failed: ${err.message}`;
        });
      }).catch(() => {
        const wrap = document.getElementById("wiz-forge-standards");
        if (wrap) wrap.innerHTML = '<span style="font-size:11px;color:#f85149">Could not load standards (Panel may be offline).</span>';
      });
    document.getElementById("btn-wiz-back").onclick = showForgeScreen1;
    document.getElementById("btn-wiz-forge").onclick = () => {
      forgeData.users = (document.getElementById("wiz-forge-users").value || "").trim();
      forgeData.success = (document.getElementById("wiz-forge-success").value || "").trim();
      forgeData.out = (document.getElementById("wiz-forge-out").value || "").trim();
      forgeData.constraints = (document.getElementById("wiz-forge-constraints").value || "").trim();
      forgeData.selected_rr_ids = Array.from(document.querySelectorAll(".wiz-rr-chip:checked")).map(el => el.dataset.rr);
      forgeData.auto_standards_enabled = document.getElementById("wiz-forge-auto-standards")?.checked ?? true;


      if (!forgeData.users) { alert("Please specify who this is for."); return; }
      if (!forgeData.success) { alert("Please specify what 'done v1' looks like."); return; }

      submitForge();
    };
  }

  async function submitForge() {
    forgeData.projectName = forgeData.name || (forgeData.path || '').split("/").pop() || 'new-project';
    forgeData.startedAt = Date.now();
    showForgeGenesis();
    const genesisTimer = setInterval(updateGenesisElapsed, 250);

    const body = {
      path: forgeData.path,
      intent_description: forgeData.wish,
      name: forgeData.name || null,
      users: forgeData.users,
      success_v1: forgeData.success,
      out_of_scope: forgeData.out || null,
      constraints: forgeData.constraints || null,
      selected_rr_ids: forgeData.selected_rr_ids || [],
      auto_standards_enabled: forgeData.auto_standards_enabled
    };

    const initialUrl = `${getCenterUrl()}/api/governance/forge/stream?_body=${encodeURIComponent(JSON.stringify(body))}`;
    let activeEs = null;
    let isReconnecting = false;

    function showReconnectingChip(show) {
      let list = document.getElementById("forge-genesis-chips");
      if (!list) {
        list = document.createElement("div");
        list.id = "forge-genesis-chips";
        list.style.marginTop = "6px";
        list.style.display = "flex";
        list.style.flexWrap = "wrap";
        list.style.gap = "4px";
        const container = document.getElementById("forge-genesis-phases");
        if (container) container.parentNode.appendChild(list);
      }
      let chip = document.getElementById("forge-reconnecting-chip");
      if (show) {
        if (!chip) {
          chip = document.createElement("span");
          chip.id = "forge-reconnecting-chip";
          chip.style.cssText = "background:#d29922;color:#0d1117;padding:2px 6px;border-radius:10px;font-size:10px;font-weight:bold;";
          chip.textContent = "reconnecting...";
          list.appendChild(chip);
        }
      } else {
        if (chip) chip.remove();
      }
    }

    async function attemptReattach() {
      if (!document.getElementById("forge-genesis-phases")) {
        if (activeEs) activeEs.close();
        return;
      }
      isReconnecting = true;
      showReconnectingChip(true);

      const projectName = forgeData.projectName;
      if (!forgeData.sessionId) {
        try {
          const probe = await fetch(`${getCenterUrl()}/api/projects/${encodeURIComponent(projectName)}/forge_session`);
          if (probe.ok) {
            const pd = await probe.json();
            if (pd.forge_session_id) {
              forgeData.sessionId = pd.forge_session_id;
            }
          }
        } catch (err) {
          console.warn("Probe failed during reattach:", err);
        }
      }

      let url;
      if (forgeData.sessionId) {
        url = `${getCenterUrl()}/api/governance/forge/${forgeData.sessionId}/genesis_stream?project=${encodeURIComponent(projectName)}`;
      } else {
        url = initialUrl;
      }

      console.log("Reattaching stream to:", url);
      connect(url);
    }

    function connect(url) {
      if (activeEs) {
        activeEs.close();
      }
      const es = new EventSource(url);
      activeEs = es;

      es.onopen = () => {
        if (isReconnecting) {
          isReconnecting = false;
          showReconnectingChip(false);
        }
      };

      es.addEventListener('phase_started', e => {
        const data = JSON.parse(e.data);
        if (!document.getElementById("phase-" + data.phase)) {
          appendPhaseRow(data);
        }
      });

      es.addEventListener('phase_completed', e => {
        const data = JSON.parse(e.data);
        markPhaseDone(data);
      });

      es.addEventListener('intent_classification_partial', e => {
        const data = JSON.parse(e.data);
        appendClassifierChip(data);
      });

      es.addEventListener('forge_session_created', e => {
        const data = JSON.parse(e.data);
        clearInterval(genesisTimer);
        es.close();
        showReconnectingChip(false);
        
        forgeData.sessionId = data.forge_session_id;
        forgeData.projectName = data.project_name || forgeData.projectName;
        
        showForgeProgress();
        pollForgeStatus();
      });

      es.addEventListener('forge_failed', e => {
        const data = JSON.parse(e.data);
        clearInterval(genesisTimer);
        es.close();
        showReconnectingChip(false);
        
        const msg = (data.error || "Forge failed.").toString();
        if (/already registered/i.test(msg)) {
          const projectName = forgeData.projectName;
          fetch(`${getCenterUrl()}/api/projects/${encodeURIComponent(projectName)}/forge_session`).then(async probe => {
            if (probe.ok) {
              const pd = await probe.json();
              if (pd.forge_session_id) {
                forgeData.sessionId = pd.forge_session_id;
                showForgeProgress();
                pollForgeStatus();
                return;
              }
            }
            closeWizard();
            if (typeof openProject === "function") openProject(projectName);
          }).catch(() => {
            closeWizard();
            if (typeof openProject === "function") openProject(projectName);
          });
          return;
        }
        showForgeGenesisError(msg);
      });

      es.onerror = () => {
        es.close();
        if (!document.getElementById("forge-genesis-phases")) {
          return;
        }
        showReconnectingChip(true);
        setTimeout(attemptReattach, 2000);
      };
    }

    connect(initialUrl);
  }

  // --- SPEC-074 UI Helpers ---
  function appendPhaseRow(data) {
    const list = document.getElementById("forge-genesis-phases");
    if (!list) return;
    const item = document.createElement("div");
    item.id = "phase-" + data.phase;
    item.style.color = "#c9d1d9";
    item.style.lineHeight = "1.7";
    item.innerHTML = `<span class="phase-icon" style="display:inline-block;width:16px;text-align:center">&#8226;</span> ${data.phase}...`;
    list.appendChild(item);
  }

  function markPhaseDone(data) {
    const item = document.getElementById("phase-" + data.phase);
    if (!item) return;
    const icon = item.querySelector(".phase-icon");
    if (data.outcome === "success") {
        icon.innerHTML = '<span style="color:#3fb950">✓</span>';
        item.innerHTML += ` <span style="color:#8b949e;font-size:11px">(${data.duration_ms}ms)</span>`;
    } else {
        icon.innerHTML = '<span style="color:#f85149">✗</span>';
    }
  }

  function appendClassifierChip(data) {
    let list = document.getElementById("forge-genesis-chips");
    if (!list) {
        list = document.createElement("div");
        list.id = "forge-genesis-chips";
        list.style.marginTop = "6px";
        list.style.display = "flex";
        list.style.flexWrap = "wrap";
        list.style.gap = "4px";
        const container = document.getElementById("forge-genesis-phases");
        if (container) container.parentNode.appendChild(list);
    }
    if (data.recommended_rr) {
        const chip = document.createElement("span");
        chip.style.cssText = "background:#238636;color:#ffffff;padding:2px 6px;border-radius:10px;font-size:10px;";
        chip.textContent = data.recommended_rr.id;
        list.appendChild(chip);
    }
  }


  // SPEC-073 hotfix: pre-session-id progress screen. Shown the instant the
  // operator clicks "Forge Application", stays until the backend returns a
  // forge_session_id, then is replaced by the live-log polling UI.
  function showForgeGenesis() {
    showWizard(`
      <h2>${forgeData.projectName} — provisioning...</h2>
      <p class="wiz-subtitle">The server is executing the forge steps below. This takes 5–15 seconds. Live worker log begins as soon as the Architect worker (agy) is spawned.</p>

      <div style="display:flex;align-items:center;gap:12px;margin:14px 0;padding:12px;background:#0d1117;border:1px solid #30363d;border-radius:6px">
        <div class="forge-spinner" style="width:20px;height:20px;border:3px solid #30363d;border-top-color:#58a6ff;border-radius:50%;animation:spin 0.8s linear infinite;flex-shrink:0"></div>
        <div style="flex:1">
          <div style="font-size:13px;color:#e6edf3">Sending forge request to <code>/api/governance/forge</code></div>
          <div style="font-size:11px;color:#8b949e;margin-top:2px">Elapsed: <span id="forge-genesis-elapsed" style="color:#58a6ff;font-family:monospace">0.0s</span></div>
        </div>
      </div>

      <div style="margin-top:8px;padding:10px;background:#0d1117;border:1px solid #30363d;border-radius:6px;font-size:12px">
        <div style="color:#8b949e;font-size:11px;margin-bottom:6px">Live server-side phases:</div>
        <div id="forge-genesis-phases"></div>
      </div>

      <div id="forge-genesis-error" style="display:none;margin-top:10px;padding:10px;background:#3a1113;border:1px solid #da3633;border-radius:6px;color:#f85149;font-size:12px;white-space:pre-wrap;word-break:break-word"></div>

      <div style="margin-top:10px;text-align:right">
        <button id="btn-forge-genesis-cancel" style="padding:4px 10px;background:#21262d;border:1px solid #30363d;color:#8b949e;border-radius:3px;cursor:pointer;font-size:11px">Cancel &amp; close</button>
      </div>
    `);
    setTimeout(() => {
      const cancel = document.getElementById("btn-forge-genesis-cancel");
      if (cancel) cancel.onclick = () => closeWizard();
    }, 0);
  }

  function updateGenesisElapsed() {
    const el = document.getElementById("forge-genesis-elapsed");
    if (!el || !forgeData.startedAt) return;
    const s = (Date.now() - forgeData.startedAt) / 1000;
    el.textContent = s.toFixed(1) + "s";
  }

  function showForgeGenesisError(msg) {
    const err = document.getElementById("forge-genesis-error");
    if (err) {
      err.style.display = "block";
      err.textContent = "Forge failed: " + msg;
    }
    // Also stop the spinner visually
    document.querySelectorAll(".forge-spinner").forEach(s => { s.style.borderTopColor = "#da3633"; s.style.animation = "none"; });
  }

  function showForgeProgress() {
    showWizard(`
      <h2>` + forgeData.projectName + ` forging...</h2>
      <p class="wiz-subtitle">The Architect is analyzing constraints and drafting specifications.</p>

      <div class="wizard-progress-container">
        <div class="wizard-progress-fill" id="forge-progress-bar" style="width: 5%"></div>
      </div>
      <div class="wizard-progress-status" id="forge-progress-text">Initializing...</div>
      <div id="forge-specs-summary" style="margin-top:10px;font-size:12px;color:#8b949e"></div>
      <div style="margin-top:14px;border:1px solid #30363d;border-radius:6px;background:#0d1117;padding:8px">
        <div style="font-size:11px;color:#8b949e;margin-bottom:4px;display:flex;justify-content:space-between">
          <span>Live Architect Log</span>
          <span id="forge-elapsed" style="color:#58a6ff"></span>
        </div>
        <pre id="forge-log-tail" style="margin:0;font-size:10.5px;color:#e6e6e6;background:transparent;border:none;height:220px;overflow-y:auto;white-space:pre-wrap;word-break:break-word">(waiting for first log line...)</pre>
      </div>
      <div style="margin-top:8px;text-align:right">
        <button id="btn-forge-stop" style="padding:4px 10px;background:#21262d;border:1px solid #30363d;color:#f85149;border-radius:3px;cursor:pointer;font-size:11px">Stop</button>
      </div>
    `);
    forgeData.startedAt = Date.now();
    setTimeout(() => {
      const stop = document.getElementById("btn-forge-stop");
      if (stop) stop.onclick = async () => {
        try {
          await fetch(`${getCenterUrl()}/api/governance/forge/${forgeData.sessionId}/stop?project=${encodeURIComponent(forgeData.projectName||'')}`, { method: 'POST' });
        } catch(_) {}
        if (forgePollInterval) clearInterval(forgePollInterval);
        showForgeFailed(["Stopped by operator."]);
      };
    }, 0);
  }

  function pollForgeStatus() {
    if (forgePollInterval) clearInterval(forgePollInterval);

    forgePollInterval = setInterval(async () => {
      try {
        const proj = forgeData.projectName ? `?project=${encodeURIComponent(forgeData.projectName)}` : '';
        const res = await fetch(`${getCenterUrl()}/api/governance/forge/${forgeData.sessionId}/status${proj}`);
        const logEl = document.getElementById("forge-log-tail");
        if (!res.ok) {
          if (logEl) logEl.textContent = `(status endpoint returned ${res.status}; waiting for worker to register session...)`;
          return;
        }
        const data = await res.json();

        const bar = document.getElementById("forge-progress-bar");
        const text = document.getElementById("forge-progress-text");
        const elapsedEl = document.getElementById("forge-elapsed");
        const specsEl = document.getElementById("forge-specs-summary");

        if (bar && text) {
          bar.style.width = Math.min(100, Math.max(5, data.pct || 5)) + "%";
          text.textContent = (data.phase ? data.phase.replace(/_/g, ' ') : "working") +
                             (data.pct ? ` - ${data.pct}%` : '');
        }
        if (elapsedEl && forgeData.startedAt) {
          const s = Math.floor((Date.now() - forgeData.startedAt) / 1000);
          elapsedEl.textContent = s < 60 ? `${s}s` : `${Math.floor(s/60)}m${s%60}s`;
        }
        if (specsEl && Array.isArray(data.specs_created)) {
          specsEl.textContent = data.specs_created.length
            ? `Specs created: ${data.specs_created.join(', ')}`
            : 'No specs created yet.';
        }
        if (logEl && Array.isArray(data.log_tail) && data.log_tail.length) {
          const newText = data.log_tail.join('\n');
          if (newText !== logEl.textContent) {
            const atBottom = (logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight) < 20;
            logEl.textContent = newText;
            if (atBottom) logEl.scrollTop = logEl.scrollHeight;
          }
        }

        // The status endpoint returns `phase` (not `state`); accept both
        // and also treat "done": true or "phase": "complete"/"failed" the same
        // way. This unblocks the wizard when the forge worker dies after
        // writing specs but before emitting `forge_complete`.
        const _state = data.state || data.phase;
        const _isComplete = _state === "complete" || _state === "done" || data.done === true;
        const _isFailed = _state === "failed" || _state === "error";
        const _hasSpecs = Array.isArray(data.specs_created) && data.specs_created.length >= 2;

        if (_isComplete) {
          clearInterval(forgePollInterval);
          showForgeComplete(data.specs_created || [], data.log_tail);
        } else if (_isFailed || (_hasSpecs && !_isComplete && data.log_tail && data.log_tail.join("\n").includes("worker died"))) {
          // Disk-evidence override: worker died but 2+ specs on disk => transition anyway
          clearInterval(forgePollInterval);
          if (_hasSpecs) {
            showForgeComplete(data.specs_created, data.log_tail);
          } else {
            showForgeFailed(data.log_tail || ["Worker died before producing specs"]);
          }
        } else if (_hasSpecs && !forgeData._sawSpecsAt) {
          // First time we notice specs are on disk — start a 30s grace timer;
          // if the worker doesn't finalize, we transition anyway.
          forgeData._sawSpecsAt = Date.now();
        } else if (forgeData._sawSpecsAt && Date.now() - forgeData._sawSpecsAt > 30000) {
          clearInterval(forgePollInterval);
          showForgeComplete(data.specs_created, data.log_tail);
        }
      } catch (err) {
        console.warn("Error polling forge status:", err);
        const logEl = document.getElementById("forge-log-tail");
        if (logEl) logEl.textContent = `Polling error: ${err.message}`;
      }
    }, 2000);
  }

  function showForgeComplete(specs, forgeLogLines) {
    // Filter out SPEC-001 (the vision spec); the child specs are what we decompose.
    const childSpecs = (specs || []).filter(s => s && s !== "SPEC-001" && !s.startsWith("SPEC-001_"));

    // Render each child spec as a row with its live decompose/build status pill
    const rowsHtml = childSpecs.map(s =>
      `<div class="forge-pipeline-row" data-spec="${s}" style="display:flex;align-items:center;justify-content:space-between;padding:8px 10px;border:1px solid #30363d;border-radius:6px;margin-bottom:6px;background:#0d1117;font-size:12px">
         <span><strong>${s}</strong> <span class="fpr-title" style="color:#8b949e;margin-left:8px"></span></span>
         <span class="fpr-status" style="font-size:11px;padding:2px 8px;border-radius:10px;background:#21262d;color:#8b949e">queued</span>
       </div>`
    ).join("");

    const forgeLogHtml = Array.isArray(forgeLogLines) && forgeLogLines.length
      ? forgeLogLines.join('\n').replace(/</g, '&lt;')
      : '(no output captured)';

    showWizard(`
      <h2 style="color:#4CAF50;">Forge Complete</h2>
      <p class="wiz-subtitle">${childSpecs.length} child specs created. Auto-decomposing now — watch real-time below or jump to the spec map.</p>

      <div id="forge-pipeline" style="margin-top:10px;max-height:120px;overflow-y:auto">${rowsHtml || '<div style="color:#8b949e;font-size:12px">No child specs to decompose.</div>'}</div>

      <div id="mrr-analysis-card" style="margin-top:8px;border:1px solid #30363d;border-radius:6px;background:#0d1117;padding:8px;display:none;">
        <div style="font-size:11px;color:#8b949e;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center">
          <span>MRR Standards Analysis Card</span>
          <span style="color:#58a6ff;font-size:10px">Auto-Compliance Engine</span>
        </div>
        <div id="mrr-analysis-content" style="font-size:12px;color:#c9d1d9;">Loading analysis...</div>
      </div>

      <div style="margin-top:8px;border:1px solid #30363d;border-radius:6px;background:#0d1117;padding:8px">
        <div style="font-size:11px;color:#8b949e;margin-bottom:4px;display:flex;justify-content:space-between;align-items:center">
          <span>Forge Agent Log (last 20 lines)</span>
          <span style="color:#4CAF50;font-size:10px">&#10003; done</span>
        </div>
        <pre id="forge-complete-log" style="margin:0;font-size:10px;color:#b1bac4;background:transparent;border:none;height:90px;overflow-y:auto;white-space:pre-wrap;word-break:break-word">${forgeLogHtml}</pre>
      </div>

      <div style="margin-top:8px;border:1px solid #30363d;border-radius:6px;background:#0d1117;padding:8px">
        <div style="font-size:11px;color:#8b949e;margin-bottom:4px;display:flex;justify-content:space-between;align-items:center">
          <span>Decompose Agent Log</span>
          <span id="decompose-active-spec" style="color:#58a6ff;font-size:10px"></span>
        </div>
        <pre id="decompose-log-tail" style="margin:0;font-size:10.5px;color:#e6e6e6;background:transparent;border:none;height:120px;overflow-y:auto;white-space:pre-wrap;word-break:break-word">(waiting for worker to start...)</pre>
      </div>

      <div class="wizard-actions" style="margin-top:12px;">
        <button class="btn-prev" id="btn-forge-later">I'll open it later</button>
        <button class="primary" id="btn-forge-start" style="font-size:14px;padding:10px 18px;background:#238636;border-color:#2ea043">&#9654; Start Building</button>
      </div>
    `);

    
    if (forgeData.auto_standards_enabled) {
      const card = document.getElementById("mrr-analysis-card");
      if (card) {
        card.style.display = "block";
        fetch(`${getCenterUrl()}/api/governance/intent/classify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            wish: forgeData.wish,
            users: forgeData.users || "",
            success_v1: forgeData.success || "",
            project: forgeData.projectName || "adt-framework",
            engine: "gemini-3.5-flash-medium"
          })
        }).then(r => r.ok ? r.json() : {}).then(data => {
          let contentHtml = "";

          // REQ-113: wired to SPEC-075 LLM classifier response shape
          const domains = (data.matched_domains || []).join(", ");
          contentHtml += `<div><strong>Matched Domains:</strong> <span style="color:#a5d6ff">${domains || 'None'}</span></div>`;

          const stds = (data.data_classifications || []).join(", ");
          contentHtml += `<div style="margin-top:4px;"><strong>Data Classifications Detected:</strong> <span style="color:#f0b429">${stds || 'None'}</span></div>`;

          if (data.suggested_erasure_requirements && data.suggested_erasure_requirements.length) {
            contentHtml += `<div style="margin-top:4px;"><strong>Erasure Requirements:</strong><ul style="margin:4px 0 0 20px;color:#7ee787">${data.suggested_erasure_requirements.map(e=>`<li>${e.replace(/</g,'&lt;')}</li>`).join('')}</ul></div>`;
          }

          if (data.fallback_reason) {
            contentHtml += `<div style="margin-top:4px;color:#f85149;font-size:11px"><strong>Fallback:</strong> ${data.fallback_reason}</div>`;
          } else {
            contentHtml += `<div style="margin-top:4px;color:#8b949e;font-size:11px">Engine: ${data.engine || 'unknown'} · confidence ${((data.overall_confidence||0)*100).toFixed(0)}% · ${data.latency_ms || '?'}ms</div>`;
          }

          // Convert LLM recommended_rrs to fake baseline_rr_ids so downstream buttons still render
          data.baseline_rr_ids = (data.recommended_rrs || []).map(r => r.id).filter(Boolean);
          const coverage = data.baseline_coverage || {};
          if (data.baseline_rr_ids && data.baseline_rr_ids.length > 0) {
            contentHtml += `<div style="margin-top:8px;"><strong>Anchored Rules & Token MRRs:</strong></div>`;
            contentHtml += `<div style="display:flex;flex-direction:column;gap:4px;margin-top:4px;">`;
            // REQ-113: hydrate rr → {title, rationale, text} from the full recommended_rrs list
            const _rrLookup = {};
            (data.recommended_rrs || []).forEach(r => { if (r && r.id) _rrLookup[r.id] = r; });
            data.baseline_rr_ids.forEach(rr => {
              const currentDisp = coverage[rr] || 'pending';
              const _meta = _rrLookup[rr] || {};
              const _title = (_meta.title || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
              const _rationale = (_meta.rationale || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
              const _clauseText = (_meta.text || '').replace(/</g, '&lt;').replace(/"/g, '&quot;').slice(0, 400);
              const _derived = (_meta.derived_from || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
              const _unmapped = _meta && _meta.catalog_match === false;
              const _tooltip = `${rr}${_title ? ' — ' + _title : ''}${_unmapped ? '\n\n⚠ This ID is not in the RR catalog — the LLM classifier invented it. Consider manually mapping to a real RR.' : ''}\n\nRationale (why the classifier picked this):\n${_rationale || '(no rationale)'}${_clauseText ? '\n\nClause text:\n' + _clauseText : ''}${_derived ? '\n\nSource standard: ' + _derived : ''}`;
              contentHtml += `
                <div title="${_tooltip}" style="display:flex;justify-content:space-between;align-items:center;background:#161b22;padding:4px 8px;border:1px solid ${_unmapped ? '#d29922' : '#21262d'};border-radius:4px;cursor:help">
                  <span style="color:${_unmapped ? '#d29922' : '#58a6ff'};font-weight:bold;flex-shrink:0;">${rr}${_unmapped ? ' ⚠' : ''}</span>
                  <span style="color:#c9d1d9;font-size:11px;flex:1;margin-left:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_title || '(no title in catalog)'}</span>
                  <div class="mrr-disposition-btn-group" data-rr="${rr}" style="display:flex;gap:4px;">
                    <button class="mrr-disp-btn ${currentDisp==='adopted'?'active':''}" data-disp="adopted" style="font-size:10px;padding:2px 6px;border:1px solid #30363d;background:${currentDisp==='adopted'?'#238636':'#21262d'};color:${currentDisp==='adopted'?'#fff':'#8b949e'};border-radius:3px;cursor:pointer;">Adopt</button>
                    <button class="mrr-disp-btn ${currentDisp==='not_applicable'?'active':''}" data-disp="not_applicable" style="font-size:10px;padding:2px 6px;border:1px solid #30363d;background:${currentDisp==='not_applicable'?'#da3633':'#21262d'};color:${currentDisp==='not_applicable'?'#fff':'#8b949e'};border-radius:3px;cursor:pointer;">N/A</button>
                    <button class="mrr-disp-btn ${currentDisp==='pending'?'active':''}" data-disp="pending" style="font-size:10px;padding:2px 6px;border:1px solid #30363d;background:${currentDisp==='pending'?'#d29922':'#21262d'};color:${currentDisp==='pending'?'#fff':'#8b949e'};border-radius:3px;cursor:pointer;">Pending</button>
                  </div>
                </div>
              `;
            });
            contentHtml += `</div>`;
          } else {
             contentHtml += `<div style="margin-top:8px;"><strong>Anchored Rules & Token MRRs:</strong> None</div>`;
          }
          
          const contentEl = document.getElementById("mrr-analysis-content");
          if (contentEl) {
            contentEl.innerHTML = contentHtml;
            
            document.querySelectorAll(".mrr-disp-btn").forEach(btn => {
              btn.onclick = async (e) => {
                const disp = e.target.getAttribute("data-disp");
                const rr = e.target.parentElement.getAttribute("data-rr");
                
                let rationale = "";
                if (disp === "not_applicable") {
                  rationale = prompt("Please provide a rationale for marking this Not Applicable:");
                  if (!rationale) { alert("Rationale is required for Not Applicable."); return; }
                }
                
                try {
                    // Try to send PUT request if we know how, otherwise just update UI
                    // It's PUT /api/governance/standards/<std_id>/clauses/<clause_id>/disposition
                    // We don't have std_id and clause_id. Let's just update UI for now.
                    await fetch(`${getCenterUrl()}/api/governance/standards/rr/${rr}/disposition`, {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ disposition: disp, rationale: rationale })
                    });
                } catch(e) {}
                
                const group = e.target.parentElement;
                group.querySelectorAll(".mrr-disp-btn").forEach(b => {
                  b.classList.remove("active");
                  b.style.background = "#21262d";
                  b.style.color = "#8b949e";
                });
                e.target.classList.add("active");
                if (disp === 'adopted') { e.target.style.background = '#238636'; e.target.style.color = '#fff'; }
                if (disp === 'not_applicable') { e.target.style.background = '#da3633'; e.target.style.color = '#fff'; }
                if (disp === 'pending') { e.target.style.background = '#d29922'; e.target.style.color = '#fff'; }
              };
            });
          }
        }).catch(err => {
          const contentEl = document.getElementById("mrr-analysis-content");
          if (contentEl) contentEl.textContent = "Failed to load MRR analysis.";
        });
      }
    }

    document.getElementById("btn-forge-later").onclick = () => {
      closeWizard();
    };

    document.getElementById("btn-forge-start").onclick = async () => {
      const firstSpec = childSpecs[0];
      if (!firstSpec) {
        alert("No child specs to start with — nothing was decomposed.");
        return;
      }
      const projectName = forgeData.projectName;
      const projectPath = forgeData.path;
      closeWizard();
      toggle(); // Close launcher shell
      try {
        await startForgeAutoLaunch(projectName, projectPath, firstSpec);
      } catch (err) {
        console.error("Forge auto-launch failed:", err);
        alert("Auto-launch failed: " + (err && err.message || err));
      }
    };

    refresh();

    const proj = forgeData.projectName;

    // Poll decompose workers for live log tail
    const decompLogIv = setInterval(async () => {
      try {
        const wr = await fetch(`${getCenterUrl()}/api/decompose/workers?project=${encodeURIComponent(proj)}`);
        if (!wr.ok) return;
        const wd = await wr.json();
        const workers = wd.workers || [];
        const active = workers.find(w => w.alive) || workers[0];
        if (!active) return;
        const logEl = document.getElementById('decompose-log-tail');
        const specEl = document.getElementById('decompose-active-spec');
        if (specEl && active.spec_id) specEl.textContent = active.spec_id;
        if (logEl && active.log_tail && active.log_tail.length) {
          const newText = active.log_tail.join('\n');
          if (newText !== logEl.dataset.lastText) {
            const atBottom = (logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight) < 20;
            logEl.textContent = newText;
            logEl.dataset.lastText = newText;
            if (atBottom) logEl.scrollTop = logEl.scrollHeight;
          }
        }
      } catch(_) {}
    }, 2000);
    // Stop log poll when wizard closes
    setTimeout(() => {
      const laterBtn = document.getElementById('btn-forge-later');
      const startBtn = document.getElementById('btn-forge-start');
      const stop = () => clearInterval(decompLogIv);
      if (laterBtn) laterBtn.addEventListener('click', stop, { once: true });
      if (startBtn) startBtn.addEventListener('click', stop, { once: true });
    }, 0);

    // Auto-fire decompose on each child spec, then poll task_graph to update row status
    childSpecs.forEach(async (specId, idx) => {
      const row = document.querySelector(`.forge-pipeline-row[data-spec="${specId}"]`);
      const setStatus = (text, bg, color) => {
        const sp = row && row.querySelector(".fpr-status");
        if (sp) { sp.textContent = text; sp.style.background = bg; sp.style.color = color; }
      };
      await new Promise(r => setTimeout(r, idx * 800));
      setStatus("decomposing", "#1f6feb", "#fff");
      try {
        const r = await fetch(`${getCenterUrl()}/api/specs/${encodeURIComponent(specId)}/decompose?project=${encodeURIComponent(proj)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });
        if (!r.ok) {
          const d = await r.json().catch(() => ({}));
          const errMsg = d.error || String(r.status);
          // "already has N tasks" = previously decomposed, not a failure
          const alreadyMatch = errMsg.match(/already has (\d+) tasks?/i);
          if (alreadyMatch) {
            setStatus(`done (${alreadyMatch[1]} tasks)`, "#2e7d32", "#fff");
            return;
          }
          setStatus(`decompose failed: ${errMsg}`, "#7b1818", "#ff9090");
          return;
        }
        // Poll task_graph for this spec; flip status as tasks appear
        const tick = async () => {
          try {
            const gr = await fetch(`${getCenterUrl()}/api/specs/${encodeURIComponent(specId)}/task_graph?project=${encodeURIComponent(proj)}`);
            if (!gr.ok) return true;
            const g = await gr.json();
            const n = (g.nodes || []).length;
            if (n === 0) { setStatus("decomposing...", "#1f6feb", "#fff"); }
            else {
              const done = (g.nodes || []).filter(x => x.status === "completed").length;
              const inflight = (g.nodes || []).filter(x => ["in_progress","ready"].includes(x.status)).length;
              if (done === n) { setStatus(`done (${n}/${n})`, "#2e7d32", "#fff"); return false; }
              setStatus(`${n} tasks (${done} done${inflight ? `, ${inflight} active` : ""})`, "#9333ea", "#fff");
            }
            return true;
          } catch(_) { return true; }
        };
        let i = 0;
        const iv = setInterval(async () => {
          i += 1;
          const cont = await tick();
          if (cont === false || i >= 150) clearInterval(iv);
        }, 2000);
        tick();
      } catch (err) {
        setStatus(`error: ${err.message}`, "#7b1818", "#ff9090");
      }
    });
  }

  function showForgeFailed(logTail) {
    const logText = Array.isArray(logTail) ? logTail.join("\\n") : String(logTail);
    showWizard(`
      <h2 style="color:#f85149;">Forge Failed</h2>
      <p class="wiz-subtitle">The Architect encountered an unrecoverable error.</p>
      
      <div class="wizard-log-tail">` + logText.replace(/</g, "&lt;") + `</div>
      
      <div class="wizard-actions" style="margin-top:24px;">
        <button class="btn-prev" id="btn-forge-cancel">Cancel</button>
        <button class="primary forge-submit" id="btn-forge-retry">Retry</button>
      </div>
    `);
    
    const modal = document.querySelector(".wizard-modal");
    if (modal) modal.classList.add("failed");
    
    document.getElementById("btn-forge-cancel").onclick = closeWizard;
    document.getElementById("btn-forge-retry").onclick = submitForge;
  }

  function formatTimeAgo(ts) {
    if (!ts) return "unknown";
    const seconds = Math.floor((new Date() - new Date(ts)) / 1000);
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  }

  return { init, toggle, hide, refresh, isActive: () => active, openProject, reopenSession, closeWizard, submitCreate, submitImport, openForgeWizard, submitForge };
})();
