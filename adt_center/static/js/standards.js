
document.addEventListener('DOMContentLoaded', () => {
    loadStandards();
    loadHealthStats();
    setupMutationPolling();
});

async function loadStandards() {
    const urlParams = new URLSearchParams(window.location.search);
    const project = urlParams.get('project');
    let url = '/api/governance/standards';
    if (project) url += '?project=' + project;

    try {
        const response = await fetch(url);
        const data = await response.json();
        renderStandardsTable(data.standards || []);
    } catch (error) {
        console.error('Error loading standards:', error);
        document.getElementById('standards-list').innerHTML = '<tr><td colspan="8" class="text-center text-danger">Failed to load standards</td></tr>';
    }
}

function renderStandardsTable(standards) {
    const list = document.getElementById('standards-list');
    const countBadge = document.getElementById('standards-count');
    
    list.innerHTML = '';
    countBadge.innerText = standards.length + ' Standards';

    if (standards.length === 0) {
        list.innerHTML = '<tr><td colspan="8" class="text-center">No standards registered</td></tr>';
        return;
    }

    standards.forEach(std => {
        const summary = std.status_summary || { total: 0, pending: 0, adopted: 0, adapted: 0, dismissed: 0 };
        const row = document.createElement('tr');
        row.style.cursor = 'pointer';
        row.onclick = () => showStandardDetail(std.id);
        
        row.innerHTML = `
            <td><strong>${std.id}</strong><br><small class="text-muted">${std.title}</small></td>
            <td>${std.version}</td>
            <td><span class="badge bg-outline-secondary">${std.scope || 'N/A'}</span></td>
            <td class="text-center"><span class="badge bg-success">${summary.adopted}</span></td>
            <td class="text-center"><span class="badge bg-info">${summary.adapted}</span></td>
            <td class="text-center"><span class="badge bg-danger">${summary.dismissed}</span></td>
            <td class="text-center"><span class="badge bg-secondary">${summary.pending}</span></td>
            <td class="text-end"><i class="bi bi-chevron-right text-muted"></i></td>
        `;
        list.appendChild(row);
    });
}

async function showStandardDetail(standardId) {
    const urlParams = new URLSearchParams(window.location.search);
    const project = urlParams.get('project');
    let url = `/api/governance/standards/${standardId}`;
    if (project) url += '?project=' + project;

    try {
        const response = await fetch(url);
        const standard = await response.json();
        
        const offcanvasElement = document.getElementById('clauseOffcanvas');
        const offcanvas = new bootstrap.Offcanvas(offcanvasElement);
        
        document.getElementById('clauseOffcanvasLabel').innerText = standard.title;
        
        const meta = document.getElementById('standard-meta');
        meta.innerHTML = `
            <div class="row">
                <div class="col-sm-6"><small class="text-muted">Publisher</small><br>${standard.publisher}</div>
                <div class="col-sm-6"><small class="text-muted">Version</small><br>${standard.version}</div>
            </div>
            <div class="mt-2">
                <small class="text-muted">Source URL</small><br>
                <a href="${standard.source_url}" target="_blank" class="text-info text-break">${standard.source_url}</a>
            </div>
        `;

        const clauseList = document.getElementById('clause-list');
        clauseList.innerHTML = '';
        
        standard.clauses.forEach(clause => {
            const row = document.createElement('tr');
            let dispClass = 'bg-secondary';
            if (clause.disposition === 'adopted') dispClass = 'bg-success';
            if (clause.disposition === 'adapted') dispClass = 'bg-info';
            if (clause.disposition === 'dismissed') dispClass = 'bg-danger';

            const adoptedClass = clause.disposition === 'adopted' ? 'btn-success' : 'btn-outline-success';
            const adaptedClass = clause.disposition === 'adapted' ? 'btn-warning' : 'btn-outline-warning';
            const dismissedClass = clause.disposition === 'dismissed' ? 'btn-danger' : 'btn-outline-danger';
            
            row.innerHTML = `
                <td><small>${clause.id}</small></td>
                <td>${clause.title}</td>
                <td><span class="badge ${dispClass}">${clause.disposition}</span></td>
                <td><span class="badge bg-outline-warning">-</span></td>
                <td class="text-end">
                    <div class="btn-group btn-group-sm" role="group">
                        <button class="btn ${adoptedClass}" onclick="event.stopPropagation(); quickAdopt('${standard.id}', '${clause.id}')">Adopt</button>
                        <button class="btn ${adaptedClass}" onclick="event.stopPropagation(); openDispositionModal('${standard.id}', '${clause.id}', 'adapted')">Adapt</button>
                        <button class="btn ${dismissedClass}" onclick="event.stopPropagation(); openDispositionModal('${standard.id}', '${clause.id}', 'dismissed')">Dismiss</button>
                    </div>
                </td>
            `;
            clauseList.appendChild(row);
        });

        offcanvas.show();
    } catch (error) {
        console.error('Error loading standard detail:', error);
    }
}

let activeStandardId = null;
let activeClauseId = null;

window.quickAdopt = async function(standardId, clauseId) {
    const urlParams = new URLSearchParams(window.location.search);
    const project = urlParams.get('project');
    let url = `/api/governance/standards/${standardId}/clauses/${clauseId}/disposition`;
    if (project) url += '?project=' + project;
    
    try {
        const response = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ disposition: 'adopted', rationale: '' })
        });
        if (response.ok) {
            loadStandards();
            showStandardDetail(standardId);
        } else {
            const data = await response.json();
            alert('Error: ' + (data.error || 'Failed to adopt clause'));
        }
    } catch (error) {
        console.error('Error adopting clause:', error);
    }
};

window.openDispositionModal = async function(standardId, clauseId, actionType) {
    activeStandardId = standardId;
    activeClauseId = clauseId;

    const urlParams = new URLSearchParams(window.location.search);
    const project = urlParams.get('project');
    let url = `/api/governance/standards/${standardId}/clauses/${clauseId}`;
    if (project) url += '?project=' + project;

    try {
        const response = await fetch(url);
        const clause = await response.json();

        document.getElementById('disp-clause-id').innerText = `${standardId} §${clauseId}`;
        document.getElementById('disp-action-title').innerText = actionType;
        document.getElementById('disp-clause-text').innerText = clause.text;
        document.getElementById('disp-select').value = actionType;
        document.getElementById('disp-rationale').value = clause.rationale || '';
        
        const modal = new bootstrap.Modal(document.getElementById('dispositionModal'));
        modal.show();
    } catch (error) {
        console.error('Error loading clause detail:', error);
    }
}

document.getElementById('save-disposition').onclick = async () => {
    const disposition = document.getElementById('disp-select').value;
    const rationale = document.getElementById('disp-rationale').value.trim();
    
    if (rationale.length < 20) {
        alert('Rationale must be at least 20 characters.');
        return;
    }

    const urlParams = new URLSearchParams(window.location.search);
    const project = urlParams.get('project');
    let url = `/api/governance/standards/${activeStandardId}/clauses/${activeClauseId}/disposition`;
    if (project) url += '?project=' + project;

    try {
        const response = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ disposition, rationale })
        });
        
        if (response.status === 202) {
            const data = await response.json();
            alert(`Sovereign Change Request submitted: ${data.scr_id}. Awaiting human approval.`);
        } else if (response.ok) {
            // success
        } else {
            const data = await response.json();
            alert('Error: ' + (data.error || 'Failed to save disposition'));
        }
        
        bootstrap.Modal.getInstance(document.getElementById('dispositionModal')).hide();
        loadStandards(); // Reload list
        if (activeStandardId) showStandardDetail(activeStandardId); // Refresh drill-down
    } catch (error) {
        console.error('Error saving disposition:', error);
    }
};

async function loadHealthStats() {
    const urlParams = new URLSearchParams(window.location.search);
    const project = urlParams.get('project');
    let url = '/api/governance/standards/coverage';
    if (project) url += '?project=' + project;

    try {
        const response = await fetch(url);
        const data = await response.json();
        // API shape: {total_standards, total_clauses,
        //   dispositions:{adopted, adapted, dismissed, pending}}
        // Coverage = (adopted + adapted) / total_clauses. Orphan = adopted
        // clauses with no spec references; the coverage API doesn't currently
        // break that out, so we surface `dismissed` here as the closest proxy
        // (both mean "counted but not driving spec work"). If a future API
        // returns an explicit `orphan` field, prefer it.
        const disp = data.dispositions || {};
        const adopted = disp.adopted || 0;
        const adapted = disp.adapted || 0;
        const pending = disp.pending || 0;
        const dismissed = disp.dismissed || 0;
        const total = data.total_clauses || 0;
        const pct = total > 0
            ? Math.round(((adopted + adapted) * 100) / total)
            : 0;

        document.getElementById('coverage-pct').innerText = pct + '%';
        document.getElementById('count-adopted').innerText = adopted + adapted;
        document.getElementById('count-orphan').innerText = (data.orphan != null) ? data.orphan : dismissed;
        document.getElementById('count-pending').innerText = pending;
    } catch (error) {
        // coverage API might not be ready yet
    }
}

function setupMutationPolling() {
    // Initial load
    loadMutations();
    // Poll every 60s
    setInterval(loadMutations, 60000);
}

async function loadMutations() {
    const urlParams = new URLSearchParams(window.location.search);
    const project = urlParams.get('project');
    let url = '/api/ads/events?limit=5&type=clause_adopted,clause_adapted,clause_dismissed,standard_registered';
    if (project) url += '&project=' + project;

    try {
        const response = await fetch(url);
        const data = await response.json();
        renderMutations(data.events || []);
    } catch (error) {
        console.error('Error loading mutations:', error);
    }
}

function renderMutations(events) {
    const list = document.getElementById('recent-mutations');
    if (events.length === 0) return;

    list.innerHTML = '';
    events.forEach(e => {
        const li = document.createElement('li');
        li.className = 'list-group-item bg-transparent border-secondary py-3';
        const ts = new Date(e.ts).toLocaleString();
        li.innerHTML = `
            <div class="d-flex justify-content-between mb-1">
                <small class="text-info">${e.action_type.replace('_', ' ').toUpperCase()}</small>
                <small class="text-muted">${ts}</small>
            </div>
            <div class="small">${e.description}</div>
        `;
        list.appendChild(li);
    });
}

document.addEventListener('DOMContentLoaded', () => {
    loadSpecsForCoverage();
    document.getElementById('spec-coverage-select').addEventListener('change', (e) => {
        const specId = e.target.value;
        if (specId) {
            loadSpecCoverage(specId);
        } else {
            document.getElementById('coverage-visualization').innerHTML = 'Select a spec to view its coverage chain.';
        }
    });
});

async function loadSpecsForCoverage() {
    try {
        const urlParams = new URLSearchParams(window.location.search);
        const project = urlParams.get('project');
        let url = '/api/specs';
        if (project) url += '?project=' + project;
        
        const response = await fetch(url);
        const specs = await response.json();
        const select = document.getElementById('spec-coverage-select');
        specs.forEach(spec => {
            const opt = document.createElement('option');
            opt.value = spec.id;
            opt.innerText = `${spec.id} - ${spec.title}`;
            select.appendChild(opt);
        });
    } catch (error) {
        console.error('Error loading specs:', error);
    }
}

async function loadSpecCoverage(specId) {
    const viz = document.getElementById('coverage-visualization');
    viz.innerHTML = '<div class="spinner-border text-primary spinner-border-sm"></div> Loading...';
    try {
        const urlParams = new URLSearchParams(window.location.search);
        const project = urlParams.get('project');
        let url = `/api/governance/specs/${specId}/coverage`;
        if (project) url += '?project=' + project;
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to fetch coverage');
        const data = await response.json();
        
        if (!data.standards_refs || data.standards_refs.length === 0) {
            viz.innerHTML = `This spec is not linked to any Rationalised Rule. Edit the spec markdown to add <code>standards_refs: [RR-xxx]</code> in the header block.`;
            return;
        }
        
        let html = `<div class="text-start">`;
        html += `<div class="mb-2"><strong>${data.spec_id}</strong> covers:</div>`;
        data.rationalised_rules.forEach(rr => {
            html += `<div class="card bg-dark border-secondary mb-2 p-2">`;
            html += `<div><span class="badge bg-secondary">${rr.id}</span> ${rr.title || ''}</div>`;
            html += `<div class="ms-3 mt-1 small text-muted">Derived from:</div>`;
            html += `<ul class="mb-0 ms-1 ps-3">`;
            if (rr.derived_from && rr.derived_from.length > 0) {
                rr.derived_from.forEach(df => {
                    html += `<li>${df}</li>`;
                });
            } else {
                html += `<li>No source clauses</li>`;
            }
            html += `</ul></div>`;
        });
        html += `</div>`;
        viz.innerHTML = html;
        
    } catch (error) {
        console.error('Error loading spec coverage:', error);
        viz.innerHTML = '<span class="text-danger">Failed to load coverage</span>';
    }
}
