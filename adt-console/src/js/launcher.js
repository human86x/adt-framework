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

  const getCenterUrl = () => localStorage.getItem("adt_center_url") || "http://localhost:5001";

  function init() {
    const main = document.getElementById("terminal-area");
    if (!main) return;

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
    document.getElementById("card-forge-mode").onclick = () => openProject("adt-framework");
    document.getElementById("card-create-project").onclick = openCreateWizard;
    document.getElementById("card-import-project").onclick = openImportWizard;
    document.getElementById("card-forge-app").onclick = openForgeWizard;

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

  function openCreateWizard() {
    showWizard(`
      <h2>Create New Project</h2>
      <div class="wizard-field">
        <label>Project Name</label>
        <input type="text" id="wiz-create-name" placeholder="my-app">
      </div>
      <div class="wizard-field">
        <label>Absolute Path</label>
        <input type="text" id="wiz-create-path" placeholder="/home/human/Projects/my-app">
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
  }

  function openImportWizard() {
    showWizard(`
      <h2>Import Project</h2>
      <div class="wizard-field">
        <label>Absolute Path</label>
        <input type="text" id="wiz-import-path" placeholder="/home/human/Projects/existing">
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
    showWizard(`
      <h2>Forge Application</h2>
      <p class="wiz-subtitle">Describe your vision. The Architect will formalize a specification and build the foundation autonomously.</p>
      <div class="wizard-field">
        <label>Your Wish</label>
        <textarea id="wiz-forge-wish" rows="4" placeholder="A governed REST API for tracking software releases, with automated test coverage and a CI/CD pipeline..."></textarea>
      </div>
      <div class="wizard-field">
        <label>Project Path <span class="wiz-required">*</span></label>
        <input type="text" id="wiz-forge-path" placeholder="/home/human/Projects/my-new-app">
      </div>
      <div class="wizard-field">
        <label>Project Name <span class="wiz-optional">(auto-detected from path)</span></label>
        <input type="text" id="wiz-forge-name" placeholder="my-new-app">
      </div>
      <div class="wizard-actions">
        <button class="btn-prev" id="btn-wiz-cancel">Cancel</button>
        <button class="primary forge-submit" id="btn-wiz-forge">Forge Application</button>
      </div>
    `);
    document.getElementById("btn-wiz-cancel").onclick = closeWizard;
    document.getElementById("btn-wiz-forge").onclick = submitForge;
    setTimeout(() => {
      const el = document.getElementById("wiz-forge-wish");
      if (el) el.focus();
    }, 100);
  }

  async function submitForge() {
    const wish = (document.getElementById("wiz-forge-wish")?.value || "").trim();
    const path = (document.getElementById("wiz-forge-path")?.value || "").trim();
    const name = (document.getElementById("wiz-forge-name")?.value || "").trim() || null;

    if (!wish) { alert("Please describe your wish."); return; }
    if (!path) { alert("Project path is required."); return; }

    const btn = document.getElementById("btn-wiz-forge");
    if (btn) { btn.disabled = true; btn.textContent = "Forging..."; }

    try {
      const res = await fetch(`${getCenterUrl()}/api/governance/forge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, intent_description: wish, name })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Forge failed.");

      const modal = document.querySelector(".wizard-modal");
      if (modal) {
        const projectName = data.project?.name || name || path.split("/").pop();
        modal.innerHTML = `
          <h2 style="color:#4CAF50;margin-top:0;">Forge Initiated</h2>
          <p style="color:#8b949e;margin-bottom:20px;">The Architect has been summoned.</p>
          <div class="forge-result">
            <div class="forge-result-row">
              <span class="forge-result-label">Project</span>
              <span>${projectName}</span>
            </div>
            <div class="forge-result-row">
              <span class="forge-result-label">Session</span>
              <span style="font-family:monospace;font-size:0.82rem">${data.session_id}</span>
            </div>
            <div class="forge-result-row">
              <span class="forge-result-label">Intent</span>
              <span style="font-family:monospace;font-size:0.82rem">${data.intent_id}</span>
            </div>
          </div>
          <p style="color:#8b949e;font-size:0.9rem;margin-top:16px;">The Architect is formalizing your specification. Monitor progress in the ADT Panel.</p>
          <div class="wizard-actions" style="margin-top:24px;">
            <button class="btn-prev" id="btn-forge-close">Close</button>
            <button class="primary" id="btn-forge-open">Open Project</button>
          </div>
        `;
        document.getElementById("btn-forge-close").onclick = closeWizard;
        document.getElementById("btn-forge-open").onclick = async () => {
          const sessionId = data.session_id;
          closeWizard();
          toggle();
          
          if (typeof SessionManager !== "undefined") {
            // Restore sessions to ensure the newly spawned one is in the local map
            await SessionManager.restore();
            // Switch to and focus the new session
            SessionManager.switchTo(sessionId);
          } else {
            openProject(projectName);
          }
        };
      }
      await refresh();
    } catch (err) {
      alert("Forge Error: " + err.toString());
      if (btn) { btn.disabled = false; btn.textContent = "Forge Application"; }
    }
  }

  function formatTimeAgo(ts) {
    if (!ts) return "unknown";
    const seconds = Math.floor((new Date() - new Date(ts)) / 1000);
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  }

  return { init, toggle, refresh, isActive: () => active, openProject, reopenSession, closeWizard, submitCreate, submitImport, openForgeWizard, submitForge };
})();
