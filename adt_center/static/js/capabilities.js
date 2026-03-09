/**
 * ADT Capabilities UI (SPEC-040)
 * Full Capability Governance: Pipeline, Events, Gates, Traceability, Wizards.
 */

document.addEventListener("DOMContentLoaded", () => {
    // ─── State ───────────────────────────────────────────────
    const state = {
        intents: [],
        events: [],
        activeIntent: null,
        activeGates: [],
        project: new URLSearchParams(window.location.search).get("project"),
        wizardStep: 1,
        wizardTotalSteps: 8,
        eventWizardStep: 1,
        eventWizardTotalSteps: 5,
        tagData: {}   // stores tag arrays keyed by container id
    };

    // ─── Status Mapping ──────────────────────────────────────
    // Map legacy/non-standard statuses to valid lifecycle columns
    const STATUS_MAP = {
        "Intent Defined":               "Intent Defined",
        "Event Under Review":           "Event Under Review",
        "Approved for Transformation":  "Approved for Transformation",
        "In Transformation":            "In Transformation",
        "Operational":                  "Operational",
        "Value Assessed":               "Value Assessed",
        "Rejected":                     "Rejected",
        "Cancelled":                    "Rejected",
        "Halted":                       "Rejected",
        // Legacy statuses
        "Active":                       "In Transformation",
        "active":                       "In Transformation",
        "Pending":                      "Intent Defined",
        "pending":                      "Intent Defined",
        "Draft":                        "Intent Defined",
        "":                             "Intent Defined"
    };

    function resolveStatus(raw) {
        return STATUS_MAP[raw] || STATUS_MAP[raw?.trim()] || "Intent Defined";
    }

    // ─── Constants ───────────────────────────────────────────
    const TYPE_COLORS = {
        "Innovation":      "badge-innovation",
        "Enhancement":     "badge-enhancement",
        "Maintenance":     "badge-maintenance",
        "Risk Mitigation": "badge-risk-mitigation",
        "Regulatory":      "badge-regulatory",
        "Operational":     "badge-operational"
    };

    const VALUE_ICONS = {
        "Revenue":             "bi-currency-dollar",
        "Efficiency":          "bi-gear-wide-connected",
        "Risk Reduction":      "bi-shield-check",
        "Customer Experience": "bi-heart",
        "Sustainability":     "bi-tree"
    };

    const EVENT_TYPE_ICONS = {
        "Innovation":      "bi-lightbulb",
        "Customer Signal": "bi-people",
        "Workforce":       "bi-eye",
        "Market":          "bi-graph-up-arrow",
        "Technology":      "bi-cpu",
        "Risk":            "bi-exclamation-triangle",
        "Regulatory":      "bi-file-earmark-ruled",
        "Ecosystem":       "bi-arrows-fullscreen",
        "Strategic":       "bi-flag",
        "Operational":     "bi-clipboard-data"
    };

    const MATURITY_LABELS = ["", "Initial", "Developing", "Defined", "Managed", "Optimized"];

    const GATE_NAMES = [
        "Validation & Classification",
        "Concept Development",
        "Strategic Feasibility",
        "Governance & Quality Review",
        "Portfolio Planning",
        "Investment Decision",
        "Transformation Initiation"
    ];

    // Gate-specific fields per SPEC-038A
    const GATE_FIELDS = {
        1: [
            { name: "classification", label: "Classification", type: "select", options: ["Innovation", "Enhancement", "Maintenance", "Risk Mitigation", "Regulatory", "Operational"] },
            { name: "priority", label: "Priority", type: "select", options: ["Low", "Medium", "High", "Critical"] },
            { name: "validator", label: "Validator", type: "text" }
        ],
        2: [
            { name: "concept_id", label: "Concept ID", type: "text" },
            { name: "prototype_required", label: "Prototype Required", type: "select", options: ["Yes", "No"] },
            { name: "architecture_concept", label: "Architecture Concept", type: "textarea" },
            { name: "concept_owner", label: "Concept Owner", type: "text" }
        ],
        3: [
            { name: "financial_feasibility", label: "Financial Feasibility", type: "select", options: ["Positive", "Marginal", "Negative"] },
            { name: "operational_feasibility", label: "Operational Feasibility", type: "select", options: ["Feasible", "Requires Change", "Not Feasible"] },
            { name: "technical_feasibility", label: "Technical Feasibility", type: "select", options: ["Feasible", "Complex", "Not Feasible"] },
            { name: "strategic_alignment", label: "Strategic Alignment", type: "select", options: ["High", "Moderate", "Low"] }
        ],
        4: [
            { name: "architecture_review", label: "Architecture Review", type: "select", options: ["Approved", "Conditional", "Rejected"] },
            { name: "risk_rating", label: "Risk Rating", type: "select", options: ["Low", "Medium", "High", "Critical"] },
            { name: "compliance_status", label: "Compliance Status", type: "select", options: ["Compliant", "Review Required", "Non-Compliant"] },
            { name: "review_board", label: "Review Board", type: "text" }
        ],
        5: [
            { name: "portfolio_priority", label: "Portfolio Priority", type: "select", options: ["Low", "Medium", "High", "Strategic"] },
            { name: "portfolio_manager", label: "Portfolio Manager", type: "text" },
            { name: "estimated_resources", label: "Estimated Resources", type: "text" },
            { name: "target_delivery_window", label: "Target Delivery Window", type: "text" }
        ],
        6: [
            { name: "investment_decision", label: "Investment Decision", type: "select", options: ["Approved", "Deferred", "Rejected", "Further Investigation"] },
            { name: "investment_board", label: "Investment Board", type: "text" },
            { name: "decision_date", label: "Decision Date", type: "date" },
            { name: "approved_budget", label: "Approved Budget", type: "text" }
        ],
        7: [
            { name: "program_id", label: "Program ID", type: "text" },
            { name: "program_manager", label: "Program Manager", type: "text" },
            { name: "start_date", label: "Start Date", type: "date" },
            { name: "delivery_organisation", label: "Delivery Organisation", type: "text" }
        ]
    };

    // ─── Element References ──────────────────────────────────
    const $ = (id) => document.getElementById(id);
    const kanbanBoard    = $("kanban-board");
    const eventFeed      = $("event-feed-container");
    const gateContainer  = $("gate-visualizer-container");
    const traceView      = $("traceability-view");
    const formWizard     = $("form-intent-wizard");
    const formEventCap   = $("form-event-capture");

    // ─── API Helpers ─────────────────────────────────────────
    function apiUrl(path) {
        const q = state.project ? `?project=${encodeURIComponent(state.project)}` : "";
        return `/api/governance/capabilities${path}${q}`;
    }

    function apiUrlWithParams(path, params) {
        const p = new URLSearchParams(params);
        if (state.project) p.set("project", state.project);
        const qs = p.toString();
        return `/api/governance/capabilities${path}${qs ? "?" + qs : ""}`;
    }

    // ─── Data Loading ────────────────────────────────────────
    async function loadData() {
        try {
            const [intentsRes, eventsRes] = await Promise.all([
                fetch(apiUrl("/intents")),
                fetch(apiUrl("/events"))
            ]);

            if (intentsRes.ok) {
                const d = await intentsRes.json();
                state.intents = d.intents || [];
            }
            if (eventsRes.ok) {
                const d = await eventsRes.json();
                state.events = d.events || [];
            }

            renderPipeline();
            renderEventFeed();
            renderPortfolioStats();
        } catch (err) {
            console.error("Failed to load capabilities data:", err);
        }
    }

    // ─── Portfolio Summary ───────────────────────────────────
    function renderPortfolioStats() {
        const total = state.intents.length;
        const active = state.intents.filter(i => resolveStatus(i.status) === "In Transformation").length;
        const assessed = state.intents.filter(i => resolveStatus(i.status) === "Value Assessed").length;

        $("stat-total").textContent = total;
        $("stat-active").textContent = active;
        $("stat-assessed").textContent = assessed;
        $("stat-events").textContent = state.events.length;

        // Avg gate progress
        if (total > 0) {
            const totalGates = state.intents.reduce((sum, i) => sum + (parseInt(i.gate) || 1), 0);
            const avg = (totalGates / total).toFixed(1);
            $("stat-avg-gate").textContent = `${avg}/7`;
        } else {
            $("stat-avg-gate").textContent = "-";
        }
    }

    // ─── Strategic Pipeline (Kanban) ─────────────────────────
    function renderPipeline() {
        if (!kanbanBoard) return;

        // Clear columns
        const columns = kanbanBoard.querySelectorAll(".kanban-col");
        columns.forEach(col => {
            col.querySelector(".kanban-cards").innerHTML = "";
            col.querySelector(".count-badge").textContent = "0";
        });

        state.intents.forEach(intent => {
            const status = resolveStatus(intent.status);
            const col = kanbanBoard.querySelector(`.kanban-col[data-status="${status}"]`);
            if (!col) return;

            const container = col.querySelector(".kanban-cards");
            container.appendChild(createIntentCard(intent));

            const badge = col.querySelector(".count-badge");
            badge.textContent = parseInt(badge.textContent) + 1;
        });
    }

    function createIntentCard(intent) {
        const div = document.createElement("div");
        const riskLevel = (intent.risk_level || intent.risk?.level || "").toLowerCase();
        div.className = `intent-card${riskLevel === "high" ? " risk-high" : ""}${riskLevel === "critical" ? " risk-critical" : ""}`;
        div.onclick = () => selectIntent(intent.intent_id);

        const typeClass = TYPE_COLORS[intent.type] || "badge-enhancement";
        const currentM = parseInt(intent.current_maturity) || 1;
        const targetM = parseInt(intent.target_maturity) || 3;
        const fillPct = (currentM / 5) * 100;
        const targetPct = (targetM / 5) * 100;
        const gateNum = parseInt(intent.gate) || 1;
        const valueIcon = VALUE_ICONS[intent.value_category] || "";
        const owner = intent.owner || intent.org_context?.owner || "";

        div.innerHTML = `
            <div class="d-flex justify-content-between align-items-start mb-1">
                <span class="card-id">${intent.intent_id}</span>
                <span class="badge ${typeClass}" style="font-size: 0.6rem;">${intent.type || "Intent"}</span>
            </div>
            <div class="card-title">${escapeHtml(intent.title)}</div>
            <div class="maturity-bar-container">
                <div class="maturity-bar-fill" style="width: ${fillPct}%"></div>
                <div class="maturity-bar-target" style="left: ${targetPct}%"></div>
            </div>
            <div class="d-flex justify-content-between align-items-center mt-1">
                <div class="d-flex align-items-center gap-2">
                    <div class="gate-dots">
                        ${[1,2,3,4,5,6,7].map(g => {
                            let cls = "";
                            if (g < gateNum) cls = "completed";
                            else if (g === gateNum) cls = "current";
                            return `<div class="gate-dot ${cls}"></div>`;
                        }).join("")}
                    </div>
                    <span class="small text-adt-muted" style="font-size: 0.6rem;">G${gateNum}/7</span>
                </div>
                <div class="d-flex align-items-center gap-1">
                    ${valueIcon ? `<i class="bi ${valueIcon} value-icon"></i>` : ""}
                    ${riskLevel ? `<span class="risk-dot ${riskLevel}"></span>` : ""}
                </div>
            </div>
            ${owner ? `<div class="small text-adt-muted mt-1" style="font-size: 0.6rem;"><i class="bi bi-person me-1"></i>${escapeHtml(owner)}</div>` : ""}
        `;
        return div;
    }

    // ─── Event Feed ──────────────────────────────────────────
    function renderEventFeed() {
        if (!eventFeed) return;

        if (state.events.length === 0) {
            eventFeed.innerHTML = `<div class="text-center py-4 text-adt-muted small">No triggering events captured yet.<br><button class="btn btn-sm btn-adt-secondary mt-2" onclick="document.getElementById('btn-capture-event').click()"><i class="bi bi-plus me-1"></i>Capture First Event</button></div>`;
            return;
        }

        const sorted = [...state.events].sort((a, b) => new Date(b.ts) - new Date(a.ts));

        eventFeed.innerHTML = sorted.map(event => {
            const icon = EVENT_TYPE_ICONS[event.type || event.event_type] || "bi-lightning-charge";
            const priority = (event.priority || "medium").toLowerCase();
            const timeAgo = formatTimeAgo(event.ts);

            return `
                <div class="event-timeline-item priority-${priority}" style="cursor: pointer;" onclick="window._selectEventIntent('${event.intent_id || ""}', '${event.event_id}')">
                    <div class="event-timeline-icon">
                        <i class="bi ${icon}"></i>
                    </div>
                    <div class="ps-1">
                        <div class="d-flex justify-content-between align-items-start">
                            <span class="small text-adt-accent" style="font-size: 0.7rem;">${event.event_id}</span>
                            <div class="d-flex align-items-center gap-1">
                                <span class="priority-badge ${priority}">${priority}</span>
                                <span class="small text-adt-muted" style="font-size: 0.6rem;">${timeAgo}</span>
                            </div>
                        </div>
                        <div class="small mt-1" style="font-size: 0.8rem;">${escapeHtml(event.description || "")}</div>
                        ${event.intent_id ? `<span class="badge bg-dark border border-adt mt-1" style="font-size: 0.6rem; cursor: pointer;" onclick="event.stopPropagation(); window._selectIntentById('${event.intent_id}')">${event.intent_id}</span>` : `<span class="small text-adt-muted" style="font-size: 0.6rem;">No linked intent</span>`}
                    </div>
                </div>
            `;
        }).join("");
    }

    // ─── Select Intent ───────────────────────────────────────
    async function selectIntent(id) {
        state.activeIntent = state.intents.find(i => i.intent_id === id);
        if (!state.activeIntent) return;

        // Load gates
        try {
            const res = await fetch(apiUrl(`/intents/${id}/gates`));
            if (res.ok) {
                const data = await res.json();
                state.activeGates = data.gates || [];
                state.activeIntent._currentGate = data.current_gate || 1;
            }
        } catch (e) {
            state.activeGates = [];
        }

        renderGateVisualizer();
        renderTraceView(id);
        showIntentDrawer();
    }

    window._selectIntentById = (id) => selectIntent(id);
    window._selectEventIntent = (intentId, eventId) => {
        if (intentId) selectIntent(intentId);
    };

    // ─── Stage-Gate Visualiser ───────────────────────────────
    function renderGateVisualizer() {
        if (!gateContainer || !state.activeIntent) return;

        const currentGate = state.activeIntent._currentGate || parseInt(state.activeIntent.gate) || 1;
        const gatesMap = {};
        state.activeGates.forEach(g => { gatesMap[g.gate_number] = g; });

        gateContainer.innerHTML = `
            <div class="px-2 py-1 mb-2 d-flex justify-content-between align-items-center">
                <span class="small fw-bold">${escapeHtml(state.activeIntent.title)}</span>
                <span class="badge bg-dark border border-adt" style="font-size: 0.6rem;">${state.activeIntent.intent_id}</span>
            </div>
            <div class="gate-stepper px-2">
                ${GATE_NAMES.map((name, i) => {
                    const num = i + 1;
                    const gate = gatesMap[num];
                    let stateClass = "locked";
                    let icon = num;
                    let detail = "";

                    if (gate) {
                        if (gate.decision === "Proceed") {
                            stateClass = "completed";
                            icon = '<i class="bi bi-check-lg"></i>';
                            detail = `<div class="gate-step-detail text-adt-green">${escapeHtml(gate.actual_outcome || "Passed")}</div>`;
                        } else if (gate.decision === "Refine") {
                            stateClass = "refined";
                            icon = '<i class="bi bi-arrow-repeat"></i>';
                            detail = `<div class="gate-step-detail text-adt-amber">${escapeHtml(gate.actual_outcome || "Refinement needed")}</div>`;
                        } else if (gate.decision === "Halt") {
                            stateClass = "halted";
                            icon = '<i class="bi bi-x-lg"></i>';
                            detail = `<div class="gate-step-detail text-adt-red">${escapeHtml(gate.actual_outcome || "Halted")}</div>`;
                        }
                    } else if (num === currentGate) {
                        stateClass = "current";
                    }

                    const evalBtn = (num === currentGate && !gate)
                        ? `<button class="btn btn-sm btn-adt-primary mt-1" style="font-size: 0.7rem; padding: 0.2rem 0.5rem;" onclick="window._openGateModal(${num})"><i class="bi bi-pencil-square me-1"></i>Evaluate Gate</button>`
                        : "";

                    return `
                        <div class="gate-step ${stateClass}">
                            <div class="gate-step-icon">${icon}</div>
                            <div class="gate-step-content">
                                <div class="small fw-bold">${name}</div>
                                ${detail}
                                ${evalBtn}
                            </div>
                        </div>
                    `;
                }).join("")}
            </div>
        `;
    }

    // ─── Gate Evaluation Modal ───────────────────────────────
    window._openGateModal = (gateNum) => {
        if (!state.activeIntent) return;

        const fields = GATE_FIELDS[gateNum] || [];

        const fieldsHtml = fields.map(f => {
            let control = "";
            if (f.type === "select") {
                control = `<select class="form-select form-control-adt" name="${f.name}">
                    ${f.options.map(o => `<option value="${o}">${o}</option>`).join("")}
                </select>`;
            } else if (f.type === "textarea") {
                control = `<textarea class="form-control form-control-adt" name="${f.name}" rows="2"></textarea>`;
            } else if (f.type === "date") {
                control = `<input type="date" class="form-control form-control-adt" name="${f.name}">`;
            } else {
                control = `<input type="text" class="form-control form-control-adt" name="${f.name}">`;
            }
            return `<div class="gate-field-group"><label class="form-label-adt">${f.label}</label>${control}</div>`;
        }).join("");

        const modalHtml = `
            <div class="modal fade modal-adt" id="modal-gate-eval" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header border-adt">
                            <h5 class="modal-title" style="font-size: 1rem;">
                                <i class="bi bi-funnel-fill text-adt-accent me-2"></i>
                                Gate ${gateNum}: ${GATE_NAMES[gateNum - 1]}
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3 p-2 rounded" style="background-color: var(--adt-bg-secondary); font-size: 0.8rem;">
                                <strong>${escapeHtml(state.activeIntent.title)}</strong>
                                <span class="text-adt-muted ms-2">${state.activeIntent.intent_id}</span>
                            </div>
                            <form id="form-gate-eval">
                                ${fieldsHtml}
                                <hr style="border-color: var(--adt-border);">
                                <div class="gate-field-group">
                                    <label class="form-label-adt">Desired Outcome</label>
                                    <input type="text" class="form-control form-control-adt" name="desired_outcome" placeholder="What should this gate confirm?">
                                </div>
                                <div class="gate-field-group">
                                    <label class="form-label-adt">Actual Outcome <span class="text-adt-red">*</span></label>
                                    <textarea class="form-control form-control-adt" name="actual_outcome" rows="2" required placeholder="Evidence or rationale for this decision..."></textarea>
                                </div>
                                <hr style="border-color: var(--adt-border);">
                                <div class="gate-field-group">
                                    <label class="form-label-adt">Decision <span class="text-adt-red">*</span></label>
                                    <div class="d-flex gap-3">
                                        <div class="form-check">
                                            <input class="form-check-input" type="radio" name="decision" value="Proceed" checked>
                                            <label class="form-check-label small text-adt-green">Proceed</label>
                                        </div>
                                        <div class="form-check">
                                            <input class="form-check-input" type="radio" name="decision" value="Refine">
                                            <label class="form-check-label small text-adt-amber">Refine</label>
                                        </div>
                                        <div class="form-check">
                                            <input class="form-check-input" type="radio" name="decision" value="Halt">
                                            <label class="form-check-label small text-adt-red">Halt</label>
                                        </div>
                                    </div>
                                </div>
                            </form>
                            <div class="small text-adt-muted mt-2" style="font-size: 0.7rem;">
                                <i class="bi bi-shield-lock me-1"></i>This action will be permanently recorded in the ADS audit trail.
                            </div>
                        </div>
                        <div class="modal-footer border-adt">
                            <button type="button" class="btn btn-sm btn-adt-secondary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-sm btn-adt-primary" id="btn-submit-gate">
                                <i class="bi bi-check-lg me-1"></i>Submit Gate Evaluation
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove old modal
        const old = $("modal-gate-eval");
        if (old) old.remove();

        document.body.insertAdjacentHTML("beforeend", modalHtml);
        const modal = new bootstrap.Modal($("modal-gate-eval"));
        modal.show();

        $("btn-submit-gate").onclick = async () => {
            const form = $("form-gate-eval");
            if (!form.checkValidity()) { form.reportValidity(); return; }

            const formData = new FormData(form);
            const payload = Object.fromEntries(formData.entries());
            payload.gate_number = gateNum;
            payload.evaluator = "HUMAN";
            payload.role = "Operator";
            payload.agent = "HUMAN";
            if (state.project) payload.project = state.project;

            // Collect gate-specific fields into decision_data
            const decisionData = {};
            (GATE_FIELDS[gateNum] || []).forEach(f => {
                if (payload[f.name] !== undefined && payload[f.name] !== "") {
                    decisionData[f.name] = payload[f.name];
                    delete payload[f.name];
                }
            });
            if (Object.keys(decisionData).length > 0) {
                payload.decision_data = decisionData;
            }

            try {
                const res = await fetch(`/api/governance/capabilities/intents/${state.activeIntent.intent_id}/gates`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });

                if (res.ok) {
                    modal.hide();
                    await loadData();
                    selectIntent(state.activeIntent.intent_id);
                } else {
                    const err = await res.json();
                    alert(`Error: ${err.error || "Gate evaluation failed"}`);
                }
            } catch (err) {
                console.error("Gate submission error:", err);
                alert("Network error submitting gate evaluation.");
            }
        };
    };

    // ─── Traceability Explorer ───────────────────────────────
    async function renderTraceView(id) {
        if (!traceView) return;
        traceView.innerHTML = `<div class="text-center py-4"><div class="spinner-border spinner-border-sm text-adt-accent"></div></div>`;

        // Show export button
        const exportBtn = $("btn-export-trace");
        if (exportBtn) exportBtn.classList.remove("d-none");

        try {
            const res = await fetch(apiUrl(`/trace/${id}`));
            if (!res.ok) throw new Error("Trace unavailable");
            const trace = await res.json();

            let html = `<div class="px-2 py-1 small">`;

            // Intent
            html += `<div class="mb-2"><div class="text-adt-muted fw-bold mb-1" style="font-size: 0.65rem; text-transform: uppercase;">Intent</div>
                <div class="trace-node" style="border-left: 3px solid var(--adt-accent);">
                    <strong>${escapeHtml(trace.intent?.title || id)}</strong>
                    <span class="text-adt-muted ms-1" style="font-size: 0.65rem;">${trace.intent?.intent_id || id}</span>
                </div></div>`;

            // Gate chain
            const gateNum = state.activeIntent?._currentGate || parseInt(state.activeIntent?.gate) || 1;
            html += `<div class="mb-2"><div class="text-adt-muted fw-bold mb-1" style="font-size: 0.65rem; text-transform: uppercase;">Gate Chain</div>
                <div class="d-flex gap-1 mb-1">
                    ${[1,2,3,4,5,6,7].map(g => {
                        let bg = "var(--adt-border)";
                        if (g < gateNum) bg = "var(--adt-green)";
                        else if (g === gateNum) bg = "var(--adt-accent)";
                        return `<div style="width: 24px; height: 6px; border-radius: 3px; background-color: ${bg};"></div>`;
                    }).join("")}
                    <span class="small text-adt-muted ms-1" style="font-size: 0.6rem;">Gate ${gateNum}/7</span>
                </div></div>`;

            // Trigger events
            const trigEvents = trace.triggering_events || [];
            html += `<div class="mb-2"><div class="text-adt-muted fw-bold mb-1" style="font-size: 0.65rem; text-transform: uppercase;">Triggering Events (${trigEvents.length})</div>`;
            if (trigEvents.length > 0) {
                trigEvents.forEach(e => {
                    html += `<div class="trace-node" style="border-left: 3px solid var(--adt-amber);">
                        <span style="font-size: 0.65rem;" class="text-adt-muted">${e.event_id}</span>: ${escapeHtml(e.description || "")}
                    </div>`;
                });
            } else {
                html += `<div class="small text-adt-muted">No events linked</div>`;
            }
            html += `</div>`;

            // Linked specs
            const specs = trace.specs || [];
            html += `<div class="mb-2"><div class="text-adt-muted fw-bold mb-1" style="font-size: 0.65rem; text-transform: uppercase;">Linked Specs (${specs.length})</div>`;
            specs.forEach(s => {
                const specId = typeof s === "string" ? s : s.id;
                html += `<div class="trace-node" style="border-left: 3px solid var(--adt-purple);">${escapeHtml(specId)}</div>`;
            });
            if (specs.length === 0) html += `<div class="small text-adt-muted">No specs linked</div>`;
            html += `</div>`;

            // Tasks
            const tasks = trace.tasks || [];
            html += `<div class="mb-2"><div class="text-adt-muted fw-bold mb-1" style="font-size: 0.65rem; text-transform: uppercase;">Tasks (${tasks.length})</div>`;
            tasks.forEach(t => {
                const isDone = t.status === "completed";
                html += `<div class="trace-node ${isDone ? "text-adt-green" : ""}" style="border-left: 3px solid ${isDone ? "var(--adt-green)" : "var(--adt-border)"};">
                    ${isDone ? '<i class="bi bi-check-circle me-1"></i>' : '<i class="bi bi-circle me-1"></i>'}
                    <span style="font-size: 0.65rem;" class="text-adt-muted">${t.id}</span>: ${escapeHtml(t.title || "")}
                </div>`;
            });
            if (tasks.length === 0) html += `<div class="small text-adt-muted">No tasks linked</div>`;
            html += `</div>`;

            // ADS audit trail
            const adsEvents = trace.ads_events || [];
            if (adsEvents.length > 0) {
                html += `<div class="mb-2"><div class="text-adt-muted fw-bold mb-1" style="font-size: 0.65rem; text-transform: uppercase;">ADS Trail (last ${Math.min(adsEvents.length, 10)})</div>`;
                adsEvents.slice(0, 10).forEach(e => {
                    html += `<div class="trace-node" style="font-size: 0.7rem; border-left: 3px solid var(--adt-border);">
                        <span class="text-adt-muted">${e.action_type || e.event_id}</span>
                    </div>`;
                });
                html += `</div>`;
            }

            html += `</div>`;
            traceView.innerHTML = html;

            // Wire export
            if (exportBtn) {
                exportBtn.onclick = () => {
                    const blob = new Blob([JSON.stringify(trace, null, 2)], { type: "application/json" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `trace_${id}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                };
            }
        } catch (err) {
            traceView.innerHTML = `<div class="text-center py-4 text-adt-muted small"><i class="bi bi-exclamation-triangle me-1"></i>Trace data unavailable for this intent.</div>`;
        }
    }

    // ─── Intent Detail Drawer ────────────────────────────────
    function showIntentDrawer() {
        const intent = state.activeIntent;
        if (!intent) return;

        const drawerTitle = $("drawer-title");
        const drawerBody = $("drawer-body");
        drawerTitle.textContent = `${intent.intent_id}: ${intent.title}`;

        const currentM = parseInt(intent.current_maturity) || 1;
        const targetM = parseInt(intent.target_maturity) || 3;
        const status = resolveStatus(intent.status);
        const org = intent.org_context || {};
        const tech = intent.technical_ecosystem || {};
        const risk = intent.risk || {};
        const val = intent.value || {};
        const gov = intent.governance || {};
        const cap = intent.capability || {};

        drawerBody.innerHTML = `
            <div class="accordion accordion-flush accordion-adt" id="drawerAccordion">
                <!-- 1. Intent Definition -->
                <div class="accordion-item">
                    <h2 class="accordion-header"><button class="accordion-button" data-bs-toggle="collapse" data-bs-target="#dsec1">1. Intent Definition</button></h2>
                    <div id="dsec1" class="accordion-collapse collapse show" data-bs-parent="#drawerAccordion">
                        <div class="accordion-body">
                            <p>${escapeHtml(intent.description || "No description")}</p>
                            <div class="mb-2"><strong>Status:</strong> <span class="badge" style="background-color: var(--adt-accent); font-size: 0.7rem;">${status}</span>
                                <span class="text-adt-muted ms-1" style="font-size: 0.7rem;">(raw: ${intent.status})</span>
                            </div>
                            <div class="mb-2"><strong>Type:</strong> ${intent.type || "Not set"}</div>
                            <div class="mb-2"><strong>Created:</strong> ${new Date(intent.ts).toLocaleString()}</div>
                            <div class="mt-2">
                                <label class="form-label-adt">Change Status</label>
                                <select class="form-select form-control-adt" id="drawer-status-select" style="font-size: 0.8rem;">
                                    ${["Intent Defined", "Event Under Review", "Approved for Transformation", "In Transformation", "Operational", "Value Assessed", "Rejected"].map(s =>
                                        `<option value="${s}" ${s === status ? "selected" : ""}>${s}</option>`
                                    ).join("")}
                                </select>
                                <button class="btn btn-sm btn-adt-primary mt-1" onclick="window._updateIntentStatus()">Update</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 2. Organisational Context -->
                <div class="accordion-item">
                    <h2 class="accordion-header"><button class="accordion-button collapsed" data-bs-toggle="collapse" data-bs-target="#dsec2">2. Organisational Context</button></h2>
                    <div id="dsec2" class="accordion-collapse collapse" data-bs-parent="#drawerAccordion">
                        <div class="accordion-body">
                            <div class="mb-2"><strong>Unit:</strong> ${escapeHtml(intent.org_unit || org.unit || "Not specified")}</div>
                            <div class="mb-2"><strong>Domain:</strong> ${escapeHtml(intent.business_domain || org.domain || "Not specified")}</div>
                            <div class="mb-2"><strong>Process:</strong> ${escapeHtml(org.process || "Not specified")}</div>
                            <div class="mb-2"><strong>Owner:</strong> ${escapeHtml(intent.owner || org.owner || "Unassigned")}</div>
                        </div>
                    </div>
                </div>

                <!-- 3. Capability Impact -->
                <div class="accordion-item">
                    <h2 class="accordion-header"><button class="accordion-button collapsed" data-bs-toggle="collapse" data-bs-target="#dsec3">3. Capability Impact</button></h2>
                    <div id="dsec3" class="accordion-collapse collapse" data-bs-parent="#drawerAccordion">
                        <div class="accordion-body">
                            <div class="mb-1"><strong>Capability:</strong> ${escapeHtml(intent.cap_name || cap.name || "General")}</div>
                            <div class="mb-1"><strong>Type:</strong> ${escapeHtml(cap.type || "Not set")}</div>
                            <div class="d-flex justify-content-between mb-1">
                                <span>Current: ${MATURITY_LABELS[currentM]}</span>
                                <span>Target: ${MATURITY_LABELS[targetM]}</span>
                            </div>
                            <div class="maturity-bar-container" style="height: 10px;">
                                <div class="maturity-bar-fill" style="width: ${(currentM/5)*100}%"></div>
                                <div class="maturity-bar-target" style="left: ${(targetM/5)*100}%; height: 18px; top: -4px;"></div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 4. Technical Ecosystem -->
                <div class="accordion-item">
                    <h2 class="accordion-header"><button class="accordion-button collapsed" data-bs-toggle="collapse" data-bs-target="#dsec4">4. Technical Ecosystem</button></h2>
                    <div id="dsec4" class="accordion-collapse collapse" data-bs-parent="#drawerAccordion">
                        <div class="accordion-body">
                            <div class="mb-2"><strong>Systems:</strong> ${renderTags(tech.systems)}</div>
                            <div class="mb-2"><strong>Data Sources:</strong> ${renderTags(tech.data_sources)}</div>
                            <div class="mb-2"><strong>Dependencies:</strong> ${renderTags(tech.dependencies)}</div>
                            <div class="mb-2"><strong>Platform:</strong> ${escapeHtml(tech.platform || "Not specified")}</div>
                        </div>
                    </div>
                </div>

                <!-- 5. Risk & Compliance -->
                <div class="accordion-item">
                    <h2 class="accordion-header"><button class="accordion-button collapsed" data-bs-toggle="collapse" data-bs-target="#dsec5">5. Risk & Compliance</button></h2>
                    <div id="dsec5" class="accordion-collapse collapse" data-bs-parent="#drawerAccordion">
                        <div class="accordion-body">
                            ${risk.level ? `<div class="mb-2 p-2 rounded" style="background-color: rgba(${risk.level === "Critical" || risk.level === "High" ? "248,81,73" : risk.level === "Medium" ? "210,153,34" : "63,185,80"}, 0.1);"><span class="risk-dot ${(risk.level || "").toLowerCase()} me-1"></span><strong>${risk.level}</strong></div>` : ""}
                            <div class="mb-2"><strong>Risk Level:</strong> ${escapeHtml(intent.risk_level || risk.level || "Not assessed")}</div>
                            <div class="mb-2"><strong>Regulatory:</strong> ${escapeHtml(risk.regulatory_impact || "None")}</div>
                            <div class="mb-2"><strong>Description:</strong> ${escapeHtml(risk.description || "Not provided")}</div>
                        </div>
                    </div>
                </div>

                <!-- 6. Value Realisation -->
                <div class="accordion-item">
                    <h2 class="accordion-header"><button class="accordion-button collapsed" data-bs-toggle="collapse" data-bs-target="#dsec6">6. Value Realisation</button></h2>
                    <div id="dsec6" class="accordion-collapse collapse" data-bs-parent="#drawerAccordion">
                        <div class="accordion-body">
                            <div class="mb-2"><strong>Expected Benefit:</strong> ${escapeHtml(val.expected_benefit || intent.expected_benefit || "Not specified")}</div>
                            <div class="mb-2"><strong>Value Category:</strong> ${escapeHtml(intent.value_category || val.category || "Not set")}
                                ${VALUE_ICONS[intent.value_category] ? `<i class="bi ${VALUE_ICONS[intent.value_category]} ms-1"></i>` : ""}
                            </div>
                            <div class="mb-2"><strong>Success Metrics:</strong> ${escapeHtml(val.success_metrics || "Not defined")}</div>
                        </div>
                    </div>
                </div>

                <!-- 7. Governance & Accountability -->
                <div class="accordion-item">
                    <h2 class="accordion-header"><button class="accordion-button collapsed" data-bs-toggle="collapse" data-bs-target="#dsec7">7. Governance & Accountability</button></h2>
                    <div id="dsec7" class="accordion-collapse collapse" data-bs-parent="#drawerAccordion">
                        <div class="accordion-body">
                            <div class="mb-2"><strong>Reporter:</strong> ${escapeHtml(gov.reporter || intent.reporter || intent.role || "Unknown")}</div>
                            <div class="mb-2"><strong>Accountable Executive:</strong> ${escapeHtml(gov.accountable_executive || "Not assigned")}</div>
                            <div class="mb-2"><strong>Review Board:</strong> ${escapeHtml(gov.review_board || "Not assigned")}</div>
                        </div>
                    </div>
                </div>

                <!-- 8. Gate Progress -->
                <div class="accordion-item">
                    <h2 class="accordion-header"><button class="accordion-button collapsed" data-bs-toggle="collapse" data-bs-target="#dsec8">8. Gate Progress</button></h2>
                    <div id="dsec8" class="accordion-collapse collapse" data-bs-parent="#drawerAccordion">
                        <div class="accordion-body">
                            <div class="gate-dots mb-2">
                                ${[1,2,3,4,5,6,7].map(g => {
                                    const gate = state.activeGates.find(x => x.gate_number === g);
                                    let cls = "";
                                    if (gate?.decision === "Proceed") cls = "completed";
                                    else if (gate?.decision === "Refine") cls = "refined";
                                    else if (gate?.decision === "Halt") cls = "halted";
                                    else if (g === (intent._currentGate || 1)) cls = "current";
                                    return `<div class="gate-dot ${cls}" title="Gate ${g}: ${GATE_NAMES[g-1]}"></div>`;
                                }).join("")}
                                <span class="small text-adt-muted ms-2">Gate ${intent._currentGate || 1}/7</span>
                            </div>
                            ${(intent._currentGate && !state.activeGates.find(g => g.gate_number === intent._currentGate))
                                ? `<button class="btn btn-sm btn-adt-primary" onclick="window._openGateModal(${intent._currentGate})"><i class="bi bi-pencil-square me-1"></i>Evaluate Next Gate</button>`
                                : ""}
                        </div>
                    </div>
                </div>
            </div>

            <!-- Footer actions -->
            <div class="p-3 border-top border-adt d-flex gap-2">
                <button class="btn btn-sm btn-adt-secondary flex-fill" onclick="window._exportIntent()">
                    <i class="bi bi-download me-1"></i>Export JSON
                </button>
                <button class="btn btn-sm flex-fill" style="background-color: rgba(248,81,73,0.15); color: var(--adt-red); border: 1px solid var(--adt-red);" onclick="window._updateIntentStatusDirect('Rejected')">
                    <i class="bi bi-x-circle me-1"></i>Archive
                </button>
            </div>
        `;

        const drawer = new bootstrap.Offcanvas($("drawer-intent-detail"));
        drawer.show();
    }

    window._updateIntentStatus = async () => {
        const sel = $("drawer-status-select");
        if (!sel || !state.activeIntent) return;
        await updateIntentStatus(state.activeIntent.intent_id, sel.value);
    };

    window._updateIntentStatusDirect = async (newStatus) => {
        if (!state.activeIntent) return;
        if (!confirm(`Set status to "${newStatus}"?`)) return;
        await updateIntentStatus(state.activeIntent.intent_id, newStatus);
    };

    async function updateIntentStatus(id, newStatus) {
        try {
            const res = await fetch(`/api/governance/capabilities/intents/${id}/status`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ status: newStatus, role: "Operator", agent: "HUMAN" })
            });
            if (res.ok) {
                await loadData();
                selectIntent(id);
            } else {
                const err = await res.json();
                alert(`Error: ${err.error || "Status update failed"}`);
            }
        } catch (e) {
            alert("Network error updating status.");
        }
    }

    window._exportIntent = () => {
        if (!state.activeIntent) return;
        const blob = new Blob([JSON.stringify(state.activeIntent, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${state.activeIntent.intent_id}.json`;
        a.click();
        URL.revokeObjectURL(url);
    };

    // ─── Intent Wizard ───────────────────────────────────────
    function renderWizardIndicators(containerId, totalSteps, currentStep) {
        const container = $(containerId);
        if (!container) return;
        container.innerHTML = Array.from({ length: totalSteps }, (_, i) => {
            const n = i + 1;
            let cls = "";
            if (n < currentStep) cls = "done";
            else if (n === currentStep) cls = "active";
            return `<div class="wizard-dot ${cls}">${n < currentStep ? '<i class="bi bi-check"></i>' : n}</div>`;
        }).join("");
    }

    const WIZARD_STEP_NAMES = ["Intent Definition", "Organisational Context", "Capability Impact", "Technical Ecosystem", "Risk & Compliance", "Value Realisation", "Governance", "Review & Submit"];

    function updateWizard() {
        const steps = formWizard.querySelectorAll(".wizard-step");
        steps.forEach(s => s.classList.add("d-none"));
        const currentStep = formWizard.querySelector(`.wizard-step[data-step="${state.wizardStep}"]`);
        if (currentStep) currentStep.classList.remove("d-none");

        $("btn-wizard-prev").disabled = (state.wizardStep === 1);

        const nextBtn = $("btn-wizard-next");
        if (state.wizardStep === state.wizardTotalSteps) {
            nextBtn.innerHTML = '<i class="bi bi-check-lg me-1"></i>Define Intent';
            nextBtn.classList.remove("btn-adt-primary");
            nextBtn.classList.add("btn-adt-primary");
        } else {
            nextBtn.innerHTML = 'Next<i class="bi bi-arrow-right ms-1"></i>';
        }

        $("wizard-step-label").textContent = `Step ${state.wizardStep} of ${state.wizardTotalSteps}: ${WIZARD_STEP_NAMES[state.wizardStep - 1]}`;
        renderWizardIndicators("wizard-indicators", state.wizardTotalSteps, state.wizardStep);

        // Update maturity preview on step 3
        if (state.wizardStep === 3) updateMaturityPreview();

        // Build review summary on step 8
        if (state.wizardStep === 8) buildReviewSummary();
    }

    function updateMaturityPreview() {
        const currentSel = formWizard.querySelector('[name="current_maturity"]');
        const targetSel = formWizard.querySelector('[name="target_maturity"]');
        if (currentSel && targetSel) {
            const c = parseInt(currentSel.value) || 1;
            const t = parseInt(targetSel.value) || 5;
            const fill = $("wizard-maturity-fill");
            const target = $("wizard-maturity-target");
            const cLabel = $("wizard-maturity-current-label");
            const tLabel = $("wizard-maturity-target-label");
            if (fill) fill.style.width = `${(c/5)*100}%`;
            if (target) target.style.left = `${(t/5)*100}%`;
            if (cLabel) cLabel.textContent = MATURITY_LABELS[c];
            if (tLabel) tLabel.textContent = MATURITY_LABELS[t];
        }
    }

    function buildReviewSummary() {
        const fd = new FormData(formWizard);
        const data = Object.fromEntries(fd.entries());
        const summary = $("wizard-review-summary");
        if (!summary) return;

        summary.innerHTML = `
            <div class="p-2 mb-2 rounded" style="background-color: var(--adt-bg-secondary);">
                <div class="fw-bold text-adt-accent">${escapeHtml(data.title || "Untitled")}</div>
                <div class="text-adt-muted mt-1">${escapeHtml(data.description || "No description")}</div>
                <div class="mt-1"><span class="badge ${TYPE_COLORS[data.type] || "badge-enhancement"}" style="font-size: 0.65rem;">${data.type}</span></div>
            </div>
            <table class="table table-sm text-adt-text" style="font-size: 0.75rem;">
                <tbody>
                    ${data.org_unit ? `<tr><td class="text-adt-muted">Unit</td><td>${escapeHtml(data.org_unit)}</td></tr>` : ""}
                    ${data.business_domain ? `<tr><td class="text-adt-muted">Domain</td><td>${escapeHtml(data.business_domain)}</td></tr>` : ""}
                    ${data.owner ? `<tr><td class="text-adt-muted">Owner</td><td>${escapeHtml(data.owner)}</td></tr>` : ""}
                    ${data.cap_name ? `<tr><td class="text-adt-muted">Capability</td><td>${escapeHtml(data.cap_name)}</td></tr>` : ""}
                    <tr><td class="text-adt-muted">Maturity</td><td>${MATURITY_LABELS[data.current_maturity] || "?"} -> ${MATURITY_LABELS[data.target_maturity] || "?"}</td></tr>
                    ${data.risk_level ? `<tr><td class="text-adt-muted">Risk</td><td><span class="risk-dot ${data.risk_level.toLowerCase()} me-1"></span>${data.risk_level}</td></tr>` : ""}
                    ${data.value_category ? `<tr><td class="text-adt-muted">Value</td><td>${data.value_category}</td></tr>` : ""}
                    ${data.reporter ? `<tr><td class="text-adt-muted">Reporter</td><td>${escapeHtml(data.reporter)}</td></tr>` : ""}
                </tbody>
            </table>
        `;
    }

    $("btn-wizard-next").addEventListener("click", async () => {
        if (state.wizardStep < state.wizardTotalSteps) {
            // Validate step 1 required fields
            if (state.wizardStep === 1) {
                const title = formWizard.querySelector('[name="title"]');
                const desc = formWizard.querySelector('[name="description"]');
                if (!title.value.trim() || !desc.value.trim()) {
                    formWizard.reportValidity();
                    return;
                }
            }
            state.wizardStep++;
            updateWizard();
        } else {
            // Submit
            await submitNewIntent();
        }
    });

    $("btn-wizard-prev").addEventListener("click", () => {
        if (state.wizardStep > 1) {
            state.wizardStep--;
            updateWizard();
        }
    });

    async function submitNewIntent() {
        const fd = new FormData(formWizard);
        const data = Object.fromEntries(fd.entries());

        const payload = {
            title: data.title,
            type: data.type,
            description: data.description,
            role: "Operator",
            agent: "HUMAN"
        };

        // Organisational context
        if (data.org_unit || data.business_domain || data.process_impacted || data.owner) {
            payload.org_context = {
                unit: data.org_unit || "",
                domain: data.business_domain || "",
                process: data.process_impacted || "",
                owner: data.owner || ""
            };
            if (data.owner) payload.owner = data.owner;
        }

        // Capability
        if (data.cap_name || data.cap_type) {
            payload.capability = { name: data.cap_name || "", type: data.cap_type || "" };
            payload.cap_name = data.cap_name || "";
        }
        payload.current_maturity = data.current_maturity || "1";
        payload.target_maturity = data.target_maturity || "5";

        // Technical ecosystem
        const systems = state.tagData["tag-systems"] || [];
        const dataSources = state.tagData["tag-data-sources"] || [];
        const deps = state.tagData["tag-dependencies"] || [];
        if (systems.length || dataSources.length || deps.length || data.tech_platform) {
            payload.technical_ecosystem = {
                systems: systems,
                data_sources: dataSources,
                dependencies: deps,
                platform: data.tech_platform || ""
            };
        }

        // Risk
        if (data.risk_level || data.regulatory_impact || data.risk_description) {
            payload.risk = {
                level: data.risk_level || "Medium",
                regulatory_impact: data.regulatory_impact || "",
                description: data.risk_description || ""
            };
            payload.risk_level = data.risk_level || "Medium";
        }

        // Value
        if (data.expected_benefit || data.value_category || data.success_metrics) {
            payload.value = {
                expected_benefit: data.expected_benefit || "",
                category: data.value_category || "",
                success_metrics: data.success_metrics || ""
            };
            payload.value_category = data.value_category || "";
        }

        // Governance
        if (data.reporter || data.accountable_executive || data.review_board) {
            payload.governance = {
                reporter: data.reporter || "",
                accountable_executive: data.accountable_executive || "",
                review_board: data.review_board || ""
            };
        }

        if (state.project) payload.project = state.project;

        try {
            const res = await fetch("/api/governance/capabilities/intents", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                const result = await res.json();
                bootstrap.Modal.getInstance($("modal-intent-wizard"))?.hide();
                formWizard.reset();
                state.wizardStep = 1;
                clearAllTags();
                await loadData();
                // Select the new intent
                if (result.intent_id) selectIntent(result.intent_id);
            } else {
                const err = await res.json();
                alert(`Error: ${err.error || "Failed to create intent"}`);
            }
        } catch (err) {
            console.error("Intent creation error:", err);
            alert("Network error creating intent.");
        }
    }

    // ─── Event Capture Wizard ────────────────────────────────
    const EVENT_STEP_NAMES = ["Event Details", "Organisational Context", "Technical Ecosystem", "Link to Intent", "Review & Submit"];

    function updateEventWizard() {
        const steps = formEventCap.querySelectorAll(".event-step");
        steps.forEach(s => s.classList.add("d-none"));
        const currentStep = formEventCap.querySelector(`.event-step[data-step="${state.eventWizardStep}"]`);
        if (currentStep) currentStep.classList.remove("d-none");

        $("btn-event-prev").disabled = (state.eventWizardStep === 1);

        const nextBtn = $("btn-event-next");
        if (state.eventWizardStep === state.eventWizardTotalSteps) {
            nextBtn.innerHTML = '<i class="bi bi-lightning-charge me-1"></i>Submit Event';
        } else {
            nextBtn.innerHTML = 'Next<i class="bi bi-arrow-right ms-1"></i>';
        }

        $("event-wizard-label").textContent = `Step ${state.eventWizardStep} of ${state.eventWizardTotalSteps}: ${EVENT_STEP_NAMES[state.eventWizardStep - 1]}`;
        renderWizardIndicators("event-wizard-indicators", state.eventWizardTotalSteps, state.eventWizardStep);

        // Populate intent select on step 4
        if (state.eventWizardStep === 4) populateIntentSelect();

        // Build review on step 5
        if (state.eventWizardStep === 5) buildEventReview();
    }

    function populateIntentSelect() {
        const sel = $("evt-intent-select");
        if (!sel) return;
        sel.innerHTML = '<option value="">-- No linked intent --</option>';
        state.intents.forEach(i => {
            sel.innerHTML += `<option value="${i.intent_id}">${i.intent_id}: ${escapeHtml(i.title)}</option>`;
        });
    }

    function buildEventReview() {
        const fd = new FormData(formEventCap);
        const data = Object.fromEntries(fd.entries());
        const summary = $("event-review-summary");
        if (!summary) return;

        const icon = EVENT_TYPE_ICONS[data.event_type] || "bi-lightning-charge";

        summary.innerHTML = `
            <div class="p-2 mb-2 rounded" style="background-color: var(--adt-bg-secondary);">
                <div class="d-flex align-items-center gap-2">
                    <i class="bi ${icon}"></i>
                    <span class="fw-bold">${data.event_type}</span>
                    <span class="priority-badge ${(data.priority || "medium").toLowerCase()}">${data.priority}</span>
                </div>
                <div class="mt-1">${escapeHtml(data.description || "")}</div>
            </div>
            ${data.intent_id ? `<div class="small mb-1"><strong>Linked to:</strong> ${data.intent_id}</div>` : ""}
            ${data.evt_org_unit ? `<div class="small mb-1"><strong>Unit:</strong> ${escapeHtml(data.evt_org_unit)}</div>` : ""}
        `;
    }

    $("btn-event-next").addEventListener("click", async () => {
        if (state.eventWizardStep < state.eventWizardTotalSteps) {
            if (state.eventWizardStep === 1) {
                const desc = formEventCap.querySelector('[name="description"]');
                if (!desc.value.trim()) { formEventCap.reportValidity(); return; }
            }
            state.eventWizardStep++;
            updateEventWizard();
        } else {
            await submitEvent();
        }
    });

    $("btn-event-prev").addEventListener("click", () => {
        if (state.eventWizardStep > 1) {
            state.eventWizardStep--;
            updateEventWizard();
        }
    });

    async function submitEvent() {
        const fd = new FormData(formEventCap);
        const data = Object.fromEntries(fd.entries());

        const payload = {
            type: data.event_type,
            priority: data.priority || "Medium",
            description: data.description,
            role: "Operator",
            agent: "HUMAN"
        };

        if (data.intent_id) payload.intent_id = data.intent_id;

        // Org context
        if (data.evt_org_unit || data.evt_business_domain) {
            payload.org_context = {
                unit: data.evt_org_unit || "",
                domain: data.evt_business_domain || "",
                process: data.evt_process || "",
                owner: data.evt_owner || ""
            };
        }

        // Tech ecosystem tags
        const evtSystems = state.tagData["evt-tag-systems"] || [];
        const evtData = state.tagData["evt-tag-data"] || [];
        if (evtSystems.length || evtData.length || data.evt_platform) {
            payload.technical_ecosystem = {
                systems: evtSystems,
                data_sources: evtData,
                platform: data.evt_platform || ""
            };
        }

        if (state.project) payload.project = state.project;

        try {
            const res = await fetch("/api/governance/capabilities/events", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                bootstrap.Modal.getInstance($("modal-event-capture"))?.hide();
                formEventCap.reset();
                state.eventWizardStep = 1;
                clearAllTags();
                await loadData();
            } else {
                const err = await res.json();
                alert(`Error: ${err.error || "Failed to capture event"}`);
            }
        } catch (err) {
            console.error("Event capture error:", err);
            alert("Network error capturing event.");
        }
    }

    // ─── Tag Input System ────────────────────────────────────
    function initTagInputs() {
        document.querySelectorAll(".tag-container").forEach(container => {
            const id = container.id;
            state.tagData[id] = [];
            const input = container.querySelector(".tag-input");
            if (!input) return;

            container.addEventListener("click", () => input.focus());

            input.addEventListener("keydown", (e) => {
                if (e.key === "Enter" || e.key === ",") {
                    e.preventDefault();
                    const val = input.value.trim();
                    if (val && !state.tagData[id].includes(val)) {
                        state.tagData[id].push(val);
                        renderTagChips(container, id);
                    }
                    input.value = "";
                }
                if (e.key === "Backspace" && !input.value && state.tagData[id].length > 0) {
                    state.tagData[id].pop();
                    renderTagChips(container, id);
                }
            });
        });
    }

    function renderTagChips(container, id) {
        container.querySelectorAll(".tag-chip").forEach(c => c.remove());
        const input = container.querySelector(".tag-input");
        state.tagData[id].forEach((tag, idx) => {
            const chip = document.createElement("span");
            chip.className = "tag-chip";
            chip.innerHTML = `${escapeHtml(tag)}<span class="tag-remove" onclick="window._removeTag('${id}', ${idx})">&times;</span>`;
            container.insertBefore(chip, input);
        });
    }

    window._removeTag = (containerId, idx) => {
        state.tagData[containerId].splice(idx, 1);
        const container = $(containerId);
        if (container) renderTagChips(container, containerId);
    };

    function clearAllTags() {
        Object.keys(state.tagData).forEach(id => {
            state.tagData[id] = [];
            const container = $(id);
            if (container) renderTagChips(container, id);
        });
    }

    // ─── Utility ─────────────────────────────────────────────
    function escapeHtml(str) {
        if (!str) return "";
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    function formatTimeAgo(ts) {
        if (!ts) return "";
        const diff = Date.now() - new Date(ts).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return "just now";
        if (mins < 60) return `${mins}m ago`;
        const hrs = Math.floor(mins / 60);
        if (hrs < 24) return `${hrs}h ago`;
        const days = Math.floor(hrs / 24);
        return `${days}d ago`;
    }

    function renderTags(arr) {
        if (!arr || !Array.isArray(arr) || arr.length === 0) return '<span class="text-adt-muted">None</span>';
        return arr.map(t => `<span class="tag-chip">${escapeHtml(t)}</span>`).join(" ");
    }

    // ─── Wire Buttons ────────────────────────────────────────
    $("btn-new-intent").onclick = () => {
        state.wizardStep = 1;
        formWizard.reset();
        clearAllTags();
        updateWizard();
        new bootstrap.Modal($("modal-intent-wizard")).show();
    };

    $("btn-capture-event").onclick = () => {
        state.eventWizardStep = 1;
        formEventCap.reset();
        clearAllTags();
        updateEventWizard();
        new bootstrap.Modal($("modal-event-capture")).show();
    };

    $("btn-refresh-all").onclick = () => loadData();
    $("btn-refresh-events").onclick = () => loadData();

    // Maturity preview live update
    formWizard.querySelector('[name="current_maturity"]')?.addEventListener("change", updateMaturityPreview);
    formWizard.querySelector('[name="target_maturity"]')?.addEventListener("change", updateMaturityPreview);

    // ─── Init ────────────────────────────────────────────────
    initTagInputs();
    loadData();
    updateWizard();
});
