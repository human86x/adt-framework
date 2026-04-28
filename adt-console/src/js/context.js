// Context panel — live governance data for current session
// SPEC-021: Pull from ADT Center API + local file watchers

const ContextPanel = (() => {
  const getCenterUrl = () => localStorage.getItem("adt_center_url") || "http://localhost:5001";
  let currentSession = null;
  let escalationCount = 0;
  let pollInterval = null;
  let allSpecs = {};
  let showAllRoles = false;
  const spawnedSessions = new Set();

  async function update(session) {    currentSession = session;

    document.getElementById('ctx-role').textContent = session.role || '--';

    const agentEl = document.getElementById('ctx-agent');
    agentEl.textContent = session.agent?.toUpperCase() || '--';
    agentEl.style.color = session.color || 'var(--text-primary)';

    document.getElementById('ctx-task').textContent = 'Connecting...';
    document.getElementById('ctx-task-priority').textContent = '';
    document.getElementById('ctx-task-priority').className = 'ctx-priority';
    document.getElementById('ctx-spec').textContent = '--';
    document.getElementById('ctx-event-count').textContent = '';

    // SPEC-036: Update Sandbox status
    const sandboxEl = document.getElementById('ctx-sandbox');
    if (sandboxEl) {
      if (session.sandboxed) {
        sandboxEl.innerHTML = '<span class="text-adt-success">Active</span>';
      } else if (session.agent_user === 'agent') {
        sandboxEl.innerHTML = '<span class="text-adt-accent">Tier 1</span>';
      } else {
        sandboxEl.innerHTML = '<span style="opacity:0.5">None</span>';
      }
    }

    // SPEC-034: Update role filter indicator
    updateFilterIndicator();

    if (session.startTime) {
      updateUptime(session);
    }

    await fetchSpecs();
    await fetchIntents();
    await fetchTaskData(session);
    await fetchADSEvents(session);
    await fetchRequests();
    await fetchDelegations();
    await fetchDTCPStatus();
    await fetchCapabilityContext(session);
    if (typeof fetchSessionTree === "function") await fetchSessionTree();

    // If Tauri, try reading local files as fallback
    if (window.__TAURI__) {
      fetchLocalData(session);
    }
  }

  let currentIntents = [];
  let currentTasks = [];

  async function fetchIntents() {
    try {
      const projectName = currentSession?.project;
      let url = projectName 
        ? `${getCenterUrl()}/api/governance/capabilities/intents?project=${encodeURIComponent(projectName)}`
        : `${getCenterUrl()}/api/governance/capabilities/intents`;
      
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();
      currentIntents = data.intents || [];
    } catch {
      currentIntents = [];
    }
  }

  function renderOrchestrationTree() {
    const container = document.getElementById('ctx-orchestration-tree');
    if (!container) return;

    if (currentTasks.length === 0) {
      container.innerHTML = '<div class="ctx-empty">Aggregating hierarchy...</div>';
      return;
    }

    // Group tasks by Spec, then Spec by Intent
    const specsWithTasks = {};
    currentTasks.forEach(task => {
      if (!specsWithTasks[task.spec_ref]) {
        specsWithTasks[task.spec_ref] = [];
      }
      specsWithTasks[task.spec_ref].push(task);
    });

    const intentsWithSpecs = {};
    // Add intents from active tasks
    Object.keys(specsWithTasks).forEach(specId => {
      const spec = allSpecs[specId];
      const intent = currentIntents.find(i => i.intent_id === spec?.intent_id) || {
        intent_id: 'GLOBAL',
        title: 'General Framework Evolution'
      };

      if (!intentsWithSpecs[intent.intent_id]) {
        intentsWithSpecs[intent.intent_id] = {
          data: intent,
          specs: {}
        };
      }
      intentsWithSpecs[intent.intent_id].specs[specId] = specsWithTasks[specId];
    });

    container.innerHTML = Object.values(intentsWithSpecs).map(intent => `
      <div class="tree-node intent-node">
        <div class="tree-header"><i class="bi bi-diamond-fill me-1"></i>${intent.data.title}</div>
        <div class="tree-children">
          ${Object.entries(intent.specs).map(([specId, tasks]) => {
            const spec = allSpecs[specId] || { title: specId };
            return `
              <div class="tree-node spec-node" id="node-spec-${specId}">
                <div class="tree-header"><i class="bi bi-file-earmark-medical me-1"></i>${spec.title}</div>
                <div class="tree-children">
                  ${tasks.map(task => {
                    const statusClass = task.status === 'in_progress' ? 'status-active' : (task.status === 'completed' ? 'status-done' : '');
                    const isCompleted = task.status === 'completed';
                    
                    // SPEC-041: Find sessions for this task (if session_id mapping exists in tasks)
                    // For now, we mock/check if task has session data
                    const sessionInfo = task.active_sessions || [];
                    
                    return `
                      <div class="tree-node task-node ${statusClass}" id="node-task-${task.id}">
                        <div class="tree-header d-flex justify-content-between align-items-center">
                          <span><strong class="me-1">${task.id}:</strong> ${task.title}</span>
                          ${!isCompleted ? `<button class="btn-prioritize" onclick="ContextPanel.prioritizeTask('${task.id}')" title="Prioritize Task">&#9654;</button>` : ''}
                        </div>
                        <div class="tree-children">
                          ${sessionInfo.map(s => `
                            <div class="tree-node session-node">
                              <div class="tree-header" style="font-size: 9px; opacity: 0.8;">
                                <i class="bi bi-cpu me-1"></i>Session: ${s.session_id.substring(0,8)}... (${s.agent})
                              </div>
                            </div>
                          `).join('')}
                        </div>
                      </div>
                    `;
                  }).join('')}
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `).join('');
  }

  async function prioritizeTask(taskId) {
    if (!currentSession) return;
    
    ToastManager.show('info', 'Prioritizing', `Sending steer signal for ${taskId}...`);
    
    try {
      if (window.__TAURI__) {
        // Fix command name to match Rust ipc.rs: inject_pty_command
        await window.__TAURI__.core.invoke('inject_pty_command', {
          sessionId: currentSession.id,
          data: `User hint: Focus on Task ID: ${taskId} immediately.`
        });
      }
      
      // Also log to ADS via the new steering endpoint (SPEC-039)
      const projectName = currentSession?.project;
      let url = projectName 
        ? `${getCenterUrl()}/api/governance/steer?project=${encodeURIComponent(projectName)}`
        : `${getCenterUrl()}/api/governance/steer`;

      await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent: 'HUMAN',
          role: 'Operator',
          action_type: 'human_steering',
          description: `Human prioritized task ${taskId} via Console UI.`,
          spec_ref: 'SPEC-039',
          authorized: true,
          action_data: { task_id: taskId }
        })
      });
    } catch (e) {
      console.error("Prioritize error:", e);
    }
  }

  function handleADSFeedback(event) {
    const pulseEl = document.getElementById('thinking-pulse');
    const workingOn = document.getElementById('ctx-working-on');
    
    if (!pulseEl) return;

    pulseEl.className = 'thinking-monitor';
    
    if (event.action_type.startsWith('pending_read')) {
      pulseEl.classList.add('pulse-blue');
    } else if (event.action_type.startsWith('pending_edit')) {
      pulseEl.classList.add('pulse-amber');
      if (event.params?.file && workingOn) {
        workingOn.textContent = `Working on: ${event.params.file.split('/').pop()}`;
        workingOn.style.display = 'block';
      }
    } else if (event.action_type.includes('denied')) {
      pulseEl.classList.add('pulse-red');
      if (workingOn) workingOn.style.display = 'none';
    } else if (event.action_type.includes('complete') || event.action_type.includes('success')) {
      pulseEl.classList.add('pulse-green');
      if (workingOn) workingOn.style.display = 'none';
      setTimeout(() => pulseEl.classList.remove('pulse-green'), 2000);
    }
  }


  async function fetchCostData(session) {
    try {
      const projectName = session?.project;
      const sessionId = session?.id;
      if (!sessionId) return;

      const url = `${getCenterUrl()}/api/governance/session/${sessionId}/cost?project=${encodeURIComponent(projectName || "")}`;
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();

      updateCostMonitor(data.cost_usd, data.input_tokens + data.output_tokens);
    } catch (e) {
      console.error("fetchCostData error:", e);
    }
  }

  function updateCostMonitor(cost, tokens) {
    const costEl = document.getElementById("ctx-cost-value");
    const tokenEl = document.getElementById("ctx-token-value");
    
    if (costEl) {
      const costStr = cost < 0.01 && cost > 0 ? "<$0.01" : `$${cost.toFixed(2)}`;
      costEl.textContent = costStr;
    }
    if (tokenEl) {
      const tokenStr = tokens >= 1000000 ? (tokens / 1000000).toFixed(1) + "M" : 
                       (tokens >= 1000 ? (tokens / 1000).toFixed(1) + "K" : tokens);
      tokenEl.textContent = tokenStr;
    }
  }

  function updateFilterIndicator() {
    const filterEl = document.getElementById('ctx-role-filter');
    const roleEl = document.getElementById('ctx-filter-role');
    const btn = document.getElementById('btn-show-all-roles');
    
    if (!filterEl || !currentSession?.role) {
      if (filterEl) filterEl.style.display = 'none';
      return;
    }

    if (showAllRoles) {
      filterEl.style.display = 'flex';
      roleEl.textContent = 'All roles';
      btn.textContent = 'Filter by role';
    } else {
      filterEl.style.display = 'flex';
      roleEl.textContent = currentSession.role.replace(/_/g, ' ');
      btn.textContent = 'Show all';
    }
  }

  // SPEC-040: Capability context state
  let activeCapIntent = null;
  let activeCapGates = [];
  let activeCapCurrentGate = 1;

  const GATE_NAMES_CTX = [
    "Validation & Classification",
    "Concept Development",
    "Strategic Feasibility",
    "Governance & Quality Review",
    "Portfolio Planning",
    "Investment Decision",
    "Transformation Initiation"
  ];

  const GATE_FIELDS_CTX = {
    1: [
      { name: "classification", label: "Classification", type: "select", options: ["Innovation", "Enhancement", "Maintenance", "Risk Mitigation", "Regulatory", "Operational"] },
      { name: "priority", label: "Priority", type: "select", options: ["Low", "Medium", "High", "Critical"] },
      { name: "validator", label: "Validator", type: "text" }
    ],
    2: [
      { name: "concept_id", label: "Concept ID", type: "text" },
      { name: "prototype_required", label: "Prototype Required", type: "select", options: ["Yes", "No"] },
      { name: "architecture_concept", label: "Architecture", type: "text" },
      { name: "concept_owner", label: "Owner", type: "text" }
    ],
    3: [
      { name: "financial_feasibility", label: "Financial", type: "select", options: ["Positive", "Marginal", "Negative"] },
      { name: "operational_feasibility", label: "Operational", type: "select", options: ["Feasible", "Requires Change", "Not Feasible"] },
      { name: "technical_feasibility", label: "Technical", type: "select", options: ["Feasible", "Complex", "Not Feasible"] },
      { name: "strategic_alignment", label: "Strategic", type: "select", options: ["High", "Moderate", "Low"] }
    ],
    4: [
      { name: "architecture_review", label: "Arch Review", type: "select", options: ["Approved", "Conditional", "Rejected"] },
      { name: "risk_rating", label: "Risk", type: "select", options: ["Low", "Medium", "High", "Critical"] },
      { name: "compliance_status", label: "Compliance", type: "select", options: ["Compliant", "Review Required", "Non-Compliant"] },
      { name: "review_board", label: "Review Board", type: "text" }
    ],
    5: [
      { name: "portfolio_priority", label: "Priority", type: "select", options: ["Low", "Medium", "High", "Strategic"] },
      { name: "portfolio_manager", label: "Manager", type: "text" },
      { name: "estimated_resources", label: "Resources", type: "text" }
    ],
    6: [
      { name: "investment_decision", label: "Decision", type: "select", options: ["Approved", "Deferred", "Rejected", "Further Investigation"] },
      { name: "investment_board", label: "Board", type: "text" },
      { name: "approved_budget", label: "Budget", type: "text" }
    ],
    7: [
      { name: "program_id", label: "Program ID", type: "text" },
      { name: "program_manager", label: "Manager", type: "text" },
      { name: "start_date", label: "Start Date", type: "date" }
    ]
  };

  async function fetchCapabilityContext(session) {
    try {
      const projectName = session?.project;
      let url = projectName
        ? `${getCenterUrl()}/api/governance/capabilities/trace/active?project=${encodeURIComponent(projectName)}`
        : `${getCenterUrl()}/api/governance/capabilities/trace/active`;

      const res = await fetch(url);
      if (!res.ok) {
        renderCapabilityEmpty();
        return;
      }
      const data = await res.json();

      const intent = data.intent;
      const event = data.event;
      activeCapIntent = intent;

      const intentVal = document.getElementById("ctx-intent-value");
      const eventVal = document.getElementById("ctx-event-value");
      const statusVal = document.getElementById("ctx-intent-status");
      const riskVal = document.getElementById("ctx-risk-value");
      const maturityBadge = document.getElementById("ctx-maturity-badge");

      if (intent) {
        intentVal.innerHTML = `<strong style="color:var(--accent-blue);">${intent.intent_id}</strong>: ${intent.title}`;

        // Status
        if (statusVal) {
          const status = intent.status || "Intent Defined";
          statusVal.innerHTML = `<span style="color:var(--accent-blue); font-weight:600;">${status}</span>`;
        }

        // Risk
        if (riskVal) {
          const risk = intent.risk_level || intent.risk?.level || "--";
          const riskLower = risk.toLowerCase();
          const dotClass = riskLower === "critical" ? "risk-critical" : riskLower === "high" ? "risk-high" : riskLower === "medium" ? "risk-medium" : "risk-low";
          riskVal.innerHTML = risk !== "--" ? `<span class="cap-risk-dot ${dotClass}"></span>${risk}` : "--";
        }

        // Maturity
        const currentM = parseInt(intent.current_maturity) || 1;
        const targetM = parseInt(intent.target_maturity) || 3;
        const fillEl = document.getElementById("ctx-maturity-fill");
        const targetEl = document.getElementById("ctx-maturity-target-marker");
        if (fillEl) fillEl.style.width = `${(currentM / 5) * 100}%`;
        if (targetEl) targetEl.style.left = `${(targetM / 5) * 100}%`;
        if (maturityBadge) maturityBadge.textContent = data.realized_maturity || `${currentM}/${targetM}`;

        // Fetch gate data
        await fetchGateProgress(intent.intent_id);
      } else {
        renderCapabilityEmpty();
      }

      if (event) {
        const typeIcon = event.type || event.event_type || "";
        eventVal.innerHTML = `<strong style="color:var(--accent-yellow);">${event.event_id}</strong>: ${truncate(event.description || event.title || typeIcon, 50)}`;
      } else {
        eventVal.textContent = "None detected";
      }
    } catch (e) {
      console.error("fetchCapabilityContext error:", e);
      renderCapabilityEmpty();
    }
  }

  function renderCapabilityEmpty() {
    const intentVal = document.getElementById("ctx-intent-value");
    const eventVal = document.getElementById("ctx-event-value");
    const statusVal = document.getElementById("ctx-intent-status");
    const riskVal = document.getElementById("ctx-risk-value");
    const maturityBadge = document.getElementById("ctx-maturity-badge");
    const gateLabel = document.getElementById("ctx-gate-label");
    const evalBtn = document.getElementById("btn-cap-eval-gate");

    if (intentVal) intentVal.textContent = "No active intent";
    if (eventVal) eventVal.textContent = "None detected";
    if (statusVal) statusVal.textContent = "--";
    if (riskVal) riskVal.textContent = "--";
    if (maturityBadge) maturityBadge.textContent = "--";
    if (gateLabel) gateLabel.textContent = "--";
    if (evalBtn) evalBtn.style.display = "none";

    // Reset gate segments
    document.querySelectorAll(".cap-gate-seg").forEach(seg => {
      seg.className = "cap-gate-seg";
    });

    // Reset status bar gate
    updateStatusBarGate(null);
    activeCapIntent = null;
    activeCapGates = [];
  }

  async function fetchGateProgress(intentId) {
    try {
      const res = await fetch(`${getCenterUrl()}/api/governance/capabilities/intents/${intentId}/gates`);
      if (!res.ok) return;
      const data = await res.json();
      activeCapGates = data.gates || [];
      activeCapCurrentGate = data.current_gate || 1;

      // Render gate segments
      const gatesMap = {};
      activeCapGates.forEach(g => { gatesMap[g.gate_number] = g; });

      document.querySelectorAll(".cap-gate-seg").forEach(seg => {
        const gateNum = parseInt(seg.dataset.gate);
        const gate = gatesMap[gateNum];
        seg.className = "cap-gate-seg";

        if (gate) {
          if (gate.decision === "Proceed") seg.classList.add("gate-completed");
          else if (gate.decision === "Refine") seg.classList.add("gate-refined");
          else if (gate.decision === "Halt") seg.classList.add("gate-halted");
        } else if (gateNum === activeCapCurrentGate) {
          seg.classList.add("gate-current");
        }
      });

      // Gate label
      const gateLabel = document.getElementById("ctx-gate-label");
      if (gateLabel) gateLabel.textContent = `${activeCapCurrentGate}/7`;

      // Show/hide evaluate gate button
      const evalBtn = document.getElementById("btn-cap-eval-gate");
      const currentGateEvaluated = gatesMap[activeCapCurrentGate];
      if (evalBtn) {
        evalBtn.style.display = (!currentGateEvaluated && activeCapCurrentGate <= 7) ? "" : "none";
      }

      // Update status bar gate indicator
      updateStatusBarGate(activeCapCurrentGate);
    } catch (e) {
      console.error("fetchGateProgress error:", e);
    }
  }

  function updateStatusBarGate(gateNum) {
    const el = document.getElementById("status-gate");
    const dot = document.getElementById("gate-status-dot");
    if (!el) return;

    if (gateNum === null || gateNum === undefined) {
      el.innerHTML = '<span class="status-dot dot-grey" id="gate-status-dot"></span> Gate: --';
      return;
    }

    // Determine color based on state
    let dotColor = "dot-green";
    const haltedGate = activeCapGates.find(g => g.decision === "Halt");
    const refinedGate = activeCapGates.find(g => g.decision === "Refine");
    if (haltedGate) dotColor = "dot-red";
    else if (refinedGate) dotColor = "dot-yellow";

    el.innerHTML = `<span class="status-dot ${dotColor}" id="gate-status-dot"></span> Gate: ${gateNum}/7`;
  }

  function openCapInPanel() {
    if (!activeCapIntent) return;
    // Try to open Panel Capabilities tab via the existing Panel iframe
    const panelBtn = document.getElementById("btn-adt-panel");
    if (panelBtn) panelBtn.click();
    // Navigate iframe to capabilities page
    setTimeout(() => {
      const iframe = document.getElementById("adt-panel-iframe");
      if (iframe) {
        const baseUrl = getCenterUrl();
        iframe.src = `${baseUrl}/capabilities`;
      }
    }, 100);
  }

  function openInlineGateEval() {
    if (!activeCapIntent || activeCapCurrentGate > 7) return;

    const gateNum = activeCapCurrentGate;
    const body = document.getElementById("cap-context-body");
    const inlineForm = document.getElementById("cap-inline-gate");
    const headerEl = document.getElementById("cap-inline-gate-header");
    const fieldsEl = document.getElementById("cap-inline-gate-fields");

    if (!inlineForm || !fieldsEl) return;

    // Hide main context, show form
    if (body) body.style.display = "none";
    inlineForm.style.display = "block";

    headerEl.textContent = `Gate ${gateNum}: ${GATE_NAMES_CTX[gateNum - 1]}`;

    // Render gate-specific fields
    const fields = GATE_FIELDS_CTX[gateNum] || [];
    fieldsEl.innerHTML = fields.map(f => {
      let control = "";
      if (f.type === "select") {
        control = `<select name="${f.name}">${f.options.map(o => `<option value="${o}">${o}</option>`).join("")}</select>`;
      } else if (f.type === "date") {
        control = `<input type="date" name="${f.name}">`;
      } else {
        control = `<input type="text" name="${f.name}" placeholder="${f.label}">`;
      }
      return `<div><label>${f.label}</label>${control}</div>`;
    }).join("");

    // Reset outcome
    const outcomeEl = document.getElementById("cap-gate-outcome");
    if (outcomeEl) outcomeEl.value = "";

    // Reset decision
    const proceedRadio = inlineForm.querySelector('input[value="Proceed"]');
    if (proceedRadio) proceedRadio.checked = true;
  }

  function cancelInlineGate() {
    const body = document.getElementById("cap-context-body");
    const inlineForm = document.getElementById("cap-inline-gate");
    if (body) body.style.display = "";
    if (inlineForm) inlineForm.style.display = "none";
  }

  async function submitInlineGate() {
    if (!activeCapIntent) return;

    const gateNum = activeCapCurrentGate;
    const form = document.getElementById("cap-inline-gate-form");
    const outcomeEl = document.getElementById("cap-gate-outcome");
    const outcome = outcomeEl?.value?.trim();

    if (!outcome) {
      if (outcomeEl) outcomeEl.focus();
      return;
    }

    const decision = form.querySelector('input[name="cap_decision"]:checked')?.value || "Proceed";

    // Collect gate-specific field values
    const decisionData = {};
    const fields = GATE_FIELDS_CTX[gateNum] || [];
    fields.forEach(f => {
      const el = form.querySelector(`[name="${f.name}"]`);
      if (el && el.value) decisionData[f.name] = el.value;
    });

    const payload = {
      gate_number: gateNum,
      decision: decision,
      actual_outcome: outcome,
      evaluator: "HUMAN",
      role: "Operator",
      agent: "HUMAN"
    };
    if (Object.keys(decisionData).length > 0) payload.decision_data = decisionData;

    const projectName = currentSession?.project;
    if (projectName) payload.project = projectName;

    try {
      const res = await fetch(`${getCenterUrl()}/api/governance/capabilities/intents/${activeCapIntent.intent_id}/gates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        cancelInlineGate();
        if (typeof ToastManager !== "undefined") {
          ToastManager.show("completion", "Gate Evaluated", `Gate ${gateNum} ${decision} for ${activeCapIntent.title}`);
        }
        // Refresh
        if (currentSession) await fetchCapabilityContext(currentSession);
      } else {
        const err = await res.json();
        if (typeof ToastManager !== "undefined") {
          ToastManager.show("denial", "Gate Error", err.error || "Evaluation failed");
        }
      }
    } catch (e) {
      console.error("Inline gate submit error:", e);
      if (typeof ToastManager !== "undefined") {
        ToastManager.show("denial", "Error", "ADT Center unreachable");
      }
    }
  }

  function toggleFilter() {
    showAllRoles = !showAllRoles;
    if (currentSession) {
      update(currentSession);
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
      const projectName = currentSession?.project;
      const role = currentSession?.role;
      let url = projectName 
        ? `${getCenterUrl()}/api/governance/requests?project=${encodeURIComponent(projectName)}`
        : `${getCenterUrl()}/api/governance/requests`;
      
      // SPEC-034: Role filtering
      if (role && !showAllRoles) {
        url += (url.includes('?') ? '&' : '?') + `role=${encodeURIComponent(role)}`;
      }

      const res = await fetch(url);
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
        const isCompleted = req.status.toLowerCase().includes('complete');
        const statusClass = isCompleted ? 'badge-completed' : 'badge-pending';
        
        // SPEC-035: Add Mark Complete button for human operator
        const completeBtn = !isCompleted ? 
          `<button class="btn-complete-tracker" onclick="ContextPanel.completeRequest('${req.id}', this)" title="Mark Complete">✓ Done</button>` : '';

        li.innerHTML = `
          <div class="tracker-header">
            <strong>${req.id}</strong>
            <span class="badge-adt ${statusClass}">${req.status}</span>
            ${completeBtn}
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
      const projectName = currentSession?.project;
      const url = projectName 
        ? `${getCenterUrl()}/api/governance/delegations?project=${encodeURIComponent(projectName)}`
        : `${getCenterUrl()}/api/governance/delegations`;
      const res = await fetch(url);
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
      const projectName = currentSession?.project;
      const url = projectName 
        ? `${getCenterUrl()}/api/specs?project=${encodeURIComponent(projectName)}`
        : `${getCenterUrl()}/api/specs`;
      const res = await fetch(url);
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
      const projectName = session?.project;
      const role = session?.role;
      let url = projectName 
        ? `${getCenterUrl()}/api/tasks?project=${encodeURIComponent(projectName)}`
        : `${getCenterUrl()}/api/tasks`;
      
      // SPEC-034: Role filtering
      if (role && !showAllRoles) {
        url += (url.includes('?') ? '&' : '?') + `assigned_to=${encodeURIComponent(role)}`;
      }

      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();

      currentTasks = data.tasks || [];
      const tasks = currentTasks;
      renderOrchestrationTree();

      // Find active task for this role
      // Note: If backend already filtered by assigned_to, session.role check is redundant but safe
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

        // Update To-Do list (Pending or In Progress)
        // Note: Filter by role is still needed if showAllRoles is true
        const todoTasks = tasks.filter(t => 
          (t.status === 'in_progress' || t.status === 'pending') && 
          (showAllRoles ? true : t.assigned_to?.includes(session.role))
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
              
              // SPEC-035: Add Mark Complete button for assigned role
              const completeBtn = `<button class="btn-complete-tracker" onclick="ContextPanel.completeTask('${t.id}', this)" title="Mark Complete">✓ Done</button>`;

              li.innerHTML = `
                <div class="tracker-header">
                  <strong>${t.id}</strong>
                  <span class="badge-adt badge-${t.status.replace('_', '-')}">${t.status.replace('_', ' ')}</span>
                  ${completeBtn}
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

      // Render completed tasks
      const completedTasks = tasks.filter(t => 
        t.status === 'completed' && 
        (showAllRoles ? true : t.assigned_to?.includes(session.role))
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
      fetchCostData(session);
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
      const projectName = session?.project;
      const url = projectName 
        ? `${getCenterUrl()}/api/ads/events?project=${encodeURIComponent(projectName)}`
        : `${getCenterUrl()}/api/ads/events`;
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();

      // Handle both list and object response formats
      const allEvents = Array.isArray(data) ? data : (data.events || []);
      const agentEvents = allEvents
        .filter(e => e.agent?.toLowerCase() === session.agent?.toLowerCase())
        .slice(-10)
        .reverse();

      renderADSFeed(agentEvents);
      fetchCostData(session);
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
      const projectName = session?.project;
      const url = projectName 
        ? `${getCenterUrl()}/api/ads/events?project=${encodeURIComponent(projectName)}`
        : `${getCenterUrl()}/api/ads/events`;
      const res = await fetch(url);
      if (!res.ok) return;
      const allEvents = await res.json();
      
      const list = Array.isArray(allEvents) ? allEvents : (allEvents.events || []);
      
      // Filter for delegation events targeting this role
      const requests = list.filter(e => 
        e.action_type === 'delegate_task' && 
        e.description.includes(session.role)
      ).slice(-5).reverse();
      
      const container = document.getElementById('ctx-role-requests');
      if (!container) return;
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
      handleADSFeedback(event);
      if (event.action_type?.includes('denied') || event.action_type?.includes('violation')) {
        ToastManager.show('denial', 'DENIED', truncate(event.description, 80));
      } else if (event.action_type?.includes('escalation') || event.action_type?.includes('break_glass')) {
        ToastManager.show('escalation', 'ESCALATION', truncate(event.description, 80));
      } else if (event.action_type?.includes('task_complete')) {
        ToastManager.show('completion', 'Completed', truncate(event.description, 80));
      } else if (event.action_type?.startsWith('capability_gate_')) {
        const decision = event.action_data?.decision || "Evaluated";
        const msg = truncate(event.description, 80);
        ToastManager.show('info', `Gate ${decision}`, msg);
        if (typeof NativeNotify !== 'undefined') {
          NativeNotify.send(`Gate ${decision}`, msg);
        }
      } else if (event.action_type === 'session_delegated') {
        const data = event.action_data;
        if (data && data.child_session_id && !spawnedSessions.has(data.child_session_id)) {
          // If the parent session is the active one, trigger automatic spawn
          if (currentSession && event.session_id === currentSession.id) {
            spawnedSessions.add(data.child_session_id);
            SessionManager.spawnChild(data);
          }
        }
      }
    });
  }


  function renderADSFeed(events) {
    const feed = document.getElementById("ctx-ads-feed");
    feed.innerHTML = "";

    if (events.length === 0) {
      feed.innerHTML = '<li style="color:var(--text-muted)">No events</li>';
      return;
    }

    // Group events into "Intent Clusters" (rule-based for now)
    const clusters = [];
    let currentCluster = null;

    // Use reverse() because events passed in are already reversed (latest first)
    // We want to process them chronologically for clustering, then show latest cluster first
    const chronoEvents = [...events].reverse();

    chronoEvents.forEach(event => {
      const ts = new Date(event.ts).getTime();
      const isNewCluster = !currentCluster || 
                           event.spec_ref !== currentCluster.spec_ref || 
                           (ts - currentCluster.lastTs) > 60000;

      if (isNewCluster) {
        currentCluster = {
          spec_ref: event.spec_ref,
          role: event.role,
          startTs: ts,
          lastTs: ts,
          events: [event],
          description: event.description
        };
        clusters.push(currentCluster);
      } else {
        currentCluster.events.push(event);
        currentCluster.lastTs = ts;
      }
    });

    // Render clusters (latest first)
    clusters.reverse().forEach(cluster => {
      const latestEvent = cluster.events[cluster.events.length - 1];
      if (clusters.indexOf(cluster) === 0) handleADSFeedback(latestEvent);

      const successes = cluster.events.filter(e => e.authorized).length;
      const denied = cluster.events.filter(e => !e.authorized).length;
      
      const node = document.createElement("div");
      const statusClass = denied > 0 ? "denied" : "success";
      node.className = `timeline-node ${statusClass}`;
      
      const time = new Date(cluster.lastTs).toLocaleTimeString("en-US", { hour12: false, minute: "2-digit", second: "2-digit" });
      
      // Check for exit codes in cluster events
      let exitBadge = "";
      cluster.events.forEach(e => {
        if (e.execution_result && e.execution_result.exit_code !== undefined) {
          const code = e.execution_result.exit_code;
          const badgeClass = code === 0 ? "exit-0" : "exit-err";
          exitBadge += `<span class="exit-badge ${badgeClass}">${code}</span>`;
        }
      });

      // Jurisdiction visual feedback (SPEC-041 Phase 3)
      const firstPath = cluster.events.find(e => e.params?.file || e.params?.path)?.params?.file;
      let tierBadge = "";
      if (firstPath && typeof JurisdictionUI !== "undefined") {
        const tier = JurisdictionUI.getPathTierSync(firstPath, cluster.role);
        tierBadge = JurisdictionUI.renderTierBadge(tier);
        node.classList.add(JurisdictionUI.getTierClass(tier));
      }

      node.innerHTML = `
        <div class="node-header">
          <span class="node-title">${tierBadge}${cluster.spec_ref || "UNSPECIFIED"}</span>
          <span class="node-time">${time}</span>
        </div>
        <div class="node-summary">${truncate(cluster.description, 80)}${exitBadge}</div>
        <div class="node-stats">
          <span style="color:var(--accent-green)">● ${successes}</span>
          ${denied > 0 ? `<span style="color:var(--accent-red)">● ${denied}</span>` : ""}
          <span style="opacity:0.5">${cluster.events.length} events</span>
        </div>
      `;
      
      feed.appendChild(node);
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

  async function fetchDTCPStatus() {
    try {
      const projectName = currentSession?.project;
      const url = projectName 
        ? `${getCenterUrl()}/api/dtcp/status?project=${encodeURIComponent(projectName)}`
        : `${getCenterUrl()}/api/dtcp/status`;
      const res = await fetch(url);
      if (!res.ok) {
        document.getElementById('status-dtcp').innerHTML =
          '<span class="status-dot dot-grey"></span> DTCP: offline';
        return;
      }
      const data = await res.json();
      document.getElementById('status-dtcp').innerHTML =
        `<span class="status-dot dot-green"></span> DTCP: ${data.status || 'active'}`;
    } catch {
      document.getElementById('status-dtcp').innerHTML =
        '<span class="status-dot dot-grey"></span> DTCP: --';
    }
  }

  function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
  }

  // Listen for file watcher events from Rust backend
  function initWatchers() {
    // SPEC-034: Role filter toggle
    const filterBtn = document.getElementById('btn-show-all-roles');
    if (filterBtn) {
      filterBtn.addEventListener('click', () => toggleFilter());
    }

    if (window.__TAURI__) {
      window.__TAURI__.event.listen('ads-updated', () => {
        if (currentSession) {
          fetchADSEvents(currentSession);
          fetchRoleRequests(currentSession);
          fetchDelegations();
          fetchCapabilityContext(currentSession);
        }
        fetchSessionTree(); // SPEC-042: refresh swarm tree on any ADS update
      });

      window.__TAURI__.event.listen('capabilities-updated', () => {
        if (currentSession) fetchCapabilityContext(currentSession);
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
            fetchDTCPStatus();
            fetchSessionTree();
          }
        }, 10000);
      }
    
      async function completeTask(taskId, btn) {
        if (!currentSession?.role) {
          ToastManager.show('denial', 'Error', 'No active session role');
          return;
        }
        
        const evidence = prompt(`Mark task ${taskId} as complete?\nEvidence:`);
        if (evidence === null) return;
    
        if (btn) {
          btn.classList.add('loading');
          btn.disabled = true;
        }
    
        try {
          const res = await fetch(`${getCenterUrl()}/api/tasks/${taskId}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              status: 'completed',
              role: currentSession.role,
              agent: currentSession.agent || 'GEMINI',
              evidence: evidence || 'Completed via Operator Console'
            })
          });
    
          if (res.ok) {
            ToastManager.show('completion', 'Task Completed', taskId);
            await fetchTaskData(currentSession);
          } else {
            const data = await res.json();
            ToastManager.show('denial', 'Failed', data.error || 'Unknown error');
          }
        } catch (e) {
          ToastManager.show('denial', 'Error', 'ADT Center unreachable');
        } finally {
          if (btn) {
            btn.classList.remove('loading');
            btn.disabled = false;
          }
        }
      }
    
      async function completeRequest(reqId, btn) {
        if (!currentSession?.role) {
          ToastManager.show('denial', 'Error', 'No active session role');
          return;
        }

        if (!confirm(`Mark request ${reqId} as COMPLETED?`)) return;

        if (btn) {
          btn.classList.add('loading');
          btn.disabled = true;
        }

        try {
          const res = await fetch(`${getCenterUrl()}/api/governance/requests/${reqId}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              status: 'COMPLETED',
              role: currentSession.role,
              agent: currentSession.agent || 'GEMINI'
            })
          });

          if (res.ok) {
            ToastManager.show('completion', 'Request Completed', reqId);
            await fetchRequests();
          } else {
            const data = await res.json();
            ToastManager.show('denial', 'Failed', data.error || 'Unknown error');
          }
        } catch (e) {
          ToastManager.show('denial', 'Error', 'ADT Center unreachable');
        } finally {
          if (btn) {
            btn.classList.remove('loading');
            btn.disabled = false;
          }
        }
      }

      async function fetchSessionTree() {
        try {
          const getCenterUrl = () => localStorage.getItem("adt_center_url") || "http://localhost:5001";
          const res = await fetch(`${getCenterUrl()}/api/governance/sessions/tree`);
          if (!res.ok) return;
          const data = await res.json();
          renderSessionTree(data.sessions || []);
          // SPEC-042: Auto-spawn PTYs for children that appear in tree but don't have a local session
          const allSessionIds = new Set((window.SessionManager ? window.SessionManager.getAll() : []).map(s => s.id));
          function walkAndSpawn(nodes) {
            for (const node of (nodes || [])) {
              if (node.session_id && !spawnedSessions.has(node.session_id) && !allSessionIds.has(node.session_id)) {
                spawnedSessions.add(node.session_id);
                if (window.SessionManager && window.SessionManager.spawnChild) {
                  window.SessionManager.spawnChild({
                    child_role: node.role,
                    child_harness: node.agent || 'claude',
                    task_id: node.task_id || '',
                    spec_ref: node.spec_ref || 'SPEC-042',
                    child_session_id: node.session_id,
                    skip_permissions: true,
                    context_hint: node.context_hint || null
                  }).catch(e => console.warn('[SWARM] Auto-spawn failed:', e));
                }
              }
              walkAndSpawn(node.children);
            }
          }
          walkAndSpawn(data.sessions || []);
        } catch (e) {
          console.error("fetchSessionTree error:", e);
        }
      }

      function renderSessionTree(tree) {
        const container = document.getElementById("ctx-sessions-tree");
        if (!container) return;

        if (!tree || tree.length === 0) {
          container.innerHTML = "<div class=\"ctx-empty\">No active swarm</div>";
          return;
        }

        const renderNode = (node) => {
          const isClaude = (node.agent || "").toLowerCase().includes("claude");
          const isGemini = (node.agent || "").toLowerCase().includes("gemini");
          const badgeClass = isClaude ? "badge-claude" : (isGemini ? "badge-gemini" : "");
          const badgeChar = isClaude ? "C" : (isGemini ? "G" : "?");
          const isActive = currentSession && node.session_id === currentSession.id;
          const activeClass = isActive ? "active-tab" : "";

          const roleParts = (node.role || "??").split("_");
          const roleAbbr = roleParts.map(word => word[0]).join("").toUpperCase();

          const status = node.status || "active";
          const pulseClass = status === "spawning" ? "pulse-spawning"
                           : status === "completed" ? "pulse-done"
                           : "pulse-active";
          const isForge = !!(node.context_hint?.includes("forge_mode") || node.spec_ref === "SPEC-043");
          const hasChildren = node.children && node.children.length > 0;

          let html = `<div class="session-node">
              <div class="session-node-content ${activeClass}" onclick="SessionManager.switchTo('${node.session_id}')">
                <span class="${pulseClass}"></span>
                <span class="harness-badge ${badgeClass}">${badgeChar}</span>
                <span class="session-role-abbr" title="${node.role}">${roleAbbr}</span>
                ${node.task_id ? `<span class="session-task-id">${node.task_id}</span>` : ""}
                ${isForge ? '<span class="forge-badge">FORGE</span>' : ""}
                ${node.spec_ref ? `<span class="session-spec-ref">${node.spec_ref.replace("SPEC-", "")}</span>` : ""}
              </div>
              ${hasChildren ? `<div class="swarm-causal-indicator" title="${node.children.length} child session${node.children.length > 1 ? "s" : ""}">&#8627; ${node.children.length}</div>` : ""}`;

          if (hasChildren) {
            html += `<div class="session-children">`;
            node.children.forEach(child => {
              html += renderNode(child);
            });
            html += `</div>`;
          }

          html += `</div>`;
          return html;
        };

        container.innerHTML = tree.map(node => renderNode(node)).join("");
      }

      return { 
        update, initWatchers, updateUptime, toggleFilter, 
        completeTask, completeRequest, prioritizeTask, 
        openCapInPanel, openInlineGateEval, cancelInlineGate, submitInlineGate, 
        fetchSessionTree, renderSessionTree 
      };
      })();

    
    // Global alias for onclick handlers
    window.ContextPanel = ContextPanel;
    