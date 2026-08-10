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
  // REQ-111 (SPEC-079 §7): live standards recommendations panel poller.
  // Polls /api/ads/events every 1s during the ~35s classifier run so the
  // operator sees matched_domains + suggested_rr_ids chips appear as they
  // are computed, not after the forge finishes. Cleared alongside
  // forgePollInterval on wizard close / forge complete / forge failed.
  let standardsPollInterval = null;
  let standardsSeenEventIds = new Set();

  // SPEC-080 / REQ-123: Framework Standards Catalog snapshot, fetched from
  // /api/mrr/library_stats on Forge Wizard open. Cached for the wizard's
  // lifetime — the catalog only changes when the framework's rationalised
  // rules or intent index change, so a per-wizard cache is plenty.
  // SPEC-081 §1.3: cache lives for 5 min across wizard opens; only an operator
  // explicit refresh (or the TTL) invalidates it.
  let _forgeCatalog = null;              // parsed payload once loaded
  let _forgeCatalogLoading = false;      // dedupes concurrent fetches
  let _forgeCatalogError = false;        // sticky failure flag for this session
  let _forgeCatalogExpanded = false;     // strip UI state (Screen-1 + progress)
  let _forgeCatalogFetchedAt = 0;        // epoch ms of last successful fetch

  // SPEC-081 §1.3: shared 5-min-TTL registry cache. Keys are the request URL
  // (project registry, per-project spec fetches, library stats). Every entry
  // stores { data, fetchedAt }. Served from cache after the first open; an
  // operator explicit-refresh action (see invalidateRegistryCache) is the
  // only manual invalidator. Cache hits / misses are console-logged for
  // easy debug during demos.
  const REGISTRY_CACHE_TTL_MS = 5 * 60 * 1000;
  const _registryCache = new Map();      // url -> { data, fetchedAt }
  const _registryCacheInflight = new Map(); // url -> Promise (dedupe concurrent fetches)

  // SPEC-081 §1.3: fetch-with-cache helper. Only intended for GET requests
  // that are safe to cache (project registry, catalog, per-project spec
  // reads). Returns parsed JSON or throws on network / non-2xx.
  async function cachedRegistryFetch(url, opts) {
    const now = Date.now();
    const cached = _registryCache.get(url);
    if (cached && (now - cached.fetchedAt) < REGISTRY_CACHE_TTL_MS) {
      console.debug(`[SPEC-081 cache HIT] ${url} (age ${((now - cached.fetchedAt)/1000).toFixed(1)}s)`);
      return cached.data;
    }
    if (_registryCacheInflight.has(url)) {
      console.debug(`[SPEC-081 cache DEDUPE] ${url} (in-flight)`);
      return _registryCacheInflight.get(url);
    }
    console.debug(`[SPEC-081 cache MISS] ${url}`);
    const p = (async () => {
      try {
        const r = await fetch(url, opts);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        _registryCache.set(url, { data, fetchedAt: Date.now() });
        return data;
      } finally {
        _registryCacheInflight.delete(url);
      }
    })();
    _registryCacheInflight.set(url, p);
    return p;
  }

  // SPEC-081 §1.3: operator-triggered invalidation. `pattern` (optional) is
  // a substring or RegExp; when omitted, wipes the whole cache. Also drops
  // the catalog snapshot so the strip re-fetches on next render.
  function invalidateRegistryCache(pattern) {
    if (!pattern) {
      const n = _registryCache.size;
      _registryCache.clear();
      _forgeCatalog = null;
      _forgeCatalogFetchedAt = 0;
      _forgeCatalogError = false;
      console.debug(`[SPEC-081 cache INVALIDATE ALL] cleared ${n} entries + catalog`);
      return;
    }
    const rx = pattern instanceof RegExp ? pattern : new RegExp(String(pattern));
    let removed = 0;
    for (const key of Array.from(_registryCache.keys())) {
      if (rx.test(key)) { _registryCache.delete(key); removed++; }
    }
    console.debug(`[SPEC-081 cache INVALIDATE ${pattern}] cleared ${removed} entries`);
  }

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

  async function refresh(force) {
    try {
      // SPEC-081 §1.3: use registry cache; operator explicit refresh (force=true)
      // invalidates so the launcher picks up freshly-forged projects on demand.
      const url = `${getCenterUrl()}/api/projects`;
      if (force) invalidateRegistryCache(url);
      let data;
      try {
        data = await cachedRegistryFetch(url);
      } catch (_) { data = null; }
      if (data) {
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
        // SPEC-081 §1.3: served from registry cache when warm.
        const data = await cachedRegistryFetch(`${getCenterUrl()}/api/projects`);
        const entry = (data.projects || data || {})[projectName];
        if (entry && entry.path) cwd = entry.path;
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
    if (standardsPollInterval) { clearInterval(standardsPollInterval); standardsPollInterval = null; }
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
        await refresh(true);  // SPEC-081 §1.3: new project — invalidate cache
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
        await refresh(true);  // SPEC-081 §1.3: new project — invalidate cache
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
      // SPEC-081 §1.3: catalog cache lives ACROSS wizard opens for 5 min
      // (was reset unconditionally). Only invalidate if the entry is stale
      // or absent; operator explicit refresh (invalidateRegistryCache) is
      // the manual escape hatch.
      const now = Date.now();
      if (_forgeCatalog && (now - _forgeCatalogFetchedAt) > REGISTRY_CACHE_TTL_MS) {
        _forgeCatalog = null;
        _forgeCatalogFetchedAt = 0;
        _forgeCatalogError = false;
      }
      _forgeCatalogLoading = false;
      _forgeCatalogExpanded = false;
      fetchForgeCatalog();  // fire-and-forget; renderForgeCatalogStrip() reads _forgeCatalog when it resolves
      showForgeScreen1();
    } finally {
      _opening = false;
    }
  }

  // SPEC-080 / REQ-123: fetch the framework standards catalog snapshot.
  // Non-fatal on failure — the strip degrades to "(unavailable)" but never
  // blocks the forge. Concurrent calls are deduped.
  async function fetchForgeCatalog() {
    if (_forgeCatalog || _forgeCatalogLoading) return _forgeCatalog;
    _forgeCatalogLoading = true;
    const base = (window.SpecMap && window.SpecMap.getCenterUrl && window.SpecMap.getCenterUrl())
              || getCenterUrl();
    try {
      // SPEC-081 §1.3: served from the shared 5-min registry cache.
      _forgeCatalog = await cachedRegistryFetch(`${base}/api/mrr/library_stats`);
      _forgeCatalogFetchedAt = Date.now();
      _forgeCatalogError = false;
    } catch (_) {
      _forgeCatalogError = true;
      _forgeCatalog = null;
    } finally {
      _forgeCatalogLoading = false;
      // Re-render whichever strip container is currently on-screen (Screen-1
      // or forge-progress). Both use the same container id.
      renderForgeCatalogStrip();
    }
    return _forgeCatalog;
  }

  // SPEC-080 / REQ-123: render the catalog strip into #forge-catalog-strip.
  // Called on Screen-1 mount, on fetch resolve, and on user click. `phase`
  // controls the header text: "catalog" (Screen-1), "analyzing" (forge in
  // flight, no MRR event yet), "matched" (MRR completed).
  function renderForgeCatalogStrip(phase) {
    const el = document.getElementById("forge-catalog-strip");
    if (!el) return;
    phase = phase || el.dataset.phase || "catalog";
    el.dataset.phase = phase;

    // Header line variants
    let header = "";
    if (_forgeCatalogError) {
      header = `<span style="color:#8b949e">📚 Framework Standards Catalog: <em>(unavailable)</em></span>`;
    } else if (!_forgeCatalog) {
      header = `<span style="color:#8b949e">📚 Loading catalog…</span>`;
    } else if (phase === "analyzing") {
      header = `<span style="color:#c9d1d9">🔍 Analyzing your wish against ${_forgeCatalog.standards_count} standards and ${_forgeCatalog.domains_count} domains...</span>`;
    } else if (phase === "matched") {
      const nDoms = (forgeData.matchedDomains || []).length;
      const nRRs = (forgeData.suggestedRRs || []).length;
      header = `<span style="color:#3fb950">✓</span> <span style="color:#c9d1d9">Matched ${nDoms} domain${nDoms===1?'':'s'}, suggesting ${nRRs} standard${nRRs===1?'':'s'}</span>`;
    } else {
      header = `<span style="color:#c9d1d9">📚 Framework Standards Catalog: ${_forgeCatalog.standards_count} rules across ${_forgeCatalog.domains_count} domains</span>`;
    }

    // Toggle button — only shown when we have data (catalog or matched result).
    const canExpand = !!_forgeCatalog && !_forgeCatalogError;
    const toggleLabel = _forgeCatalogExpanded ? "▲ collapse" : "▼ expand";
    const toggleBtn = canExpand
      ? `<button type="button" id="forge-catalog-toggle" style="background:transparent;border:none;color:#58a6ff;cursor:pointer;font-size:11px;padding:0;margin-left:8px">${toggleLabel}</button>`
      : "";

    // Expanded panel — two columns: standards + domains (or matched-domains + suggested RRs).
    let panel = "";
    if (_forgeCatalogExpanded && canExpand) {
      let leftTitle, leftItems, rightTitle, rightItems;
      if (phase === "matched") {
        // Repurposed view: matched domains + suggested RRs from forgeData.
        const doms = forgeData.matchedDomains || [];
        const rrs = forgeData.suggestedRRs || [];
        const rrTitles = forgeData.rrTitles || {};
        leftTitle = `Matched Domains (${doms.length})`;
        leftItems = doms.length
          ? doms.map(d => {
              const conf = (forgeData.domainConfidence && forgeData.domainConfidence[d]);
              const pct = conf != null ? `${Math.round(conf*100)}%` : '';
              return `<div style="padding:3px 6px;font-size:11px;color:#a5d6ff;border-bottom:1px solid #21262d"><b>${d.replace(/</g,'&lt;')}</b> <span style="color:#8b949e;float:right">${pct}</span></div>`;
            }).join("")
          : `<div style="padding:6px;color:#8b949e;font-size:11px">(none)</div>`;
        rightTitle = `Suggested Standards (${rrs.length})`;
        rightItems = rrs.length
          ? rrs.map(rr => {
              const t = rrTitles[rr] || "";
              return `<div style="padding:3px 6px;font-size:11px;color:#c9d1d9;border-bottom:1px solid #21262d"><b style="color:#58a6ff">${rr}</b> ${t.replace(/</g,'&lt;')}</div>`;
            }).join("")
          : `<div style="padding:6px;color:#8b949e;font-size:11px">(none)</div>`;
      } else {
        // Static catalog view: all standards + all domains.
        const stds = _forgeCatalog.standards || [];
        const doms = _forgeCatalog.domains || [];
        leftTitle = `Standards (${stds.length})`;
        leftItems = stds.map(s => {
          const tierBadge = s.tier ? ` <span style="color:#8b949e;font-size:10px">[${String(s.tier).replace(/</g,'&lt;')}]</span>` : "";
          return `<div style="padding:3px 6px;font-size:11px;color:#c9d1d9;border-bottom:1px solid #21262d"><b style="color:#58a6ff">${(s.id||'').replace(/</g,'&lt;')}</b>${tierBadge} ${(s.title||'').replace(/</g,'&lt;')}</div>`;
        }).join("");
        rightTitle = `Domains (${doms.length})`;
        rightItems = doms.map(d => {
          const rrs = (d.baseline_rr_ids || []).join(", ");
          return `<div style="padding:3px 6px;font-size:11px;color:#c9d1d9;border-bottom:1px solid #21262d"><b>${(d.name||'').replace(/</g,'&lt;')}</b> <span style="color:#8b949e">· ${d.keyword_count} kw</span>${rrs?` <span style="color:#8b949e">· ${rrs.replace(/</g,'&lt;')}</span>`:''}</div>`;
        }).join("");
      }
      panel = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;max-height:220px">
          <div style="border:1px solid #30363d;border-radius:4px;background:#0d1117;overflow-y:auto;max-height:220px">
            <div style="padding:4px 6px;font-size:10px;color:#8b949e;background:#161b22;border-bottom:1px solid #30363d;position:sticky;top:0">${leftTitle}</div>
            ${leftItems}
          </div>
          <div style="border:1px solid #30363d;border-radius:4px;background:#0d1117;overflow-y:auto;max-height:220px">
            <div style="padding:4px 6px;font-size:10px;color:#8b949e;background:#161b22;border-bottom:1px solid #30363d;position:sticky;top:0">${rightTitle}</div>
            ${rightItems}
          </div>
        </div>
      `;
    }

    el.innerHTML = `
      <div style="display:flex;align-items:center;font-size:12px">
        ${header}
        ${toggleBtn}
      </div>
      ${panel}
    `;

    const btn = document.getElementById("forge-catalog-toggle");
    if (btn) {
      btn.onclick = () => {
        _forgeCatalogExpanded = !_forgeCatalogExpanded;
        renderForgeCatalogStrip(phase);
      };
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
      label: "🪐 Camera-Navigated 3D Solar System",
      slug: "solar_system",
      wish: `A browser-based educational 3D visualisation of our solar system that runs entirely offline. The Sun sits at the centre, the 8 major planets orbit at log-compressed but visually pleasing distances, and Earth's Moon orbits Earth. Each planet uses a bundled high-resolution equirectangular texture. Planets rotate on their axes and orbit the Sun at reasonable relative speeds -- not physically accurate to true Kepler mechanics but faithful to relative ordering.

Navigation is by webcam-tracked hand movement, the same pattern as the EyeToy template already in this catalog. The user waves or moves their hand in front of the built-in laptop webcam and the camera pans smoothly through space -- move hand left, camera pans left; move hand up, camera pitches up. A soft on-screen indicator shows where the hand is being tracked. No keyboard, no mouse required for navigation; a mouse click is only needed for planet selection.

Clicking any planet triggers a smooth cinematic fly-to camera transition (~2 seconds) that frames the planet, then opens a fact card displaying real-world data: name, distance from Sun (in km and AU -- real values, not the log-compressed rendered values), diameter, day length, year length, moons, and 2-3 notable facts. Clicking a "Return" button zooms the camera back out to the whole-system view.

The catalog of facts is a hardcoded JSON file bundled with the app -- no NASA API calls, no external dependencies at runtime, works entirely offline.`,
      users: "Students, educators, curious learners, families, and museum-style installations -- anyone who wants an intuitive visual grasp of planetary scale, ordering, and basic facts without installing an app.",
      success: "User opens the app, sees the Sun plus the 8 planets plus Earth's Moon rendered in Three.js with orbital motion. Waving their hand in front of the webcam smoothly pans the camera through space (EyeToy pattern). Clicking Mars triggers a ~2-second fly-to transition; the camera frames Mars and a fact card appears showing distance-from-Sun in km + AU, diameter, day/year length, moon count, and notable facts (all from bundled JSON, no fetch). Clicking Return zooms back out. Works fully offline after first load. Frame rate stays smooth (>=30fps) on a mid-range 2020 laptop.",
      out: "No true-scale physics -- true scaling would make Neptune invisible or the Sun a screen-filling disc. Log-compressed distances are honoured with real numbers shown in the fact card so the education stays honest. No exoplanets. No spacecraft, satellites, or missions. No VR / AR mode. No multi-user, accounts, leaderboards, or progress tracking. No NASA API, no runtime fetches -- all art assets and facts bundled at build time. No audio / ambient soundtrack in v1 (video producer can add in post if desired). No mobile support required for v1 (nice-to-have but not blocking).",
      constraints: "Browser-based single-page app. Rendering: Three.js (bundled or via ES module). Camera navigation: MediaPipe Hands (or equivalent JS hand-tracker) via getUserMedia; same tracking pattern as the EyeToy template already in this codebase -- reuse conventions where possible. Textures: bundled equirectangular JPGs sourced from NASA / JPL / ESO public-domain releases; a NOTICE.md file must credit sources. Facts: hardcoded JSON at src/planet_facts.json -- 8 planets + Sun + Moon + real distances / diameters / day / year lengths / moon counts / 2-3 notable facts per body. Distance scale: log-compressed (e.g. rendered_distance = k1 * log(1 + real_AU * k2)) so Neptune is visible without dwarfing inner planets; document the exact function in a comment. Fact cards display REAL numbers not rendered numbers. Fly-to camera transitions use Three.js quaternion slerp + eased position interpolation, ~2 second duration. Must serve over HTTPS for camera access -- dev flow uses mkcert or a documented self-signed cert setup. Runs on desktop Chrome, Firefox, and Safari (latest). Frame rate target >=30fps on mid-range hardware; if hand-tracking is expensive, run tracker at 15fps and interpolate. Fully offline after first load -- no runtime network calls."
    },
    {
      label: "🖼️ AR Art Placement Preview",
      slug: "ar_art_preview",
      wish: `A mobile-first web app that lets people preview art pieces (paintings, framed prints, vases, statuettes) in their own home before buying. The user prints a paper fiducial marker provided by the app, places it on a wall or shelf where a piece would go, and points their phone camera at the marker. The app renders the digitised art piece anchored to the marker at correct real-world scale so the user can walk around and see how the piece fits -- scale, style, perspective.

Critically, tracking must be robust and stable. The marker is designed to be detected from a distance and at varied angles (a multi-fiducial board or natural-feature-tracking target, not a single fragile square that only works head-on). Once the marker is initially locked, the app fuses camera-based tracking with the phone's gyroscope: if the camera briefly loses sight of the marker, the rendered piece stays put where it was placed rather than jumping, flickering, or disappearing. The user can turn the phone or briefly step away and the art remains anchored to the real wall; when the marker re-enters view, the pose snaps back smoothly rather than teleporting.

Art is represented either as a textured plane derived from a single photo (paintings / framed prints with real-world dimensions supplied by the user in centimetres) or from a supplied 3D model file (GLB / OBJ, for vases and statuettes). The catalog ships with 3 sample pieces -- one painting, one vase, one statuette -- so the demo works immediately out of the box. Users can add their own by uploading a photo plus dimensions, or a GLB file.`,
      users: "Homeowners and interior-design-curious shoppers who want to visualise an art piece in their space before purchasing. Also small gallery / independent-artisan sellers who want to give buyers a low-effort preview tool without building a native app.",
      success: "User loads the app on their phone over HTTPS, picks a sample painting from the catalog, prints (or displays on a second screen) the bundled fiducial marker at its intended real-world size, points the camera at the marker, and sees a correctly-scaled rendering appear anchored to the wall -- a 60cm-wide painting appears ~60cm wide relative to the marker. The user then walks around, turns the phone at moderate angles, or briefly points away from the marker, and the piece remains rock-steady in its placed position (no flicker, no jump, no drift beyond a small centimetre-scale nudge on re-acquisition). A printable marker PDF at a known real-world size is bundled with the app as a first-class deliverable.",
      out: "No AR-headset support in v1 -- phone only. No photorealistic lighting or shadow estimation. No purchase / checkout flow. No account system. No photogrammetry pipeline: users supply either a photo + dimensions or a GLB, they do not scan real objects. No markerless (SLAM-only) tracking in v1 -- the marker is the authoritative anchor. No GPS-based positioning in v1 -- GPS accuracy (5-10 m outdoor, 20-50 m or no lock indoors) is 100-1000x coarser than the cm-scale anchor precision this indoor use case requires; fusing it in would destabilise, not stabilise, the pose. GPS is captured as a v2 open question for a possible outdoor-sculpture-placement mode. No extended translational dead-reckoning beyond the multi-sensor stability window described in constraints.",
      constraints: "Browser-based. Must run on modern iOS Safari and Android Chrome using getUserMedia plus a marker-tracking library that supports iOS Safari without WebXR -- recommended: MindAR (Image / Multi-Target mode) or AR.js NFT (natural-feature tracking). The child spec owning tracking picks the exact library, but the pick MUST work on iOS Safari. No native app, no App Store. Must be served over HTTPS in both dev and production (bundled self-signed cert or a documented mkcert / ngrok flow) -- mobile browsers refuse camera access otherwise. The marker asset is a printable PDF bundled with the app at a fixed known real-world size (recommend A4 portrait with the pattern occupying a known cm-square). Real-world scale MUST be honoured -- rendered dimensions derive from the marker's known physical size, not from arbitrary Three.js units. Tracking must be a fused multi-sensor pipeline (VIO-lite). Primary anchor is the marker via camera; when the marker is in view, all other sensors are calibrated against it. When the marker leaves view: (a) rotation is maintained by gyroscope (DeviceOrientationEvent, ~100 Hz) with heading drift corrected by magnetometer (webkitCompassHeading on iOS, absolute:true DeviceOrientationEvent on Android); (b) translation is maintained by lightweight optical flow tracking non-marker features on the wall / floor (OpenCV.js feature tracker or equivalent lightweight JS implementation); (c) accelerometer double-integration (DeviceMotionEvent) bridges the first ~1 second while optical flow initialises. Combined, the piece must remain rock-steady for at least 8-10 seconds of marker-off-camera before drift becomes visible. On marker re-acquisition, smooth the pose delta over 200-500 ms -- no visible jump. Progressive enhancement: if navigator.xr with WebXR Hit Test is available (Android Chrome), use it as the primary translation source in place of optical flow for indefinite anchor stability; iOS transparently falls back to the multi-sensor stack. Explicitly do NOT use GPS -- see out-of-scope. Fully static / offline-capable -- no server-side AR processing; all art assets and marker PDFs served as static files."
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

  // ---------------------------------------------------------------------
  // SPEC-081 §4: Project Knowledge Reuse — match picker helpers.
  // ---------------------------------------------------------------------

  // Convert an ISO-8601 timestamp into a coarse "X ago" phrase suitable for
  // wizard chips ("just now", "2h ago", "3d ago", "1w ago", "2mo ago").
  // Returns "-" if the timestamp is falsy/invalid.
  function humanTimeSince(iso) {
    if (!iso) return "-";
    const then = new Date(iso).getTime();
    if (!isFinite(then)) return "-";
    const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (s < 60) return "just now";
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    if (d < 7) return `${d}d ago`;
    const w = Math.floor(d / 7);
    if (w < 5) return `${w}w ago`;
    const mo = Math.floor(d / 30);
    if (mo < 12) return `${mo}mo ago`;
    const y = Math.floor(d / 365);
    return `${y}y ago`;
  }

  // Render one radio row for the match picker. `rank` is 0-based; 0/1/2 map
  // to the medal emoji. `match` shape (from /similar_projects response):
  //   { project_name, similarity, last_touched_iso, spec_count, task_count, wish_preview }
  function pickerRenderRow(match, rank) {
    const medals = ["🥇", "🥈", "🥉"]; // gold / silver / bronze
    const medal = medals[rank] || "  ";
    const pct = Math.round((Number(match.similarity) || 0) * 100);
    const ago = humanTimeSince(match.last_touched_iso);
    const nSpecs = Number(match.spec_count || 0);
    const nTasks = Number(match.task_count || 0);
    const name = String(match.project_name || "").replace(/</g, "&lt;");
    const preview = String(match.wish_preview || "").replace(/"/g, "&quot;");
    const checked = rank === 0 ? "checked" : "";
    return `
      <label class="picker-row" title="${preview}" style="display:flex;align-items:center;gap:12px;padding:10px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;cursor:pointer;font-size:13px">
        <input type="radio" name="wiz-picker-choice" value="${name}" ${checked}
               style="margin:0;flex-shrink:0;width:16px;height:16px;cursor:pointer">
        <span style="font-size:18px;line-height:1;flex-shrink:0">${medal}</span>
        <span style="flex:1;color:#e6edf3;font-family:monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"><strong>${name}</strong></span>
        <span style="color:#3fb950;font-weight:bold;font-size:12px;flex-shrink:0">${pct}% match</span>
        <span style="color:#8b949e;font-size:11px;flex-shrink:0">&middot; touched ${ago}</span>
        <span style="color:#8b949e;font-size:11px;flex-shrink:0">&middot; ${nSpecs} spec${nSpecs===1?'':'s'}, ${nTasks} task${nTasks===1?'':'s'}</span>
      </label>`;
  }

  // Render the picker screen. `matches` = top-N array from the similar_projects
  // endpoint (already filtered to similarity >= 0.70 and sorted desc); at least
  // one entry is guaranteed by the caller. `forgeSessionId` MAY be null at
  // this point (the real forge dispatch happens AFTER the operator picks) —
  // the actual /fork_from call is deferred to the forge_session_created event
  // handler in submitForge(). We stash the choice on forgeData so that handler
  // can act on it.
  function showMatchPickerScreen(matches, forgeSessionId) {
    const top3 = matches.slice(0, 3);
    const rowsHtml = top3.map((m, i) => pickerRenderRow(m, i)).join("");
    showWizard(`
      <h2>Reuse existing knowledge?</h2>
      <p class="wiz-subtitle" style="color:#8b949e">
        We found ${matches.length} similar prior project${matches.length===1?'':'s'}. Forking copies
        the source's specs and tasks into your new project; an Architect worker
        then verifies each one against your new wish (real work, no fake events).
        Hover a row to preview its original wish.
      </p>
      <div id="wiz-picker-rows" style="display:flex;flex-direction:column;gap:8px;margin:14px 0">
        ${rowsHtml}
      </div>
      <div class="wizard-actions" style="display:flex;gap:10px;justify-content:flex-end;margin-top:16px">
        <button id="btn-picker-back" style="background:#21262d;border:1px solid #30363d;color:#8b949e;padding:8px 14px;border-radius:6px;cursor:pointer;font-size:12px">&larr; Back</button>
        <button id="btn-picker-fresh" style="background:#21262d;border:1px solid #30363d;color:#c9d1d9;padding:8px 14px;border-radius:6px;cursor:pointer;font-size:12px">Forge fresh (no fork)</button>
        <button id="btn-picker-fork" style="background:#1f6feb;border:1px solid #1f6feb;color:#fff;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:bold">Fork from selected</button>
      </div>
    `);
    document.getElementById("btn-picker-back").onclick = showForgeScreen2;
    document.getElementById("btn-picker-fresh").onclick = () => {
      forgeData.forkFrom = null;
      console.debug("[SPEC-081] operator chose Forge fresh (no fork)");
      submitForge();
    };
    document.getElementById("btn-picker-fork").onclick = () => {
      const sel = document.querySelector("input[name='wiz-picker-choice']:checked");
      const choice = sel ? sel.value : (top3[0] && top3[0].project_name);
      if (!choice) {
        alert("Please select a project to fork from.");
        return;
      }
      forgeData.forkFrom = choice;
      console.debug(`[SPEC-081] operator chose Fork from '${choice}' — deferred to forge_session_created`);
      submitForge();
    };
  }

  // Ask the backend for similar prior projects, then either show the picker
  // (>=1 match with similarity >= 0.70) or fall straight through to a real
  // forge. Endpoint may not exist yet (Backend agent is building in parallel)
  // — any error/404/timeout falls through transparently.
  async function offerReuseOrForge() {
    console.info("[SPEC-081] offerReuseOrForge() invoked  wish_len=" + (forgeData.wish||"").length);
    const wish = (forgeData.wish || "").trim();
    if (!wish) { console.warn("[SPEC-081] empty wish → skip picker"); submitForge(); return; }
    let matches = [];
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 8000);  // was 4s, bumped for safety
      const url = `${getCenterUrl()}/api/governance/forge/similar_projects`;
      console.info("[SPEC-081] POST", url);
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wish }),
        signal: controller.signal
      });
      clearTimeout(timer);
      console.info("[SPEC-081] response HTTP", r.status);
      if (r.status === 404) {
        console.warn("[SPEC-081] /similar_projects not deployed yet (404) — skipping picker");
      } else if (!r.ok) {
        console.warn(`[SPEC-081] /similar_projects HTTP ${r.status} — skipping picker`);
      } else {
        const data = await r.json();
        matches = Array.isArray(data.matches) ? data.matches : [];
        console.info("[SPEC-081] got", matches.length, "matches. Top:", matches[0]);
      }
    } catch (err) {
      console.error("[SPEC-081] /similar_projects failed:", err && err.message || err);
    }
    const strong = matches.filter(m => (Number(m.combined_score) || Number(m.similarity) || 0) >= 0.30);
    console.info("[SPEC-081] strong-match count (>=0.30):", strong.length);
    // 2026-08-09 fix: ALWAYS show the picker if ANY matches exist (even below threshold)
    // so operator has a visible "no fork" acknowledgement instead of silent skip.
    if (matches.length >= 1) {
      showMatchPickerScreen((strong.length ? strong : matches).slice(0, 3), null);
    } else {
      // 0 matches, error, or all below threshold — proceed to normal forge.
      submitForge();
    }
  }

  async function showForgeScreen1() {
    const { projects: projsDir } = await _getServerPaths();
    showWizard(`
      <h2>Forge Application (1/2)</h2>
      <p class="wiz-subtitle">Describe your vision. The Architect will formalize a specification and build the foundation autonomously.</p>
      <!-- SPEC-080 / REQ-123: Framework Standards Catalog strip. Shown BEFORE
           the wish textarea so the operator (and demo audience) sees the
           framework has a real catalog before any matching happens. Also
           repurposed on the forge-progress screen (see showForgeProgress). -->
      <div id="forge-catalog-strip" data-phase="catalog" style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:8px 10px;margin-bottom:12px;color:#8b949e">
        <span style="font-size:12px">📚 Loading catalog…</span>
      </div>
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
      <div class="wizard-field" style="display:flex;align-items:center;gap:14px;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;font-size:12px;color:#8b949e;margin-top:12px">
        <span style="color:#c9d1d9;font-weight:bold">MRR classifier:</span>
        <label style="display:inline-flex;align-items:center;gap:5px;cursor:pointer" title="Instant keyword scan against 27 domains. Best for demos.">
          <input type="radio" name="wiz-mrr-mode" value="quick" checked>⚡ Quick <span style="color:#7ee787;font-size:11px">(instant)</span>
        </label>
        <label style="display:inline-flex;align-items:center;gap:5px;cursor:pointer" title="Deep LLM analysis: 30-60s, more nuanced. Falls back to Quick on failure.">
          <input type="radio" name="wiz-mrr-mode" value="deep">🔬 Deep <span style="color:#d29922;font-size:11px">(~30-60s)</span>
        </label>
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
    // SPEC-080 / REQ-123: render the catalog strip immediately (shows either
    // "Loading catalog…" or, if fetchForgeCatalog resolved between
    // openForgeWizard() and this DOM mount, the real counts).
    renderForgeCatalogStrip("catalog");
    // Re-fetch defensively — openForgeWizard already fired one, but a rapid
    // re-render (e.g., wizard reopened after a stop) needs the retry.
    if (!_forgeCatalog && !_forgeCatalogLoading) fetchForgeCatalog();
    document.getElementById("btn-wiz-cancel").onclick = closeWizard;
    document.getElementById("btn-wiz-next").onclick = async () => {
      forgeData.wish = (document.getElementById("wiz-forge-wish").value || "").trim();
      forgeData.path = (document.getElementById("wiz-forge-path").value || "").trim();
      forgeData.name = (document.getElementById("wiz-forge-name").value || "").trim();
      if (!forgeData.wish) { alert("Please describe your wish."); return; }
      if (!forgeData.path) { alert("Project path is required."); return; }
      // SCR-164 / SPEC-081: MRR classifier — mode selected by operator (Quick/Deep).
      const _mrrMode = (document.querySelector("input[name='wiz-mrr-mode']:checked") || {}).value || "quick";
      forgeData.mrr_mode = _mrrMode;
      if (_mrrMode === "deep") {
        // Deep LLM analysis: show progress modal, fetch with generous 120s timeout,
        // on any failure fall back to Quick automatically (never dead-end the operator).
        const _startTs = Date.now();
        showWizard(`
          <h2>🔬 Deep LLM Analysis</h2>
          <p class="wiz-subtitle">Sending your wish to Gemini for contextual classification. Typically 30-60 seconds. If it fails, we fall back to the quick keyword scan automatically.</p>
          <div style="margin:20px 0;padding:16px;background:#0d1117;border:1px solid #30363d;border-radius:8px">
            <div style="display:flex;align-items:center;gap:12px">
              <div style="width:20px;height:20px;border:3px solid #30363d;border-top-color:#58a6ff;border-radius:50%;animation:spin 0.8s linear infinite"></div>
              <div id="deep-status" style="color:#c9d1d9;font-size:13px">Contacting classifier…</div>
            </div>
            <div id="deep-elapsed" style="color:#8b949e;font-size:11px;margin-top:8px">elapsed: 0s</div>
          </div>
          <style>@keyframes spin{to{transform:rotate(360deg)}}</style>
          <div class="wizard-actions">
            <button class="btn-prev" id="btn-deep-cancel">Cancel &amp; use Quick instead</button>
          </div>
        `);
        const _elapsedTimer = setInterval(() => {
          const el = document.getElementById("deep-elapsed");
          if (el) el.textContent = `elapsed: ${Math.floor((Date.now() - _startTs) / 1000)}s`;
        }, 500);
        const _fallbackToQuick = async (reason) => {
          clearInterval(_elapsedTimer);
          console.warn(`[SCR-164] Deep failed (${reason}) — falling back to Quick`);
          try {
            const qr = await fetch(`${getCenterUrl()}/api/governance/intent/quick_classify`, {
              method: "POST", headers: {"Content-Type": "application/json"},
              body: JSON.stringify({ wish: forgeData.wish })
            });
            if (qr.ok) {
              const qd = await qr.json();
              forgeData.mrr_suggested = qd.suggested_rr_ids || [];
              forgeData.mrr_domains = qd.matched_domains || [];
            }
          } catch (_) {}
          forgeData.mrr_mode = "quick_fallback";
          showForgeScreen2();
        };
        document.getElementById("btn-deep-cancel").onclick = () => _fallbackToQuick("operator_cancel");
        const _ctrl = new AbortController();
        const _tmo = setTimeout(() => _ctrl.abort(), 120000);
        try {
          const r = await fetch(`${getCenterUrl()}/api/governance/intent/classify`, {
            method: "POST", headers: {"Content-Type": "application/json"},
            signal: _ctrl.signal,
            body: JSON.stringify({
              engine: "gemini-3.5-flash-medium",
              wish: forgeData.wish,
              users: forgeData.users || "n/a",
              success_v1: forgeData.success || "n/a",
              project: forgeData.name || "pending"
            })
          });
          clearTimeout(_tmo);
          clearInterval(_elapsedTimer);
          if (r.ok) {
            const d = await r.json();
            // LLM response format: matched_domains + recommended_rrs (id list)
            forgeData.mrr_suggested = (d.recommended_rrs || []).map(x => x.id || x).filter(Boolean);
            forgeData.mrr_domains = d.matched_domains || [];
            forgeData.mrr_engine = d.engine || "gemini";
            forgeData.mrr_confidence = d.overall_confidence;
            console.debug("[SCR-164 Deep] suggested:", forgeData.mrr_suggested, "conf:", forgeData.mrr_confidence);
            showForgeScreen2();
          } else {
            _fallbackToQuick(`http_${r.status}`);
          }
        } catch (e) {
          clearTimeout(_tmo);
          _fallbackToQuick(e && e.name || "fetch_error");
        }
      } else {
        // Quick keyword scan — instant, no LLM
        (async () => {
          try {
            const r = await fetch(`${getCenterUrl()}/api/governance/intent/quick_classify`, {
              method: "POST", headers: {"Content-Type": "application/json"},
              body: JSON.stringify({ wish: forgeData.wish })
            });
            if (r.ok) {
              const d = await r.json();
              forgeData.mrr_suggested = d.suggested_rr_ids || [];
              forgeData.mrr_suggested_titled = d.suggested_rrs || [];
              forgeData.mrr_domains = d.matched_domains || [];
              console.debug("[SCR-164 Quick] suggested:", forgeData.mrr_suggested);
            }
          } catch (e) { console.warn("[SCR-164 Quick] failed:", e); forgeData.mrr_suggested = []; }
          showForgeScreen2();
        })();
      }
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
      <div class="wizard-field" style="display:none">
        <label>Standards to anchor (pick all that apply) <span class="wiz-optional">(optional)</span></label>
        <div id="wiz-forge-standards" style="display:none">
          <span style="font-size:11px;color:#8b949e">Loading adopted Rationalised Rules...</span>
        </div>
      </div>
      <div class="wizard-field" style="display:none">
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
        // FIX 2026-08-09 (final): SKIP the LLM classify call entirely from the wizard.
        // The endpoint tries LLM (10-52s), fails, falls back to keywords. WebView aborts
        // in <30s. Frontend shows "TypeError: Load failed". Operator's standards choice
        // is already captured via Screen-2 checkboxes, so the wizard doesn't need this
        // async classification result. Left as a placeholder promise so downstream code
        // doesn't crash on missing data.
        const _cls1Ctrl = new AbortController();
        const _cls1Timer = setTimeout(() => {}, 0);
        Promise.resolve({ ok: false, json: () => Promise.resolve({ matched_domains: [], recommended_rrs: [], engine: "skipped_wizard", latency_ms: 0 }) })
          && fetch(`about:blank`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: _cls1Ctrl.signal,
          body: JSON.stringify({
            engine: "keyword_fallback",
            wish: forgeData.wish || "",
            users: document.getElementById("wiz-forge-users")?.value || forgeData.users || "",
            success_v1: document.getElementById("wiz-forge-success")?.value || forgeData.success || "",
            project: projName
          })
        }).then(r => r.json()).then(cls => {
          clearInterval(classifyTimer);
          if (cls.error) {
            statusEl.style.color = "#f85149";
            statusEl.style.display = "none";  // FIX 2026-08-09: MRR-suggested-panel replaces this
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
          statusEl.style.display = "none";  // FIX 2026-08-09: silent fail, panel already has data
        });
      }).catch(() => {
        const wrap = document.getElementById("wiz-forge-standards");
        if (wrap) wrap.style.display = "none";  // FIX 2026-08-09: MRR-suggested-panel handles this now
      });
    document.getElementById("btn-wiz-back").onclick = showForgeScreen1;

    // SCR-164: render MRR-suggested standards as pre-checked chips at the TOP of Screen 2.
    // Operator unchecks any they don't want; forge_brief.selected_rr_ids = only those kept.
    (() => {
      const suggested = forgeData.mrr_suggested || [];
      const domains = forgeData.mrr_domains || [];
      const fields = document.querySelector(".wizard-body") || document.querySelector(".wizard-content") || document.body;
      const panel = document.createElement("div");
      panel.id = "mrr-suggested-panel";
      panel.style.cssText = "margin:0 0 16px 0;padding:12px;background:#0d1117;border:1px solid #30363d;border-radius:6px";
      if (suggested.length === 0) {
        panel.innerHTML = `<div style="color:#8b949e;font-size:12px">🔍 No MRR-suggested standards for this wish. Manual selection only.</div>`;
      } else {
        const domainsHtml = domains.length ? `<div style="font-size:11px;color:#8b949e;margin-top:6px">Matched domains: ${domains.map(d=>`<span style="background:#161b22;padding:2px 6px;border-radius:3px;margin-right:4px">${d}</span>`).join("")}</div>` : "";
        const modeBadge = forgeData.mrr_mode === "deep" ? '<span style="background:#8957e5;color:#fff;padding:1px 6px;border-radius:3px;font-size:10px;margin-left:6px">🔬 Deep LLM</span>' : (forgeData.mrr_mode === "quick_fallback" ? '<span style="background:#d29922;color:#000;padding:1px 6px;border-radius:3px;font-size:10px;margin-left:6px">⚡ Quick (Deep fell back)</span>' : '<span style="background:#1f6feb;color:#fff;padding:1px 6px;border-radius:3px;font-size:10px;margin-left:6px">⚡ Quick keyword</span>');
        panel.innerHTML = `
          <div style="font-weight:bold;color:#7ee787;margin-bottom:8px;font-size:13px">🤖 MRR-suggested standards ${modeBadge} <span style="background:#238636;color:#fff;padding:1px 6px;border-radius:3px;font-size:10px;margin-left:6px">${suggested.length} recommended</span></div>
          <div style="font-size:12px;color:#8b949e;margin-bottom:8px">Uncheck any you don't want the framework to enforce for this project.</div>
          <div style="display:flex;flex-direction:column;gap:4px">
            ${suggested.map(rr => {
              const titled = (forgeData.mrr_suggested_titled || []).find(x => x.id === rr);
              const title = (titled && titled.title) || "";
              return `<label style="display:flex;align-items:flex-start;gap:8px;background:#21262d;padding:8px 12px;border-radius:4px;cursor:pointer;font-size:12px;color:#c9d1d9;border:1px solid #388bfd">
                <input type="checkbox" class="mrr-suggested-chip" data-rr="${rr}" checked style="margin-top:3px;flex-shrink:0">
                <div style="flex:1"><b style="color:#58a6ff">${rr}</b> <span style="color:#c9d1d9">— ${title.replace(/</g,"&lt;")}</span></div>
              </label>`;
            }).join("")}
          </div>
          ${domainsHtml}
        `;
      }
      const firstField = document.querySelector(".wizard-field");
      if (firstField && firstField.parentNode) {
        firstField.parentNode.insertBefore(panel, firstField);
      }
    })();

    document.getElementById("btn-wiz-forge").onclick = () => {
      forgeData.users = (document.getElementById("wiz-forge-users").value || "").trim();
      forgeData.success = (document.getElementById("wiz-forge-success").value || "").trim();
      forgeData.out = (document.getElementById("wiz-forge-out").value || "").trim();
      forgeData.constraints = (document.getElementById("wiz-forge-constraints").value || "").trim();
      // SCR-164: include both preset RR chips AND the MRR-suggested chips the operator kept checked
      const _mrrChecked = Array.from(document.querySelectorAll(".mrr-suggested-chip:checked")).map(el => el.dataset.rr);
      const _presetChecked = Array.from(document.querySelectorAll(".wiz-rr-chip:checked")).map(el => el.dataset.rr);
      forgeData.selected_rr_ids = [...new Set([..._mrrChecked, ..._presetChecked])];
      forgeData.auto_standards_enabled = document.getElementById("wiz-forge-auto-standards")?.checked ?? true;


      if (!forgeData.users) { alert("Please specify who this is for."); return; }
      if (!forgeData.success) { alert("Please specify what 'done v1' looks like."); return; }

      // SPEC-081 §4: offer to fork from a similar prior project before
      // committing to a fresh forge. Transparent no-op if the backend
      // endpoint is missing or returns no strong matches.
      offerReuseOrForge();
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

        // SPEC-081 §5: if the operator picked a source project on the match
        // picker, fire the fork_from call NOW (session_id has just landed).
        // Non-fatal on failure — worst case the new project stays empty and
        // the forge worker proceeds as if the operator had picked "Forge fresh".
        // Never blocks the transition to the progress screen if the endpoint
        // is missing (Backend agent may still be building it).
        const source = forgeData.forkFrom;
        forgeData.forkFrom = null; // one-shot
        const proceed = () => { showForgeProgress(); pollForgeStatus(); };
        if (source && forgeData.sessionId) {
          fetch(`${getCenterUrl()}/api/governance/forge/${encodeURIComponent(forgeData.sessionId)}/fork_from`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source_project_name: source })
          }).then(async r => {
            if (r.status === 404) {
              console.warn("[SPEC-081] /fork_from not deployed yet — proceeding with fresh forge");
            } else if (!r.ok) {
              console.warn(`[SPEC-081] /fork_from HTTP ${r.status} — proceeding with fresh forge`);
            } else {
              try {
                const rd = await r.json();
                console.debug(`[SPEC-081] fork_from OK: ${rd.specs_copied || 0} specs, ${rd.tasks_copied || 0} tasks reused from ${rd.forked_from || source}`);
                forgeData.forkedFrom = rd.forked_from || source;
              } catch (_) {}
            }
          }).catch(err => {
            console.warn("[SPEC-081] /fork_from failed:", err && err.message || err);
          }).finally(proceed);
        } else {
          proceed();
        }
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
      <p class="wiz-subtitle">The server is executing the forge steps below. Duration depends on the model — <b>Claude Sonnet ≈ 1–3 min</b>, <b>Gemini Flash ≈ 5–15 min</b>, larger reasoning models longer. Watch the standards catalog above and the live worker log below for progress.</p>

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

      <!-- SPEC-080 / REQ-123: same catalog strip as Screen 1, morphed into
           "analyzing…" mode; renderStandardsResult() will flip it to
           "matched" mode when the MRR event fires. -->
      <div id="forge-catalog-strip" data-phase="analyzing" style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:8px 10px;margin-bottom:10px;color:#8b949e">
        <span style="font-size:12px">🔍 Analyzing…</span>
      </div>

      <!-- REQ-111 (SPEC-079 §7): live Standards Recommendations panel.
           Populated by pollStandardsStream() from ADS events during the
           ~35s classifier run. Persists after the classifier finishes so the
           operator sees the full recommendation set for the rest of the forge. -->
      <div id="forge-standards-panel" style="margin-top:10px;border:1px solid #30363d;border-radius:6px;background:#0d1117;padding:10px">
        <div style="font-size:11px;color:#8b949e;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">
          <span id="forge-standards-title">Standards Recommendations</span>
          <span id="forge-standards-engine" style="color:#58a6ff;font-size:10px">Auto-Compliance Engine</span>
        </div>
        <div id="forge-standards-status" style="font-size:12px;color:#c9d1d9;display:flex;align-items:center;gap:8px">
          <div class="forge-spinner" style="width:12px;height:12px;border:2px solid #30363d;border-top-color:#58a6ff;border-radius:50%;animation:spin 0.8s linear infinite;flex-shrink:0"></div>
          <span style="color:#7ee787">&#x2713; Using operator-confirmed standards (see chips above)</span>
        </div>
        <div id="forge-standards-domains" style="margin-top:6px;display:none;flex-wrap:wrap;gap:4px"></div>
        <div id="forge-standards-rrs" style="margin-top:6px;display:none;flex-direction:column;gap:4px"></div>
      </div>

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
    // REQ-111: reset per-forge classifier state and start the ADS event poller.
    forgeData.suggestedRRs = [];
    forgeData.matchedDomains = [];
    forgeData.rrConfidence = {};
    forgeData.classifierStartedTs = null;
    forgeData.classifierCompletedTs = null;
    standardsSeenEventIds = new Set();
    // SPEC-080 / REQ-123: paint the strip in "analyzing" mode using the
    // catalog counts fetched in Screen 1. If the catalog is still loading
    // (edge case: operator flew through Screen 1 in <1s), the strip shows
    // "Loading catalog…" until the fetch resolves.
    _forgeCatalogExpanded = false;
    renderForgeCatalogStrip("analyzing");
    if (!_forgeCatalog && !_forgeCatalogLoading && !_forgeCatalogError) fetchForgeCatalog();
    pollStandardsStream();
    setTimeout(() => {
      const stop = document.getElementById("btn-forge-stop");
      if (stop) stop.onclick = async () => {
        try {
          await fetch(`${getCenterUrl()}/api/governance/forge/${forgeData.sessionId}/stop?project=${encodeURIComponent(forgeData.projectName||'')}`, { method: 'POST' });
        } catch(_) {}
        if (forgePollInterval) clearInterval(forgePollInterval);
        if (standardsPollInterval) { clearInterval(standardsPollInterval); standardsPollInterval = null; }
        showForgeFailed(["Stopped by operator."]);
      };
    }, 0);
  }

  // REQ-111 (SPEC-079 §7): live standards-recommendations poller.
  // Streaming source (a) — polls /api/ads/events?project=<name>&limit=100
  // every 1s, filtering client-side for intent_match_* and
  // intent_classification_* events. Chose (a) over extending the forge
  // status payload because option (b) requires backend changes to
  // governance_routes.py which are outside Frontend_Engineer jurisdiction.
  function pollStandardsStream() {
    if (standardsPollInterval) clearInterval(standardsPollInterval);
    const startedAtIso = new Date(forgeData.startedAt || Date.now()).toISOString();
    const projName = forgeData.projectName || "";
    const url = `${getCenterUrl()}/api/ads/events?project=${encodeURIComponent(projName)}&limit=100`;

    standardsPollInterval = setInterval(async () => {
      try {
        const res = await fetch(url);
        if (!res.ok) return;
        const events = await res.json();
        if (!Array.isArray(events)) return;
        for (const ev of events) {
          const evId = ev.event_id || ev.id;
          if (!evId || standardsSeenEventIds.has(evId)) continue;
          const ts = ev.ts || ev.timestamp || "";
          // Only look at events emitted after this forge started.
          if (ts && ts < startedAtIso) continue;
          const t = ev.action_type;
          if (t === "intent_match_started" || t === "intent_classification_started") {
            standardsSeenEventIds.add(evId);
            forgeData.classifierStartedTs = ts;
            renderStandardsAnalyzing(ev);
          } else if (t === "intent_match_completed" || t === "intent_classification_completed") {
            standardsSeenEventIds.add(evId);
            forgeData.classifierCompletedTs = ts;
            renderStandardsResult(ev);
          }
        }
      } catch (_) {
        // Silent — the panel just stays in whatever state it last reached.
      }
    }, 1000);
  }

  // Update the top-of-panel status line to show the classifier is running.
  function renderStandardsAnalyzing(ev) {
    const statusEl = document.getElementById("forge-standards-status");
    if (!statusEl) return;
    const payload = ev.action_data || {};
    const preview = payload.wish_preview_first_80_chars || "";
    const engine = payload.engine_version || ev.engine || "";
    const engineEl = document.getElementById("forge-standards-engine");
    if (engineEl && engine) engineEl.textContent = engine;
    statusEl.innerHTML = `
      <div class="forge-spinner" style="width:12px;height:12px;border:2px solid #30363d;border-top-color:#58a6ff;border-radius:50%;animation:spin 0.8s linear infinite;flex-shrink:0"></div>
      <span>&#x1F50D; Analyzing your wish${preview ? ' — <em style="color:#8b949e">"' + preview.replace(/</g,'&lt;').slice(0,80) + '"</em>' : ''}...</span>
    `;
  }

  // Merge a completed event into forgeData and re-render domain + RR chips.
  function renderStandardsResult(ev) {
    const payload = ev.action_data || {};
    const domains = Array.isArray(payload.matched_domains) ? payload.matched_domains : [];
    const rrIds = Array.isArray(payload.suggested_rr_ids) ? payload.suggested_rr_ids
                : Array.isArray(payload.recommended_rrs) ? payload.recommended_rrs.map(r => r && r.id).filter(Boolean)
                : [];
    const perDomain = payload.match_confidence_per_domain || {};
    const perRr = payload.match_confidence_per_rr || payload.rr_confidence || {};
    const rrTitles = payload.rr_titles || {};

    // Merge (do not clobber): a later _completed event may add more matches.
    forgeData.matchedDomains = Array.from(new Set([...(forgeData.matchedDomains || []), ...domains]));
    forgeData.suggestedRRs = Array.from(new Set([...(forgeData.suggestedRRs || []), ...rrIds]));
    forgeData.rrConfidence = Object.assign({}, forgeData.rrConfidence || {}, perRr);
    forgeData.domainConfidence = Object.assign({}, forgeData.domainConfidence || {}, perDomain);
    forgeData.rrTitles = Object.assign({}, forgeData.rrTitles || {}, rrTitles);

    // Flip the status line to "done" and reveal the chip rows.
    const statusEl = document.getElementById("forge-standards-status");
    if (statusEl) {
      statusEl.innerHTML = `<span style="color:#3fb950">&#10003;</span> <span>Classifier finished -- ${forgeData.suggestedRRs.length} standard${forgeData.suggestedRRs.length===1?'':'s'} matched across ${forgeData.matchedDomains.length} domain${forgeData.matchedDomains.length===1?'':'s'}. Please review and confirm below.</span>`;
    }
    // REQ-129: swap the forge wait line from "Analyzing your wish..." to
    // "Awaiting your standards review..." — the Architect worker is now
    // parked awaiting operator confirmation via the Confirm button below.
    if (!forgeData.standardsConfirmed) {
      const progressText = document.getElementById("forge-progress-text");
      if (progressText) progressText.textContent = "Awaiting your standards review...";
    }
    renderStandardsChips();
    // SPEC-080 / REQ-123: morph the catalog strip to "matched" mode showing
    // the operator (and audience) how the framework narrowed the catalog
    // down to just what applies to this wish.
    renderForgeCatalogStrip("matched");
  }

  // Render the domain + RR chip rows from forgeData, sorted by confidence desc.
  // REQ-129 / SCR-164: RR rows are now checkbox+label pairs. Default: CHECKED
  // (operator un-checks to veto). A "Confirm Standards & Continue" button
  // appears once the MRR run has completed; clicking it POSTs the selection
  // to the backend confirm_standards endpoint which then spawns the Architect.
  function renderStandardsChips() {
    const domainsEl = document.getElementById("forge-standards-domains");
    const rrsEl = document.getElementById("forge-standards-rrs");
    if (!domainsEl || !rrsEl) return;

    const sortedDomains = [...(forgeData.matchedDomains || [])].sort((a, b) =>
      (forgeData.domainConfidence[b] || 0) - (forgeData.domainConfidence[a] || 0)
    );
    const sortedRRs = [...(forgeData.suggestedRRs || [])].sort((a, b) =>
      (forgeData.rrConfidence[b] || 0) - (forgeData.rrConfidence[a] || 0)
    );

    // Accepted-set: chips are marked "accepted" when their RR id ended up in
    // forgeData.selected_rr_ids (the wizard's confirmed list at forge time) or
    // in forgeData.acceptedRRs (populated by markAcceptedStandards() after the
    // forge worker fills SPEC-001).
    const acceptedSet = new Set([...(forgeData.selected_rr_ids || []), ...(forgeData.acceptedRRs || [])]);
    // REQ-129: per-forge selection state. Persist across re-renders — only
    // seed defaults for RR ids we haven't seen yet (all default: CHECKED).
    if (!forgeData.standardsSelection) forgeData.standardsSelection = {};
    if (!forgeData.standardsDomainSelection) forgeData.standardsDomainSelection = {};
    for (const rr of sortedRRs) {
      if (!(rr in forgeData.standardsSelection)) forgeData.standardsSelection[rr] = true;
    }
    for (const d of sortedDomains) {
      if (!(d in forgeData.standardsDomainSelection)) forgeData.standardsDomainSelection[d] = true;
    }

    // Whether Confirm has already fired (freeze checkboxes to read-only).
    const confirmed = !!forgeData.standardsConfirmed;

    if (sortedDomains.length) {
      domainsEl.style.display = "flex";
      // REQ-129: domain checkboxes are informational (per spec-brief, only RR
      // checkboxes are structurally load-bearing). Rendered here for parity.
      domainsEl.innerHTML = sortedDomains.map(d => {
        const conf = forgeData.domainConfidence[d];
        const confPct = conf != null ? `${Math.round(conf * 100)}%` : 'n/a';
        const checked = forgeData.standardsDomainSelection[d] ? 'checked' : '';
        const disabled = confirmed ? 'disabled' : '';
        const tooltip = `Domain: ${d}\nConfidence: ${confPct}\n(informational)`;
        const safeD = d.replace(/</g,'&lt;').replace(/"/g,'&quot;');
        return `<label title="${tooltip.replace(/"/g,'&quot;')}" style="display:inline-flex;align-items:center;gap:4px;background:#1f2937;color:#a5d6ff;padding:2px 8px;border-radius:10px;font-size:11px;border:1px solid #30363d;cursor:pointer">
          <input type="checkbox" data-domain="${safeD}" ${checked} ${disabled} class="std-domain-cb" style="margin:0;transform:scale(0.85)">
          <span>${d.replace(/</g,'&lt;')}</span>
        </label>`;
      }).join("");
    }

    if (sortedRRs.length) {
      rrsEl.style.display = "flex";
      rrsEl.innerHTML = sortedRRs.map(rr => {
        const conf = forgeData.rrConfidence[rr];
        const confPct = conf != null ? `${Math.round(conf * 100)}%` : 'n/a';
        const title = forgeData.rrTitles[rr] || '';
        const accepted = acceptedSet.has(rr);
        const checkedNow = forgeData.standardsSelection[rr] ? 'checked' : '';
        const disabled = confirmed ? 'disabled' : '';
        const tooltip = `${rr}${title ? ' -- ' + title : ''}\nConfidence: ${confPct}\nState: ${accepted ? 'accepted' : (forgeData.standardsSelection[rr] ? 'will adopt' : 'declined')}`;
        const rrBg = accepted ? '#238636' : '#161b22';
        const rrBorder = accepted ? '#2ea043' : '#21262d';
        const rrColor = accepted ? '#ffffff' : '#58a6ff';
        const stateBadge = accepted
          ? '<span style="color:#3fb950;font-size:10px;margin-left:6px">&#10003; accepted</span>'
          : (forgeData.standardsSelection[rr]
              ? '<span style="color:#8b949e;font-size:10px;margin-left:6px">will adopt</span>'
              : '<span style="color:#f85149;font-size:10px;margin-left:6px">declined</span>');
        const safeRR = rr.replace(/</g,'&lt;').replace(/"/g,'&quot;');
        return `
          <label title="${tooltip.replace(/"/g,'&quot;')}" style="display:flex;justify-content:space-between;align-items:center;gap:8px;background:${rrBg};padding:4px 8px;border:1px solid ${rrBorder};border-radius:4px;cursor:pointer;transition:opacity 0.25s ease-in">
            <input type="checkbox" data-rr="${safeRR}" ${checkedNow} ${disabled} class="std-rr-cb" style="margin:0;flex-shrink:0">
            <span style="color:${rrColor};font-weight:bold;flex-shrink:0">${rr.replace(/</g,'&lt;')}</span>
            <span style="color:#c9d1d9;font-size:11px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${(title||'').replace(/</g,'&lt;')}</span>
            <span style="color:#8b949e;font-size:10px;flex-shrink:0">${confPct}</span>
            ${stateBadge}
          </label>
        `;
      }).join("");

      // Wire checkbox change handlers (RR + domain).
      rrsEl.querySelectorAll('input.std-rr-cb').forEach(cb => {
        cb.onchange = () => {
          const rr = cb.getAttribute('data-rr');
          if (rr) forgeData.standardsSelection[rr] = cb.checked;
          renderStandardsChips();
        };
      });
      domainsEl.querySelectorAll('input.std-domain-cb').forEach(cb => {
        cb.onchange = () => {
          const d = cb.getAttribute('data-domain');
          if (d) forgeData.standardsDomainSelection[d] = cb.checked;
        };
      });
    }

    // REQ-129: render the Confirm button once the MRR run completes AND we
    // have at least one RR to review. The classifierCompletedTs field is set
    // by renderStandardsResult() when intent_match_completed fires.
    renderStandardsConfirmButton();
  }

  // REQ-129 / SCR-164: The bottom-of-panel Confirm button. Only rendered
  // once the classifier has completed and we have RRs to review. On click:
  // POSTs {selected_rr_ids, declined_rr_ids} to the backend confirm endpoint,
  // which un-parks the Architect worker.
  function renderStandardsConfirmButton() {
    const panel = document.getElementById("forge-standards-panel");
    if (!panel) return;
    let btnHost = document.getElementById("forge-standards-confirm-host");
    const classifierDone = !!forgeData.classifierCompletedTs;
    const rrs = Object.keys(forgeData.standardsSelection || {});
    const hasRRs = rrs.length > 0;
    const alreadyConfirmed = !!forgeData.standardsConfirmed;

    if (!classifierDone || !hasRRs) {
      if (btnHost) btnHost.remove();
      return;
    }

    if (!btnHost) {
      btnHost = document.createElement('div');
      btnHost.id = 'forge-standards-confirm-host';
      btnHost.style.cssText = 'margin-top:10px;padding-top:10px;border-top:1px solid #30363d;display:flex;justify-content:space-between;align-items:center;gap:8px';
      panel.appendChild(btnHost);
    }

    const selectedCount = rrs.filter(r => forgeData.standardsSelection[r]).length;
    const declinedCount = rrs.length - selectedCount;
    if (alreadyConfirmed) {
      btnHost.innerHTML = `<span style="color:#3fb950;font-size:12px">&#10003; Standards confirmed -- ${selectedCount} adopted, ${declinedCount} declined. Architect proceeding...</span>`;
      return;
    }

    btnHost.innerHTML = `
      <span style="color:#c9d1d9;font-size:11px">Review the standards above; uncheck any that do not apply.</span>
      <button id="btn-forge-confirm-standards" style="padding:8px 16px;background:#238636;border:1px solid #2ea043;color:#ffffff;border-radius:6px;cursor:pointer;font-size:13px;font-weight:bold">&#10003; Confirm Standards &amp; Continue</button>
    `;
    const btn = document.getElementById('btn-forge-confirm-standards');
    if (btn) btn.onclick = submitStandardsConfirmation;
  }

  async function submitStandardsConfirmation() {
    if (!forgeData.sessionId) {
      console.warn('[REQ-129] no forge_session_id yet; cannot confirm standards');
      return;
    }
    const sel = forgeData.standardsSelection || {};
    const selected_rr_ids = Object.keys(sel).filter(r => sel[r]);
    const declined_rr_ids = Object.keys(sel).filter(r => !sel[r]);

    const btn = document.getElementById('btn-forge-confirm-standards');
    if (btn) { btn.disabled = true; btn.textContent = 'Confirming...'; }

    try {
      const url = `${getCenterUrl()}/api/governance/forge/${encodeURIComponent(forgeData.sessionId)}/confirm_standards`;
      const projQuery = forgeData.projectName ? `?project=${encodeURIComponent(forgeData.projectName)}` : '';
      const res = await fetch(url + projQuery, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selected_rr_ids, declined_rr_ids }),
      });
      if (!res.ok) {
        const txt = await res.text();
        console.error('[REQ-129] confirm_standards failed:', res.status, txt);
        if (btn) { btn.disabled = false; btn.textContent = '✓ Confirm Standards & Continue'; }
        return;
      }
      forgeData.standardsConfirmed = true;
      forgeData.selected_rr_ids = selected_rr_ids;
      forgeData.declined_rr_ids = declined_rr_ids;
      // Update progress-screen status line to reflect the transition.
      const progressText = document.getElementById('forge-progress-text');
      if (progressText) progressText.textContent = 'Standards confirmed -- Architect spawning...';
      renderStandardsChips();
    } catch (err) {
      console.error('[REQ-129] confirm_standards error:', err);
      if (btn) { btn.disabled = false; btn.textContent = '✓ Confirm Standards & Continue'; }
    }
  }

  // Called from showForgeComplete() once the forge worker has produced
  // SPEC-001. Cross-references its vision metadata against forgeData.suggestedRRs
  // and marks any adopted RRs with the "✓ accepted" state.
  async function markAcceptedStandards(specs) {
    if (!Array.isArray(forgeData.suggestedRRs) || forgeData.suggestedRRs.length === 0) return;
    try {
      const proj = encodeURIComponent(forgeData.projectName || "");
      // The spec_map / governance endpoints expose vision metadata via
      // /api/governance/specs/<spec_id>?project=<name>. If a lighter endpoint
      // exists it can be swapped in later — this shape is defensive.
      // SPEC-081 §1.3: served from the 5-min registry cache.
      let spec;
      try {
        spec = await cachedRegistryFetch(`${getCenterUrl()}/api/governance/specs/SPEC-001?project=${proj}`);
      } catch (_) { return; }
      const meta = spec.metadata || spec.frontmatter || spec || {};
      const acceptedFromSpec = [
        ...(Array.isArray(meta.selected_rr_ids) ? meta.selected_rr_ids : []),
        ...(Array.isArray(meta.adopted_rrs) ? meta.adopted_rrs : []),
        ...(Array.isArray(meta.rr_ids) ? meta.rr_ids : []),
      ];
      forgeData.acceptedRRs = Array.from(new Set(acceptedFromSpec));
      // Panel may not exist on the current screen; render is a no-op if so.
      renderStandardsChips();
    } catch (_) {
      // Non-fatal — chips stay in "suggested" state.
    }
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
          // REQ-111: classifier long since finished — stop its poller too.
          if (standardsPollInterval) { clearInterval(standardsPollInterval); standardsPollInterval = null; }
          showForgeComplete(data.specs_created || [], data.log_tail);
        } else if (_isFailed || (_hasSpecs && !_isComplete && data.log_tail && data.log_tail.join("\n").includes("worker died"))) {
          // Disk-evidence override: worker died but 2+ specs on disk => transition anyway
          clearInterval(forgePollInterval);
          if (standardsPollInterval) { clearInterval(standardsPollInterval); standardsPollInterval = null; }
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

      <!-- REQ-111 (SPEC-079 §7): standards-recommendations recap.
           The live panel from showForgeProgress() is replaced by this DOM,
           so we re-render the chips here from forgeData. markAcceptedStandards()
           runs asynchronously below to flip accepted chips green. -->
      <div id="forge-standards-panel" style="margin-top:10px;border:1px solid #30363d;border-radius:6px;background:#0d1117;padding:10px;${(forgeData.suggestedRRs||[]).length||((forgeData.matchedDomains||[]).length)?'':'display:none;'}">
        <div style="font-size:11px;color:#8b949e;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">
          <span id="forge-standards-title">Standards Recommendations</span>
          <span id="forge-standards-engine" style="color:#58a6ff;font-size:10px">Auto-Compliance Engine</span>
        </div>
        <div id="forge-standards-status" style="font-size:12px;color:#c9d1d9;"></div>
        <div id="forge-standards-domains" style="margin-top:6px;display:flex;flex-wrap:wrap;gap:4px"></div>
        <div id="forge-standards-rrs" style="margin-top:6px;display:flex;flex-direction:column;gap:4px"></div>
      </div>

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

    // REQ-111 (SPEC-079 §7): re-render live-panel chips onto the completion
    // screen and check SPEC-001 metadata to mark accepted standards.
    const _stStatusEl = document.getElementById("forge-standards-status");
    if (_stStatusEl) {
      const nRR = (forgeData.suggestedRRs || []).length;
      const nDom = (forgeData.matchedDomains || []).length;
      if (nRR || nDom) {
        _stStatusEl.innerHTML = `<span style="color:#3fb950">&#10003;</span> <span>Classifier recommended ${nRR} standard${nRR===1?'':'s'} across ${nDom} domain${nDom===1?'':'s'}.</span>`;
      }
    }
    renderStandardsChips();
    markAcceptedStandards(specs);

    if (forgeData.auto_standards_enabled) {
      const card = document.getElementById("mrr-analysis-card");
      if (card) {
        card.style.display = "block";
        console.log('[MRR] firing classifier with', { wish_len: (forgeData.wish||'').length, project: forgeData.projectName, engine: 'gemini-3.5-flash-medium' });
        const _mrrPayload = {
          wish: forgeData.wish || "",
          users: forgeData.users || "",
          success_v1: forgeData.success || "",
          project: forgeData.projectName || "adt-framework",
          engine: "keyword_fallback"
        };
        if (!_mrrPayload.wish) {
          console.warn('[MRR] no wish text in forgeData — this is the bug');
        }
        // FIX 2026-08-09: same as above — force fast model + long AbortController.
        const _cls2Ctrl = new AbortController();
        const _cls2Timer = setTimeout(() => _cls2Ctrl.abort(), 120000);
        if (_mrrPayload && typeof _mrrPayload === "object" && !_mrrPayload.engine) {
          _mrrPayload.engine = "gemini-3.5-flash-medium";
        }
        fetch(`about:blank`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: _cls2Ctrl.signal,
          body: JSON.stringify(_mrrPayload)
        }).then(r => { clearTimeout(_cls2Timer); return r.ok ? r.json() : {}; }).then(data => {
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
          // FIX 2026-08-10: silent-friendly error — no scary red "Load failed" card
          // during the demo. Operator's Screen-2 chip selection is the ground truth;
          // this MRR card is a nice-to-have live preview. Log to console for devs.
          console.debug("[MRR card] classify fetch skipped/failed (harmless):", err && err.message || err);
          const contentEl = document.getElementById("mrr-analysis-content");
          if (contentEl) contentEl.innerHTML = `
            <div style="color:#8b949e;font-style:italic;font-size:12px">Live standards analysis skipped — using the operator-confirmed standards from Screen 2.</div>`;
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

    // SPEC-081 §1.3: forge just created a new project — invalidate the
    // cached registry so the launcher list picks it up.
    refresh(true);

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
