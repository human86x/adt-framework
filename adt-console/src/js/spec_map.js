window.SpecMap = window.SpecMap || {};

window.SpecMap.getCenterUrl = function() {
  return localStorage.getItem('adt_center_url') || 'http://localhost:5001';
};

window.SpecMap.bindEventHandlers = function(cy) {
  // Store reference to cy for context menu actions
  window.SpecMap.cy = cy;

  // SPEC-062 Amendment D: per-node context menu
  cy.on('cxttap', 'node', function(evt){
    const node = evt.target;
    const data = node.data();
    const status = (data.status || 'pending').toLowerCase();
    let menu = document.getElementById('spec-map-context-menu');
    if (!menu) {
      menu = document.createElement('div');
      menu.id = 'spec-map-context-menu';
      menu.className = 'spec-map-context-menu';
      document.body.appendChild(menu);
    }
    const isFailed = status === 'failed' || status === 'skipped' || status === 'blocked';
    const specId = window.SpecMap.state.currentSpecId;
    menu.innerHTML = `
      <div class="cm-item" data-action="build">Build this task only</div>
      <div class="cm-item" data-action="mark-complete">Mark complete</div>
      ${isFailed ? '<div class="cm-item" data-action="redispatch">Re-dispatch failed</div>' : ''}
    `;
    const pos = evt.renderedPosition || evt.position || {x: 0, y: 0};
    const canvas = document.getElementById('spec-map-canvas');
    const rect = canvas ? canvas.getBoundingClientRect() : {left: 0, top: 0};
    menu.style.left = (rect.left + pos.x) + 'px';
    menu.style.top = (rect.top + pos.y) + 'px';
    menu.style.display = 'block';
    menu.querySelectorAll('.cm-item').forEach(item => {
      item.onclick = function() {
        menu.style.display = 'none';
        const action = this.getAttribute('data-action');
        const centerUrl = window.SpecMap.getCenterUrl();
        if (action === 'build' || action === 'redispatch') {
          fetch(`${centerUrl}/api/governance/specs/${specId}/build`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              triggered_by: 'spec_map_node_menu',
              harness: 'antigravity',
              target_task_id: data.task_id,
              force: action === 'redispatch'
            })
          })
          .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e.error || 'failed')))
          .then(d => {
            if (window.ToastManager) window.ToastManager.show('info', 'Build Dispatched', `Task ${data.task_id} -> build ${d.build_id}`);
            node.addClass('pulse-building');
            setTimeout(() => { try { node.removeClass('pulse-building'); } catch(_){} }, 60000);
            // Auto-open task detail panel so worker log is immediately visible
            setTimeout(() => {
              const detailPanel = document.getElementById('spec-map-detail');
              if (detailPanel) detailPanel.style.display = 'block';
              window.SpecMap.showNodeDetail(node);
            }, 800);
          })
          .catch(err => {
            if (window.ToastManager) window.ToastManager.show('denial', 'Build Failed', String(err));
          });
        } else if (action === 'mark-complete') {
          const ts = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
          const tsId = ts.replace(/[-:]/g, '').replace('T', '_').replace('Z', '') + '_taskmark';
          fetch('http://localhost:5002/log', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              event_id: `evt_${tsId.slice(0,20)}`,
              ts: ts,
              agent: 'HUMAN', role: 'Systems_Architect',
              action_type: 'task_status_updated',
              description: `Manually marked ${data.task_id} as completed via spec map menu.`,
              spec_ref: specId, authorized: true, tier: 3,
              action_data: {task_id: data.task_id, new_status: 'completed', source: 'spec_map_menu'}
            })
          })
          .then(() => {
            if (window.ToastManager) window.ToastManager.show('info', 'Status Updated', `${data.task_id} marked completed`);
            window.SpecMap.fetchAndRender(specId);
          });
        }
      };
    });
  });

  // hide context menu on any other click
  document.addEventListener('click', function(e) {
    const menu = document.getElementById('spec-map-context-menu');
    if (menu && menu.style.display === 'block' && !menu.contains(e.target)) {
      menu.style.display = 'none';
    }
  });

  // 1. Task node click -> right panel
  cy.on('tap', 'node', function(evt){
    const node = evt.target;
    const data = node.data();
    window.SpecMap.showDetailPanel(data);
  });

  // 2. Double-click task node -> open SPEC-052 session view
  // Cytoscape doesn't have a native dblclick, so we use a double-tap logic or just generic handler
  let lastNodeTap = 0;
  let lastNodeTapped = null;
  cy.on('tap', 'node', function(evt){
    const node = evt.target;
    const now = Date.now();
    if (lastNodeTapped === node && now - lastNodeTap < 300) {
      // Double click detected
      if(window.SessionManager && window.SessionManager.filterByTask) {
         window.SessionManager.filterByTask(node.data('task_id'));
         document.getElementById('btn-dashboard').click();
      }
    }
    lastNodeTap = now;
    lastNodeTapped = node;
  });

  // 3. Right-click node context menu
  cy.on('cxttap', 'node', function(evt){
    const node = evt.target;
    window.SpecMap.showNodeContextMenu(evt.originalEvent, node.data());
  });

  // SPEC-062-H thought cloud: hover in-progress tasks to see live worker log
  cy.on('mouseover', 'node', function(evt){
    const node = evt.target;
    const data = node.data();
    if (data.status !== 'in_progress') return;
    const proj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
    const e = evt.originalEvent;
    const x = e ? e.clientX : 100;
    const y = e ? e.clientY : 100;
    window.SpecMap._showThoughtCloud(data.task_id, proj, x, y);
  });
  cy.on('mousemove', 'node', function(evt){
    const state = window.SpecMap._thoughtCloud;
    if (state && state.el && evt.originalEvent) {
      state.el.style.left = (evt.originalEvent.clientX + 16) + 'px';
      state.el.style.top  = (evt.originalEvent.clientY + 16) + 'px';
    }
  });
  cy.on('mouseout', 'node', function(){
    window.SpecMap._hideThoughtCloud();
  });

  // 4. Right-click background context menu
  cy.on('cxttap', function(evt){
    if(evt.target === cy) {
      window.SpecMap.showBgContextMenu(evt.originalEvent);
    }
  });

  // Worker token clicks are handled via DOM events since they are HTML overlays outside Cytoscape
  const canvasContainer = document.getElementById('spec-map-canvas');
  if (canvasContainer && !canvasContainer.dataset.eventsBound) {
    canvasContainer.dataset.eventsBound = "true";
    canvasContainer.addEventListener('click', function(e) {
      if(e.target.closest('.worker-token')) {
        const token = e.target.closest('.worker-token');
        const sessionId = token.dataset.sessionId;
        // Open steering chat (SPEC-061)
        if(window.SessionManager && window.SessionManager.openSteeringChat) {
          window.SessionManager.openSteeringChat(sessionId);
        }
      }
    });
  }

  // Hide context menus on normal canvas click
  cy.on('tap', function(evt){
    window.SpecMap.hideContextMenus();
  });
};

window.SpecMap.showDetailPanel = async function(data) {
  const detailPanel = document.getElementById('spec-map-detail');
  const content = document.getElementById('smd-content');
  
  if (!data) {
    detailPanel.style.display = 'none';
    return;
  }
  
  detailPanel.style.display = 'block';
  content.innerHTML = `<div style="color:var(--text-muted);font-size:12px;">Loading...</div>`;

  // DEBUG: wrap full render in outer try/catch so any throw surfaces in the panel
  try {

  let depsHtml = '';
  if (data.depends_on && data.depends_on.length > 0) {
    depsHtml = `<h4>Dependencies</h4><ul style="padding-left:16px;">` + data.depends_on.map(d => {
      let status = 'unknown';
      if(window.SpecMap.cy) {
        const depNode = window.SpecMap.cy.getElementById(d);
        if(depNode && depNode.length > 0) {
          status = depNode.data('status') || 'unknown';
        }
      }
      return `<li style="margin-bottom:4px;">${d} <span class="ctx-badge" style="font-size:0.7em; margin-left:4px;">${status}</span></li>`;
    }).join('') + `</ul>`;
  } else {
    depsHtml = `<h4>Dependencies</h4><p style="color:var(--text-muted)">None</p>`;
  }

  // Format events dynamically by fetching from ADS
  let eventsHtml = `<h4>Recent Events</h4><ul style="padding-left:16px;"><li style="color:var(--text-muted)">None found</li></ul>`;
  // SPEC-062-E + operator request 2026-06-26: failure detail surfaced on failed/blocked task click
  let failureHtml = '';
  let workerActivityHtml = '';
          let watchdogHtml = '';
          let liveLogHtml = '';
  // Hoisted so the render template can reference them even when the Tauri fetch
  // skips (no __TAURI__) or throws.
  let runtimeHarness = null, runtimeModel = null, runtimeChosenVia = null, runtimeRiskScore = null;
  // Reset worker session tracking per click
  window.SpecMap._wsPid = null;
  window.SpecMap._wsSession = null;
  window.SpecMap._wsTs = null;

  if (data.task_id) {
     try {
       // PRIMARY: HTTP endpoint that knows per-project paths. Tauri's read_project_file
       // is hardcoded to the framework root and silently returns the wrong file for
       // /tmp/forge_test_* and other external projects.
       const proj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
       let adsContent = null;
       try {
         const r = await Promise.race([
           fetch(`${window.SpecMap.getCenterUrl()}/api/projects/${encodeURIComponent(proj)}/ads_tail?max_lines=3000`),
           new Promise((_, rej) => setTimeout(() => rej(new Error('ads_tail HTTP timed out after 3s')), 3000))
         ]);
         if (r.ok) {
           const j = await r.json();
           adsContent = j.content || "";
         }
       } catch(_) {
         // Fall back to Tauri (will only work for framework-internal projects)
         if (window.__TAURI__) {
           try {
             adsContent = await Promise.race([
               window.__TAURI__.core.invoke('read_project_file', { path: '_cortex/ads/events.jsonl' }),
               new Promise((_, rej) => setTimeout(() => rej(new Error('read_project_file timed out after 3s')), 3000))
             ]);
           } catch(__) { adsContent = ""; }
         }
       }
       if (adsContent) {
          const lines = adsContent.trim().split('\n').filter(Boolean);
          const taskEvents = [];
          const failureEvents = [];
          const FAIL_TYPES = new Set([
            'build_worker_failed', 'build_worker_silent_exit', 'build_worker_timeout',
            'build_worker_orphaned', 'build_worker_stalled',
            'denied_edit', 'denied_containment', 'denied_patch',
            'task_failed', 'build_verification_finding',
          ]);
          for (let i = lines.length - 1; i >= 0; i--) {
             try {
                const ev = JSON.parse(lines[i]);
                const ad = ev.action_data || {};
                const tidMatch = (ad.task_id === data.task_id) || (ad.target_task_id === data.task_id) ||
                                 (Array.isArray(ad.task_ids) && ad.task_ids.includes(data.task_id));
                if (tidMatch) {
                  if (ev.action_type === "task_risk_assessed" && runtimeModel === null) {
                    runtimeModel = ad.chosen_model || null;
                    runtimeChosenVia = ad.chosen_via || null;
                    runtimeRiskScore = ad.score;
                  }
                  if (ev.action_type === "build_worker_spawned" && runtimeHarness === null) {
                    runtimeHarness = ad.harness || null;
                    if (!runtimeModel) runtimeModel = ad.model || null;
                  }
                  // Capture session_id + pid for the most recent spawn of this task,
                  // for the "Worker Activity" filtered audit trail below.
                  if (ev.action_type === "build_worker_spawned" && !window.SpecMap._wsPid) {
                    window.SpecMap._wsPid = ad.pid;
                    window.SpecMap._wsSession = ev.session_id;
                    window.SpecMap._wsTs = ev.ts;
                  }
                  // Fallback: any event with ad.pid for this task records the pid
                  if (!window.SpecMap._wsPid && ad.pid) {
                    window.SpecMap._wsPid = ad.pid;
                  }
                }
                const roleMatch = !tidMatch && ev.role === data.role &&
                                  FAIL_TYPES.has(ev.action_type) &&
                                  ev.ts && (Date.now() - new Date(ev.ts).getTime() < 2*3600*1000);
                if (tidMatch) {
                   if (taskEvents.length < 8) taskEvents.push(ev);
                   if (FAIL_TYPES.has(ev.action_type) && failureEvents.length < 5) failureEvents.push(ev);
                } else if (roleMatch && failureEvents.length < 5 && (data.status === 'failed' || data.status === 'in_progress' || data.status === 'blocked')) {
                   failureEvents.push(ev);
                }
                if (taskEvents.length >= 8 && failureEvents.length >= 5) break;
             } catch(e) {}
          }
          if (taskEvents.length > 0) {
             eventsHtml = `<h4>Recent Events</h4><ul style="padding-left:16px;">` +
                          taskEvents.map(e => `<li>${e.action_type || 'event'} <span style="font-size:0.7em;color:var(--text-muted)">(${(e.ts || '').substring(11,19)})</span></li>`).join('') +
                          `</ul>`;
          }
          // Build the per-worker ADS audit trail (filter by PID OR session_id)
          if (window.SpecMap._wsPid || window.SpecMap._wsSession) {
            const wpid = window.SpecMap._wsPid;
            const wsid = window.SpecMap._wsSession;
            const workerEvents = [];
            for (let i = lines.length - 1; i >= 0; i--) {
              try {
                const ev = JSON.parse(lines[i]);
                const ad = ev.action_data || {};
                if ((wpid && ad.pid === wpid) || (wsid && ev.session_id === wsid)) {
                  workerEvents.push(ev);
                  if (workerEvents.length >= 60) break;
                }
              } catch(_) {}
            }
            if (workerEvents.length > 0) {
              workerEvents.reverse();
              const fmtWE = (e) => {
                const ad = e.action_data || {};
                const ts = (e.ts || '').substring(11,19);
                let color = '#8b949e';
                if (e.action_type.startsWith('denied_')) color = '#ff9090';
                else if (e.action_type.includes('completed') || e.action_type.includes('verified')) color = '#5cf080';
                else if (e.action_type.includes('failed') || e.action_type.includes('timeout')) color = '#ff7070';
                else if (e.action_type.includes('progress')) color = '#79c0ff';
                const extras = [];
                if (ad.path) extras.push(`<code style="font-size:9px">${(ad.path||'').split('/').slice(-2).join('/')}</code>`);
                if (ad.tasks_completed != null) extras.push(`${ad.tasks_completed}/${ad.task_total||'?'} done`);
                if (ad.stall_count) extras.push(`stalls=${ad.stall_count}`);
                if (ad.returncode != null) extras.push(`rc=${ad.returncode}`);
                const ex = extras.length ? ` <span style="color:var(--text-muted);font-size:10px">${extras.join(' &middot; ')}</span>` : '';
                return `<li style="margin-bottom:3px;font-size:11px;list-style:none;padding-left:0"><span style="color:var(--text-muted);font-size:10px">${ts}</span> <strong style="color:${color}">${e.action_type}</strong>${ex}</li>`;
              };
              workerActivityHtml = `
                <div style="margin-top:14px;border:1px solid #30363d;border-radius:6px;padding:8px;background:#0d1117">
                  <h4 style="margin:0 0 6px 0;font-size:12px;color:#58a6ff">Worker Activity <span style="font-weight:normal;color:var(--text-muted);font-size:10px">(${workerEvents.length} events, PID ${wpid||'?'})</span></h4>
                  <ul style="margin:0;padding:0;max-height:200px;overflow-y:auto">
                    ${workerEvents.map(fmtWE).join('')}
                  </ul>
                </div>`;
            }
          }  // end Worker Activity block

          // === SPEC-062-H: Sanity Watchdog conversation panel ===
          try {
            const _proj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
            const _tid = data.task_id || data.id;
            if (_tid) {
              const wdRes = await fetch(`${window.SpecMap.getCenterUrl()}/api/tasks/${encodeURIComponent(_tid)}/watchdog?project=${encodeURIComponent(_proj)}`);
              if (wdRes.ok) {
                const wd = await wdRes.json();
                if (wd && Array.isArray(wd.events)) {
                  if (wd.events.length === 0) {
                    // Always-visible "watching" status — so operator knows the watchdog is alive.
                    watchdogHtml = `<div id="smd-watchdog" style="margin-top:14px;border:1px solid #30363d;border-radius:6px;padding:8px;background:#0d1117"><h4 style="margin:0 0 4px 0;font-size:12px;color:#8bd88f">🐕 Sanity Watchdog — watching, no interventions</h4><div style="font-size:11px;color:var(--text-muted)">No narration/tool-stall detected on this worker. Escalates at ${5} narration lines + ${60}s no tool calls.</div></div>`;
                  } else {
                  const levelColor = wd.watchdog_level >= 3 ? '#ff5555'
                                    : wd.watchdog_level === 2 ? '#ff9900'
                                    : '#f0d000';
                  const rows = wd.events.map(e => {
                    const ts = new Date((e.ts || 0) * 1000).toLocaleTimeString();
                    const lvl = e.level != null ? `L${e.level}` : '';
                    const act = (e.action || '').replace(/_/g,' ');
                    const pid = e.worker_pid ? `pid=${e.worker_pid}` : '';
                    const injected = e.injected === false ? '<span style="color:#ff9090">✗ inject failed</span>'
                                    : e.injected === true ? '<span style="color:#7bd88f">✓ delivered</span>' : '';
                    const score = e.score ? `<span style="color:var(--text-muted);font-size:10px">nar=${e.score.narration_lines}, tools=${e.score.tool_markers}</span>` : '';
                    return `<li style="margin-bottom:6px;padding:6px;border-left:3px solid ${levelColor};background:#0d1117"><span style="font-size:10px;color:var(--text-muted)">${ts}</span> <strong style="color:${levelColor}">${lvl}</strong> ${act} ${pid} ${injected}<br>${score}</li>`;
                  }).join('');
                  watchdogHtml = `
                    <div id="smd-watchdog" style="margin-top:14px;border:1px solid ${levelColor};border-radius:6px;padding:8px;background:#150a08">
                      <h4 style="margin:0 0 6px 0;font-size:12px;color:${levelColor}">
                        🐕 Sanity Watchdog — Level ${wd.watchdog_level}
                        <span style="font-weight:normal;color:var(--text-muted);font-size:10px">(${wd.events.length} intervention${wd.events.length===1?'':'s'})</span>
                      </h4>
                      <ul style="margin:0;padding:0;list-style:none;max-height:180px;overflow-y:auto">${rows}</ul>
                    </div>`;
                  }
                }
              }
            }
          } catch (e) {
            console.warn('watchdog fetch failed', e);
          }

          // === Live Worker Console (SPEC-062-H visibility upgrade) ===
          try {
            const _projLog = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
            const _tidLog  = data.task_id || data.id;
            if (_tidLog) {
              const logRes = await fetch(`${window.SpecMap.getCenterUrl()}/api/tasks/${encodeURIComponent(_tidLog)}/worker_log_tail?project=${encodeURIComponent(_projLog)}&max_lines=40`);
              if (logRes.ok) {
                const ld = await logRes.json();
                if (ld && Array.isArray(ld.lines)) {
                  const active = ld.is_active;
                  const stale = ld.stale_sec != null ? `${Math.round(ld.stale_sec)}s ago` : '';
                  const headerColor = active ? '#7bd88f' : '#8b949e';
                  const pulseDot = active ? '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#7bd88f;margin-right:6px;animation:pulse 1s infinite"></span>' : '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#5a5a5a;margin-right:6px"></span>';
                  const linesHtml = ld.lines.length ? ld.lines.map(l => `<div style="font-family:monospace;font-size:10px;color:#c9d1d9;padding:1px 0;border-bottom:1px solid #161b22">${(l||'').replace(/[<>]/g,'')}</div>`).join('') : `<div style="font-size:11px;color:var(--text-muted);padding:8px">no output yet</div>`;
                  liveLogHtml = `
                    <div id="smd-live-log" data-task-id="${_tidLog}" style="margin-top:14px;border:1px solid ${active?'#238636':'#30363d'};border-radius:6px;padding:8px;background:#0d1117">
                      <div class="smd-live-log-model" style="display:flex; align-items:center; gap:8px; margin-bottom:8px; padding:6px 10px; background:linear-gradient(90deg, #0d1117, #131820); border:1px solid #30363d; border-radius:5px;">
                        <span style="font-size:10px; color:#8b949e; font-weight:600; letter-spacing:0.5px;">HARNESS</span>
                        <span class="smd-live-log-harness" style="font-size:13px; font-weight:700; color:#c9d1d9;">—</span>
                        <span style="font-size:10px; color:#8b949e; font-weight:600; margin-left:8px; letter-spacing:0.5px;">MODEL</span>
                        <span class="smd-live-log-model-name" style="font-size:13px; font-weight:700; color:#7ee787;">—</span>
                      </div>
                      <h4 class="smd-live-log-header" style="margin:0 0 6px 0;font-size:12px;color:${headerColor}">${pulseDot}Live Worker Log ${active?'<span style="font-size:10px;color:#7bd88f">(active)</span>':`<span style="font-size:10px;color:var(--text-muted)">(idle · updated ${stale})</span>`}</h4>
                      <div class="smd-live-log-body" style="max-height:240px;overflow-y:auto;background:#0a0e14;padding:4px;border-radius:3px">${linesHtml}</div>
                      <div class="smd-live-log-meta" style="font-size:10px;color:var(--text-muted);margin-top:4px">${ld.log_path || ''} · ${ld.total_lines || 0} lines</div>
                    </div>`;
                }
              }
            }
          } catch (e) { console.warn('live log fetch failed', e); }

          if (failureEvents.length > 0 && (data.status === 'failed' || data.status === 'blocked' || data.status === 'in_progress')) {
            const fmtEv = (e) => {
              const ad = e.action_data || {};
              const ts = (e.ts || '').substring(11,19);
              const desc = (e.description || '').replace(/[<>]/g, '');
              const extras = [];
              if (ad.returncode != null) extras.push(`exit=${ad.returncode}`);
              if (ad.timeout_sec)        extras.push(`timeout=${ad.timeout_sec}s`);
              if (ad.stall_count)        extras.push(`stalls=${ad.stall_count}`);
              if (ad.log_path)           extras.push(`<code style="font-size:10px">${ad.log_path.split('/').slice(-1)[0]}</code>`);
              if (ad.path)               extras.push(`<code style="font-size:10px">${ad.path}</code>`);
              const extraStr = extras.length ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px">${extras.join(' &middot; ')}</div>` : '';
              const stderr = ad.stderr_tail ? `<pre style="font-size:10px;color:#ff9090;background:#1a0808;padding:4px;margin-top:4px;max-height:120px;overflow:auto;border-radius:3px">${ad.stderr_tail.replace(/[<>]/g,'')}</pre>` : '';
              return `<li style="margin-bottom:8px"><strong style="color:#ff7070">${e.action_type}</strong> <span style="font-size:0.7em;color:var(--text-muted)">${ts}</span><div style="font-size:12px">${desc}</div>${extraStr}${stderr}</li>`;
            };
            failureHtml = `
              <div style="margin-top:16px;border:1px solid #c62828;border-radius:6px;padding:10px;background:#1a0808">
                <h4 style="color:#ff5252;margin:0 0 8px 0">Why it failed</h4>
                <ul style="padding-left:16px;margin:0;list-style:none">
                  ${failureEvents.map(fmtEv).join('')}
                </ul>
              </div>`;
          }
       }
     } catch(e) {
       console.warn('Failed to fetch ADS events for detail panel', e);
       eventsHtml = `<h4>Recent Events</h4><div style="color:var(--text-muted);font-size:11px;padding:6px 0">
         Events unavailable: ${(e && e.message) || e}.<br>
         (Common for projects outside the framework root. Use the spec map node colors / status badges instead.)
       </div>`;
     }
  } else if (data.recent_events && data.recent_events.length > 0) {
    eventsHtml = `<h4>Recent Events</h4><ul style="padding-left:16px;">` + 
                 data.recent_events.slice(0, 5).map(e => `<li>${e.type || 'event'}</li>`).join('') + 
                 `</ul>`;
  }

  let liveActivityHtml = '';
  if (data.worker && data.worker.recent_actions && data.worker.recent_actions.length > 0) {
    const actions = data.worker.recent_actions.slice(0, 3);
    const lastActionTs = data.worker.last_action_ts || data.worker.last_event_time;
    
    let relativeTs = 'recently';
    if (lastActionTs) {
      const ms = Date.now() - new Date(lastActionTs).getTime();
      const s = Math.floor(ms / 1000);
      if (s < 60) relativeTs = `${s}s ago`;
      else if (s < 3600) relativeTs = `${Math.floor(s/60)}m ago`;
      else relativeTs = `${Math.floor(s/3600)}h ago`;
    }

    liveActivityHtml = `
      <div style="margin-top:16px; border-top:1px solid var(--border); padding-top:16px;">
        <h4 style="color:var(--accent-blue); margin-bottom:8px;">Live Activity <span style="font-size:0.8em; color:var(--text-muted); font-weight:normal; margin-left:8px;">${relativeTs}</span></h4>
        <ul style="padding-left:16px; font-size:12px; margin:0;">
          ${actions.map(a => {
            const label = typeof a === 'string' ? a : (a.type || a.action_type || JSON.stringify(a));
            return `<li>${label}</li>`;
          }).join('')}
        </ul>
      </div>
    `;
  }

  // Cache spec_ref onto the data object for the re-run fallback
  if (data.spec_ref) {
    window.SpecMap._lastTaskSpecRef = data.spec_ref;
  }

  // SPEC-067-C: model escalation banner (works for Paul: stays on agy, upgrades model)
  const currentAgyModel = data.assigned_model || '';
  const isAlreadyOnClaude = currentAgyModel.toLowerCase().includes('claude');
  let escalationHtml = '';
  if (data.harness_escalation_offered && !isAlreadyOnClaude && data.task_id) {
    escalationHtml = `
      <div style="margin-top:10px;padding:10px;border:2px solid #ffd60a;border-radius:6px;background:#332600;color:#ffd60a;font-size:12px">
        <div style="font-weight:bold;margin-bottom:4px">&#9888; Stuck on default agy model</div>
        <div style="color:#e6edf3;margin-bottom:8px">This task failed multiple times with no code produced. Default agy model (Gemini) keeps narrating instead of writing files. Try a heavier model.</div>
        <button id="smd-escalate-btn" type="button"
                data-task-id="${data.task_id}"
                data-spec-ref="${(data.spec_ref||'').replace(/"/g,'&quot;')}"
                style="background:#1f6feb;color:#fff;border:none;padding:6px 14px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600">
          Retry with Claude Sonnet (via agy)
        </button>
        <span id="smd-escalate-status" style="margin-left:8px;font-size:11px;color:#8b949e"></span>
      </div>`;
  }

  // Re-run + reassign controls (custom div-based dropdowns -- native <select> popups are
  // unreadable on WebKitGTK in Tauri because GTK paints the dropdown outside our CSS scope)
  let rerunHtml = '';
  if (data.task_id && (data.status === 'failed' || data.status === 'blocked' || data.status === 'in_progress' || data.status === 'ready')) {
    const MODELS = [
      { v: '', l: 'default' },
      { v: 'Claude Sonnet 4.6 (Thinking)', l: 'Claude Sonnet 4.6' },
      { v: 'Claude Opus 4.6 (Thinking)',   l: 'Claude Opus 4.6' },
      { v: 'Gemini 3.1 Pro (High)',        l: 'Gemini 3.1 Pro' },
      { v: 'Gemini 3.5 Flash (High)',      l: 'Gemini 3.5 Flash' },
    ];
    const HARNESSES = [
      { v: '', l: 'default' },
      { v: 'antigravity', l: 'antigravity' },
      { v: 'claude', l: 'claude' },
      { v: 'gemini', l: 'gemini' },
    ];
    const currentModel   = data.assigned_model || '';
    const currentHarness = data.assigned_harness || '';
    const curModelLabel  = (MODELS.find(m => m.v === currentModel)   || MODELS[0]).l;
    const curHarnLabel   = (HARNESSES.find(h => h.v === currentHarness) || HARNESSES[0]).l;
    const riskBadge = (data.risk_level === 'high')
      ? `<span class="ctx-badge" style="background:#9333ea;color:#fff" title="Predicted heavy workload">RISK: HIGH</span>`
      : '';
    const ddHtml = (id, items, curVal, curLabel, minW) => `
      <div class="adt-dd" id="${id}" data-value="${curVal}" style="max-width:none">
        <div class="adt-dd-toggle" role="button" tabindex="0" style="min-width:${minW}px">
          <span class="adt-dd-label">${curLabel}</span><span class="adt-dd-caret">&#9662;</span>
        </div>
        <ul class="adt-dd-list" hidden role="listbox">
          ${items.map(it => `<li class="adt-dd-item${it.v===curVal?' adt-dd-item-current':''}" role="option" data-value="${it.v}">${it.l}</li>`).join('')}
        </ul>
      </div>`;
    rerunHtml = `
      <div style="margin-top:10px;padding:8px;border:1px solid var(--border);border-radius:4px;background:#0d1117">
        ${riskBadge}
        <div style="display:flex;gap:6px;align-items:center;margin-top:6px;flex-wrap:wrap">
          <label style="font-size:11px;color:var(--text-muted)">Harness</label>
          ${ddHtml('smd-harness-dd', HARNESSES, currentHarness, curHarnLabel, 110)}
          <label style="font-size:11px;color:var(--text-muted);margin-left:4px">Model</label>
          ${ddHtml('smd-model-dd', MODELS, currentModel, curModelLabel, 170)}
          <button id="smd-reassign-btn" type="button"
                  data-task-id="${data.task_id}"
                  style="padding:3px 8px;background:#2e7d32;border:none;color:#fff;border-radius:3px;cursor:pointer;font-size:11px">Reassign</button>
        </div>
        <div style="margin-top:6px">
          <button id="smd-rerun-btn" type="button"
                  data-task-id="${data.task_id}"
                  data-status="${data.status || ''}"
                  data-spec-ref="${(data.spec_ref||'').replace(/"/g,'&quot;')}"
                  style="padding:6px 12px;background:#1f6feb;border:none;color:#fff;border-radius:4px;cursor:pointer;font-size:12px">
            Re-run This Task
          </button>
          <span id="smd-rerun-status" style="margin-left:8px;font-size:11px;color:var(--text-muted)"></span>
        </div>
      </div>`;
  }

  // SPEC-062-G one-liner: just a clickable summary near top when failed
  let failureSummaryHtml = '';
  if (failureHtml && (data.status === 'failed' || data.status === 'blocked')) {
    failureSummaryHtml = `
      <div style="margin:6px 0 10px 0;padding:6px 8px;border-left:3px solid #c62828;background:#1a0808;color:#ff9090;font-size:12px;cursor:pointer"
           onclick="document.getElementById('smd-failure-detail')?.scrollIntoView({behavior:'smooth'});">
        &#9888; Task failed - <span style="text-decoration:underline">see Why it failed at bottom</span>
      </div>`;
  }

  // Move full failure detail to the very bottom with an anchor id
  const failureBlockBottom = failureHtml
    ? `<div id="smd-failure-detail">${failureHtml}</div>`
    : '';

  const panelTitle = document.getElementById('smd-panel-title');
  if (panelTitle && data.task_id) panelTitle.textContent = `Task Detail  ${data.task_id}`;
  else if (panelTitle) panelTitle.textContent = 'Task Detail';

  content.innerHTML = `
    <div style="margin-bottom: 12px;">
      <span class="ctx-badge">${data.task_id || ''}</span>
      <span class="ctx-badge badge-blue">${data.role || 'Unknown Role'}</span>
      <span class="ctx-badge" style="background:${data.status === 'failed' ? '#c62828' : data.status === 'completed' ? '#2e7d32' : '#6e7681'};color:#fff">${data.status || 'unknown'}</span>
      ${runtimeHarness || runtimeModel ? `<span class="ctx-badge" style="background:#21262d;color:#58a6ff;font-size:10px;margin-left:4px" title="Actual harness/model used in last run">${(runtimeHarness||'?')}${runtimeModel ? ' / '+runtimeModel : ''}${runtimeChosenVia ? ' (via '+runtimeChosenVia+(runtimeRiskScore != null ? ', risk='+runtimeRiskScore : '')+')' : ''}</span>` : ''}
    </div>
    <div style="font-weight:700; font-size:15px; color:#e6edf3; margin-bottom:10px; line-height:1.35">${data.title || 'Untitled Task'}</div>
    ${failureSummaryHtml}
    <div style="font-size:13px; color:#b1bac4; margin-bottom:14px; line-height:1.5">${data.description || 'No description available.'}</div>
    ${escalationHtml}
    ${rerunHtml}
    ${depsHtml}
    ${eventsHtml}
    ${liveActivityHtml}
    <div style="margin-top: 16px;">
      <a href="#" onclick="if(window.GovernancePanel) { window.GovernancePanel.switchTab('taskboard'); document.getElementById('btn-governance').click(); }" style="color: var(--accent-blue); text-decoration: underline; cursor: pointer;">Open in Tasks tab</a>
    </div>
    ${workerActivityHtml}
              ${watchdogHtml}
              ${liveLogHtml}
    ${failureBlockBottom}
  `;

  } catch(_outerErr) {
    console.error('[showDetailPanel] caught:', _outerErr);
    content.innerHTML = `
      <div style="color:#ff7070;padding:8px;font-size:12px;border:1px solid #c62828;border-radius:4px;background:#1a0808">
        <strong>Render error</strong><br>
        ${(_outerErr && _outerErr.stack) || _outerErr}
      </div>`;
    return;
  }

  // Bind escalation button programmatically (inline onclick can silently fail in WebKitGTK)
  const escBtn = document.getElementById('smd-escalate-btn');
  if (escBtn && !escBtn.dataset.bound) {
    escBtn.dataset.bound = "true";
    escBtn.addEventListener('click', (ev) => {
      ev.preventDefault(); ev.stopPropagation();
      const tid = escBtn.dataset.taskId;
      const sref = escBtn.dataset.specRef;
      escBtn.disabled = true;
      escBtn.textContent = 'Clicking...';
      escBtn.style.opacity = '0.6';
      if (typeof window.SpecMap.escalateToClaudeAndRetry === 'function') {
        window.SpecMap.escalateToClaudeAndRetry(tid, sref);
      } else {
        alert('escalateToClaudeAndRetry handler missing');
        escBtn.disabled = false; escBtn.textContent = 'Retry with Claude Sonnet (via agy)'; escBtn.style.opacity = '1';
      }
    });
  }
  // Same treatment for Reassign + Re-run buttons: bind programmatically, immediate feedback
  const rsBtn = document.getElementById('smd-reassign-btn');
  if (rsBtn && !rsBtn.dataset.bound) {
    rsBtn.dataset.bound = "true";
    rsBtn.addEventListener('click', (ev) => {
      ev.preventDefault(); ev.stopPropagation();
      const orig = rsBtn.textContent;
      rsBtn.disabled = true; rsBtn.textContent = 'Reassigning...'; rsBtn.style.opacity = '0.6';
      Promise.resolve(window.SpecMap.reassignTask(rsBtn.dataset.taskId)).finally(() => {
        setTimeout(() => { rsBtn.disabled = false; rsBtn.textContent = orig; rsBtn.style.opacity = '1'; }, 1500);
      });
    });
  }
  const rrBtn = document.getElementById('smd-rerun-btn');
  if (rrBtn && !rrBtn.dataset.bound) {
    rrBtn.dataset.bound = "true";
    rrBtn.addEventListener('click', (ev) => {
      ev.preventDefault(); ev.stopPropagation();
      rrBtn.disabled = true; rrBtn.textContent = 'Dispatching...'; rrBtn.style.opacity = '0.6';
      window.SpecMap.rerunFailedTask(rrBtn.dataset.taskId, rrBtn.dataset.status, rrBtn.dataset.specRef);
    });
  }

  // Bind custom dropdowns after innerHTML write
  ['smd-harness-dd', 'smd-model-dd'].forEach(id => {
    const dd = document.getElementById(id);
    if (!dd) return;
    const toggle = dd.querySelector('.adt-dd-toggle');
    const list = dd.querySelector('.adt-dd-list');
    const label = dd.querySelector('.adt-dd-label');
    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      // close any other open dropdowns
      document.querySelectorAll('.adt-dd-list').forEach(l => { if (l !== list) l.hidden = true; });
      list.hidden = !list.hidden;
    });
    list.querySelectorAll('.adt-dd-item').forEach(li => {
      li.addEventListener('click', (e) => {
        e.stopPropagation();
        const v = li.dataset.value;
        dd.dataset.value = v;
        label.textContent = li.textContent;
        list.querySelectorAll('.adt-dd-item').forEach(x => x.classList.remove('adt-dd-item-current'));
        li.classList.add('adt-dd-item-current');
        list.hidden = true;
      });
    });
  });
  // Close on outside click
  if (!window.SpecMap._ddOutsideHandlerBound) {
    document.addEventListener('click', () => {
      document.querySelectorAll('.adt-dd-list').forEach(l => l.hidden = true);
    });
    window.SpecMap._ddOutsideHandlerBound = true;
  }
};

// SPEC-061-B operator override: set per-task harness/model for next run
// SPEC-067-C: one-click escalate to claude harness + immediately re-run
window.SpecMap.escalateToClaudeAndRetry = async function(taskId, specRefHint) {
  const status = document.getElementById('smd-escalate-status');
  const btn = document.getElementById('smd-escalate-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Escalating...'; btn.style.opacity = '0.6'; }
  const project = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
  try {
    // Stay on agy harness (works for Paul too), upgrade MODEL to Claude Sonnet within agy
    await fetch(`${window.SpecMap.getCenterUrl()}/api/tasks/${encodeURIComponent(taskId)}/reassign?project=${encodeURIComponent(project)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ harness: 'antigravity', model: 'Claude Sonnet 4.6 (Thinking)' })
    });
    await fetch(`${window.SpecMap.getCenterUrl()}/api/tasks/${encodeURIComponent(taskId)}/reset?project=${encodeURIComponent(project)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_status: 'ready', clear_failure: true })
    });
    let specId = (window.SpecMap.state && window.SpecMap.state.currentSpecId) || specRefHint || window.SpecMap._lastTaskSpecRef;
    if (!specId) {
      if (status) status.textContent = 'No spec id resolved';
      if (btn) { btn.disabled = false; btn.textContent = 'Retry with Claude'; btn.style.opacity = '1'; }
      return;
    }
    const r = await fetch(`${window.SpecMap.getCenterUrl()}/api/governance/specs/${encodeURIComponent(specId)}/build?project=${encodeURIComponent(project)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ triggered_by: 'escalation_retry', harness: 'antigravity', target_task_id: taskId, force: true })
    });
    const d = await r.json().catch(() => ({}));
    if (r.ok) {
      if (status) status.textContent = `Dispatched as ${d.build_id || 'claude build'}`;
      if (btn) { btn.textContent = 'Dispatched'; }
    } else {
      if (status) status.textContent = `Failed: ${d.error || r.status}`;
      if (btn) { btn.disabled = false; btn.textContent = 'Retry with Claude'; btn.style.opacity = '1'; }
    }
  } catch (err) {
    if (status) status.textContent = `Error: ${err.message}`;
    if (btn) { btn.disabled = false; btn.textContent = 'Retry with Claude'; btn.style.opacity = '1'; }
  }
};


window.SpecMap.reassignTask = async function(taskId) {
  const harness = (document.getElementById('smd-harness-dd')?.dataset.value) || '';
  const model   = (document.getElementById('smd-model-dd')?.dataset.value)   || '';
  const statusEl = document.getElementById('smd-rerun-status');
  const project = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
  if (!harness && !model) {
    if (statusEl) statusEl.textContent = 'Pick a harness or model to reassign.';
    return;
  }
  const body = {};
  if (harness) body.harness = harness;
  if (model)   body.model = model;
  try {
    const res = await fetch(`${window.SpecMap.getCenterUrl()}/api/tasks/${encodeURIComponent(taskId)}/reassign?project=${encodeURIComponent(project)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (statusEl) statusEl.textContent = `Reassign failed: ${d.error || res.status}`;
      return;
    }
    if (statusEl) statusEl.textContent = `Reassigned. Next run will use ${d.assigned_harness||'default harness'} / ${d.assigned_model||'default model'}.`;
  } catch (err) {
    if (statusEl) statusEl.textContent = 'Network error: ' + err.message;
  }
};

// SPEC-062-D / operator request 2026-06-26: re-dispatch a single failed/blocked task
window.SpecMap.rerunFailedTask = async function(taskId, currentStatus, specRefHint) {
  const statusEl = document.getElementById('smd-rerun-status');
  const btn = document.getElementById('smd-rerun-btn');
  if (!taskId) return;
  // Resolve spec_id from: state > inline hint > cached _lastTaskSpecRef
  let specId = (window.SpecMap.state && window.SpecMap.state.currentSpecId) || '';
  if (!specId && specRefHint) specId = specRefHint;
  if (!specId && window.SpecMap._lastTaskSpecRef) specId = window.SpecMap._lastTaskSpecRef;
  const project = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
  if (!specId) {
    if (statusEl) statusEl.textContent = 'No spec selected (try clicking the task node first).';
    console.warn('[SpecMap] rerunFailedTask: no specId', {taskId, currentStatus, specRefHint, state: window.SpecMap.state});
    return;
  }
  if (btn) { btn.disabled = true; btn.textContent = 'Dispatching...'; }
  if (statusEl) statusEl.textContent = '';

  // 1. Reset task status to ready so the build executor picks it up cleanly
  try {
    await fetch(`${window.SpecMap.getCenterUrl()}/api/tasks/${encodeURIComponent(taskId)}/reset?project=${encodeURIComponent(project)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_status: 'ready', clear_failure: true })
    });
  } catch(_) { /* non-fatal: build endpoint may still pick it up */ }

  // 2. Trigger build scoped to this task with force=true
  try {
    const res = await fetch(`${window.SpecMap.getCenterUrl()}/api/governance/specs/${encodeURIComponent(specId)}/build?project=${encodeURIComponent(project)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        triggered_by: 'spec_map_rerun_button',
        harness: 'antigravity',
        target_task_id: taskId,
        force: true,
      })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (statusEl) statusEl.textContent = `Failed: ${data.error || res.status}`;
      if (btn) { btn.disabled = false; btn.textContent = 'Re-run This Task'; }
      return;
    }
    if (statusEl) statusEl.textContent = `Build ${data.build_id || 'dispatched'} — live log loading below...`;
    if (btn) { btn.textContent = 'Dispatched'; }
    // Refresh the detail panel so smd-live-log repopulates with fresh build_id
    setTimeout(() => {
      if (window.SpecMap.state && window.SpecMap.state.cy) {
        const node = window.SpecMap.state.cy.getElementById(taskId);
        if (node && node.length) window.SpecMap.showNodeDetail(node);
      }
    }, 1200);
  } catch(err) {
    if (statusEl) statusEl.textContent = 'Network error: ' + err.message;
    if (btn) { btn.disabled = false; btn.textContent = 'Re-run This Task'; }
  }
};

window.SpecMap.hideContextMenus = function() {
  const nodeMenu = document.getElementById('sm-node-context-menu');
  const bgMenu = document.getElementById('sm-bg-context-menu');
  if(nodeMenu) nodeMenu.style.display = 'none';
  if(bgMenu) bgMenu.style.display = 'none';
};

window.SpecMap.showNodeContextMenu = function(e, data) {
  window.SpecMap.hideContextMenus();
  const menu = document.getElementById('sm-node-context-menu');
  if(!menu) return;
  menu.style.display = 'block';
  menu.style.left = e.pageX + 'px';
  menu.style.top = e.pageY + 'px';
  menu.dataset.taskId = data.task_id;
};

window.SpecMap.showBgContextMenu = function(e) {
  window.SpecMap.hideContextMenus();
  const menu = document.getElementById('sm-bg-context-menu');
  if(!menu) return;
  menu.style.display = 'block';
  menu.style.left = e.pageX + 'px';
  menu.style.top = e.pageY + 'px';
};

// Bind context menu actions
document.addEventListener('DOMContentLoaded', () => {
  const nodeMenu = document.getElementById('sm-node-context-menu');
  if(nodeMenu) {
    nodeMenu.addEventListener('click', (e) => {
      if(e.target.classList.contains('sm-menu-item')) {
        const action = e.target.dataset.action;
        const taskId = nodeMenu.dataset.taskId;
        if(action === 'dispatch') {
          console.log('Dispatch worker to', taskId);
          const specId = window.SpecMap.state.currentSpecId;
          if(!specId) {
            if(window.ToastManager) window.ToastManager.show('denial', 'No Spec', 'Cannot dispatch without active spec');
            return;
          }
          const centerUrl = window.SpecMap.getCenterUrl();
          fetch(`${centerUrl}/api/governance/specs/${specId}/build`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ triggered_by: 'console_dispatch', harness: 'claude', target_task_id: taskId })
          })
          .then(res => {
             if(!res.ok) return res.json().then(err => { throw new Error(err.error || res.statusText); });
             return res.json();
          })
          .then(data => {
            if(window.ToastManager) window.ToastManager.show('info', 'Worker Dispatched', `Queued worker for ${taskId}`);
            if(window.BuildManager && window.BuildManager.showBuildProgress) {
               window.BuildManager.showBuildProgress(data.build_id, specId);
            }
          })
          .catch(err => {
            if(window.ToastManager) window.ToastManager.show('denial', 'Dispatch Failed', err.message);
          });
        } else if(action === 'block') {
          console.log('Mark blocked', taskId);
          if(window.ToastManager) {
            window.ToastManager.show('info', 'Mark Blocked', `Task ${taskId} marked as blocked`);
          }
        } else if(action === 'copy') {
          navigator.clipboard.writeText(taskId);
          if(window.ToastManager) {
            window.ToastManager.show('info', 'Copied', `Task ID ${taskId} copied to clipboard`);
          }
        }
        window.SpecMap.hideContextMenus();
      }
    });
  }

  const bgMenu = document.getElementById('sm-bg-context-menu');
  if(bgMenu) {
    bgMenu.addEventListener('click', (e) => {
      if(e.target.classList.contains('sm-menu-item')) {
        const action = e.target.dataset.action;
        if(action === 'relayout') {
          if(window.SpecMap.cy) {
             const layoutName = typeof cytoscapeDagre === 'function' ? 'dagre' : 'breadthfirst';
             window.SpecMap.cy.layout({name: layoutName, rankDir: 'TB', nodeSep: 40, rankSep: 80}).run();
          }
        } else if(action === 'export') {
          if(window.SpecMap.cy) {
            const png64 = window.SpecMap.cy.png({full: true});
            const a = document.createElement('a');
            a.href = png64;
            a.download = 'spec-map.png';
            a.click();
          }
        } else if(action === 'switch') {
          const selector = document.getElementById('spec-map-selector');
          if(selector) selector.focus();
        }
        window.SpecMap.hideContextMenus();
      }
    });
  }
  
  // Hide menus on outside click
  document.addEventListener('click', (e) => {
    if(!e.target.closest('.sm-context-menu') && e.target.tagName !== 'CANVAS') {
      window.SpecMap.hideContextMenus();
    }
  });
});

// ---------------------------------------------------------------------------
// SPEC-062 task_350/task_353 - architect direct implementation 2026-06-20
// init, selector population, fetch-and-render, polling for live updates.
// ---------------------------------------------------------------------------

window.SpecMap.state = window.SpecMap.state || {
  cy: null,
  currentSpecId: null,
  pollTimer: null,
  pollMs: 4000,
  lastFetchKey: null,
  activeBuild: null,
  buildStartTime: 0,
  buildTimer: null
};

window.SpecMap.show = function() {
  const view = document.getElementById('spec-map-view');
  if (view) view.style.display = 'flex';
};

window.SpecMap.hide = function() {
  const view = document.getElementById('spec-map-view');
  if (view) view.style.display = 'none';
  window.SpecMap.stopPolling();
};

window.SpecMap.init = function() {
  window.SpecMap.populateSelector().then(() => {
    const sel = document.getElementById('spec-map-selector');
    if (sel && !sel.dataset.bound) {
      sel.dataset.bound = "true";
      sel.addEventListener('change', (e) => {
        const id = e.target.value;
        if (id) window.SpecMap.loadSpec(id);
        else window.SpecMap.updateActionButtons(null);
      });
    }
    // Auto-load first non-empty option if nothing selected yet
    if (sel && sel.value && !window.SpecMap.state.currentSpecId) {
      window.SpecMap.loadSpec(sel.value);
    }

    // Bind Action Buttons
    const btnApprove = document.getElementById('sm-btn-approve');
    const btnBuild = document.getElementById('sm-btn-build');
    if (btnApprove && !btnApprove.dataset.bound) {
      btnApprove.dataset.bound = "true";
      btnApprove.addEventListener('click', window.SpecMap.handleApprove);
    }
    if (btnBuild && !btnBuild.dataset.bound) {
      btnBuild.dataset.bound = "true";
      btnBuild.addEventListener('click', window.SpecMap.handleBuild);
    }
    const btnStop = document.getElementById('sm-btn-stop');
    if (btnStop && !btnStop.dataset.bound) {
      btnStop.dataset.bound = "true";
      btnStop.addEventListener('click', window.SpecMap.handleStop);
    }
    const btnLaunch = document.getElementById('sm-btn-launch');
    if (btnLaunch && !btnLaunch.dataset.bound) {
      btnLaunch.dataset.bound = "true";
      btnLaunch.addEventListener('click', window.SpecMap.handleLaunch);
    }
    const btnCCI = document.getElementById('sm-btn-cci');
    if (btnCCI && !btnCCI.dataset.bound) {
      btnCCI.dataset.bound = "true";
      btnCCI.addEventListener('click', window.SpecMap.openChangeRequest);
    }
    // Detect on first bind
    if (window.SpecMap.refreshLaunchButton) window.SpecMap.refreshLaunchButton();

    const btnIn = document.getElementById('sm-btn-zoom-in');
    const btnOut = document.getElementById('sm-btn-zoom-out');
    const btnFit = document.getElementById('sm-btn-zoom-fit');
    if (btnIn && !btnIn.dataset.bound) {
      btnIn.dataset.bound = "true";
      btnIn.addEventListener('click', () => {
        if (window.SpecMap.state.cy) window.SpecMap.state.cy.zoom({ level: window.SpecMap.state.cy.zoom() * 1.2, renderedPosition: { x: window.SpecMap.state.cy.width()/2, y: window.SpecMap.state.cy.height()/2 } });
      });
    }
    if (btnOut && !btnOut.dataset.bound) {
      btnOut.dataset.bound = "true";
      btnOut.addEventListener('click', () => {
        if (window.SpecMap.state.cy) window.SpecMap.state.cy.zoom({ level: window.SpecMap.state.cy.zoom() * 0.8, renderedPosition: { x: window.SpecMap.state.cy.width()/2, y: window.SpecMap.state.cy.height()/2 } });
      });
    }
    if (btnFit && !btnFit.dataset.bound) {
      btnFit.dataset.bound = "true";
      btnFit.addEventListener('click', () => {
        if (window.SpecMap.state.cy) window.SpecMap.state.cy.fit(null, 40);
      });
    }
  });
};

window.SpecMap.handleApprove = function() {
  const specId = window.SpecMap.state.currentSpecId;
  if (!specId) return;
  const btnApprove = document.getElementById('sm-btn-approve');
  if (btnApprove) {
    btnApprove.disabled = true;
    btnApprove.textContent = 'Approving...';
  }
  fetch(`${window.SpecMap.getCenterUrl()}/api/specs/${encodeURIComponent(specId)}/status`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'APPROVED' })
  })
  .then(res => res.ok ? res.json() : res.json().then(err => { throw new Error(err.error || res.statusText); }))
  .then(() => {
    if(window.ToastManager) window.ToastManager.show('completion', 'Spec Approved', `Approved ${specId}`);
    return window.SpecMap.fetchAndRender(specId);
  })
  .catch(err => {
    if(window.ToastManager) window.ToastManager.show('denial', 'Approval Failed', err.message);
  })
  .finally(() => {
    if (btnApprove) btnApprove.textContent = 'Approve';
  });
};

window.SpecMap.handleBuild = async function() {
  const specId = window.SpecMap.state.currentSpecId;
  if (!specId) return;
  const project = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
  const centerUrl = window.SpecMap.getCenterUrl();

  // IMMEDIATE visual feedback: disable button + show pressed state + spinner text
  const btnBuild = document.getElementById('sm-btn-build');
  let _origBuildLabel = null;
  if (btnBuild) {
    _origBuildLabel = btnBuild.textContent;
    btnBuild.disabled = true;
    btnBuild.dataset.busy = "true";
    btnBuild.textContent = "Loading preview...";
    btnBuild.style.opacity = "0.6";
    btnBuild.style.cursor = "wait";
  }
  const _restoreBuildBtn = (label) => {
    if (!btnBuild) return;
    btnBuild.disabled = false;
    btnBuild.dataset.busy = "";
    btnBuild.textContent = label || _origBuildLabel || "Build";
    btnBuild.style.opacity = "";
    btnBuild.style.cursor = "";
  };

  // 1. Fetch build preview so operator sees harness/model + token impact BEFORE dispatch
  let preview = null;
  try {
    const r = await fetch(`${centerUrl}/api/specs/${encodeURIComponent(specId)}/build_preview?project=${encodeURIComponent(project)}`);
    if (r.ok) preview = await r.json();
  } catch(_) {}

  // 2. Confirm with operator if preview has Claude workers (token cost) or fails
  if (preview && (preview.claude_workers > 0 || preview.total_workers > 8)) {
    const breakdown = `${preview.total_workers} workers across ${preview.waves.length} waves:\n` +
      `  Claude: ${preview.claude_workers}\n` +
      `  Antigravity (agy): ${preview.agy_workers}\n` +
      `  Gemini direct: ${preview.gemini_workers}\n\n` +
      preview.waves.map(w => `Wave ${w.wave}: ` +
        w.workers.map(x => `${x.role}(${x.harness}/${x.model||'auto'},${x.task_count}t,risk=${x.risk_score})`).join(', ')
      ).join('\n');
    if (!confirm(`Build ${specId} on ${project}?\n\n${breakdown}\n\nProceed?`)) {
      _restoreBuildBtn();
      return;
    }
  }
  if (btnBuild) btnBuild.textContent = "Dispatching...";

  window.SpecMap.updateBuildStrip({
    state: 'queued', specId, buildId: 'build_...',
    wave: 'wave 0/0', elapsed: '0s', progress: 0
  });

  fetch(`${centerUrl}/api/governance/specs/${encodeURIComponent(specId)}/build?project=${encodeURIComponent(project)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ triggered_by: 'spec_map_build_button', harness: 'antigravity' })
  })
  .then(res => {
     if(!res.ok) return res.json().then(err => { throw new Error(err.error || res.statusText); });
     return res.json();
  })
  .then(data => {
    if(window.ToastManager) window.ToastManager.show('info', 'Build Dispatched', `Queued build for ${specId}`);
    window.SpecMap.updateBuildStrip({
      state: 'dispatched',
      buildId: data.build_id
    });
    if(window.BuildManager && window.BuildManager.showBuildProgress) {
       window.BuildManager.showBuildProgress(data.build_id, specId);
    }
    // Keep button disabled while build is actually running -- a separate
    // poll re-enables it when the build reaches a terminal state.
    if (btnBuild) {
      btnBuild.textContent = "Build running...";
      btnBuild.style.background = "#1f6feb";
      btnBuild.style.color = "#fff";
    }
    window.SpecMap._watchBuildToReenable(data.build_id, specId, project, _restoreBuildBtn);
  })
  .catch(err => {
    const _recoverProject = project;
    const _recoverSpecId = specId;
    const _recoverCenter = centerUrl;
    setTimeout(async () => {
      try {
        const chk = await fetch(`${_recoverCenter}/api/governance/specs/${encodeURIComponent(_recoverSpecId)}/builds?latest=1&project=${encodeURIComponent(_recoverProject)}`);
        if (chk.ok) {
          const latest = await chk.json();
          const bid = latest && (latest.build_id || (latest.build && latest.build.build_id));
          const st  = latest && (latest.status  || (latest.build && latest.build.status));
          if (bid && st && ['initiated','running','dispatched'].includes(st)) {
            window.SpecMap.updateBuildStrip({ state: 'dispatched', buildId: bid });
            if (btnBuild) { btnBuild.textContent = 'Build running...'; btnBuild.style.background = '#1f6feb'; btnBuild.style.color = '#fff'; }
            window.SpecMap._watchBuildToReenable(bid, _recoverSpecId, _recoverProject, _restoreBuildBtn);
            if (window.ToastManager) window.ToastManager.show('info', 'Build recovered', `Build ${bid} is running -- initial request timed out but server started it.`);
            return;
          }
        }
      } catch(_) {}
      if(window.ToastManager) window.ToastManager.show('denial', 'Build Failed', err.message);
      window.SpecMap.updateBuildStrip({ state: 'failed', wave: '-', elapsed: '-', progress: 0 });
      _restoreBuildBtn("Build (failed - retry)");
    }, 3000);
  });
};

// Poll the build until it reaches a terminal state, then re-enable the Build button.
window.SpecMap._watchBuildToReenable = function(buildId, specId, project, restoreFn) {
  const centerUrl = window.SpecMap.getCenterUrl();
  let i = 0;
  const iv = setInterval(async () => {
    i += 1;
    try {
      const r = await fetch(`${centerUrl}/api/governance/builds/${encodeURIComponent(buildId)}?project=${encodeURIComponent(project)}`);
      if (r.ok) {
        const d = await r.json();
        const st = d.status || (d.build && d.build.status);
        if (st && !["initiated","running","dispatched","queued"].includes(st)) {
          clearInterval(iv);
          // Reset styling
          const btn = document.getElementById('sm-btn-build');
          if (btn) {
            btn.style.background = "";
            btn.style.color = "";
          }
          restoreFn();
          return;
        }
      }
    } catch(_) {}
    // Safety: bail after 30 min so we don't poll forever
    if (i >= 900) {
      clearInterval(iv);
      const btn = document.getElementById('sm-btn-build');
      if (btn) {
        btn.style.background = "";
        btn.style.color = "";
      }
      restoreFn();
    }
  }, 2000);
};


window.SpecMap.handleStop = async function() {
  const specId = window.SpecMap.state.currentSpecId;
  if (!specId) return;
  if (!confirm(`Stop ALL running builds for ${specId}? This will SIGTERM every worker.`)) return;
  const project = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
  try {
    const r = await fetch(`${window.SpecMap.getCenterUrl()}/api/specs/${encodeURIComponent(specId)}/stop_builds?project=${encodeURIComponent(project)}`, { method: 'POST' });
    const d = await r.json().catch(() => ({}));
    if (window.ToastManager) {
      window.ToastManager.show(r.ok ? 'info' : 'denial',
        r.ok ? 'Builds Stopped' : 'Stop Failed',
        r.ok ? `Aborted ${(d.aborted_builds||[]).length} build(s); killed ${d.killed_count||0} worker(s).` : (d.error||'unknown'));
    }
    window.SpecMap.updateBuildStrip({ state: 'aborted', wave: '-', elapsed: '-', progress: 0 });
  } catch (err) {
    if (window.ToastManager) window.ToastManager.show('denial', 'Stop Error', err.message);
  }
};



// SPEC-062-H: keep the Live Worker Log panel refreshing while the sidebar is
// open on an in_progress task. Poll every 2 s; update log body + freshness
// header in-place (no whole-panel rerender). Auto-stops when the panel is
// hidden or a different task is opened.


// SPEC-062-H: Thought cloud — hover an in_progress task node on the map to see
// the last few worker log lines in a floating bubble, updated every 2 s. On
// mouseleave the cloud fades out. Only active tasks get one (idle nodes just
// show the standard tooltip).
window.SpecMap._thoughtCloud = { el: null, pollId: null, currentTaskId: null };

window.SpecMap._showThoughtCloud = function(taskId, project, x, y) {
  const state = window.SpecMap._thoughtCloud;
  if (state.currentTaskId === taskId && state.el) {
    // Just reposition
    state.el.style.left = (x + 16) + 'px';
    state.el.style.top = (y + 16) + 'px';
    return;
  }
  window.SpecMap._hideThoughtCloud();
  const cloud = document.createElement('div');
  cloud.id = 'smd-thought-cloud';
  cloud.style.cssText = `
    position:fixed; z-index:9998; left:${x+16}px; top:${y+16}px;
    width:380px; max-height:280px; overflow:hidden;
    background:linear-gradient(#161b22, #0d1117);
    border:1px solid #d29922; border-radius:10px;
    box-shadow: 0 8px 24px rgba(210,153,34,0.35), 0 0 0 1px rgba(210,153,34,0.15);
    padding:8px; font-family:system-ui,-apple-system,sans-serif; font-size:11px;
    color:#e6edf3; pointer-events:none;
    transition:opacity 120ms ease; opacity:0;
  `;
  cloud.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;font-size:11px;color:#d29922;font-weight:600">
      <span>💭 Thinking · ${taskId}</span>
      <span id="smd-thought-cloud-time" style="font-size:10px;color:#8b949e"></span>
    </div>
    <div id="smd-thought-cloud-hm" style="display:flex;gap:6px;align-items:center;margin-bottom:6px;padding:4px 6px;background:#0a0e14;border:1px solid #30363d;border-radius:4px;font-size:10px">
      <span style="color:#8b949e;font-weight:600;letter-spacing:0.5px">HARNESS</span>
      <span id="smd-thought-cloud-harness" style="color:#c9d1d9;font-weight:700">—</span>
      <span style="color:#8b949e;font-weight:600;letter-spacing:0.5px;margin-left:6px">MODEL</span>
      <span id="smd-thought-cloud-model" style="color:#7ee787;font-weight:700">—</span>
    </div>
    <div id="smd-thought-cloud-body" style="font-family:monospace;font-size:10px;line-height:1.5;color:#c9d1d9;max-height:220px;overflow-y:auto"></div>`;
  document.body.appendChild(cloud);
  state.el = cloud;
  state.currentTaskId = taskId;
  requestAnimationFrame(() => { cloud.style.opacity = '1'; });

  const fmt = (ms) => { const d = new Date(ms); return d.toLocaleTimeString('en-GB', {hour12:false}); };
  const refresh = async () => {
    if (!state.el) return;
    try {
      const r = await fetch(`${window.SpecMap.getCenterUrl()}/api/tasks/${encodeURIComponent(taskId)}/worker_log_tail?project=${encodeURIComponent(project)}&max_lines=12`);
      if (!r.ok) return;
      const d = await r.json();
      const timeEl   = state.el.querySelector('#smd-thought-cloud-time');
      const bodyEl   = state.el.querySelector('#smd-thought-cloud-body');
      const hEl      = state.el.querySelector('#smd-thought-cloud-harness');
      const mEl      = state.el.querySelector('#smd-thought-cloud-model');

      // Harness + model: prefer API response, fall back to map node data
      let harness = d.harness || null;
      let model   = d.model   || null;
      if ((!harness || !model) && window.SpecMap.state && window.SpecMap.state.cy) {
        const cyNode = window.SpecMap.state.cy.getElementById(taskId);
        if (cyNode && cyNode.length) {
          harness = harness || cyNode.data('assigned_harness') || cyNode.data('harness') || null;
          model   = model   || cyNode.data('assigned_model')   || null;
          if (!model) {
            const hist = cyNode.data('attempt_history') || [];
            if (hist.length) model = hist[hist.length-1].model || null;
          }
        }
      }
      if (hEl) {
        hEl.textContent = harness ? String(harness).toUpperCase() : '—';
        hEl.style.color = harness === 'antigravity' ? '#e6a23c'
                        : harness === 'claude'      ? '#c8b6ff'
                        : harness === 'gemini'      ? '#79c0ff'
                        : '#c9d1d9';
      }
      if (mEl) {
        mEl.textContent = model || 'default';
        mEl.style.color = String(model||'').toLowerCase().includes('claude') ? '#c8b6ff'
                        : String(model||'').toLowerCase().includes('gemini') ? '#79c0ff'
                        : '#7ee787';
      }

      if (timeEl) timeEl.textContent = fmt(Date.now()) + (d.is_active ? ' · live' : ` · idle ${Math.round(d.stale_sec||0)}s`);
      if (bodyEl) {
        const lines = (d.lines || []).filter(l => l && l.trim());
        bodyEl.innerHTML = lines.length
          ? lines.slice(-12).map(l => `<div style="padding:2px 0;border-bottom:1px solid #161b22;white-space:pre-wrap;word-break:break-word">${l.replace(/[<>]/g,'')}</div>`).join('')
          : `<div style="color:#8b949e">…worker thinking…</div>`;
        // ALWAYS scroll to bottom so latest thought is visible
        bodyEl.scrollTop = bodyEl.scrollHeight;
      }
    } catch (e) {}
  };
  refresh();
  state.pollId = setInterval(refresh, 2000);
};

window.SpecMap._hideThoughtCloud = function() {
  const state = window.SpecMap._thoughtCloud;
  if (state.pollId) { clearInterval(state.pollId); state.pollId = null; }
  if (state.el) {
    const el = state.el;
    el.style.opacity = '0';
    setTimeout(() => { try { el.remove(); } catch(_) {} }, 130);
    state.el = null;
  }
  state.currentTaskId = null;
};




// SPEC-062-H: watch for new specs added to the current project via ADS.
// When a `spec_created` event is seen, refresh the spec selector, toast
// the operator, and if the empty-spec card is currently open on a spec
// that just got tasks, auto-swap to the task-graph render.
window.SpecMap._seenSpecs = window.SpecMap._seenSpecs || new Set();
window.SpecMap._watchNewSpecs = function() {
  if (window.SpecMap._newSpecPoll) return;
  window.SpecMap._newSpecPoll = setInterval(async () => {
    const proj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
    try {
      const r = await fetch(`${window.SpecMap.getCenterUrl()}/api/specs?project=${encodeURIComponent(proj)}`);
      if (!r.ok) return;
      const d = await r.json();
      const specs = d.specs || [];
      const currentIds = new Set(specs.map(s => s.id));
      // First time we see this project — seed the set, no toast
      const seenKey = `${proj}::seeded`;
      if (!window.SpecMap._seenSpecs.has(seenKey)) {
        specs.forEach(s => window.SpecMap._seenSpecs.add(`${proj}::${s.id}`));
        window.SpecMap._seenSpecs.add(seenKey);
        return;
      }
      // Detect any brand-new IDs since last poll
      const newSpecs = specs.filter(s => !window.SpecMap._seenSpecs.has(`${proj}::${s.id}`));
      if (newSpecs.length) {
        newSpecs.forEach(s => window.SpecMap._seenSpecs.add(`${proj}::${s.id}`));
        // Refresh the spec selector so the new spec is immediately pickable
        if (window.SpecMap.populateSelector) window.SpecMap.populateSelector();
        // Toast + optional auto-select if there's exactly one new spec
        for (const ns of newSpecs) {
          if (window.ToastManager) {
            window.ToastManager.show('info',
              `🆕 New spec: ${ns.id}`,
              (ns.title || '').substring(0, 80));
          }
        }
      }
      // Also: if we're currently rendering the empty-spec card AND the current
      // spec now has tasks, auto-swap to the task graph.
      const openSpec = window.SpecMap.state && window.SpecMap.state.currentSpecId;
      const emptyCard = document.querySelector('.empty-spec-card');
      if (openSpec && emptyCard) {
        try {
          const gr = await fetch(`${window.SpecMap.getCenterUrl()}/api/specs/${encodeURIComponent(openSpec)}/task_graph?project=${encodeURIComponent(proj)}`);
          if (gr.ok) {
            const gd = await gr.json();
            if ((gd.nodes || []).length > 0 && window.SpecMap.loadSpec) {
              window.SpecMap.loadSpec(openSpec);
            }
          }
        } catch (e) { /* swallow */ }
      }
    } catch (e) { /* swallow */ }
  }, 4000);
};
document.addEventListener('DOMContentLoaded', () => {
  if (window.SpecMap._watchNewSpecs) window.SpecMap._watchNewSpecs();
});


window.SpecMap._liveLogPoll = { intervalId: null, currentTaskId: null };

window.SpecMap._startLiveLogPoll = function(taskId, project) {
  const state = window.SpecMap._liveLogPoll;
  if (state.currentTaskId === taskId && state.intervalId) return;
  window.SpecMap._stopLiveLogPoll();
  state.currentTaskId = taskId;
  // Line-timestamp memory: taskId -> Map(line_text -> first_seen_ts_ms)
  state.lineSeenAt = state.lineSeenAt || {};
  state.lineSeenAt[taskId] = new Map();
  // Track whether we have EVER seen content — never regress to "no output yet"
  state.hadContent = state.hadContent || {};

  const fmtTs = (ts) => {
    const d = new Date(ts);
    return d.toLocaleTimeString('en-GB', { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0').slice(0, 2);
  };

  state.intervalId = setInterval(async () => {
    const container = document.getElementById('smd-live-log');
    if (!container) { window.SpecMap._stopLiveLogPoll(); return; }
    const openTaskId = container.dataset.taskId;
    if (openTaskId && openTaskId !== taskId) {
      window.SpecMap._stopLiveLogPoll();
      return;
    }
    try {
      const url = `${window.SpecMap.getCenterUrl()}/api/tasks/${encodeURIComponent(taskId)}/worker_log_tail?project=${encodeURIComponent(project)}&max_lines=60`;
      const r = await fetch(url);
      if (!r.ok) return;
      const ld = await r.json();
      if (!ld || !Array.isArray(ld.lines)) return;

      const body = container.querySelector('.smd-live-log-body');
      const header = container.querySelector('.smd-live-log-header');
      const meta = container.querySelector('.smd-live-log-meta');
      const seenMap = state.lineSeenAt[taskId];
      const nowMs = Date.now();

      // Stamp each line: reuse prior timestamp if seen, else stamp now
      const stampedLines = [];
      for (const raw of ld.lines) {
        const line = raw || '';
        if (!line.trim()) continue;
        if (!seenMap.has(line)) seenMap.set(line, nowMs);
        stampedLines.push({ ts: seenMap.get(line), text: line });
      }
      // GC: only keep timestamps for lines currently in the tail (prevents
      // unbounded growth). If a line dropped out, it likely rolled past the
      // 60-line window; forget it.
      if (seenMap.size > 200) {
        const activeSet = new Set(stampedLines.map(l => l.text));
        for (const k of Array.from(seenMap.keys())) {
          if (!activeSet.has(k)) seenMap.delete(k);
        }
      }

      if (body) {
        const wasAtBottom = (body.scrollHeight - body.scrollTop - body.clientHeight) < 20;
        if (stampedLines.length) {
          state.hadContent[taskId] = true;
          body.innerHTML = stampedLines.map(({ts, text}) => `
            <div style="display:flex; gap:6px; padding:1px 0; border-bottom:1px solid #161b22; font-family:monospace; font-size:10px;">
              <span style="color:#8b949e; flex-shrink:0; min-width:78px;">${fmtTs(ts)}</span>
              <span style="color:#c9d1d9; flex:1; white-space:pre-wrap; word-break:break-word;">${text.replace(/[<>]/g,'')}</span>
            </div>`).join('');
          if (wasAtBottom) body.scrollTop = body.scrollHeight;
        } else if (!state.hadContent[taskId]) {
          // Only show placeholder if we've NEVER seen content for this task.
          // Prevents flapping to "no output yet" when the log gets truncated
          // between fast-fail retry attempts.
          body.innerHTML = `<div style="font-size:11px;color:var(--text-muted);padding:8px">no output yet</div>`;
        }
        // else: keep the last-known content, do not wipe
      }

      if (header) {
        const active = ld.is_active;
        const stale = ld.stale_sec != null ? `${Math.round(ld.stale_sec)}s ago` : '';
        const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${active?'#7bd88f':'#5a5a5a'};margin-right:6px;${active?'animation:pulse 1s infinite':''}"></span>`;
        header.innerHTML = `${dot}Live Worker Log ${active
          ? '<span style="font-size:10px;color:#7bd88f">(active)</span>'
          : `<span style="font-size:10px;color:var(--text-muted)">(idle · updated ${stale})</span>`}`;
        header.style.color = active ? '#7bd88f' : '#8b949e';
        container.style.borderColor = active ? '#238636' : '#30363d';
      }
      if (meta) meta.textContent = `${ld.log_path || ''} · ${ld.total_lines || 0} lines`;
      // SPEC-062-H visible harness+model — pulls from the tail endpoint if
      // present, else derives from the current task node data on the map.
      const harnessEl = container.querySelector('.smd-live-log-harness');
      const modelEl   = container.querySelector('.smd-live-log-model-name');
      let harness = ld.harness || null;
      let model   = ld.model || null;
      if ((!harness || !model) && window.SpecMap.state && window.SpecMap.state.cy) {
        const cyNode = window.SpecMap.state.cy.getElementById(taskId);
        if (cyNode && cyNode.length) {
          harness = harness || cyNode.data('assigned_harness') || cyNode.data('harness') || null;
          model   = model   || cyNode.data('assigned_model')   || null;
          if (!model) {
            const hist = cyNode.data('attempt_history') || [];
            if (hist.length) model = hist[hist.length-1].model || null;
          }
        }
      }
      if (harnessEl) {
        harnessEl.textContent = harness ? String(harness).toUpperCase() : '—';
        harnessEl.style.color = harness === 'antigravity' ? '#e6a23c'
                              : harness === 'claude' ? '#c8b6ff'
                              : harness === 'gemini' ? '#79c0ff'
                              : '#c9d1d9';
      }
      if (modelEl) {
        modelEl.textContent = model || 'default';
        modelEl.style.color = String(model||'').toLowerCase().includes('claude') ? '#c8b6ff'
                            : String(model||'').toLowerCase().includes('gemini') ? '#79c0ff'
                            : String(model||'').toLowerCase().includes('gpt') ? '#7ee787'
                            : '#7ee787';
      }
    } catch (e) { /* swallow */ }
  }, 2000);
};

window.SpecMap._stopLiveLogPoll = function() {
  const state = window.SpecMap._liveLogPoll;
  if (state.intervalId) { clearInterval(state.intervalId); state.intervalId = null; }
  state.currentTaskId = null;
};


// Resolve a project name → absolute path via adt_center's registry.
// Cached in window.SpecMap.state._projectPaths keyed by name.
window.SpecMap._resolveProjectPath = async function(projectName) {
  if (!projectName) return null;
  window.SpecMap.state._projectPaths = window.SpecMap.state._projectPaths || {};
  const cached = window.SpecMap.state._projectPaths[projectName];
  if (cached) return cached;
  try {
    const r = await fetch(`${window.SpecMap.getCenterUrl()}/api/projects`);
    if (!r.ok) return null;
    const data = await r.json();
    const projects = data.projects || data || {};
    const entry = projects[projectName];
    if (entry && entry.path) {
      window.SpecMap.state._projectPaths[projectName] = entry.path;
      return entry.path;
    }
  } catch (_) {}
  return null;
};

// Detect the project's entry point and update the Launch button state.
// Called on init, project switch, and after build completion.
window.SpecMap.refreshLaunchButton = async function() {
  const btn = document.getElementById('sm-btn-launch');
  if (!btn) return;
  const project = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
  const projectPath = await window.SpecMap._resolveProjectPath(project);
  if (!projectPath) {
    btn.disabled = true;
    btn.title = `Project path unknown for "${project}"`;
    btn.textContent = '▶ Launch app';
    return;
  }
  try {
    const invoke = window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke;
    if (!invoke) return;
    const info = await invoke('detect_project_launch', { projectPath });
    if (info && info.launchable) {
      btn.disabled = false;
      btn.style.background = '#1f6feb';
      btn.style.borderColor = '#388bfd';
      btn.title = `${info.description}\n(cwd: ${projectPath})`;
      btn.textContent = `▶ Launch (${info.kind})`;
      btn.dataset.launchKind = info.kind;
    } else {
      btn.disabled = true;
      btn.style.background = '#3a3a3a';
      btn.style.borderColor = '#555';
      btn.title = (info && info.reason) || 'No runnable entry point yet — build first';
      btn.textContent = '▶ Launch app';
    }
  } catch (err) {
    btn.disabled = true;
    btn.title = 'Launch detect failed: ' + (err && err.message || err);
  }
};

window.SpecMap.handleLaunch = async function() {
  const btn = document.getElementById('sm-btn-launch');
  if (!btn || btn.disabled) return;
  const project = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
  const projectPath = await window.SpecMap._resolveProjectPath(project);
  if (!projectPath) return;
  const origLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = '▶ Launching...';
  try {
    const invoke = window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke;
    const result = await invoke('launch_project', { projectPath });
    // Cache the launched URL (parsed from Rust's OK message: "Launched: <cmd> (log: ...)")
    // so the Change Request description can auto-fill "Reported while testing <url>".
    try {
      const match = String(result || '').match(/http[s]?:\/\/[^\s)]+/);
      window.SpecMap.state = window.SpecMap.state || {};
      window.SpecMap.state.lastLaunchUrl = match ? match[0] : projectPath;
    } catch (_) {}
    if (window.ToastManager) window.ToastManager.show('info', 'Launched', result || 'started');
    btn.textContent = '▶ Launched ✓';
    setTimeout(() => { btn.textContent = origLabel; btn.disabled = false; }, 2500);
  } catch (err) {
    if (window.ToastManager) window.ToastManager.show('denial', 'Launch failed', String(err));
    btn.textContent = origLabel;
    btn.disabled = false;
  }
};

// Open the Change Request dialog. Auto-fills:
//   - "Attached to" = currently active spec
//   - description = a hint of the running test URL (if Launch was recently used)
window.SpecMap.openChangeRequest = function() {
  const dlg = document.getElementById('cci-dialog');
  if (!dlg) return;
  const project = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
  const specId  = (window.SpecMap.state && window.SpecMap.state.currentSpecId) || '';
  const linkedEl = document.getElementById('cci-linked-spec');
  if (linkedEl) linkedEl.value = specId ? `${specId} (project: ${project})` : `(no spec selected — project: ${project})`;
  const descEl = document.getElementById('cci-desc');
  if (descEl && !descEl.value) {
    // If a Launch happened recently, hint the test URL from the last launch log filename.
    const lastLaunch = window.SpecMap.state && window.SpecMap.state.lastLaunchUrl;
    if (lastLaunch) descEl.placeholder = `Reported while testing ${lastLaunch}. Describe what went wrong and what you expected.`;
  }
  // Focus title for fast typing
  const titleEl = document.getElementById('cci-title');
  setTimeout(() => titleEl && titleEl.focus(), 50);
  dlg.showModal();
};

// Wire the dialog buttons ONCE the DOM is ready. This binds submit + cancel.
window.SpecMap._bindCCIDialog = function() {
  const dlg = document.getElementById('cci-dialog');
  const form = document.getElementById('cci-form');
  const btnCancel = document.getElementById('btn-cci-cancel');
  if (!dlg || !form || form.dataset.bound === 'true') return;
  form.dataset.bound = 'true';
  btnCancel.addEventListener('click', () => dlg.close());
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const type  = document.getElementById('cci-type').value;
    const title = document.getElementById('cci-title').value.trim();
    const desc  = document.getElementById('cci-desc').value.trim();
    if (!title || !desc) return;
    const project = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
    const specId  = (window.SpecMap.state && window.SpecMap.state.currentSpecId) || '';
    const body = {
      title: title,
      description: desc,
      type: type,
      status: 'Intent Defined',
      standards_refs: [],
      agent: 'OPERATOR',
      role: 'Overseer',
      capability: { linked_spec: specId || null },
      project: project
    };
    const submitBtn = form.querySelector('button[type="submit"]');
    const origLabel = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Submitting...';
    try {
      const r = await fetch(`${window.SpecMap.getCenterUrl()}/api/governance/capabilities/intents?project=${encodeURIComponent(project)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        if (window.ToastManager) window.ToastManager.show('info', 'Change Request Filed',
          `Intent ${data.intent_id || ''} created — view in Capabilities Kanban.`);
        // Reset & close
        document.getElementById('cci-title').value = '';
        document.getElementById('cci-desc').value = '';
        dlg.close();
      } else {
        const err = (data.details && data.details.join('; ')) || data.error || `HTTP ${r.status}`;
        if (window.ToastManager) window.ToastManager.show('denial', 'Intent rejected', err);
        else alert('Intent rejected: ' + err);
      }
    } catch (err) {
      if (window.ToastManager) window.ToastManager.show('denial', 'Network error', String(err));
      else alert('Network error: ' + err);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = origLabel;
    }
  });
};
document.addEventListener('DOMContentLoaded', () => {
  if (window.SpecMap && window.SpecMap._bindCCIDialog) window.SpecMap._bindCCIDialog();
});



// SPEC-062-H Fix D: derive a task's retry/escalation attempt count from
// recent ADS events, so the map can show a small badge like "×3" when a
// worker has been auto-restarted, and the sidebar can list the full
// escalation history (attempt N -> model X -> outcome).
window.SpecMap._attemptCountFromEvents = function(events, taskId) {
  if (!Array.isArray(events) || !taskId) return { count: 0, history: [], exhausted: false };
  const history = [];
  let exhausted = false;
  for (const e of events) {
    const ad = e.action_data || {};
    const ids = ad.task_ids || (ad.task_id ? [ad.task_id] : []);
    if (!ids.includes(taskId)) continue;
    if (e.action_type === "fast_fail_narrator_killed" || e.action_type === "worker_escalation_step") {
      history.push({
        ts: e.ts, attempt: ad.attempt, model: ad.model || "default",
        outcome: e.action_type === "worker_escalation_step" ? "escalated" : "narrator_killed",
        note: ad.note || "",
      });
    }
    if (e.action_type === "worker_all_escalations_exhausted") exhausted = true;
  }
  return { count: history.length, history, exhausted };
};

window.SpecMap.updateActionButtons = function(graph) {
  const btnApprove = document.getElementById('sm-btn-approve');
  const btnBuild = document.getElementById('sm-btn-build');
  const specId = window.SpecMap.state.currentSpecId;

  if (!specId) {
    if (btnApprove) btnApprove.disabled = true;
    if (btnBuild) btnBuild.disabled = true;
    return;
  }

  if (btnBuild) btnBuild.disabled = false;

  if (btnApprove) {
    if (graph && graph.spec_status) {
      btnApprove.disabled = (graph.spec_status === 'APPROVED');
    } else {
      btnApprove.disabled = false; // Enable optimistically if no status available
    }
  }
};

window.SpecMap.updateBuildStrip = function(data) {
  const strip = document.getElementById('sm-build-strip');
  if (!strip) return;

  if (data.state === 'hidden') {
    strip.style.display = 'none';
    return;
  }

  strip.style.display = 'flex';

  if (data.buildId !== undefined) document.getElementById('sm-build-id').textContent = data.buildId;
  if (data.specId !== undefined) document.getElementById('sm-build-spec').textContent = data.specId;
  if (data.wave !== undefined) document.getElementById('sm-build-wave').textContent = data.wave;
  if (data.elapsed !== undefined) document.getElementById('sm-build-elapsed').textContent = data.elapsed;
  
  if (data.state) {
    const statusEl = document.getElementById('sm-build-status');
    statusEl.textContent = data.state;
    statusEl.className = `sm-build-status ${data.state}`;
    window.SpecMap.state.activeBuild = window.SpecMap.state.activeBuild || {};
    window.SpecMap.state.activeBuild.buildId = data.buildId || window.SpecMap.state.activeBuild.buildId;

    if (data.state === 'complete' || data.state === 'failed') {
      if (window.SpecMap.state.buildTimer) {
        clearInterval(window.SpecMap.state.buildTimer);
        window.SpecMap.state.buildTimer = null;
      }
      if (data.state === 'complete') {
        setTimeout(() => {
          strip.style.display = 'none';
          window.SpecMap.state.activeBuild = null;
        }, 30000);
      }
    } else if (data.state === 'running' || data.state === 'dispatched' || data.state === 'queued') {
      if (!window.SpecMap.state.buildTimer) {
        window.SpecMap.state.buildStartTime = Date.now();
        window.SpecMap.state.buildTimer = setInterval(() => {
          if (!window.SpecMap.state.activeBuild) return;
          const elapsed = Math.floor((Date.now() - window.SpecMap.state.buildStartTime) / 1000);
          document.getElementById('sm-build-elapsed').textContent = `${elapsed}s`;
        }, 1000);
      }
    }
  }
  
  if (data.progress !== undefined) {
    document.getElementById('sm-build-progress-fill').style.width = `${data.progress}%`;
  }
};

window.SpecMap.populateSelector = function() {
  const sel = document.getElementById('spec-map-selector');
  if (!sel) return Promise.resolve();
  // Try the SPEC-050 registry endpoint first; fall back to a simpler one.
  const _proj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
  return fetch(`${window.SpecMap.getCenterUrl()}/api/governance/specs?project=${encodeURIComponent(_proj)}`)
    .then(r => r.ok ? r.json() : Promise.reject('specs endpoint failed'))
    .then(data => {
      const specs = Array.isArray(data) ? data : (data.specs || []);
      const items = [];
      if (Array.isArray(specs)) {
        specs.forEach(s => items.push({id: s.id || s.spec_id, title: s.title || '', status: s.status || ''}));
      } else if (typeof specs === 'object') {
        Object.keys(specs).forEach(id => items.push({id, title: (specs[id] && specs[id].title) || '', status: (specs[id] && specs[id].status) || ''}));
      }

      items.sort((a, b) => (a.id || '').localeCompare(b.id || ''));
      sel.innerHTML = '<option value="">Select a Spec...</option>' +
        items.map(s => `<option value="${s.id}">${s.id} - ${s.title}</option>`).join('');
      // SPEC-062 Amendment D fix: preserve current selection after option rebuild
      // so polling-driven re-population doesn't visually reset the dropdown.
      if (window.SpecMap.state && window.SpecMap.state.currentSpecId) {
        sel.value = window.SpecMap.state.currentSpecId;
      }
    })
    .catch(err => {
      console.warn('SpecMap: spec list fetch failed', err);
      sel.innerHTML = '<option value="">No specs available</option>';
    });
};

window.SpecMap.loadSpec = function(specId) {
  window.SpecMap.state.currentSpecId = specId;
  // Show loading state until fetch completes
  const canvas = document.getElementById('spec-map-canvas');
  if (canvas) {
    canvas.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted,#8b949e);font-size:13px">
      <span style="display:inline-block;width:14px;height:14px;border:2px solid #30363d;border-top-color:#58a6ff;border-radius:50%;margin-right:8px;animation:smdSpin 0.8s linear infinite"></span>
      Loading ${specId} (project: ${(window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework'})...
    </div>
    <style>@keyframes smdSpin { to { transform: rotate(360deg); } }</style>`;
  }
  // Wipe stale detail panel content right away
  const detail = document.getElementById('smd-content');
  if (detail) detail.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:8px">Loading...</div>';
  // Invalidate cache key so fetchAndRender always re-runs even if same spec_id
  if (window.SpecMap.state) window.SpecMap.state.lastFetchKey = null;
  return window.SpecMap.fetchAndRender(specId).then(() => {
    window.SpecMap.startPolling(specId);
  });
};

// SPEC-062 Amendment D3 build marker — visible in DevTools console
console.log('[SpecMap] Loaded build with D3 patch (adt-framework default + localStorage trap fix)');

window.SpecMap.fetchAndRender = function(specId) {
  // SPEC-062 Amendment D3: ALWAYS boot in adt-framework. Ignore stale localStorage
  // (which traps operators in dead projects like vr_mats). Honor in-session switches
  // via state.currentProject; localStorage only used as a one-shot warning marker so we
  // can announce what the operator USED to have selected.
  window.SpecMap.state = window.SpecMap.state || {};
  if (!window.SpecMap.state.currentProject) {
    window.SpecMap.state.currentProject = 'adt-framework';
    try {
      const _prevSaved = localStorage.getItem('adt_spec_map_project');
      if (_prevSaved && _prevSaved !== 'adt-framework') {
        console.log('[SpecMap] Reset project default to adt-framework (was: ' + _prevSaved + '). Use the dropdown to switch if needed.');
        localStorage.removeItem('adt_spec_map_project');
      }
    } catch(_) {}
  }
  const proj = window.SpecMap.state.currentProject;
  const base = window.SpecMap.getCenterUrl();

  function _tryFetch(projectName) {
    const url = projectName
      ? `${base}/api/specs/${encodeURIComponent(specId)}/task_graph?project=${encodeURIComponent(projectName)}`
      : `${base}/api/specs/${encodeURIComponent(specId)}/task_graph`;
    return fetch(url).then(r => r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`));
  }

  return _tryFetch(proj)
    .then(graph => {
      // Self-heal: if the spec has zero nodes AND no intent in current project,
      // it probably lives in a different project. Try across all known projects.
      const isEmpty = (graph.nodes || []).length === 0 && !graph.spec_intent;
      if (!isEmpty) return graph;
      // Probe /api/projects for any project that actually has this spec populated.
      return fetch(`${base}/api/projects`).then(r => r.ok ? r.json() : {}).then(projs => {
        const candidates = Object.keys(projs || {}).filter(n => n !== proj);
        // Sort: put adt-framework first as the most common owner
        candidates.sort((a, b) => (b === 'adt-framework') - (a === 'adt-framework'));
        function tryNext(i) {
          if (i >= candidates.length) return graph; // give up, use empty
          return _tryFetch(candidates[i]).then(g => {
            if ((g.nodes || []).length > 0 || g.spec_intent) {
              // Found it! Auto-switch the project.
              window.SpecMap.state.currentProject = candidates[i];
              try { localStorage.setItem('adt_spec_map_project', candidates[i]); } catch(_) {}
              if (window.ToastManager) window.ToastManager.show('info', 'Auto-switched project',
                `${specId} is in ${candidates[i]}, switched from ${proj}`);
              return g;
            }
            return tryNext(i + 1);
          }).catch(() => tryNext(i + 1));
        }
        return tryNext(0);
      });
    })
    .then(graph => {
      // Cheap change detection so polling does not redraw identical state.
      const key = JSON.stringify([
        graph.rollup,
        (graph.nodes || []).map(n => [n.task_id, n.status]),
        (graph.workers || []).map(w => [w.session_id, w.current_task_id, w.last_tool, w.last_event_time])
      ]);
      if (key === window.SpecMap.state.lastFetchKey) return;
      window.SpecMap.state.lastFetchKey = key;
      window.SpecMap.render(graph);
      window.SpecMap.updateActionButtons(graph);
    })
    .catch(err => {
      const canvas = document.getElementById('spec-map-canvas');
      if (canvas) canvas.innerHTML =
        `<div style="padding:24px;color:var(--text-muted);">
           Failed to load ${specId}: ${err}
         </div>`;
    });
};

window.SpecMap.render = function(graph) {
  const canvas = document.getElementById('spec-map-canvas');
  if (!canvas) return;

  // SPEC-062 Amendment D fix: ALWAYS render rollup header (with project switcher)
  // before the empty-spec early-return, so the operator can change projects
  // even when the current spec has zero tasks.
  window.SpecMap._renderRollup(graph);

  // SPEC-062 Amendment D: empty-spec card
  const nodeCount = (graph.nodes || []).length;
  if (nodeCount === 0) {
    if (window.SpecMap.state.cy) {
      try { window.SpecMap.state.cy.destroy(); } catch(_) {}
      window.SpecMap.state.cy = null;
    }
    canvas.innerHTML = `
      <div class="empty-spec-card">
        <div class="esc-title">${graph.spec_id || ''}</div>
        <div class="esc-subtitle">${(graph.spec_title || '').replace(/</g, '&lt;')}</div>
        <div class="esc-intent">${(graph.spec_intent || 'No intent paragraph available.').replace(/</g, '&lt;')}</div>
        <div class="esc-status">Not yet decomposed - zero tasks defined.</div>
        <button class="esc-btn" id="esc-decompose-btn">Decompose Now</button>
        <div class="esc-help">Spawns a Systems_Architect worker to read the spec and propose 5-15 tasks.</div>
        <div class="esc-feed" id="esc-progress-feed"></div>
      </div>`;
    const btn = document.getElementById('esc-decompose-btn');
    if (btn) {
      btn.onclick = function() {
        btn.disabled = true;
        btn.textContent = 'Decomposing...';
        const feed = document.getElementById('esc-progress-feed');
        if (feed) feed.innerHTML = '<div class="esc-feed-item">Spawning Architect worker...</div>';
        const _decProj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
        fetch(`${window.SpecMap.getCenterUrl()}/api/specs/${encodeURIComponent(graph.spec_id)}/decompose?project=${encodeURIComponent(_decProj)}`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({triggered_by: 'spec_map_empty_card', project: _decProj})
        })
        .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e.error || 'request failed')))
        .then(data => {
          const tid = data.task_id;
          const autoOK = data.auto_spawned === true;
          const errMsg = data.spawn_error;
          const pid = data.worker_pid;
          let html = '';
          if (autoOK) {
            html = `<div class="esc-feed-item" style="border-left:3px solid #2ea043;">` +
              `<strong>Task ${tid} - worker spawned (PID ${pid})</strong><br>` +
              `<span style="font-size:11px;color:var(--text-muted);">agy worker is decomposing the spec in background. ` +
              `Watch <code>${data.worker_log || 'worker log'}</code> for progress. Map will auto-refresh in 60s.</span>` +
              `</div>`;
            setTimeout(() => window.SpecMap.fetchAndRender(graph.spec_id), 60000);
          } else {
            html = `<div class="esc-feed-item" style="border-left:3px solid #f85149;">` +
              `<strong>Task ${tid} queued, but auto-spawn FAILED.</strong><br>` +
              `<span style="font-size:11px;color:#f85149;">${errMsg || 'unknown error'}</span><br>` +
              `<span style="font-size:11px;color:var(--text-muted);">Fall back to manual: spawn an agy session and paste:</span><br>` +
              `<code style="display:block;background:#0d1117;padding:6px 8px;margin-top:6px;border-radius:3px;font-size:11px;">ADT_TASK_ID=${tid}</code>` +
              `<button class="esc-btn-copy" style="margin-top:6px;padding:4px 10px;font-size:11px;background:#1f6feb;color:#fff;border:none;border-radius:3px;cursor:pointer;" data-tid="${tid}">Copy task ID</button>` +
              `</div>`;
          }
          if (feed) feed.insertAdjacentHTML('beforeend', html);
          // Bind copy button
          const cbtn = feed && feed.querySelector('.esc-btn-copy');
          if (cbtn) cbtn.addEventListener('click', () => {
            navigator.clipboard.writeText(tid).then(() => {
              if (window.ToastManager) window.ToastManager.show('info', 'Copied', tid);
            });
          });
          btn.disabled = false;
          btn.textContent = 'Decompose Now';
        })
        .catch(err => {
          btn.disabled = false;
          btn.textContent = 'Decompose Now';
          if (feed) feed.insertAdjacentHTML('beforeend',
            `<div class="esc-feed-item esc-feed-err">Failed: ${err}</div>`);
        });
      };
    }
    return;
  }

  // (rollup is rendered earlier by _renderRollup; do not re-render here)
  // Build Cytoscape elements
  const STATUS_COLOR = {
    'pending': '#4A5568', 'ready': '#3182CE', 'in_progress': '#D69E2E',
    'completed': '#38A169', 'done': '#38A169', 'failed': '#E53E3E',
    'skipped': '#E53E3E', 'blocked': '#E53E3E'
  };
  // SPEC-062 Amendment D: status icons per node
  const STATUS_ICON = {
    'completed': '✓', 'done': '✓',
    'in_progress': '⟳',
    'ready': '○',
    'pending': '⊝',
    'blocked': '⊘',
    'failed': '✗', 'skipped': '✗'
  };
  const ROLE_LETTER = {
    'Systems_Architect': 'S', 'Backend_Engineer': 'B',
    'Frontend_Engineer': 'F', 'DevOps_Engineer': 'D', 'Overseer': 'O'
  };

  const elements = [];
  (graph.nodes || []).forEach(n => {
    const status = (n.status || 'pending').toLowerCase();
    let harness = null;
    let worker = null;
    if (graph.workers) {
      worker = graph.workers.find(w => w.current_task_id === n.task_id);
      if (worker) harness = worker.harness;
    }
    elements.push({
      group: 'nodes',
      data: {
        id: n.task_id,
        task_id: n.task_id,
        title: n.title || '',
        role: n.role || '',
        status: status,
        label: `${STATUS_ICON[status] || '?'} ${ROLE_LETTER[n.role] || '?'} ${n.task_id}\n${(n.title || '').slice(0, 36)}`,
        description: n.description || '',
        depends_on: n.depends_on || [],
        color: STATUS_COLOR[status] || '#4A5568',
        progress: n.progress || 0,
        harness: harness,
        worker: worker,
        // SPEC-067-C + escalation UI fields
        spec_ref: n.spec_ref || (window.SpecMap.state && window.SpecMap.state.currentSpecId) || '',
        assigned_harness: n.assigned_harness || null,
        assigned_model: n.assigned_model || null,
        harness_escalation_offered: n.harness_escalation_offered || false,
        reconciled_from_failed: n.reconciled_from_failed || false,
        auto_retry_count: n.auto_retry_count || 0,
        // SPEC-062-H Fix D: escalation ladder attempt count (yellow/orange/red badge)
        attempt_count: n.attempt_count || 0,
        attempt_history: n.attempt_history || [],
        escalations_exhausted: n.escalations_exhausted || false,
        last_failed_reason: n.last_failed_reason || null,
        risk_level: n.risk_level || null,
        acceptance_criteria: n.acceptance_criteria || [],
        progress_percent: n.progress_percent,
        progress_message: n.progress_message,
        progress_updated_at: n.progress_updated_at
      }
    });
  });
  (graph.edges || []).forEach(e => {
    elements.push({
      group: 'edges',
      data: {id: `e_${e.from}_${e.to}`, source: e.from, target: e.to}
    });
  });

  // Re-init Cytoscape only if first render or canvas was wiped.
  if (!window.SpecMap.state.cy || !canvas.querySelector('canvas')) {
    canvas.innerHTML = '';
    if (typeof cytoscape !== 'function') {
      canvas.innerHTML = '<div style="padding:24px;color:#E53E3E;">cytoscape.js not loaded.</div>';
      return;
    }
    if (typeof cytoscapeDagre === 'function' && cytoscape.use) {
      try { cytoscape.use(cytoscapeDagre); } catch(_) {}
    }
    window.SpecMap.state.cy = cytoscape({
      container: canvas,
      elements: elements,
      style: window.GraphRenderer ? window.GraphRenderer.getStyleSheet() : [],
      layout: { name: (typeof cytoscapeDagre === 'function' ? 'dagre' : 'breadthfirst'),
                rankDir: 'TB', nodeSep: 40, rankSep: 80 }
    });
    window.SpecMap.state.cy.userZoomingEnabled(false);
    if (window.SpecMap.bindEventHandlers) {
      window.SpecMap.bindEventHandlers(window.SpecMap.state.cy);
    }
    
    window.SpecMap.state.cy.on('render pan zoom position', () => {
      if (window.SpecMap.updateTokenPositions) window.SpecMap.updateTokenPositions();
    });
  } else {
    // Refresh in place
    const cy = window.SpecMap.state.cy;
    cy.elements().remove();
    cy.add(elements);
    cy.layout({ name: (typeof cytoscapeDagre === 'function' ? 'dagre' : 'breadthfirst'),
                rankDir: 'TB', nodeSep: 40, rankSep: 80 }).run();
  }
  
  if (window.SpecMap.renderWorkerTokens) {
    window.SpecMap.renderWorkerTokens(graph);
    // Initial position sync once layout is roughly done
    setTimeout(() => {
      if (window.SpecMap.updateTokenPositions) window.SpecMap.updateTokenPositions();
    }, 100);
  }
};

window.SpecMap.startPolling = function(specId) {
  window.SpecMap.stopPolling();
  
  if (window.__TAURI__) {
    // SPEC-062 sec 2.5: Live update via ADS event stream + 500ms debounce
    let debounceTimer = null;
    let lastLineCount = 0;

    // Initial baseline
    window.__TAURI__.core.invoke('read_project_file', { path: '_cortex/ads/events.jsonl' })
      .then(content => {
         if (content) lastLineCount = content.trim().split('\n').filter(l => l.trim()).length;
      }).catch(() => {});

    const p = window.__TAURI__.event.listen('ads-updated', async () => {
      try {
        const content = await window.__TAURI__.core.invoke('read_project_file', { path: '_cortex/ads/events.jsonl' });
        if (!content) return;
        
        const lines = content.trim().split('\n').filter(l => l.trim());
        const newLinesCount = lines.length;
        if (newLinesCount <= lastLineCount) {
          lastLineCount = newLinesCount;
          return;
        }

        const newEvents = lines.slice(lastLineCount).map(l => {
          try { return JSON.parse(l); } catch { return null; }
        }).filter(Boolean);
        
        lastLineCount = newLinesCount;

        let shouldRefetch = false;
        for (const ev of newEvents) {
          const type = ev.action_type || '';
          const data = ev.action_data || {};
          const eventSpecId = data.spec_id || ev.spec_ref || ev.spec_id;
          
          if (window.SpecMap.state.activeBuild && data.build_id) {
            const currentBuildId = window.SpecMap.state.activeBuild.buildId;
            if (data.build_id === currentBuildId || currentBuildId === 'build_...') {
              if (type === 'build_wave_start') {
                window.SpecMap.updateBuildStrip({ buildId: data.build_id, state: 'running', wave: `wave ${data.wave_number}/${data.total_waves || '?'}` });
              } else if (type === 'build_complete') {
                window.SpecMap.updateBuildStrip({ state: 'complete', progress: 100 });
              } else if (type === 'build_failed') {
                window.SpecMap.updateBuildStrip({ state: 'failed' });
              }
            }
          }

          if (type === 'task_status_changed' && eventSpecId === specId) {
            shouldRefetch = true;
          }
          if (['worker_session_started', 'worker_session_ended', 'worker_steered'].includes(type) && eventSpecId === specId) {
            shouldRefetch = true;
          }
          if (type === 'tool_completed' && eventSpecId === specId) {
             shouldRefetch = true;
          }
        }

        if (shouldRefetch) {
          if (debounceTimer) clearTimeout(debounceTimer);
          debounceTimer = setTimeout(() => {
            if (window.SpecMap.state.currentSpecId === specId) {
              window.SpecMap.fetchAndRender(specId);
            }
          }, 500);
        }
      } catch (err) {
        console.warn('SpecMap polling error:', err);
      }
    });
    window.SpecMap.state.adsUnlistenPromise = p;
  } else {
    // Fallback for non-Tauri browser environments
    window.SpecMap.state.pollTimer = setInterval(() => {
      if (window.SpecMap.state.currentSpecId === specId) {
        window.SpecMap.fetchAndRender(specId);
      }
    }, window.SpecMap.state.pollMs);
  }
};

window.SpecMap.stopPolling = function() {
  if (window.SpecMap.state.pollTimer) {
    clearInterval(window.SpecMap.state.pollTimer);
    window.SpecMap.state.pollTimer = null;
  }
  if (window.SpecMap.state.adsUnlistenPromise) {
    window.SpecMap.state.adsUnlistenPromise.then(unlisten => {
      if (typeof unlisten === 'function') unlisten();
    }).catch(err => console.warn(err));
    window.SpecMap.state.adsUnlistenPromise = null;
  }
};

window.SpecMap.renderWorkerTokens = function(graph) {
  const canvas = document.getElementById('spec-map-canvas');
  if (!canvas) return;

  // Find or create layer
  let layer = document.getElementById('sm-tokens-layer');
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'sm-tokens-layer';
    layer.style.position = 'absolute';
    layer.style.top = '0';
    layer.style.left = '0';
    layer.style.width = '100%';
    layer.style.height = '100%';
    layer.style.pointerEvents = 'none'; // let clicks pass through to canvas
    canvas.appendChild(layer);
  }

  // Clear existing
  layer.innerHTML = '';

  const ROLE_LETTER = {
    'Systems_Architect': 'S', 'Backend_Engineer': 'B',
    'Frontend_Engineer': 'F', 'DevOps_Engineer': 'D', 'Overseer': 'O'
  };

  if (graph.workers && Array.isArray(graph.workers)) {
    const taskCounts = {}; // for diagonal stacking

    graph.workers.forEach(w => {
      if (!w.current_task_id) return;
      
      const count = taskCounts[w.current_task_id] || 0;
      taskCounts[w.current_task_id] = count + 1;

      const token = document.createElement('div');
      token.className = `worker-token harness-${(w.harness || 'unknown').toLowerCase()}`;
      token.dataset.taskId = w.current_task_id;
      token.dataset.sessionId = w.session_id;
      token.dataset.stackIndex = count;
      
      // Pointer events auto so we can hover/click them
      token.style.pointerEvents = 'auto';

      let pulse = false;
      const now = Date.now();
      if (w.last_event_time) {
         const t = new Date(w.last_event_time).getTime();
         if (now - t < 5000) pulse = true;
      } else if (w.last_tool) {
         // fallback if we just have a fresh tool update
         pulse = true;
      }
      if (pulse) {
         token.classList.add('pulse');
      }

      token.title = `Model: ${w.model || 'Unknown'}\nStarted: ${w.started_at || 'Unknown'}\nLast Tool: ${w.last_tool || 'None'}\nADS: ${w.session_id || 'None'}`;
      token.innerHTML = w.harness ? w.harness.charAt(0).toUpperCase() : '?';

      layer.appendChild(token);
    });
  }
};

window.SpecMap.updateTokenPositions = function() {
  if (!window.SpecMap.state.cy) return;
  const cy = window.SpecMap.state.cy;
  const layer = document.getElementById('sm-tokens-layer');
  if (!layer) return;

  const tokens = layer.querySelectorAll('.worker-token');
  tokens.forEach(token => {
    const taskId = token.dataset.taskId;
    const node = cy.getElementById(taskId);
    if (node && node.length > 0) {
      const pos = node.renderedPosition();
      const zoom = cy.zoom();
      
      const nodeW = 260 * zoom;
      const nodeH = 90 * zoom;
      
      const x = pos.x + (nodeW / 2);
      const y = pos.y - (nodeH / 2);

      const stackIndex = parseInt(token.dataset.stackIndex || '0');
      const offset = stackIndex * 8;

      token.style.left = (x + offset) + 'px';
      token.style.top = (y + offset) + 'px';
      token.style.display = 'flex';
    } else {
      token.style.display = 'none';
    }
  });
};



// SPEC-062 Amendment D fix: rollup rendering extracted so it can run before empty-spec early-return
window.SpecMap._renderRollup = function(graph) {
  // Rollup header
  const rollup = document.getElementById('spec-map-rollup');
  if (rollup && graph.rollup) {
    const r = graph.rollup;
    const progress = r.percent_complete || 0;
    
    // SPEC-052 progress logic color
    let color = 'var(--accent-blue)';
    if (progress >= 100) color = 'var(--accent-green)';
    else if (progress > 80) color = '#56d364';
    else if (progress > 20) color = 'var(--accent-blue)';
    else color = '#79c0ff';

    const _curProj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
    rollup.innerHTML =
      `<div style="display:flex; align-items:center; gap:10px;">` +
      `  <span class="objective-spec-id">${graph.spec_id}</span>` +
      `  <span class="objective-intent" style="color:var(--text-muted); font-size:0.85em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:340px;" title="${graph.spec_intent || ''}">${graph.spec_intent || graph.spec_title || ''}</span>` +
      `  <div class="objective-progress-bar" style="width:160px; height:8px; background:var(--bg-tertiary); border-radius:4px; overflow:hidden; flex-shrink:0;">` +
      `    <div class="objective-progress-fill" style="width: ${progress}%; background-color: ${color}; height:100%; transition:width 0.3s ease;"></div>` +
      `  </div>` +
      `  <span class="objective-progress-text" style="font-size:0.85em; color:var(--text-muted); white-space:nowrap;">${progress}% (${r.tasks_completed || 0}/${r.tasks_total || 0})</span>` +
      `</div>`;

  }
};


// === SPEC-062 Amendment D7: live status polling for spec map ===
window.SpecMap.LivePoll = (function() {
  let timer = null;
  let currentSpec = null;

  function ensureBanner() {
    let banner = document.getElementById('spec-map-live-banner');
    if (banner) return banner;
    banner = document.createElement('div');
    banner.id = 'spec-map-live-banner';
    banner.className = 'spec-map-live-banner';
    banner.hidden = true;
    // Insert just above the spec map canvas
    const canvas = document.getElementById('spec-map-canvas');
    if (canvas && canvas.parentNode) {
      canvas.parentNode.insertBefore(banner, canvas);
    } else {
      document.body.appendChild(banner);
    }
    return banner;
  }

  function fmtAge(tsStr) {
    if (!tsStr) return '';
    try {
      const t = new Date(tsStr).getTime();
      const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
      if (sec < 60) return sec + 's ago';
      if (sec < 3600) return Math.floor(sec / 60) + 'm ago';
      return Math.floor(sec / 3600) + 'h ago';
    } catch(_) { return ''; }
  }

  function render(status) {
    const banner = ensureBanner();
    if (!status || !status.is_active) {
      banner.hidden = true;
      banner.innerHTML = '';
      // Remove active class from any nodes
      if (window.SpecMap.state.cy) {
        try { window.SpecMap.state.cy.nodes().removeClass('cy-task-active'); } catch(_){}
      }
      return;
    }
    banner.hidden = false;
    const parts = [];

    if (status.active_build) {
      const b = status.active_build;
      const roles = (b.roles_active || []).join(', ') || '...';
      const wave = b.wave || '?';
      const total = b.total_waves || '?';
      parts.push(
        '<span class="live-pill live-build">BUILD</span>' +
        `<span class="live-detail">wave ${wave}/${total}</span>` +
        `<span class="live-detail">roles: ${roles}</span>` +
        `<span class="live-meta">${b.build_id} · started ${fmtAge(b.started_at)}</span>`
      );
    }

    // Show at most 1 decompose card: prefer alive workers; skip exited workers that already created tasks (done = no longer relevant)
    const visibleWorkers = (status.decompose_workers || [])
      .filter(w => w.alive || w.tasks_created_so_far === 0)
      .slice(0, 1);
    visibleWorkers.forEach(w => {
      const pill = w.alive ? 'live-decompose' : 'live-decompose-dead';
      const stateText = w.alive ? 'agy alive' : 'agy exited';
      const last = (w.log_tail && w.log_tail.length) ? w.log_tail[w.log_tail.length - 1] : '';
      parts.push(
        `<span class="live-pill ${pill}">DECOMPOSE</span>` +
        `<span class="live-detail">${stateText} · ${w.tasks_created_so_far} tasks</span>` +
        `<span class="live-meta" title="${(last||'').replace(/"/g,'&quot;')}">${(last||'').slice(0,90)}</span>`
      );
    });

    // SPEC-062 Amendment F: VERIFY row (active or latest)
    if (status.active_verification) {
      const v = status.active_verification;
      const aliveTxt = v.alive ? 'auditing' : 'verifier exited';
      parts.push(
        '<span class="live-pill live-verify">VERIFY</span>' +
        `<span class="live-detail">Overseer ${aliveTxt} · iter ${v.iteration}/3</span>` +
        `<span class="live-meta">${v.findings_received} findings · PID ${v.verifier_pid || '?'}</span>`
      );
    } else if (status.latest_verification) {
      const lv = status.latest_verification;
      const s  = lv.summary || {};
      const ok = lv.state === 'verified';
      const cls = ok ? 'live-verify-pass' : 'live-verify-fail';
      const label = ok
        ? `&#10003; PASSED &middot; ${s.passed||0} criteria &middot; ${s.failed||0} fails`
        : `&#10007; ${s.failed||0} of ${(s.passed||0)+(s.failed||0)+(s.partial||0)+(s.cannot_verify||0)} criteria FAILED &middot; iter ${lv.iteration||1}`;
      parts.push(
        `<span class="live-pill ${cls}">VERIFY</span>` +
        `<span class="live-detail">${label}</span>` +
        `<span class="live-meta" title="${(s.recommendation||'').replace(/"/g,'&quot;')}">${(s.recommendation||'').slice(0,90)}</span>`
      );
    }

    if (status.recent_events && status.recent_events.length) {
      const e = status.recent_events[0];
      parts.push(
        `<span class="live-event">${e.action_type} · ${fmtAge(e.ts)}</span>`
      );
    }

    banner.innerHTML = parts.map(p => '<div class="live-row">' + p + '</div>').join('');

    // Pulse nodes that are part of the current build wave (best-effort by status)
    if (window.SpecMap.state.cy) {
      try {
        window.SpecMap.state.cy.nodes().forEach(n => {
          const st = (n.data('status') || '').toLowerCase();
          if (st === 'in_progress' || st === 'running' || st === 'active') {
            n.addClass('cy-task-active');
          } else {
            n.removeClass('cy-task-active');
          }
        })
    if (window.SpecMap._paintWatchdogBadges) window.SpecMap._paintWatchdogBadges();;
      } catch(_) {}
    }
  }

  function tick() {
    if (!currentSpec) return;
    const proj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
    fetch(`${window.SpecMap.getCenterUrl()}/api/specs/${encodeURIComponent(currentSpec)}/live_status?project=${encodeURIComponent(proj)}`)
      .then(r => r.ok ? r.json() : null)
      .then(render)
      .catch(() => {});
  }

  function start(specId) {
    currentSpec = specId;
    if (timer) clearInterval(timer);
    tick();
    timer = setInterval(tick, 3000);
  }

  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
    currentSpec = null;
    const banner = document.getElementById('spec-map-live-banner');
    if (banner) banner.hidden = true;
  }

  return { start, stop, tick, render };
})();

// Hook into fetchAndRender so we start polling on each spec view
(function() {
  const _origLoad = window.SpecMap.loadSpec;
  if (_origLoad) {
    window.SpecMap.loadSpec = function(specId) {
      window.SpecMap.LivePoll.start(specId);
      return _origLoad(specId);
    };
  }
})();


// SPEC-062 Amendment D8 -- per-task progression indicator on the map.
// When the live banner refreshes, also walk task_graph (cy.nodes) and pulse those
// matching status in_progress; show elapsed time in node label suffix.
(function() {
  if (window.SpecMap._taskProgressionInstalled) return;
  window.SpecMap._taskProgressionInstalled = true;

  function _fmtElapsed(startIso) {
    if (!startIso) return '';
    try {
      const start = new Date(startIso).getTime();
      const sec = Math.max(0, Math.floor((Date.now() - start) / 1000));
      if (sec < 60) return sec + 's';
      if (sec < 3600) return Math.floor(sec / 60) + 'm' + (sec % 60) + 's';
      return Math.floor(sec / 3600) + 'h' + Math.floor((sec % 3600) / 60) + 'm';
    } catch(_) { return ''; }
  }

  

// SPEC-062-H: poll watchdog per-task levels every 5s and paint node borders.
// Cheap fetch of intents/summary-like listing — we just call the task_graph
// events and let per-task ADS scans surface via the existing sidebar. For the
// map badge, we do a single fetch of watchdog markers by scanning the ops dir
// via a small helper endpoint would be cleaner, but keeping it lightweight:
// each node's watchdog_level is derivable from task ADS events already loaded.
window.SpecMap._paintWatchdogBadges = function() {
  const cy = window.SpecMap.state && window.SpecMap.state.cy;
  if (!cy) return;
  cy.nodes().forEach(n => {
    const evs = (n.data('ads_events_recent') || []);
    let level = 0;
    for (const e of evs) {
      if (e.action_type === 'worker_stuck_sharded') level = Math.max(level, 3);
      else if (e.action_type === 'worker_respawn_anti_narration_requested') level = Math.max(level, 2);
      else if (e.action_type === 'worker_narration_detected') level = Math.max(level, 1);
    }
    n.data('watchdog_level', level);
    if (level > 0) {
      n.addClass('watchdog-active');
      n.data('watchdog_stroke', level >= 3 ? '#ff5555' : level === 2 ? '#ff9900' : '#f0d000');
    } else {
      n.removeClass('watchdog-active');
    }
  });
};

  // Refresh task statuses from API every 3s using task_graph re-fetch (cheap)
  setInterval(() => {
    const specId = window.SpecMap.state && window.SpecMap.state.currentSpecId;
    const cy = window.SpecMap.state && window.SpecMap.state.cy;
    if (!specId || !cy) return;
    const proj = window.SpecMap.state.currentProject || 'adt-framework';
    fetch(`${window.SpecMap.getCenterUrl()}/api/specs/${encodeURIComponent(specId)}/task_graph?project=${encodeURIComponent(proj)}`)
      .then(r => r.ok ? r.json() : null)
      .then(graph => {
        if (!graph || !graph.nodes) return;
        graph.nodes.forEach(n => {
          const cyNode = cy.getElementById(n.task_id);
          if (cyNode && cyNode.length) {
            // Refresh escalation fields every poll so banner appears within 3s of backend flip
            if (n.harness_escalation_offered !== cyNode.data('harness_escalation_offered')) {
              cyNode.data('harness_escalation_offered', n.harness_escalation_offered);
            }
            if (n.assigned_harness !== cyNode.data('assigned_harness')) {
              cyNode.data('assigned_harness', n.assigned_harness);
            }
            if (n.assigned_model !== cyNode.data('assigned_model')) {
              cyNode.data('assigned_model', n.assigned_model);
            }
            const oldStatus = (cyNode.data('status') || '').toLowerCase();
            const newStatus = (n.status || '').toLowerCase();
            if (oldStatus !== newStatus) {
              cyNode.data('status', newStatus);
              // Update label prefix with new status icon
              const STATUS_ICON_RUNTIME = {
                'completed': '✓', 'done': '✓',
                'in_progress': '⟳', 'ready': '○', 'pending': '⊝',
                'blocked': '⊘', 'failed': '✗', 'skipped': '✗'
              };
              const roleLetter = (cyNode.data('label') || '').split(' ')[1] || '?';
              const tid = n.task_id;
              const title = (n.title || '').slice(0, 36);
              const elapsed = newStatus === 'in_progress' ? ' [' + _fmtElapsed(n.started_at) + ']' : '';
              cyNode.data('label', `${STATUS_ICON_RUNTIME[newStatus] || '?'} ${roleLetter} ${tid}${elapsed}\n${title}`);
            }
            // Update elapsed + progress on in_progress nodes (SPEC-062 D9)
            if (newStatus === 'in_progress') {
              const roleLetter = ((cyNode.data('role') || '?')[0] || '?').toUpperCase();
              const tid = n.task_id;
              const title = (n.title || '').slice(0, 36);
              const elapsed = n.started_at ? ' [' + _fmtElapsed(n.started_at) + ']' : '';
              const pct = (typeof n.progress_percent === 'number') ? n.progress_percent
                          : ((typeof n.progress === 'number' && n.progress > 0 && n.progress < 100) ? n.progress : null);
              const msg = n.progress_message ? ' ' + n.progress_message.slice(0, 30) : '';
              let bar = '';
              if (pct !== null && pct !== undefined) {
                const filled = Math.round(pct / 10);
                bar = '\n[' + '█'.repeat(filled) + '░'.repeat(10 - filled) + '] ' + pct + '%' + msg;
              }
              cyNode.data('label',
                `⟳ ${roleLetter} ${tid}${elapsed}\n${title}${bar}`);
            }
            // Pulse class
            if (newStatus === 'in_progress') {
              cyNode.addClass('cy-task-active');
            } else {
              cyNode.removeClass('cy-task-active');
            }
          }
        });
      })
      .catch(()=>{});
  }, 3000);

  console.log('[SpecMap] per-task progression hook installed');
})();


// SPEC-062 Amendment F: per-task verification badge overlay.
// Polls latest_verification.build_id from live_status, then fetches
// /api/builds/<id>/verification to index findings per task_id, and
// decorates node labels with ✓/⚠/✗.
(function() {
  if (window.SpecMap._verifyBadgeInstalled) return;
  window.SpecMap._verifyBadgeInstalled = true;

  function worstStatus(statuses) {
    if (statuses.includes('fail')) return 'fail';
    if (statuses.includes('partial')) return 'partial';
    if (statuses.includes('cannot_verify')) return 'cannot_verify';
    if (statuses.includes('pass')) return 'pass';
    return null;
  }

  function badgeFor(status) {
    if (status === 'pass') return '<span style="color:#2e7d32;font-weight:700">&#10003;</span>';
    if (status === 'partial' || status === 'cannot_verify')
      return '<span style="color:#ff9800;font-weight:700">&#9888;</span>';
    if (status === 'fail') return '<span style="color:#c62828;font-weight:700">&#10007;</span>';
    return '';
  }

  function badgeChar(status) {
    if (status === 'pass') return '✓';
    if (status === 'partial' || status === 'cannot_verify') return '⚠';
    if (status === 'fail') return '✗';
    return '';
  }

  function openVerificationDrawer(taskId, findings) {
    let drawer = document.getElementById('spec-map-verify-drawer');
    if (!drawer) {
      drawer = document.createElement('div');
      drawer.id = 'spec-map-verify-drawer';
      drawer.className = 'spec-map-verify-drawer';
      document.body.appendChild(drawer);
    }
    const rows = findings.map(f =>
      `<tr><td>${badgeFor(f.status)}</td>
           <td><code>${(f.criterion||'').replace(/</g,'&lt;')}</code></td>
           <td>${(f.evidence||'').replace(/</g,'&lt;')}</td>
           <td><small>${f.severity||''}</small></td></tr>`
    ).join('');
    drawer.innerHTML =
      `<div class="vd-head"><strong>Verification findings: ${taskId}</strong>
         <button onclick="document.getElementById('spec-map-verify-drawer').style.display='none'">×</button></div>
       <table class="vd-table"><thead><tr><th></th><th>Criterion</th><th>Evidence</th><th>Sev</th></tr></thead>
              <tbody>${rows||'<tr><td colspan=4>No findings recorded for this task.</td></tr>'}</tbody></table>`;
    drawer.style.display = 'block';
  }
  window.SpecMap._openVerificationDrawer = openVerificationDrawer;

  let lastBuildId = null;
  let findingsByTask = {};

  function applyBadges() {
    const cy = window.SpecMap.state && window.SpecMap.state.cy;
    if (!cy) return;
    cy.nodes().forEach(n => {
      const tid = n.data('task_id') || n.id();
      const arr = findingsByTask[tid] || [];
      if (!arr.length) return;
      const status = worstStatus(arr.map(f => f.status));
      const ch = badgeChar(status);
      if (!ch) return;
      const label = n.data('label') || '';
      if (label.indexOf(' ' + ch) === -1) {
        n.data('label', label + ' ' + ch);
      }
    });
  }

  // Cytoscape click handler for badges -- on any node tap, if it has findings, offer drawer.
  function bindNodeClickForVerify() {
    const cy = window.SpecMap.state && window.SpecMap.state.cy;
    if (!cy || cy._verifyClickBound) return;
    cy.on('tap', 'node', evt => {
      const tid = evt.target.data('task_id') || evt.target.id();
      const arr = findingsByTask[tid];
      if (arr && arr.length) {
        openVerificationDrawer(tid, arr);
      }
    });
    cy._verifyClickBound = true;
  }

  setInterval(() => {
    const specId = window.SpecMap.state && window.SpecMap.state.currentSpecId;
    if (!specId) return;
    const proj = window.SpecMap.state.currentProject || 'adt-framework';
    fetch(`${window.SpecMap.getCenterUrl()}/api/specs/${encodeURIComponent(specId)}/live_status?project=${encodeURIComponent(proj)}`)
      .then(r => r.ok ? r.json() : null)
      .then(status => {
        if (!status) return;
        const lv = status.latest_verification || status.active_verification;
        if (!lv || !lv.build_id) return;
        if (lv.build_id === lastBuildId && status.active_verification == null) return;
        lastBuildId = lv.build_id;
        return fetch(`${window.SpecMap.getCenterUrl()}/api/builds/${encodeURIComponent(lv.build_id)}/verification?project=${encodeURIComponent(proj)}`)
          .then(r => r.ok ? r.json() : null)
          .then(vr => {
            if (!vr) return;
            findingsByTask = {};
            (vr.findings || []).forEach(f => {
              if (!findingsByTask[f.task_id]) findingsByTask[f.task_id] = [];
              findingsByTask[f.task_id].push(f);
            });
            bindNodeClickForVerify();
            applyBadges();
          });
      })
      .catch(()=>{});
  }, 5000);

  console.log('[SpecMap] verification badge overlay installed');
})();


// SPEC-062 D12: header project dropdown - independent of in-map rollup dropdown
window.SpecMap.bindHeaderProjectDropdown = function() {
  const dd = document.getElementById('spec-map-header-project-dd');
  if (!dd || dd.dataset.bound === 'true') return;
  dd.dataset.bound = 'true';

  const toggle = dd.querySelector('.adt-dd-toggle');
  const list = dd.querySelector('.adt-dd-list');
  const labelEl = dd.querySelector('.adt-dd-label');

  window.SpecMap.state = window.SpecMap.state || {};
  let curProj = window.SpecMap.state.currentProject || 'adt-framework';
  labelEl.textContent = curProj;
  dd.dataset.value = curProj;

  function _switchTo(newProj) {
    curProj = newProj;
    labelEl.textContent = newProj;
    dd.dataset.value = newProj;
    list.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    window.SpecMap.state.currentProject = newProj;
    try { localStorage.setItem('adt_spec_map_project', newProj); } catch(_) {}
    // Update Launch button state for new project
    if (window.SpecMap.refreshLaunchButton) window.SpecMap.refreshLaunchButton();
    // Re-populate the spec selector for this project
    if (window.SpecMap.populateSelector) {
      window.SpecMap.populateSelector().then(() => {
        // Auto-select first spec of the new project
        const sel = document.getElementById('spec-map-selector');
        if (sel && sel.options.length > 1) {
          sel.selectedIndex = 1;
          if (window.SpecMap.loadSpec) window.SpecMap.loadSpec(sel.value);
        } else {
          const canvas = document.getElementById('spec-map-canvas');
          if (canvas) canvas.innerHTML = '<div style="padding:24px;color:var(--text-muted);">No specs in project ' + newProj + '. Decompose one to start.</div>';
        }
      });
    }
  }

  function _refreshList() {
    return fetch(`${window.SpecMap.getCenterUrl()}/api/projects`)
      .then(r => r.ok ? r.json() : {})
      .then(projs => {
        let names = Object.keys(projs || {}).sort();
        if (!names.includes('adt-framework')) names.unshift('adt-framework');  // SPEC-062 D15: always offer adt-framework
        if (!names.length) return;
        list.innerHTML = names.map(n =>
          `<li class="adt-dd-item${n === curProj ? ' adt-dd-item-current' : ''}" role="option" data-value="${n}">${n}</li>`
        ).join('');
      })
      .catch(()=>{});
  }

  toggle.addEventListener('click', e => {
    e.stopPropagation();
    const willOpen = list.hidden;
    if (willOpen) _refreshList();  // SPEC-062 D12 fix: re-fetch every open so list never goes stale
    list.hidden = !willOpen;
    toggle.setAttribute('aria-expanded', String(willOpen));
  });

  list.addEventListener('click', e => {
    const item = e.target.closest('.adt-dd-item');
    if (item) _switchTo(item.dataset.value);
  });

  document.addEventListener('click', ev => {
    if (!dd.contains(ev.target)) { list.hidden = true; toggle.setAttribute('aria-expanded','false'); }
  });
  document.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') { list.hidden = true; toggle.setAttribute('aria-expanded','false'); }
  });

  // Initial populate
  _refreshList();
};

// Hook into init: bind header dropdown alongside spec selector
(function() {
  const _origInit = window.SpecMap.init;
  if (_origInit) {
    window.SpecMap.init = function() {
      try { window.SpecMap.bindHeaderProjectDropdown(); } catch(_) {}
      return _origInit.apply(this, arguments);
    };
  }
})();


// SPEC-062 D13: immersive mode -- right sidebar slides out, task detail slides in
(function() {
  function _update() {
    const view = document.getElementById('spec-map-view');
    const visible = view && view.style.display !== 'none' && view.offsetParent !== null;
    document.body.classList.toggle('spec-map-active', !!visible);
  }
  // Observe spec-map-view visibility via MutationObserver on style attribute
  const view = document.getElementById('spec-map-view');
  if (view) {
    new MutationObserver(_update).observe(view, { attributes: true, attributeFilter: ['style', 'class'] });
    _update();  // initial sync
  }
  // Also re-sync on hashchange / tab switch / clicks (cheap defense)
  document.addEventListener('click', () => setTimeout(_update, 50));

  // When entering immersive mode, populate the spec-map-detail panel with a default "current spec summary"
  // so it doesn't appear empty before user clicks a task
  const detailPanel = document.getElementById('spec-map-detail');
  if (detailPanel) {
    const origObserver = new MutationObserver(() => {
      if (document.body.classList.contains('spec-map-active') &&
          (!detailPanel.innerHTML || detailPanel.innerHTML.trim() === '')) {
        const sid = window.SpecMap.state && window.SpecMap.state.currentSpecId;
        const proj = window.SpecMap.state && window.SpecMap.state.currentProject;
        detailPanel.innerHTML =
          '<div style="font-size:13px;color:var(--text-secondary,#b1bac4);">' +
          '<h3 style="margin:0 0 12px 0;color:var(--text-primary,#e6e6e6);font-size:14px;">Task Panel</h3>' +
          '<div style="opacity:0.7;font-size:11px;margin-bottom:8px;">Click a task node to see details, build status, and worker activity.</div>' +
          '<div style="font-size:11px;">Current spec: <strong>' + (sid || '-') + '</strong></div>' +
          '<div style="font-size:11px;">Project: <strong>' + (proj || '-') + '</strong></div>' +
          '</div>';
      }
    });
    origObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  }
})();

// Auto-start the live-log poll whenever a new smd-live-log element appears.
// Also stop the poll when the panel is closed (element removed).
(function () {
  function _kick() {
    const el = document.getElementById('smd-live-log');
    if (!el) { window.SpecMap._stopLiveLogPoll(); return; }
    const taskId = el.dataset.taskId;
    const proj = (window.SpecMap.state && window.SpecMap.state.currentProject) || 'adt-framework';
    if (taskId) window.SpecMap._startLiveLogPoll(taskId, proj);
  }
  // Kick on load in case the panel already exists
  document.addEventListener('DOMContentLoaded', _kick);
  // Watch for mutations affecting the smd-content region
  new MutationObserver(_kick).observe(document.body, {childList: true, subtree: true});
  window.SpecMap._liveLogAutoStart = true;
})();

