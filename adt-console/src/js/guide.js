/**
 * SPEC-032 Phase D: Guided Setup System
 * Provides a step-by-step walkthrough for new projects.
 */

const GuideSystem = (() => {
  let active = false;
  let currentStep = 1;
  let projectContext = null;
  let guideState = {
    enabled: true,
    current_step: 1,
    completed_steps: [],
    skipped_steps: []
  };

  const STEPS = [
    { id: 1, title: "Describe Project", desc: "Identify mission and tech stack." },
    { id: 2, title: "Set Up Folder", desc: "Initialize directory and ADT scaffold." },
    { id: 3, title: "Configure Governance", desc: "Define roles and jurisdictions." },
    { id: 4, title: "Write First Spec", desc: "Create SPEC-001 to start building." },
    { id: 5, title: "Start Services", desc: "Launch DTTP enforcement." },
    { id: 6, title: "Launch Agent", desc: "Start your first governed session." },
    { id: 7, title: "Governing", desc: "Project setup complete." }
  ];

  function init() {
    const termArea = document.getElementById("terminal-area");
    if (!termArea) return;

    const guideEl = document.createElement("div");
    guideEl.id = "guide-bottom-sheet";
    guideEl.className = "guide-bottom-sheet";
    guideEl.style.display = "none";
    
    guideEl.innerHTML = `
      <div class="guide-progress-bar" id="guide-toggle">
        <div class="progress-track"><div id="guide-progress-fill" class="progress-fill"></div></div>
        <span id="guide-step-label">Step 1 of 7: Describe Project</span>
        <button class="guide-collapse-btn">▼</button>
      </div>
      <div class="guide-body" id="guide-body">
        <div class="guide-content" id="guide-content">
          <!-- Step content injected here -->
        </div>
        <div class="guide-actions">
          <button class="btn-skip" id="btn-guide-skip">Skip Step</button>
          <div class="d-flex gap-2">
            <button class="btn-prev" id="btn-guide-prev" disabled>Back</button>
            <button class="primary" id="btn-guide-next">Next Step</button>
          </div>
        </div>
      </div>
    `;

    termArea.appendChild(guideEl);

    document.getElementById("guide-toggle").addEventListener("click", toggleCollapse);
    document.getElementById("btn-guide-skip").addEventListener("click", skipStep);
    document.getElementById("btn-guide-prev").addEventListener("click", prevStep);
    document.getElementById("btn-guide-next").addEventListener("click", nextStep);

    addStyles();
  }

  function addStyles() {
    const style = document.createElement("style");
    style.innerHTML = `
      .guide-bottom-sheet {
        position: absolute;
        bottom: 0;
        left: 0;
        width: 100%;
        background: #0d1117;
        border-top: 2px solid #6B7FD7;
        z-index: 500;
        display: flex;
        flex-direction: column;
        transition: transform 0.3s ease;
        box-shadow: 0 -5px 20px rgba(0,0,0,0.5);
      }
      .guide-bottom-sheet.collapsed {
        transform: translateY(calc(100% - 40px));
      }
      .guide-progress-bar {
        height: 40px;
        display: flex;
        align-items: center;
        padding: 0 20px;
        cursor: pointer;
        background: #161b22;
        justify-content: space-between;
      }
      .progress-track {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 3px;
        background: #30363d;
      }
      .progress-fill {
        height: 100%;
        background: #6B7FD7;
        transition: width 0.3s ease;
      }
      .guide-body {
        padding: 24px 40px;
        max-height: 400px;
        overflow-y: auto;
      }
      .guide-content h3 {
        margin: 0 0 12px 0;
        color: #e6edf3;
      }
      .guide-content p {
        color: #8b949e;
        font-size: 0.95rem;
      }
      .guide-actions {
        margin-top: 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .btn-skip { background: none; border: none; color: #8b949e; cursor: pointer; text-decoration: underline; }
      .btn-prev { background: #161b22; border: 1px solid #30363d; color: #e6edf3; padding: 8px 16px; border-radius: 4px; cursor: pointer; }
      .btn-prev:disabled { opacity: 0.5; cursor: not-allowed; }
    `;
    document.head.appendChild(style);
  }

  function activate(project) {
    projectContext = project;
    active = true;
    currentStep = 1;
    document.getElementById("guide-bottom-sheet").style.display = "flex";
    renderStep();
  }

  function toggleCollapse() {
    document.getElementById("guide-bottom-sheet").classList.toggle("collapsed");
  }

  function renderStep() {
    const step = STEPS[currentStep - 1];
    const content = document.getElementById("guide-content");
    const label = document.getElementById("guide-step-label");
    const fill = document.getElementById("guide-progress-fill");

    label.innerText = `Step ${currentStep} of 7: ${step.title}`;
    fill.style.width = `${(currentStep / 7) * 100}%`;
    
    document.getElementById("btn-guide-prev").disabled = currentStep === 1;
    document.getElementById("btn-guide-next").innerText = currentStep === 7 ? "Start Working" : "Next Step";

    let stepHtml = `<h3>${step.title}</h3><p>${step.desc}</p>`;
    
    switch(currentStep) {
      case 1: stepHtml += renderStep1(); break;
      case 2: stepHtml += renderStep2(); break;
      case 3: stepHtml += renderStep3(); break;
      case 4: stepHtml += renderStep4(); break;
    }

    content.innerHTML = stepHtml;
  }

  function renderStep1() {
    return `
      <div class="mt-3">
        <label class="d-block mb-1 ctx-meta">Project Name</label>
        <input type="text" class="form-control-adt mb-2" value="${projectContext.name}" readonly>
        <label class="d-block mb-1 ctx-meta">Mission Description</label>
        <textarea class="form-control-adt" rows="3" placeholder="Describe what this project achieves..."></textarea>
      </div>
    `;
  }

  function renderStep2() {
    return `
      <div class="mt-3">
        <p>ADT scaffolding will create the following in <code class="text-accent">${projectContext.path}</code>:</p>
        <ul class="small text-adt-muted">
          <li>_cortex/ (ADS, Specs, Tasks)</li>
          <li>config/ (Jurisdictions, DTTP policy)</li>
          <li>.claude/ & .gemini/ (Agent hooks)</li>
        </ul>
      </div>
    `;
  }

  function renderStep3() {
    return `
      <div class="mt-3">
        <p>Recommended roles for this project:</p>
        <div class="form-check"><input type="checkbox" checked> Backend_Engineer (src/, tests/)</div>
        <div class="form-check"><input type="checkbox" checked> Systems_Architect (_cortex/, docs/)</div>
        <div class="form-check"><input type="checkbox"> Frontend_Engineer (templates/, static/)</div>
      </div>
    `;
  }

  function renderStep4() {
    return `
      <div class="mt-3">
        <label class="d-block mb-1 ctx-meta">SPEC-001 Title</label>
        <input type="text" class="form-control-adt mb-2" placeholder="Implement core engine architecture">
        <label class="d-block mb-1 ctx-meta">Description</label>
        <textarea class="form-control-adt" rows="2" placeholder="What should SPEC-001 achieve?"></textarea>
      </div>
    `;
  }

  function nextStep() {
    if (currentStep < 7) {
      currentStep++;
      renderStep();
    } else {
      document.getElementById("guide-bottom-sheet").style.display = "none";
      active = false;
    }
  }

  function prevStep() {
    if (currentStep > 1) {
      currentStep--;
      renderStep();
    }
  }

  function skipStep() {
    nextStep();
  }

  return { init, activate };
})();
