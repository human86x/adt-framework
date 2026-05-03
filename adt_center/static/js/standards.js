
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

            row.innerHTML = `
                <td><small>${clause.id}</small></td>
                <td>${clause.title}</td>
                <td><span class="badge ${dispClass}">${clause.disposition}</span></td>
                <td><span class="badge bg-outline-warning">-</span></td>
                <td class="text-end">
                    <button class="btn btn-sm btn-outline-light" onclick="event.stopPropagation(); openDispositionModal('${standard.id}', '${clause.id}')">
                        <i class="bi bi-pencil"></i>
                    </button>
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

async function openDispositionModal(standardId, clauseId) {
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
        document.getElementById('disp-clause-text').innerText = clause.text;
        document.getElementById('disp-select').value = clause.disposition;
        document.getElementById('disp-rationale').value = clause.rationale || '';
        
        toggleRationale(clause.disposition);

        const modal = new bootstrap.Modal(document.getElementById('dispositionModal'));
        modal.show();
    } catch (error) {
        console.error('Error loading clause detail:', error);
    }
}

document.getElementById('disp-select').addEventListener('change', (e) => {
    toggleRationale(e.target.value);
});

function toggleRationale(disposition) {
    const container = document.getElementById('rationale-container');
    if (disposition === 'adapted' || disposition === 'dismissed') {
        container.classList.remove('d-none');
    } else {
        container.classList.add('d-none');
    }
}

document.getElementById('save-disposition').onclick = async () => {
    const disposition = document.getElementById('disp-select').value;
    const rationale = document.getElementById('disp-rationale').value;
    
    if ((disposition === 'adapted' || disposition === 'dismissed') && !rationale) {
        alert('Rationale is required for adapted or dismissed dispositions.');
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
        
        document.getElementById('coverage-pct').innerText = (data.covered_pct || 0) + '%';
        document.getElementById('count-adopted').innerText = data.adopted || 0;
        document.getElementById('count-orphan').innerText = data.orphan || 0;
        document.getElementById('count-pending').innerText = data.pending || 0;
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
