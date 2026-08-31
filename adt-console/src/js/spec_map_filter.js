// =============================================================================
// SPEC-111 — Spec Map Filtering and Focus Set
// Tasks 4 (filter logic), 5 (Bootstrap Wizard), 6 (Manage Focus panel)
// Frontend_Engineer — sovereign operator authority 2026-08-29
// =============================================================================

window.SpecMapFilter = window.SpecMapFilter || {};

// ---------------------------------------------------------------------------
// DEFAULT manifest (used when backend endpoint is not yet live)
// ---------------------------------------------------------------------------
window.SpecMapFilter.DEFAULT_MANIFEST = {
  version: 1,
  role_categories: {
    Systems_Architect: [],
    Backend_Engineer: [],
    Frontend_Engineer: [],
    DevOps_Engineer: [],
    Overseer: []
  },
  focus_set: [],
  hide_statuses: ["COMPLETED", "DEPRECATED", "SUPERSEDED"],
  last_bootstrapped_at: null,
  last_updated_by: null,
  last_updated_at: null
};

window.SpecMapFilter.DEFAULT_ROLES = [
  "Systems_Architect",
  "Backend_Engineer",
  "Frontend_Engineer",
  "DevOps_Engineer",
  "Overseer"
];

// SPEC-111 amendment (2026-08-30): fetch the ACTIVE project's role vocabulary
// from adt-center. Falls back to DEFAULT_ROLES only if the endpoint fails or
// the project has no vocabulary. Governed projects can define their own roles
// (OceanPulse ships Embedded_Engineer, Network_Engineer, Integration_Engineer,
// QA_Engineer, Product_Manager beyond ADT's core five).
window.SpecMapFilter.fetchProjectRoles = async function(projectId) {
  try {
    const base = (window.SpecMap && window.SpecMap.getCenterUrl && window.SpecMap.getCenterUrl())
                 || 'http://localhost:5001';
    const r = await fetch(`${base}/api/projects/${encodeURIComponent(projectId)}/roles`);
    if (r.ok) {
      const d = await r.json();
      if (Array.isArray(d.roles) && d.roles.length > 0) return d.roles;
    }
  } catch (_) { /* fall through */ }
  return window.SpecMapFilter.DEFAULT_ROLES;
};

// In-session toggle state (resets per project open)
window.SpecMapFilter._toggles = {
  showCompleted: false,
  showAllCategories: false,
  showAllSpecs: false
};

// Cached manifest for current project
window.SpecMapFilter._manifest = null;
window.SpecMapFilter._manifestProject = null;

// ---------------------------------------------------------------------------
// 3.3 FILTER LOGIC
// ---------------------------------------------------------------------------
window.SpecMapFilter.applyFilters = function(specs, manifest, activeRole) {
  if (!specs || !specs.length) return specs;

  const m = manifest || window.SpecMapFilter.DEFAULT_MANIFEST;
  const t = window.SpecMapFilter._toggles;

  // Master override: show all specs
  if (t.showAllSpecs) return specs;

  // Priority 1: focus_set non-empty -> keep only those IDs, ignore everything else
  if (m.focus_set && m.focus_set.length > 0) {
    const focusSet = new Set(m.focus_set);
    return specs.filter(s => focusSet.has(s.id || s.spec_id));
  }

  let result = specs;

  // Priority 2: drop hide_statuses (unless showCompleted toggle on)
  if (!t.showCompleted && m.hide_statuses && m.hide_statuses.length > 0) {
    const hideSet = new Set((m.hide_statuses).map(s => s.toUpperCase()));
    result = result.filter(s => !hideSet.has((s.status || '').toUpperCase()));
  }

  // Priority 3: role-based category filter (unless showAllCategories or no mapping)
  if (!t.showAllCategories) {
    const roleCats = m.role_categories || {};
    const catList = roleCats[activeRole];
    // Only filter if category list is non-empty (empty array = no filter, show warning)
    if (catList && catList.length > 0) {
      const catSet = new Set(catList);
      result = result.filter(s => {
        // Specs with null category always pass
        if (s.category == null) return true;
        return catSet.has(s.category);
      });
    }
  }

  return result;
};

// ---------------------------------------------------------------------------
// MANIFEST FETCH (with fallback to default)
// ---------------------------------------------------------------------------
window.SpecMapFilter.fetchManifest = async function(projectId) {
  const base = window.SpecMap.getCenterUrl();
  try {
    const r = await fetch(`${base}/api/projects/${encodeURIComponent(projectId)}/spec-map`);
    if (r.ok) {
      const data = await r.json();
      return data;
    }
  } catch (_) {}
  // Fallback: return a copy of the default
  return JSON.parse(JSON.stringify(window.SpecMapFilter.DEFAULT_MANIFEST));
};

// ---------------------------------------------------------------------------
// MANIFEST PUT
// ---------------------------------------------------------------------------
window.SpecMapFilter.saveManifest = async function(projectId, manifest) {
  const base = window.SpecMap.getCenterUrl();
  manifest.last_updated_by = "operator";
  manifest.last_updated_at = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
  const r = await fetch(`${base}/api/projects/${encodeURIComponent(projectId)}/spec-map`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(manifest)
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(d.error || `HTTP ${r.status}`);
  }
  // ADS event
  window.SpecMapFilter._logAds('spec_map_updated', 'spec-map manifest updated via Manage Focus', { project: projectId });
  window.SpecMapFilter._manifest = manifest;
  return await r.json();
};

// ---------------------------------------------------------------------------
// ADS logging
// ---------------------------------------------------------------------------
window.SpecMapFilter._logAds = function(actionType, description, extraData) {
  const ts = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
  const evId = 'evt_' + ts.replace(/[-:T.Z]/g,'').slice(0,16) + '_smf';
  fetch('http://localhost:5002/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event_id: evId, ts,
      agent: 'console', role: 'Frontend_Engineer',
      action_type: actionType,
      description: description,
      spec_ref: 'SPEC-111', authorized: true, tier: 3,
      action_data: Object.assign({
        spec_ref: 'SPEC-111',
        authority: 'operator_sovereign_override_for_SPEC-111'
      }, extraData || {})
    })
  }).catch(() => {});
};

// ---------------------------------------------------------------------------
// DROPDOWN HEADER: toggle controls
// Injected into the spec-map header area (row 1) beside the spec selector.
// ---------------------------------------------------------------------------
window.SpecMapFilter.injectDropdownControls = function() {
  if (document.getElementById('smf-controls-row')) return;

  // Insert after the spec selector row1
  const headerRow1 = document.querySelector('.spec-map-header-row1');
  if (!headerRow1) return;

  const row = document.createElement('div');
  row.id = 'smf-controls-row';
  row.style.cssText = 'display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-left:8px;';

  row.innerHTML = `
    <label class="smf-toggle" title="Show completed/deprecated/superseded specs">
      <input type="checkbox" id="smf-chk-completed">
      <span class="smf-toggle-track"></span>
      <span class="smf-toggle-label">Show completed</span>
    </label>
    <label class="smf-toggle" title="Show specs from all categories, ignoring role filter">
      <input type="checkbox" id="smf-chk-allcats">
      <span class="smf-toggle-track"></span>
      <span class="smf-toggle-label">Show all categories</span>
    </label>
    <label class="smf-toggle" title="Show every spec regardless of status, role or focus set">
      <input type="checkbox" id="smf-chk-allspecs">
      <span class="smf-toggle-track"></span>
      <span class="smf-toggle-label">Show all specs</span>
    </label>
    <button id="smf-btn-focus" class="smf-gear-btn" title="Manage Focus (SPEC-111)">&#9881; Focus</button>
    <div id="smf-no-filter-warning" style="display:none;background:#332600;border:1px solid #d29922;border-radius:4px;padding:2px 8px;font-size:11px;color:#d29922;cursor:pointer;" title="Click to configure in Manage Focus">
      no category filter configured for this role
    </div>
  `;

  headerRow1.appendChild(row);

  // Bind toggles
  function bindToggle(id, key) {
    const chk = document.getElementById(id);
    if (!chk) return;
    chk.checked = window.SpecMapFilter._toggles[key];
    chk.addEventListener('change', () => {
      window.SpecMapFilter._toggles[key] = chk.checked;
      window.SpecMapFilter._refreshSelectorWithFilter();
    });
  }
  bindToggle('smf-chk-completed',  'showCompleted');
  bindToggle('smf-chk-allcats',    'showAllCategories');
  bindToggle('smf-chk-allspecs',   'showAllSpecs');

  // Gear button -> Manage Focus
  const gearBtn = document.getElementById('smf-btn-focus');
  if (gearBtn) gearBtn.addEventListener('click', () => window.SpecMapFilter.openManageFocus());

  // Warning banner -> Manage Focus
  const warn = document.getElementById('smf-no-filter-warning');
  if (warn) warn.addEventListener('click', () => window.SpecMapFilter.openManageFocus());
};

// ---------------------------------------------------------------------------
// Apply filters to the spec selector dropdown (the existing <select>)
// ---------------------------------------------------------------------------
window.SpecMapFilter._refreshSelectorWithFilter = async function() {
  const sel = document.getElementById('spec-map-selector');
  if (!sel) return;

  const proj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';

  // Fetch all specs
  let specs = [];
  try {
    const base = window.SpecMap.getCenterUrl();
    const r = await fetch(`${base}/api/governance/specs?project=${encodeURIComponent(proj)}`);
    if (r.ok) {
      const data = await r.json();
      specs = Array.isArray(data) ? data : (data.specs || []);
    }
  } catch (_) {}

  // Normalize spec objects
  specs = specs.map(s => ({
    id: s.id || s.spec_id,
    title: s.title || '',
    status: s.status || '',
    category: s.category !== undefined ? s.category : null
  }));

  // Exclude Vision spec (existing logic)
  specs = specs.filter(s => !(s.id === 'SPEC-001' && (s.title||'').trim().toLowerCase() === 'vision'));

  // Get active role
  const activeRole = window.SpecMapFilter._getActiveRole();

  // Get manifest (use cached)
  let manifest = window.SpecMapFilter._manifest;
  if (!manifest || window.SpecMapFilter._manifestProject !== proj) {
    manifest = await window.SpecMapFilter.fetchManifest(proj);
    window.SpecMapFilter._manifest = manifest;
    window.SpecMapFilter._manifestProject = proj;
  }

  // Show/hide "no filter configured" warning
  const warn = document.getElementById('smf-no-filter-warning');
  if (warn) {
    const roleCats = (manifest.role_categories || {})[activeRole];
    const noFilter = !roleCats || roleCats.length === 0;
    warn.style.display = (noFilter && !window.SpecMapFilter._toggles.showAllCategories && !window.SpecMapFilter._toggles.showAllSpecs) ? '' : 'none';
  }

  // Apply filters
  const filtered = window.SpecMapFilter.applyFilters(specs, manifest, activeRole);
  filtered.sort((a, b) => (a.id || '').localeCompare(b.id || ''));

  const currentVal = sel.value;
  sel.innerHTML = '<option value="">Select a Spec...</option>' +
    filtered.map(s => `<option value="${s.id}">${s.id} - ${s.title}</option>`).join('');

  // Restore selection if still in filtered list
  if (currentVal && filtered.some(s => s.id === currentVal)) {
    sel.value = currentVal;
  }
};

window.SpecMapFilter._getActiveRole = function() {
  // Try to derive from active session context
  const ctxRole = document.getElementById('ctx-role');
  if (ctxRole && ctxRole.textContent && ctxRole.textContent.trim() !== '—') {
    return ctxRole.textContent.trim();
  }
  return 'Systems_Architect';
};

// ---------------------------------------------------------------------------
// Intercept populateSelector to apply filters
// ---------------------------------------------------------------------------
window.SpecMapFilter._hookPopulateSelector = function() {
  if (window.SpecMap._filterHooked) return;
  window.SpecMap._filterHooked = true;

  const _orig = window.SpecMap.populateSelector;
  window.SpecMap.populateSelector = function() {
    return _orig.apply(this, arguments).then(() => {
      // After base populate, apply filters
      window.SpecMapFilter._refreshSelectorWithFilter();
    });
  };
};

// ---------------------------------------------------------------------------
// Intercept project switch to reset toggles and re-check wizard trigger
// ---------------------------------------------------------------------------
window.SpecMapFilter._hookProjectSwitch = function() {
  if (window.SpecMap._filterProjHooked) return;
  window.SpecMap._filterProjHooked = true;

  const origBind = window.SpecMap.bindHeaderProjectDropdown;
  if (!origBind) return;

  window.SpecMap.bindHeaderProjectDropdown = function() {
    origBind.apply(this, arguments);
    // Observe project dropdown for changes
    const dd = document.getElementById('spec-map-header-project-dd');
    if (!dd || dd.dataset.filterHooked) return;
    dd.dataset.filterHooked = 'true';
    // When a new project is selected, reset toggles + manifest cache + check wizard
    const list = dd.querySelector('.adt-dd-list');
    if (list) {
      list.addEventListener('click', () => {
        setTimeout(async () => {
          // Reset toggles
          window.SpecMapFilter._toggles = { showCompleted: false, showAllCategories: false, showAllSpecs: false };
          ['smf-chk-completed', 'smf-chk-allcats', 'smf-chk-allspecs'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.checked = false;
          });
          // Invalidate manifest cache
          window.SpecMapFilter._manifest = null;
          window.SpecMapFilter._manifestProject = null;
          // Check wizard trigger
          const proj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
          const m = await window.SpecMapFilter.fetchManifest(proj);
          window.SpecMapFilter._manifest = m;
          window.SpecMapFilter._manifestProject = proj;
          if (!m.last_bootstrapped_at) {
            // Fetch specs for the wizard
            const base = window.SpecMap.getCenterUrl();
            let specs = [];
            try {
              const r = await fetch(`${base}/api/governance/specs?project=${encodeURIComponent(proj)}`);
              if (r.ok) {
                const d = await r.json();
                specs = Array.isArray(d) ? d : (d.specs || []);
              }
            } catch (_) {}
            window.SpecMapFilter.openBootstrapWizard(proj, specs, m);
          }
        }, 400);
      });
    }
  };
};

// ---------------------------------------------------------------------------
// TASK 5 — Bootstrap Wizard Modal
// ---------------------------------------------------------------------------
window.SpecMapFilter.openBootstrapWizard = async function(projectId, specs, existingManifest) {
  if (document.getElementById('smf-wizard-modal')) return;

  const roles = await window.SpecMapFilter.fetchProjectRoles(projectId);

  // Gather unique categories
  const catSet = new Set();
  let hasUncategorized = false;
  (specs || []).forEach(s => {
    const cat = s.category !== undefined ? s.category : null;
    if (cat == null) {
      hasUncategorized = true;
    } else {
      catSet.add(cat);
    }
  });
  const categories = Array.from(catSet).sort();
  if (hasUncategorized) categories.push('(uncategorized)');

  const manifest = existingManifest || JSON.parse(JSON.stringify(window.SpecMapFilter.DEFAULT_MANIFEST));

  // Build header cells
  const thHtml = roles.map(r => `<th style="writing-mode:vertical-lr;transform:rotate(180deg);padding:4px 2px;font-size:10px;color:#8b949e;font-weight:500;white-space:nowrap;max-width:32px;text-align:left;">${r}</th>`).join('');

  // Build body rows
  const rowsHtml = categories.map(cat => {
    const cells = roles.map(role => {
      const id = `smf-wiz-${_safeId(cat)}-${_safeId(role)}`;
      return `<td style="text-align:center;padding:4px;"><input type="checkbox" id="${id}" data-cat="${cat}" data-role="${role}" class="smf-wiz-cell"></td>`;
    }).join('');
    return `<tr><td style="padding:4px 8px;font-size:12px;color:#e6edf3;white-space:nowrap;">${_esc(cat)}</td>${cells}</tr>`;
  }).join('');

  const modal = document.createElement('div');
  modal.id = 'smf-wizard-modal';
  modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;';

  modal.innerHTML = `
    <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:24px;max-width:700px;width:95%;max-height:85vh;overflow-y:auto;color:#e6edf3;font-size:13px;box-shadow:0 16px 48px rgba(0,0,0,0.6);">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;">
        <div>
          <h2 style="margin:0 0 4px 0;font-size:17px;color:#58a6ff;">Route this project's specs to roles</h2>
          <div style="color:#8b949e;font-size:11px;">Project: <strong>${_esc(projectId)}</strong> &mdash; check which categories each role should see in the Spec Map dropdown.</div>
        </div>
        <button id="smf-wiz-skip" style="background:transparent;border:none;color:#8b949e;font-size:18px;cursor:pointer;padding:0;margin-left:12px;" title="Configure later">&times;</button>
      </div>
      <div id="smf-wiz-no-cats" style="${categories.length === 0 ? '' : 'display:none;'}padding:12px;background:#21262d;border-radius:4px;color:#8b949e;font-size:12px;margin-bottom:12px;">
        No categorized specs found in this project yet. You can configure role-to-category mappings in Manage Focus after specs are categorized.
      </div>
      <div id="smf-wiz-matrix-wrap" style="${categories.length === 0 ? 'display:none;' : ''}overflow-x:auto;margin-bottom:12px;">
        <table style="border-collapse:collapse;min-width:100%;">
          <thead><tr><th style="padding:4px 8px;text-align:left;font-size:11px;color:#8b949e;font-weight:500;">Category</th>${thHtml}</tr></thead>
          <tbody id="smf-wiz-body">${rowsHtml}</tbody>
        </table>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <button id="smf-wiz-assign-all" class="smf-btn-secondary">Assign all to all</button>
        <button id="smf-wiz-auto-guess" class="smf-btn-secondary">Auto-guess by name</button>
        <span style="flex:1"></span>
        <a href="#" id="smf-wiz-manage-focus-link" style="font-size:11px;color:#58a6ff;align-self:center;">Open Manage Focus &rsaquo;</a>
      </div>
      <div id="smf-wiz-status" style="font-size:11px;color:#8b949e;min-height:18px;margin-bottom:8px;"></div>
      <div style="display:flex;gap:8px;justify-content:flex-end;">
        <button id="smf-wiz-save" style="background:#1f6feb;color:#fff;border:1px solid #388bfd;border-radius:4px;padding:6px 16px;cursor:pointer;font-size:13px;font-weight:600;">Save &amp; continue</button>
        <button id="smf-wiz-later" style="background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:4px;padding:6px 16px;cursor:pointer;font-size:13px;">Configure later</button>
      </div>
    </div>
  `;

  document.body.appendChild(modal);

  function _getMatrix() {
    const rc = {};
    roles.forEach(r => { rc[r] = []; });
    modal.querySelectorAll('.smf-wiz-cell').forEach(chk => {
      if (chk.checked) {
        const cat = chk.dataset.cat;
        const role = chk.dataset.role;
        if (cat !== '(uncategorized)' && role && rc[role]) {
          rc[role].push(cat);
        }
      }
    });
    return rc;
  }

  function _setAll(val) {
    modal.querySelectorAll('.smf-wiz-cell').forEach(chk => { chk.checked = val; });
  }

  function _autoGuess() {
    modal.querySelectorAll('.smf-wiz-cell').forEach(chk => {
      chk.checked = false;
      const cat = (chk.dataset.cat || '').toLowerCase();
      const role = chk.dataset.role;
      if (role === 'Backend_Engineer' && /software|code|backend|api|server/.test(cat)) chk.checked = true;
      if (role === 'Frontend_Engineer' && /frontend|ui|web/.test(cat)) chk.checked = true;
      if (role === 'DevOps_Engineer' && /ops|devops|infra|deploy/.test(cat)) chk.checked = true;
      if ((role === 'Overseer' || role === 'Systems_Architect') && /governance|audit|compliance/.test(cat)) chk.checked = true;
    });
  }

  document.getElementById('smf-wiz-assign-all').onclick = () => _setAll(true);
  document.getElementById('smf-wiz-auto-guess').onclick = _autoGuess;

  document.getElementById('smf-wiz-skip').onclick = document.getElementById('smf-wiz-later').onclick = () => {
    modal.remove();
    const statusEl = document.getElementById('smf-no-filter-warning');
    if (statusEl) statusEl.style.display = '';
  };

  document.getElementById('smf-wiz-manage-focus-link').onclick = (e) => {
    e.preventDefault();
    modal.remove();
    window.SpecMapFilter.openManageFocus();
  };

  document.getElementById('smf-wiz-save').onclick = async () => {
    const btn = document.getElementById('smf-wiz-save');
    const statusEl = document.getElementById('smf-wiz-status');
    btn.disabled = true;
    btn.textContent = 'Saving...';
    try {
      const rc = _getMatrix();
      const newManifest = Object.assign({}, manifest, {
        role_categories: rc,
        hide_statuses: manifest.hide_statuses || ["COMPLETED", "DEPRECATED", "SUPERSEDED"],
        last_bootstrapped_at: new Date().toISOString().replace(/\.\d+Z$/, 'Z')
      });
      await window.SpecMapFilter.saveManifest(projectId, newManifest);
      window.SpecMapFilter._logAds('spec_map_bootstrap_completed', 'Bootstrap wizard completed for project ' + projectId, {
        project: projectId,
        roles_configured: roles,
        categories_seen: categories
      });
      if (statusEl) statusEl.textContent = 'Saved.';
      setTimeout(() => modal.remove(), 600);
      window.SpecMapFilter._refreshSelectorWithFilter();
    } catch (err) {
      if (statusEl) statusEl.textContent = 'Save failed: ' + err.message;
      btn.disabled = false;
      btn.textContent = 'Save & continue';
    }
  };
};

// ---------------------------------------------------------------------------
// TASK 6 — Manage Focus Panel
// ---------------------------------------------------------------------------
window.SpecMapFilter.openManageFocus = async function() {
  if (document.getElementById('smf-focus-panel')) return;

  const proj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
  const base = window.SpecMap.getCenterUrl();
  const roles = await window.SpecMapFilter.fetchProjectRoles(proj);

  // Fetch all specs
  let specs = [];
  try {
    const r = await fetch(`${base}/api/governance/specs?project=${encodeURIComponent(proj)}`);
    if (r.ok) {
      const d = await r.json();
      specs = (Array.isArray(d) ? d : (d.specs || [])).map(s => ({
        id: s.id || s.spec_id,
        title: s.title || '',
        status: s.status || '',
        category: s.category !== undefined ? s.category : null
      }));
    }
  } catch (_) {}

  // Get manifest
  let manifest = window.SpecMapFilter._manifest;
  if (!manifest || window.SpecMapFilter._manifestProject !== proj) {
    manifest = await window.SpecMapFilter.fetchManifest(proj);
    window.SpecMapFilter._manifest = manifest;
    window.SpecMapFilter._manifestProject = proj;
  }

  const panel = document.createElement('div');
  panel.id = 'smf-focus-panel';
  panel.style.cssText = 'position:fixed;top:0;right:0;width:520px;height:100%;background:#161b22;border-left:1px solid #30363d;z-index:9998;overflow-y:auto;color:#e6edf3;font-size:13px;box-shadow:-8px 0 32px rgba(0,0,0,0.5);';

  const focusSet = new Set(manifest.focus_set || []);
  const uncatSpecs = specs.filter(s => s.category == null);

  // Build category x role matrix
  const catSet = new Set();
  specs.forEach(s => { if (s.category != null) catSet.add(s.category); });
  const categories = Array.from(catSet).sort();

  // --- Section A: Focus Set ---
  const specRowsHtml = specs.map(s => {
    const checked = focusSet.has(s.id) ? 'checked' : '';
    const statusColor = s.status === 'COMPLETED' ? '#2e7d32'
      : s.status === 'ACTIVE' ? '#1f6feb'
      : s.status === 'APPROVED' ? '#388bfd'
      : '#6e7681';
    return `<tr>
      <td style="padding:3px 6px;text-align:center;"><input type="checkbox" class="smf-focus-chk" data-id="${_esc(s.id)}" ${checked}></td>
      <td style="padding:3px 6px;font-family:monospace;font-size:11px;color:#79c0ff;">${_esc(s.id)}</td>
      <td style="padding:3px 6px;font-size:11px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_esc(s.title)}">${_esc(s.title)}</td>
      <td style="padding:3px 6px;"><span style="font-size:10px;color:${statusColor}">${_esc(s.status)}</span></td>
      <td style="padding:3px 6px;font-size:10px;color:#8b949e;">${_esc(s.category || '')}</td>
    </tr>`;
  }).join('');

  // --- Section B: Role -> Category matrix ---
  const thHtml = roles.map(r => `<th style="padding:4px 6px;font-size:10px;color:#8b949e;font-weight:500;white-space:nowrap;">${_esc(r)}</th>`).join('');
  const matrixRowsHtml = categories.map(cat => {
    const cells = roles.map(role => {
      const id = `smf-mf-${_safeId(cat)}-${_safeId(role)}`;
      const checked = ((manifest.role_categories || {})[role] || []).includes(cat) ? 'checked' : '';
      return `<td style="text-align:center;padding:4px;"><input type="checkbox" id="${id}" data-cat="${_esc(cat)}" data-role="${_esc(role)}" class="smf-mf-cat-cell" ${checked}></td>`;
    }).join('');
    return `<tr><td style="padding:4px 8px;font-size:12px;color:#e6edf3;white-space:nowrap;">${_esc(cat)}</td>${cells}</tr>`;
  }).join('');

  // --- Section C: Uncategorized specs ---
  const uncatHtml = uncatSpecs.length
    ? uncatSpecs.map(s => `
        <tr>
          <td style="padding:4px 8px;font-family:monospace;font-size:11px;color:#79c0ff;">${_esc(s.id)}</td>
          <td style="padding:4px 8px;font-size:11px;max-width:160px;overflow:hidden;text-overflow:ellipsis;" title="${_esc(s.title)}">${_esc(s.title)}</td>
          <td style="padding:4px 8px;"><span style="font-size:10px;color:#8b949e;font-style:italic;">[deferred to v1.1]</span></td>
        </tr>`).join('')
    : '<tr><td colspan="3" style="padding:8px;color:#8b949e;font-style:italic;">No uncategorized specs.</td></tr>';

  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid #30363d;background:#0d1117;position:sticky;top:0;z-index:1;">
      <div>
        <div style="font-size:15px;font-weight:700;color:#58a6ff;">Manage Focus</div>
        <div style="font-size:11px;color:#8b949e;">Project: ${_esc(proj)}</div>
      </div>
      <button id="smf-focus-close" style="background:transparent;border:none;color:#8b949e;font-size:20px;cursor:pointer;padding:0;">&times;</button>
    </div>

    <!-- Section A: Focus Set -->
    <div style="padding:16px 20px;border-bottom:1px solid #30363d;">
      <div style="font-size:13px;font-weight:700;color:#e6edf3;margin-bottom:8px;">Focus Set</div>
      <div style="font-size:11px;color:#8b949e;margin-bottom:8px;">Ticked specs appear in the dropdown regardless of status or role filter.</div>
      <div style="display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
        <button id="smf-focus-only-active" class="smf-btn-secondary">Focus only ACTIVE</button>
        <button id="smf-focus-only-approved" class="smf-btn-secondary">Focus only APPROVED</button>
        <button id="smf-focus-clear" class="smf-btn-secondary smf-btn-danger">Clear focus</button>
      </div>
      <div style="max-height:280px;overflow-y:auto;border:1px solid #30363d;border-radius:4px;">
        <table style="border-collapse:collapse;width:100%;">
          <thead style="background:#0d1117;position:sticky;top:0;">
            <tr>
              <th style="padding:4px 6px;font-size:10px;color:#8b949e;font-weight:500;text-align:center;width:28px;"></th>
              <th style="padding:4px 6px;font-size:10px;color:#8b949e;font-weight:500;text-align:left;">ID</th>
              <th style="padding:4px 6px;font-size:10px;color:#8b949e;font-weight:500;text-align:left;">Title</th>
              <th style="padding:4px 6px;font-size:10px;color:#8b949e;font-weight:500;text-align:left;">Status</th>
              <th style="padding:4px 6px;font-size:10px;color:#8b949e;font-weight:500;text-align:left;">Category</th>
            </tr>
          </thead>
          <tbody>${specRowsHtml}</tbody>
        </table>
      </div>
      <div style="margin-top:10px;">
        <button id="smf-focus-save-a" style="background:#1f6feb;color:#fff;border:1px solid #388bfd;border-radius:4px;padding:5px 14px;cursor:pointer;font-size:12px;">Save focus set</button>
        <span id="smf-focus-status-a" style="margin-left:8px;font-size:11px;color:#8b949e;"></span>
      </div>
    </div>

    <!-- Section B: Role -> Category mapping -->
    <div style="padding:16px 20px;border-bottom:1px solid #30363d;">
      <div style="font-size:13px;font-weight:700;color:#e6edf3;margin-bottom:8px;">Role &rarr; Category Mapping</div>
      <div style="font-size:11px;color:#8b949e;margin-bottom:8px;">Which spec categories each role sees in the filtered dropdown.</div>
      ${categories.length === 0
        ? '<div style="color:#8b949e;font-style:italic;font-size:12px;">No categorized specs yet.</div>'
        : `<div style="overflow-x:auto;">
          <table style="border-collapse:collapse;">
            <thead><tr><th style="padding:4px 8px;text-align:left;font-size:11px;color:#8b949e;font-weight:500;">Category</th>${thHtml}</tr></thead>
            <tbody>${matrixRowsHtml}</tbody>
          </table>
        </div>`}
      <div style="margin-top:10px;">
        <button id="smf-focus-save-b" style="background:#1f6feb;color:#fff;border:1px solid #388bfd;border-radius:4px;padding:5px 14px;cursor:pointer;font-size:12px;">Save mapping</button>
        <span id="smf-focus-status-b" style="margin-left:8px;font-size:11px;color:#8b949e;"></span>
      </div>
    </div>

    <!-- Section C: Uncategorized specs -->
    <div style="padding:16px 20px;">
      <div style="font-size:13px;font-weight:700;color:#e6edf3;margin-bottom:8px;">Uncategorized Specs</div>
      <div style="font-size:11px;color:#8b949e;margin-bottom:8px;">Specs with no Category header. Inline category editing deferred to v1.1 (requires governed spec-edit API).</div>
      <div style="overflow-x:auto;border:1px solid #30363d;border-radius:4px;">
        <table style="border-collapse:collapse;width:100%;">
          <thead style="background:#0d1117;">
            <tr>
              <th style="padding:4px 8px;font-size:10px;color:#8b949e;font-weight:500;text-align:left;">ID</th>
              <th style="padding:4px 8px;font-size:10px;color:#8b949e;font-weight:500;text-align:left;">Title</th>
              <th style="padding:4px 8px;font-size:10px;color:#8b949e;font-weight:500;text-align:left;">Action</th>
            </tr>
          </thead>
          <tbody>${uncatHtml}</tbody>
        </table>
      </div>
    </div>
  `;

  document.body.appendChild(panel);

  // Bind close
  document.getElementById('smf-focus-close').onclick = () => panel.remove();

  // Batch focus actions
  document.getElementById('smf-focus-only-active').onclick = () => {
    panel.querySelectorAll('.smf-focus-chk').forEach(chk => {
      const row = chk.closest('tr');
      const statusEl = row && row.querySelector('td:nth-child(4) span');
      chk.checked = statusEl && statusEl.textContent.trim() === 'ACTIVE';
    });
  };
  document.getElementById('smf-focus-only-approved').onclick = () => {
    panel.querySelectorAll('.smf-focus-chk').forEach(chk => {
      const row = chk.closest('tr');
      const statusEl = row && row.querySelector('td:nth-child(4) span');
      chk.checked = statusEl && statusEl.textContent.trim() === 'APPROVED';
    });
  };
  document.getElementById('smf-focus-clear').onclick = () => {
    panel.querySelectorAll('.smf-focus-chk').forEach(chk => { chk.checked = false; });
  };

  // Save focus set
  document.getElementById('smf-focus-save-a').onclick = async () => {
    const btn = document.getElementById('smf-focus-save-a');
    const statusEl = document.getElementById('smf-focus-status-a');
    btn.disabled = true;
    btn.textContent = 'Saving...';
    try {
      const newFocus = Array.from(panel.querySelectorAll('.smf-focus-chk'))
        .filter(c => c.checked).map(c => c.dataset.id);
      const newManifest = Object.assign({}, window.SpecMapFilter._manifest, { focus_set: newFocus });
      await window.SpecMapFilter.saveManifest(proj, newManifest);
      if (statusEl) statusEl.textContent = 'Saved.';
      window.SpecMapFilter._refreshSelectorWithFilter();
    } catch (err) {
      if (statusEl) statusEl.textContent = 'Error: ' + err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = 'Save focus set';
    }
  };

  // Save category mapping
  document.getElementById('smf-focus-save-b').onclick = async () => {
    const btn = document.getElementById('smf-focus-save-b');
    const statusEl = document.getElementById('smf-focus-status-b');
    btn.disabled = true;
    btn.textContent = 'Saving...';
    try {
      const rc = {};
      roles.forEach(r => { rc[r] = []; });
      panel.querySelectorAll('.smf-mf-cat-cell').forEach(chk => {
        if (chk.checked) {
          const cat = chk.dataset.cat;
          const role = chk.dataset.role;
          if (cat && role && rc[role]) rc[role].push(cat);
        }
      });
      const newManifest = Object.assign({}, window.SpecMapFilter._manifest, { role_categories: rc });
      await window.SpecMapFilter.saveManifest(proj, newManifest);
      if (statusEl) statusEl.textContent = 'Saved.';
      window.SpecMapFilter._refreshSelectorWithFilter();
    } catch (err) {
      if (statusEl) statusEl.textContent = 'Error: ' + err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = 'Save mapping';
    }
  };
};

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function _esc(str) {
  return String(str || '').replace(/[<>&"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));
}
function _safeId(str) {
  return String(str || '').replace(/[^a-zA-Z0-9]/g, '_');
}

// ---------------------------------------------------------------------------
// CSS: toggle styles + misc
// ---------------------------------------------------------------------------
(function() {
  if (document.getElementById('smf-css')) return;
  const style = document.createElement('style');
  style.id = 'smf-css';
  style.textContent = `
    .smf-toggle {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      cursor: pointer;
      user-select: none;
      font-size: 11px;
      color: #8b949e;
    }
    .smf-toggle input[type="checkbox"] {
      display: none;
    }
    .smf-toggle-track {
      width: 28px;
      height: 14px;
      background: #30363d;
      border-radius: 7px;
      flex-shrink: 0;
      position: relative;
      transition: background 0.2s;
    }
    .smf-toggle-track::after {
      content: '';
      position: absolute;
      top: 2px;
      left: 2px;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #6e7681;
      transition: left 0.2s, background 0.2s;
    }
    .smf-toggle input:checked + .smf-toggle-track {
      background: #1f6feb;
    }
    .smf-toggle input:checked + .smf-toggle-track::after {
      left: 16px;
      background: #fff;
    }
    .smf-gear-btn {
      background: #21262d;
      color: #8b949e;
      border: 1px solid #30363d;
      border-radius: 4px;
      padding: 3px 9px;
      font-size: 11px;
      cursor: pointer;
      transition: background 0.15s;
    }
    .smf-gear-btn:hover {
      background: #2d333b;
      color: #e6edf3;
    }
    .smf-btn-secondary {
      background: #21262d;
      color: #e6edf3;
      border: 1px solid #30363d;
      border-radius: 4px;
      padding: 4px 10px;
      font-size: 11px;
      cursor: pointer;
    }
    .smf-btn-secondary:hover {
      background: #2d333b;
    }
    .smf-btn-danger {
      color: #f85149;
      border-color: #c62828;
    }
    .smf-btn-danger:hover {
      background: #1a0808;
    }
  `;
  document.head.appendChild(style);
})();

// ---------------------------------------------------------------------------
// INIT: hook into SpecMap.init
// ---------------------------------------------------------------------------
(function() {
  if (window.SpecMap._filterModuleInstalled) return;
  window.SpecMap._filterModuleInstalled = true;

  const _origInit = window.SpecMap.init;
  window.SpecMap.init = function() {
    // Inject toggle controls into header
    // (DOMContentLoaded may have already fired -- try immediately, else queue)
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        window.SpecMapFilter.injectDropdownControls();
        window.SpecMapFilter._hookPopulateSelector();
        window.SpecMapFilter._hookProjectSwitch();
      });
    } else {
      window.SpecMapFilter.injectDropdownControls();
      window.SpecMapFilter._hookPopulateSelector();
      window.SpecMapFilter._hookProjectSwitch();
    }
    return _origInit.apply(this, arguments);
  };

  // Also trigger wizard check on first project load (adt-framework default)
  const _origLoadSpec = window.SpecMap.loadSpec;
  let _wizardChecked = false;
  window.SpecMap.loadSpec = async function(specId) {
    if (!_wizardChecked) {
      _wizardChecked = true;
      const proj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
      try {
        const m = await window.SpecMapFilter.fetchManifest(proj);
        window.SpecMapFilter._manifest = m;
        window.SpecMapFilter._manifestProject = proj;
        if (!m.last_bootstrapped_at) {
          const base = window.SpecMap.getCenterUrl();
          let specs = [];
          try {
            const r = await fetch(`${base}/api/governance/specs?project=${encodeURIComponent(proj)}`);
            if (r.ok) {
              const d = await r.json();
              specs = (Array.isArray(d) ? d : (d.specs || []));
            }
          } catch (_) {}
          window.SpecMapFilter.openBootstrapWizard(proj, specs, m);
        }
      } catch (_) {}
    }
    return _origLoadSpec.apply(this, arguments);
  };

  console.log('[SpecMapFilter] SPEC-111 filter module installed');
})();
