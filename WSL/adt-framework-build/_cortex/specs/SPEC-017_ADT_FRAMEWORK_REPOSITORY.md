# SPEC-017: ADT Framework -- Standalone Public Repository

**Status:** APPROVED
**Priority:** HIGH
**Owner:** Systems_Architect (spec), DevOps_Engineer (build)
**Created:** 2026-02-06
**References:** SPEC-014 (DTTP), SPEC-015 (Operational Center), SPEC-016 (Help Page), ADT Whitepaper (Sheridan, 2026)

---

## 1. Purpose

Extract the ADT Framework from OceanPulse's internal `_cortex/` into a standalone, public, project-agnostic repository. The framework becomes an independent open-source product. OceanPulse becomes its first governed project (reference implementation).

**Core principle:** The court does not live inside the business it regulates.

---

## 2. Repository

**Name:** `adt-framework`
**Visibility:** Public
**Platform:** GitHub
**License:** AGPL-3.0 (open core) with commercial licensing option
**Location:** `/home/human/Projects/adt-framework/`

---

## 3. Repository Structure

```
adt-framework/
├── README.md                       # What is ADT, badges, quick start
├── LICENSE                         # AGPL-3.0
├── CONTRIBUTING.md                 # Contribution guidelines
├── setup.py                        # Python package setup
│
├── docs/
│   ├── whitepaper.md               # ADT Whitepaper (Sheridan, 2026)
│   ├── architecture.md             # System design & module overview
│   ├── getting-started.md          # Govern your first project in 10 min
│   ├── enforcement-levels.md       # Level 1/2/3 explained
│   └── api-reference.md            # DTTP & ADS API docs
│
├── adt_core/
│   ├── __init__.py
│   ├── ads/                        # Authoritative Data Source engine
│   │   ├── __init__.py
│   │   ├── logger.py               # Safe Logger v3.0 (from ops/log.py)
│   │   ├── integrity.py            # SHA-256 hash chain verification
│   │   ├── schema.py               # Event schema validation
│   │   └── query.py                # Event filtering & search
│   │
│   ├── dttp/                       # Digital Transformation Transfer Protocol
│   │   ├── __init__.py
│   │   ├── gateway.py              # Request validation & execution
│   │   ├── jurisdictions.py        # Role-to-path permission mapping
│   │   ├── actions.py              # Local/SSH/FTP action handlers
│   │   └── policy.py               # Fail-closed policy engine
│   │
│   ├── sdd/                        # Specification-Driven Development
│   │   ├── __init__.py
│   │   ├── registry.py             # Spec lifecycle (DRAFT→APPROVED→COMPLETED)
│   │   ├── validator.py            # Spec-action authorization check
│   │   └── tasks.py                # Task tracking engine
│   │
│   └── ioe/                        # Internet of Events (future)
│       ├── __init__.py
│       └── router.py               # Cross-system event routing (stub)
│
├── adt_center/                     # ADT Operational Center (SPEC-015)
│   ├── app.py                      # Flask application
│   ├── config.py                   # Configuration
│   ├── templates/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── specs.html
│   │   ├── timeline.html
│   │   ├── tasks.html
│   │   ├── dttp_monitor.html
│   │   └── about.html              # SPEC-016 Help & Principles
│   ├── static/
│   │   ├── css/
│   │   └── js/
│   └── api/
│       ├── __init__.py
│       ├── dttp_routes.py          # POST /dttp/request
│       ├── ads_routes.py           # GET /ads/events
│       ├── sdd_routes.py           # GET/POST /specs/*
│       └── task_routes.py          # GET/POST /tasks/*
│
├── adt_sdk/                        # Agent client library
│   ├── __init__.py
│   ├── client.py                   # ADTClient class
│   ├── decorators.py               # @adt.authorized, @adt.logged
│   └── hooks/                      # Hook templates for Claude/Gemini
│       ├── claude_hook.sh
│       └── gemini_hook.sh
│
├── examples/
│   └── oceanpulse/                 # Reference: how OceanPulse is governed
│       ├── README.md
│       ├── project_config.json     # Example project configuration
│       └── jurisdictions.json      # Example role-path mappings
│
└── tests/
    ├── test_ads.py
    ├── test_dttp.py
    ├── test_sdd.py
    └── test_integration.py
```

---

## 4. Module Extraction Map

What moves from OceanPulse `_cortex/` to `adt-framework`, and what stays:

### 4.1 MOVES to adt-framework (as generic engine)

| Source (OceanPulse) | Destination (ADT) | Notes |
|--------------------|--------------------|-------|
| `_cortex/ops/log.py` | `adt_core/ads/logger.py` | Generalize: remove OceanPulse-specific paths, make configurable |
| `_cortex/ads/schema.json` | `adt_core/ads/schema.py` | Convert to Python validation class |
| `_cortex/ops/repair_chain.py` | `adt_core/ads/integrity.py` | Hash chain verification + repair tools |
| `_cortex/AI_PROTOCOL.md` | `docs/` + `adt_core/sdd/` | Becomes a template. Project-specific rules stay in the project |
| `_cortex/roles/` | `adt_core/sdd/` | Role definitions become configurable, not hardcoded |
| `adt_panel/` (static panel) | `adt_center/` | Evolves into Flask app (SPEC-015) |
| Hook scripts (`.claude/`, `.gemini/`) | `adt_sdk/hooks/` | Become templates, project installs from SDK |

### 4.2 STAYS in OceanPulse (project-specific data)

| File | Reason |
|------|--------|
| `_cortex/ads/events.jsonl` | Project's own audit trail -- data, not engine |
| `_cortex/specs/*.md` | Project's specifications -- managed by ADT, owned by project |
| `_cortex/tasks.json` | Project's task list |
| `_cortex/MASTER_PLAN.md` | Project's roadmap |
| `_cortex/MEMORY_BANK.md` | Project's operational context |
| `_cortex/AGENTS.md` | Project's agent roster |

### 4.3 NEW in OceanPulse (post-migration)

| File | Purpose |
|------|---------|
| `_cortex/adt_config.json` | Points to ADT Framework instance (local path or URL) |
| `.adt/project.json` | Project registration with the ADT Operational Center |

---

## 5. Migration Strategy (Zero-Disruption)

**Critical constraint:** OceanPulse development MUST NOT stop during migration. The framework extraction happens in parallel.

### Phase 1: Bootstrap (NOW)

- Create `adt-framework` repository with skeleton structure
- Copy (not move) `ops/log.py` → `adt_core/ads/logger.py` and generalize
- Write README, LICENSE, architecture docs
- OceanPulse continues using internal `_cortex/` unchanged
- **OceanPulse impact: ZERO**

### Phase 2: Build Core Modules

- Implement `adt_core/ads/` (based on existing Safe Logger)
- Implement `adt_core/sdd/` (spec registry, basic lifecycle)
- Write tests
- OceanPulse still uses internal `_cortex/`
- **OceanPulse impact: ZERO**

### Phase 3: Build Operational Center

- Implement `adt_center/` Flask app (SPEC-015)
- Implement `adt_sdk/` client library
- Deploy ADT Operational Center locally
- Test: OceanPulse agents can call ADT API alongside internal `_cortex/`
- **OceanPulse impact: ZERO** (dual-write mode, internal still primary)

### Phase 4: Shadow Mode

- OceanPulse agents write to BOTH internal `_cortex/` and external ADT
- Compare outputs -- verify ADT produces identical results
- Human validates through Operational Center UI
- **OceanPulse impact: MINIMAL** (slight overhead from dual-write)

### Phase 5: Switchover

- OceanPulse agents switch to external ADT as primary
- Internal `_cortex/ops/` becomes a thin wrapper calling ADT SDK
- `events.jsonl` continues to live in OceanPulse (ADT writes to it via configured path)
- **OceanPulse impact: LOW** (same behaviour, different engine)

### Phase 6: Cleanup

- Remove redundant internal governance code from OceanPulse
- `_cortex/` retains only project-specific data (specs, tasks, events, plans)
- All governance logic lives in `adt-framework`
- **OceanPulse impact: NONE** (cleaner, less code)

---

## 6. DTTP Integration (SPEC-014)

DTTP is built directly in `adt-framework`, never in OceanPulse:

- `adt_core/dttp/` is the engine
- The three-user model (human/agent/dttp) is configured per-project
- OceanPulse gets DTTP enforcement when Phase 5 switchover happens
- Before that, OceanPulse continues with current hook-based enforcement

---

## 7. Licensing

### 7.1 AGPL-3.0 (Open Core)

The entire `adt-framework` repository is AGPL-3.0:
- Anyone can use, modify, and distribute
- If modified and offered as a service (SaaS), modifications must be open-sourced
- This protects against cloud providers offering ADT-as-a-service without contributing back

### 7.2 Commercial License (Future)

For enterprises that want:
- Proprietary modifications without AGPL obligations
- Support & SLA
- Multi-project management features
- SSO / enterprise integrations
- Custom deployment assistance

Commercial licensing terms to be defined separately.

### 7.3 Whitepaper

The ADT Whitepaper (Sheridan, 2026) is included in `docs/` under its own copyright. The framework implements the whitepaper's principles; the whitepaper is the intellectual foundation, not a software component.

---

## 8. Public Repository Guidelines

### 8.1 What is public

- All source code (AGPL-3.0)
- Documentation and whitepaper
- Example configurations (using OceanPulse as reference)
- Test suite
- Issue tracker and discussions

### 8.2 What is NEVER in the public repo

- Real project data (events.jsonl, actual specs, credentials)
- OceanPulse source code (separate repo, separate governance)
- Deployment secrets, API keys, SSH credentials
- Client-specific configurations
- Commercial license terms

### 8.3 Contribution Rules

- All contributions via pull request
- ADT governance applies to its own development (self-referential: ADT governs ADT)
- The whitepaper principles are not modifiable by contributors (foundational document)
- Code contributions welcome under AGPL-3.0 CLA

---

## 9. Success Criteria

- [ ] Public GitHub repository created and accessible
- [ ] README clearly explains what ADT is and how to use it
- [ ] ADS engine extracted and working independently of OceanPulse
- [ ] At least one test passing for each core module
- [ ] OceanPulse development uninterrupted throughout migration
- [ ] Whitepaper published in docs/
- [ ] License file present (AGPL-3.0)
- [ ] OceanPulse successfully governed by external ADT instance (Phase 5)

---

## 10. Amendments

This spec governs the creation of the ADT Framework as a standalone product. It is the last spec to be written inside OceanPulse's `_cortex/` for the framework itself -- future ADT specs will live in the ADT Framework's own governance.

---

*"Governance is not a feature of the system. It is the system."*
*-- ADT Framework (Sheridan, 2026)*
