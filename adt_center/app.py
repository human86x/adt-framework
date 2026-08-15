import os

import requests as http_client
import markdown
from flask import Flask, render_template, request, abort, jsonify, session
from flask_cors import CORS
from markupsafe import Markup

from adt_core.ads.query import ADSQuery
from adt_core.ads.logger import ADSLogger
from adt_core.sdd.registry import SpecRegistry
from adt_core.sdd.tasks import TaskManager
from adt_core.registry import ProjectRegistry


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("ADT_SECRET_KEY", "adt-framework-governance-secret-777")
    CORS(app, origins=["tauri://localhost", "http://localhost:*", "http://127.0.0.1:*"], supports_credentials=True)
    
    # 1. Project Registry Initialization
    app.project_registry = ProjectRegistry()
    app.FRAMEWORK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def get_project_paths(name=None):
        """Returns data paths for a project.

        - ``name`` is None/empty: return framework paths (unchanged default).
        - ``name`` matches a registered project: return that project's paths.
        - ``name`` is a non-empty string but NOT registered: SPEC-078 Part C
          (REQ-120 backend safety belt). Do NOT silently fall back to the
          framework root — that made frontend bugs which forgot to pass
          ``?project=`` invisible (framework's 89 specs bled into project
          views). Instead, return an "empty" resource set pointing to a
          per-name sentinel directory under the framework's ``_cortex``
          namespace that will not exist. SpecRegistry/TaskManager/ADSQuery
          read empties gracefully, so callers see zero specs / zero tasks
          / zero events — the exact signal a mis-scoped fetch should
          produce. The ``unknown_project`` flag lets callers who care
          detect the condition explicitly.
        """
        if name:
            project = app.project_registry.get_project(name)
        else:
            project = None

        if name and project is None:
            # SPEC-078 Part C: unknown project — return empty resource set.
            # Root points to a non-existent sentinel path so any accidental
            # file write also fails loudly rather than polluting framework.
            sentinel_root = os.path.join(
                app.FRAMEWORK_ROOT, "_cortex", "_unknown_projects", name
            )
            return {
                "root": sentinel_root,
                "ads": os.path.join(sentinel_root, "_cortex", "ads", "events.jsonl"),
                "specs": os.path.join(sentinel_root, "_cortex", "specs"),
                "tasks": os.path.join(sentinel_root, "_cortex", "tasks.json"),
                "standards": os.path.join(sentinel_root, "_cortex", "standards"),
                "name": name,
                "unknown_project": True,
            }

        root = project["path"] if project else app.FRAMEWORK_ROOT
        return {
            "root": root,
            "ads": os.path.join(root, "_cortex", "ads", "events.jsonl"),
            "specs": os.path.join(root, "_cortex", "specs"),
            "tasks": os.path.join(root, "_cortex", "tasks.json"),
            "standards": os.path.join(root, "_cortex", "standards"),
            "name": name or os.path.basename(root),
            "unknown_project": False,
        }

    app.get_project_paths = get_project_paths

    @app.before_request
    def check_remote_auth():
        token = os.environ.get('ADT_ACCESS_TOKEN')
        if not token:
            return
        is_remote = request.remote_addr not in ['127.0.0.1', '::1'] or 'Cf-Ray' in request.headers
        if is_remote:
            auth_header = request.headers.get('Authorization')
            query_token = request.args.get('token')
            if auth_header == f'Bearer {token}' or query_token == token:
                return
            abort(401, description='Unauthorized: ADT Remote Access Token Required')

    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # Configuration
    app.config["PROJECT_NAME"] = os.environ.get("ADT_PROJECT_NAME", os.path.basename(PROJECT_ROOT))
    app.config["DTCP_URL"] = os.environ.get("DTCP_URL", "http://localhost:5002")

    # Initialize engines (Legacy/Fallback)
    ADS_PATH = os.path.join(PROJECT_ROOT, "_cortex", "ads", "events.jsonl")
    SPECS_DIR = os.path.join(PROJECT_ROOT, "_cortex", "specs")
    TASKS_PATH = os.path.join(PROJECT_ROOT, "_cortex", "tasks.json")

    app.ads_query = ADSQuery(ADS_PATH)
    app.ads_logger = ADSLogger(ADS_PATH)
    app.spec_registry = SpecRegistry(SPECS_DIR)
    app.task_manager = TaskManager(TASKS_PATH, project_name=app.config["PROJECT_NAME"])

    # SPEC-020 Amendment B: Load canonical roles for normalization
    try:
        from adt_core.ads.schema import ADSEventSchema
        import json
        jurisdictions_path = os.path.join(PROJECT_ROOT, "config", "jurisdictions.json")
        if os.path.exists(jurisdictions_path):
            with open(jurisdictions_path) as f:
                jur_data = json.load(f)
                ADSEventSchema.CANONICAL_ROLES = list(jur_data.get("jurisdictions", {}).keys())
    except Exception as e:
        app.logger.warning(f"Failed to load canonical roles for normalization: {e}")

    # Register Jinja2 filter for markdown
    @app.template_filter('markdown')
    def markdown_filter(text):
        if not text:
            return ""
        return Markup(markdown.markdown(text, extensions=['fenced_code', 'tables']))

    # Register Blueprints
    from adt_center.api.dtcp_routes import dtcp_bp
    from adt_center.api.ads_routes import ads_bp
    from adt_center.api.governance_routes import governance_bp
    from adt_center.api.workers_routes import workers_bp  # SPEC-078 Part D (REQ-121)
    from adt_center.api.state_routes import state_bp  # REQ-125 Priority 5
    app.register_blueprint(dtcp_bp, url_prefix="/api/dtcp")
    app.register_blueprint(ads_bp, url_prefix="/api/ads")
    app.register_blueprint(governance_bp, url_prefix="/api")
    app.register_blueprint(workers_bp, url_prefix="/api/workers")
    app.register_blueprint(state_bp, url_prefix="/api/state")

    def _enrich_specs(specs):
        for spec in specs:
            name = spec.get("filename", "").replace(".md", "").split("_", 1)
            spec["name"] = name[1].replace("_", " ") if len(name) > 1 else spec["id"]
        return specs

    @app.context_processor
    def inject_project():
        return dict(current_project=request.args.get("project"))

    @app.route("/")
    def dashboard():
        project_name = request.args.get("project")
        paths = get_project_paths(project_name)
        
        query = ADSQuery(paths["ads"])
        task_manager = TaskManager(paths["tasks"], project_name=paths["name"])
        spec_registry = SpecRegistry(paths["specs"])
        
        events = query.get_all_events()
        tasks = task_manager.list_tasks()
        # Defensive: dashboard groups completed tasks by assigned_to; a missing
        # field would 500 the whole page. Backfill from `role` or "Unassigned".
        for t in tasks:
            if not t.get("assigned_to"):
                t["assigned_to"] = t.get("role") or "Unassigned"
        specs = _enrich_specs(spec_registry.list_specs())

        active_sessions = query.get_active_sessions()
        # DTTP/DTCP denials: primary source is SPEC-105 `worker_write_denied_by_dtcp`
        # events (which themselves carry authorized=true because they're audit
        # entries). Also count legacy authorized=false events for tier-2 policy
        # violations, and dtcp_unreachable which fails writes closed.
        _denial_types = {
            "worker_write_denied_by_dtcp",
            "dtcp_unreachable_during_reconcile",
            "dtcp_denied",
            "jurisdiction_violation",
        }
        denials = sum(
            1 for e in events
            if (not e.get("authorized", True))
            or (e.get("action_type") in _denial_types)
        )

        return render_template("dashboard.html",
                               events=events,
                               tasks=tasks,
                               specs=specs,
                               active_sessions=active_sessions,
                               denials=denials)

    @app.route("/ads")
    def ads_timeline():
        project_name = request.args.get("project")
        paths = get_project_paths(project_name)
        query = ADSQuery(paths["ads"])
        events = query.get_all_events()
        return render_template("ads.html", events=events)

    @app.route("/specs")
    def specs_page():
        project_name = request.args.get("project")
        paths = get_project_paths(project_name)
        spec_registry = SpecRegistry(paths["specs"])
        
        specs = _enrich_specs(spec_registry.list_specs())
        for spec in specs:
            detail = spec_registry.get_spec_detail(spec["id"])
            if detail:
                spec["content"] = detail.get("content", "")
        return render_template("specs.html", specs=specs)

    @app.route("/tasks")
    def tasks_page():
        project_name = request.args.get("project")
        paths = get_project_paths(project_name)
        task_manager = TaskManager(paths["tasks"], project_name=paths["name"])
        tasks = task_manager.list_tasks()
        return render_template("tasks.html", tasks=tasks)

    @app.route("/capabilities")
    def capabilities_page():
        project_name = request.args.get("project")
        paths = get_project_paths(project_name)
        from adt_core.ads.capability import CapabilityManager
        cm = CapabilityManager(paths["root"])
        intents = cm.list_intents()
        events = cm.list_events()
        return render_template("capabilities.html", intents=intents, events=events)

    @app.route("/hierarchy")
    def hierarchy_page():
        project_name = request.args.get("project")
        paths = get_project_paths(project_name)
        task_manager = TaskManager(paths["tasks"], project_name=paths["name"])
        spec_registry = SpecRegistry(paths["specs"])
        
        tasks = task_manager.list_tasks()
        specs = _enrich_specs(spec_registry.list_specs())
        
        # Load phases
        phases_path = os.path.join(paths["root"], "_cortex", "phases.json")
        phases = []
        if os.path.exists(phases_path):
            try:
                import json
                with open(phases_path, "r") as f:
                    data = json.load(f)
                    phases = data.get("phases", [])
            except:
                pass
        
        return render_template("hierarchy.html", 
                               phases=phases, 
                               tasks=tasks, 
                               specs=specs)

    @app.route("/delegation")
    def delegation_page():
        project_name = request.args.get("project")
        paths = get_project_paths(project_name)
        task_manager = TaskManager(paths["tasks"], project_name=paths["name"])
        spec_registry = SpecRegistry(paths["specs"])
        
        tasks = task_manager.list_tasks()
        specs = _enrich_specs(spec_registry.list_specs())
        
        return render_template("delegation.html", 
                               tasks=tasks, 
                               specs=specs)

    @app.route("/projects")
    def projects_page():
        projects = app.project_registry.list_projects()
        return render_template("projects.html", projects=projects)

    def _get_enriched_projects(project_dict):
        from adt_core.cli import is_port_in_use
        enriched = {}
        for name, config in project_dict.items():
            paths = get_project_paths(name)
            port = config.get("dttp_port")
            dtcp_running = is_port_in_use(port) if port else False
            stats = {"specs": 0, "tasks": 0, "ads_events": 0}
            if os.path.exists(paths["specs"]):
                stats["specs"] = len([f for f in os.listdir(paths["specs"]) if f.endswith(".md")])
            if os.path.exists(paths["tasks"]):
                try:
                    with open(paths["tasks"], "r") as f:
                        data = json.load(f)
                        stats["tasks"] = len(data.get("tasks", []))
                except: pass
            if os.path.exists(paths["ads"]):
                try:
                    with open(paths["ads"], "r") as f:
                        stats["ads_events"] = sum(1 for _ in f)
                except: pass
            enriched[name] = {**config, "dtcp_running": dtcp_running, "stats": stats}
        return enriched

    @app.route("/api/projects")
    def api_list_governed_projects():
        """SPEC-031 Amendment A: Return governed projects for the switcher.

        REQ-106: Frontend switchers (spec_map.js, launcher.js) treat this
        endpoint as the canonical project list, including the forge. If the
        governed set is empty (fresh install, service running as a user with
        an empty registry), we still include the forge so the switcher shows
        at least the framework itself rather than returning an empty {} that
        the UI collapses to "one project only".
        """
        registry = app.project_registry
        governed = registry.list_governed_projects()
        # Always include the forge (adt-framework) so the switcher can
        # navigate back to it and downstream code can resolve its path.
        forge = registry.get_forge()
        if forge:
            name = forge.pop("name")
            governed.setdefault(name, forge)
        return jsonify(_get_enriched_projects(governed))

    @app.route("/api/forge")
    def api_get_forge():
        """SPEC-031 Amendment A: Return forge (framework) metadata."""
        forge = app.project_registry.get_forge()
        if not forge:
            return jsonify({"error": "Forge not found"}), 404
        # Wrap in dict matching projects format
        name = forge.pop("name")
        return jsonify(_get_enriched_projects({name: forge}))

    @app.route("/api/projects/all")
    def api_list_all_projects():
        """SPEC-031 Amendment A: Return all projects including forge."""
        projects = app.project_registry.list_projects()
        return jsonify(_get_enriched_projects(projects))

    @app.route("/dtcp")
    def dtcp_monitor():
        project_name = request.args.get("project")
        paths = get_project_paths(project_name)
        query = ADSQuery(paths["ads"])

        events = query.get_all_events()

        # Legacy hook-based events (pre-SPEC-105) + SPEC-105 reconciler events.
        # Both flow into the same feed.
        _legacy_types = {'pending_edit', 'completed_edit', 'denied_edit'}
        _spec105_types = {
            'worker_write_denied_by_dtcp',
            'worker_reconciliation_complete',
            'dtcp_unreachable_during_reconcile',
        }
        _all_types = _legacy_types | _spec105_types

        dtcp_events = [e for e in events if e.get("action_type") in _all_types]

        # Denial count: legacy authorized=false events + explicit SPEC-105 denials.
        _denial_types = {
            'denied_edit', 'worker_write_denied_by_dtcp',
            'dtcp_unreachable_during_reconcile',
        }
        dtcp_denied = [
            e for e in dtcp_events
            if (not e.get("authorized", True))
            or (e.get("action_type") in _denial_types)
        ]

        # Aggregate per-file counts from SPEC-105 reconciler summary events.
        # Each `worker_reconciliation_complete` payload carries {allowed_count,
        # denied_count, deleted_count} for a single worker. Sum across all
        # workers so the tiles show total per-file DTCP decisions, not the
        # count of summary rows.
        allowed_files = 0
        denied_files = 0
        deleted_files = 0
        for e in events:
            if e.get("action_type") == "worker_reconciliation_complete":
                data = e.get("action_data") or {}
                allowed_files += int(data.get("allowed_count") or 0)
                denied_files += int(data.get("denied_count") or 0)
                deleted_files += int(data.get("deleted_count") or 0)
        # Also count discrete legacy-hook completed_edit / denied_edit rows.
        for e in dtcp_events:
            t = e.get("action_type")
            if t == "completed_edit" and e.get("authorized", True):
                allowed_files += 1
            elif t == "denied_edit":
                denied_files += 1
            elif t == "worker_write_denied_by_dtcp":
                # Already covered by summary denied_count for its worker; do
                # not double-count.
                pass
        total_files = allowed_files + denied_files

        # Try to get DTCP service status.
        dtcp_status = None
        dtcp_url = app.config['DTCP_URL']
        if project_name:
            project = app.project_registry.get_project(project_name)
            # Support both new dtcp_port and legacy dttp_port keys.
            port = (project or {}).get("dtcp_port") or (project or {}).get("dttp_port")
            if port:
                dtcp_url = f"http://localhost:{port}"
                
        try:
            resp = http_client.get(f"{dtcp_url}/status", timeout=2)
            if resp.ok:
                dtcp_status = resp.json()
        except http_client.RequestException:
            pass
            
        # Build spec_id -> spec dict for the event feed's optional standards
        # badges. Empty dict is fine if no specs registered.
        specs_map = {}
        try:
            spec_registry = SpecRegistry(paths["specs"])
            for s in spec_registry.list_specs():
                sid = s.get("id") or s.get("spec_id")
                if sid:
                    specs_map[sid] = s
        except Exception:
            pass

        return render_template("dtcp.html",
                               dtcp_events=dtcp_events,
                               dtcp_denied=dtcp_denied,
                               dtcp_status=dtcp_status,
                               total_files=total_files,
                               allowed_files=allowed_files,
                               denied_files=denied_files,
                               deleted_files=deleted_files,
                               specs_map=specs_map,
                               current_project=project_name)

    @app.route("/governance")
    def governance_page():
        return render_template("governance.html")

    @app.route("/standards")
    def standards_page():
        project = request.args.get("project")
        return render_template("standards.html", current_project=project)

    @app.route("/standards/rules")
    def standards_rules_page():
        project = request.args.get("project")
        return render_template("standards_rules.html", current_project=project)

    @app.route("/standards/mrr")
    def standards_mrr_page():
        project = request.args.get("project")
        return render_template("standards_mrr.html", current_project=project)

    @app.route("/about")
    def about_page():
        return render_template("about.html")

    
    # --- SPEC-062-H sanity watchdog per project ---
    try:
        from adt_center.services.sanity_watchdog import start_watchdog
        import os as _os
        _framework_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        start_watchdog(_framework_root, _framework_root)
        print(f"[sanity-watchdog] started for {_framework_root}", flush=True)
    except Exception as _e:
        import traceback as _tb
        print("[sanity-watchdog] FAILED TO START:", flush=True)
        _tb.print_exc()

    return app



# === SPEC-062 Amendment D8: zombie build auto-cleanup ===
def _zombie_cleanup_loop():
    """Background thread: every 5 min, mark any build 'running' with no ADS activity > 1h as failed."""
    import time, json
    from datetime import datetime, timezone, timedelta
    while True:
        try:
            time.sleep(300)  # 5 min
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            builds_path = os.path.join(project_root, "_cortex", "ops", "builds.json")
            ads_path = os.path.join(project_root, "_cortex", "ads", "events.jsonl")
            if not os.path.exists(builds_path) or not os.path.exists(ads_path):
                continue
            builds = json.load(open(builds_path))
            now = datetime.now(timezone.utc)
            # SPEC-062 Amendment E: zombie watcher is defense-in-depth, threshold raised to 2h
            # since lifecycle events catch worker death within minutes now.
            threshold = timedelta(hours=float(os.environ.get("ADT_ZOMBIE_WATCHER_HOURS", "2")))

            # Find last activity per build_id from recent ADS events
            last_seen = {}
            with open(ads_path, "rb") as f:
                f.seek(0, 2); end = f.tell()
                f.seek(max(0, end - 1_000_000))
                for line in f.read().decode("utf-8", errors="replace").splitlines():
                    try:
                        e = json.loads(line)
                        bid = (e.get("action_data") or {}).get("build_id") or ""
                        if not bid: continue
                        ts = e.get("ts","")
                        if ts: last_seen[bid] = max(last_seen.get(bid,""), ts)
                    except Exception:
                        pass

            zombies = 0
            for bid, b in builds.items():
                if b.get("status") not in ("initiated","running"):
                    continue
                last = last_seen.get(bid) or b.get("ts","")
                try:
                    last_dt = datetime.fromisoformat(last.replace("Z","+00:00"))
                    if now - last_dt > threshold:
                        b["status"] = "failed"
                        b["failure_reason"] = "auto-finalized by zombie watcher: no activity >1h"
                        b["finalized_at"] = now.isoformat().replace("+00:00","Z")
                        zombies += 1
                except Exception:
                    pass

            if zombies:
                with open(builds_path, "w") as f:
                    json.dump(builds, f, indent=2)
                print(f"[zombie-watcher] finalized {zombies} stale builds", flush=True)
        except Exception as e:
            print(f"[zombie-watcher] error: {e}", flush=True)


def _start_zombie_watcher():
    import threading
    t = threading.Thread(target=_zombie_cleanup_loop, daemon=True, name="zombie-watcher")
    t.start()
    print("[zombie-watcher] started (interval 5m, threshold 1h)", flush=True)


# Operator-requested: synthetic progress bars driven by filesystem activity.
# agy workers usually ignore the "POST progress hints" prompt instruction, so
# percent never gets set. This watcher imputes percent from how many files in
# src/, tests/, lib/, app/, public/, scripts/ were modified during the task's
# in_progress window.
def _synthetic_progress_loop():
    import time, json, os
    from datetime import datetime, timezone
    INTERVAL = int(os.environ.get("ADT_SYNTH_PROGRESS_INTERVAL_SEC", "30"))  # REQ-113: raised 15→30 per Paul WSL analysis
    CODE_DIRS = ("src", "tests", "lib", "app", "public", "scripts",
                 "adt_center", "adt_core", "adt_sdk", "adt-console/src",
                 "docs", "css", "js", "assets", "static", "components",
                 "pages", "views", "api", "routes", "models", "utils",
                 "frontend", "backend", "core", "dist", "build", "out")
    ROOT_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
                 ".rs", ".go", ".java", ".rb", ".php", ".json", ".yaml",
                 ".yml", ".toml", ".md", ".sh"}
    while True:
        try:
            time.sleep(INTERVAL)
            registry_path = os.path.expanduser("~/.adt/projects.json")
            if not os.path.exists(registry_path):
                continue
            with open(registry_path) as f:
                projects = json.load(f).get("projects", {})
            now = datetime.now(timezone.utc)
            now_iso = now.isoformat().replace("+00:00", "Z")
            for name, info in projects.items():
                root = info.get("path")
                if not root or not os.path.isdir(root):
                    continue
                tasks_path = os.path.join(root, "_cortex", "tasks.json")
                if not os.path.exists(tasks_path):
                    continue
                try:
                    td = json.load(open(tasks_path))
                except Exception:
                    continue
                tasks = td.get("tasks", []) if isinstance(td, dict) else td
                changed = False
                for t in tasks:
                    if t.get("status") != "in_progress":
                        continue
                    started_at = t.get("started_at")
                    if not started_at:
                        continue
                    try:
                        started_ts = datetime.fromisoformat(started_at.replace("Z","+00:00")).timestamp()
                    except Exception:
                        continue
                    mod_count = 0
                    for d in CODE_DIRS:
                        dp = os.path.join(root, d)
                        if not os.path.isdir(dp):
                            continue
                        for r2, _, files in os.walk(dp):
                            if "__pycache__" in r2 or "node_modules" in r2 or ".git" in r2:
                                continue
                            for fn in files:
                                try:
                                    if os.path.getmtime(os.path.join(r2, fn)) > started_ts:
                                        mod_count += 1
                                except Exception: pass
                    try:
                        for fn in os.listdir(root):
                            fp = os.path.join(root, fn)
                            if os.path.isfile(fp) and os.path.splitext(fn)[1].lower() in ROOT_EXTS:
                                try:
                                    if os.path.getmtime(fp) > started_ts:
                                        mod_count += 1
                                except Exception: pass
                    except Exception: pass
                    if   mod_count == 0: pct = 10
                    elif mod_count == 1: pct = 30
                    elif mod_count == 2: pct = 55
                    elif mod_count <= 4: pct = 75
                    else:                pct = 90
                    msg = f"{mod_count} file(s) modified" if mod_count else "worker active, no file changes yet"
                    # SPEC-062-H: only overwrite when the current source is
                    # synthetic (or unset). If the worker just POSTed a real
                    # progress update via /api/tasks/<id>/progress, respect it.
                    current_src = t.get("progress_source", "")
                    if current_src in ("", "synthetic_file_activity"):
                        if t.get("progress_percent") != pct or t.get("progress_message") != msg:
                            t["progress_percent"] = pct
                            t["progress_message"] = msg
                            t["progress_updated_at"] = now_iso
                            t["progress_source"] = "synthetic_file_activity"
                            changed = True
                    else:
                        # Real worker progress present — only bump message if
                        # file activity says we're at a higher progress level.
                        try:
                            stored_pct = int(t.get("progress_percent") or 0)
                        except Exception:
                            stored_pct = 0
                        if pct > stored_pct:
                            # File activity shows more than the worker last
                            # reported — merge (bump the bar, keep worker's message).
                            t["progress_percent"] = pct
                            t["progress_updated_at"] = now_iso
                            changed = True
                if changed:
                    if isinstance(td, dict):
                        td["tasks"] = tasks
                        json.dump(td, open(tasks_path, "w"), indent=2)
                    else:
                        json.dump(tasks, open(tasks_path, "w"), indent=2)
        except Exception as _e:
            print(f"[synth-progress] tick error: {_e}", flush=True)


def _start_synth_progress():
    import threading
    t = threading.Thread(target=_synthetic_progress_loop, daemon=True, name="synth-progress")
    t.start()
    print("[synth-progress] started (per-15s file-activity poll)", flush=True)




def _finalize_orphan_builds_on_startup():
    """Mark builds whose worker PIDs are not alive as 'blocked' and reset their
    in_progress tasks to 'ready'. Called once at startup so adt_center restarts
    don't leave orphan builds running forever."""
    import json, os
    from datetime import datetime, timezone
    registry_path = os.path.expanduser("~/.adt/projects.json")
    if not os.path.exists(registry_path):
        return
    projects = json.load(open(registry_path)).get("projects", {})
    cleaned = 0
    for name, info in projects.items():
        try:
            root = info.get("path")
            if not root or not os.path.isdir(root): continue
            bp = os.path.join(root, "_cortex", "ops", "builds.json")
            if not os.path.exists(bp): continue
            try:
                b = json.load(open(bp))
            except Exception: continue
            b_changed = False
            for bid, rec in b.items():
                if rec.get("status") not in ("initiated","running"): continue
                # Find any pid mentioned in this build's recent ADS events
                ads_path = os.path.join(root, "_cortex", "ads", "events.jsonl")
                alive_pid = None
                if os.path.exists(ads_path):
                    try:
                        with open(ads_path) as f:
                            for line in f:
                                try:
                                    e = json.loads(line)
                                    ad = e.get("action_data") or {}
                                    if ad.get("build_id") != bid: continue
                                    if e.get("action_type") != "build_worker_spawned": continue
                                    pid = ad.get("pid")
                                    if pid:
                                        try:
                                            os.kill(int(pid), 0)
                                            alive_pid = pid
                                            break
                                        except Exception: pass
                                except Exception: pass
                    except Exception: pass
                if alive_pid is None:
                    rec["status"] = "blocked"
                    rec["error"] = "orphaned by adt_center restart - no live worker"
                    b_changed = True
                    cleaned += 1
            if b_changed:
                json.dump(b, open(bp,'w'), indent=2)
            # Also reset in_progress tasks for orphaned builds
            tp = os.path.join(root, "_cortex", "tasks.json")
            if os.path.exists(tp):
                try:
                    td = json.load(open(tp))
                    tasks = td.get("tasks", []) if isinstance(td, dict) else td
                    t_changed = False
                    for t in tasks:
                        if t.get("status") == "in_progress":
                            t["status"] = "ready"
                            t["auto_retry_count"] = (t.get("auto_retry_count") or 0) + 1
                            for k in ("progress_percent","progress_message","progress_updated_at","progress_source"):
                                t.pop(k, None)
                            t_changed = True
                    if t_changed:
                        if isinstance(td, dict):
                            td["tasks"] = tasks
                            json.dump(td, open(tp,'w'), indent=2)
                        else:
                            json.dump(tasks, open(tp,'w'), indent=2)
                except Exception: pass
        except Exception: pass
    if cleaned:
        print(f"[startup-finalize] cleaned {cleaned} orphan build(s)", flush=True)




# Operator-requested: reality audit. Some agy workers write real code then time out
# before emitting task_completed -- framework marks the task "failed" even though
# the deliverable is on disk. This loop checks "failed" tasks for evidence of work
# (file mtimes during the task's run window) and reconciles them to "completed".
def _reality_audit_loop():
    import time, json, os
    from datetime import datetime, timezone
    INTERVAL = int(os.environ.get("ADT_REALITY_AUDIT_INTERVAL_SEC", "120"))  # REQ-113: raised 60→120 per Paul WSL analysis
    CODE_DIRS = ("src", "tests", "lib", "app", "public", "scripts",
                 "adt_center", "adt_core", "adt_sdk", "adt-console/src",
                 "docs", "css", "js", "assets", "static", "components",
                 "pages", "views", "api", "routes", "models", "utils",
                 "frontend", "backend", "core", "dist", "build", "out")
    MIN_BYTES = 500  # ignore trivial stubs (empty __init__.py etc)
    LOOKBACK_HOURS = 4
    while True:
        try:
            time.sleep(INTERVAL)
            registry_path = os.path.expanduser("~/.adt/projects.json")
            if not os.path.exists(registry_path):
                continue
            projects = json.load(open(registry_path)).get("projects", {})
            now = datetime.now(timezone.utc)
            now_ts = now.timestamp()
            now_iso = now.isoformat().replace("+00:00", "Z")
            for name, info in projects.items():
                root = info.get("path")
                if not root or not os.path.isdir(root):
                    continue
                tasks_path = os.path.join(root, "_cortex", "tasks.json")
                if not os.path.exists(tasks_path):
                    continue
                try:
                    td = json.load(open(tasks_path))
                except Exception:
                    continue
                tasks = td.get("tasks", []) if isinstance(td, dict) else td
                changed = False
                for t in tasks:
                    if t.get("status") != "failed":
                        continue
                    started_at = t.get("started_at")
                    if not started_at:
                        continue
                    try:
                        started_ts = datetime.fromisoformat(started_at.replace("Z","+00:00")).timestamp()
                    except Exception:
                        continue
                    if now_ts - started_ts > LOOKBACK_HOURS * 3600:
                        continue  # too old, skip
                    # Find substantive new/grown files during the task window
                    evidence = []
                    for d in CODE_DIRS:
                        dp = os.path.join(root, d)
                        if not os.path.isdir(dp): continue
                        for r2, _, files in os.walk(dp):
                            if "__pycache__" in r2 or "node_modules" in r2 or ".git" in r2:
                                continue
                            for fn in files:
                                fp = os.path.join(r2, fn)
                                try:
                                    st = os.stat(fp)
                                    if st.st_mtime > started_ts and st.st_size >= MIN_BYTES:
                                        evidence.append((os.path.relpath(fp, root), st.st_size))
                                except Exception: pass
                    if evidence:
                        t["status"] = "completed"
                        t["completed_at"] = now_iso
                        t["reconciled_from_failed"] = True
                        t["reconciliation_evidence"] = [{"path": p, "size": s} for p, s in evidence[:10]]
                        t.pop("failure_reason", None)
                        t.pop("error", None)
                        print(f"[reality-audit] {name}/{t.get('id')} failed -> completed ({len(evidence)} file(s) on disk)", flush=True)
                        changed = True
                if changed:
                    if isinstance(td, dict):
                        td["tasks"] = tasks
                        json.dump(td, open(tasks_path, "w"), indent=2)
                    else:
                        json.dump(tasks, open(tasks_path, "w"), indent=2)
        except Exception as _e:
            print(f"[reality-audit] tick error: {_e}", flush=True)


def _start_reality_audit():
    import threading
    t = threading.Thread(target=_reality_audit_loop, daemon=True, name="reality-audit")
    t.start()
    print("[reality-audit] started (per-60s file-evidence reconciliation)", flush=True)


def _run_startup_fsck(skip: bool = False):
    """REQ-125 Priority 4: startup fsck over load-bearing JSON files.

    If any file is corrupt, print an actionable message to stderr and
    ``sys.exit(3)`` -- Flask never binds. Bypass with ``--skip-fsck`` on
    the CLI or ``ADT_SKIP_FSCK=1`` in the environment (prints a bright
    yellow warning so operators know they're running degraded).
    """
    import sys
    from adt_core.state import run_startup_fsck

    framework_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    candidates = [
        os.path.join(framework_root, "_cortex", "tasks.json"),
        os.path.join(framework_root, "config", "intent_index.json"),
        os.path.join(framework_root, "config", "specs.json"),
        os.path.join(framework_root, "config", "jurisdictions.json"),
        os.path.join(framework_root, "_cortex", "ops", "sovereign_requests.json"),
        os.path.join(framework_root, "_cortex", "ops", "builds.json"),
    ]

    if skip:
        # Bright yellow ANSI warning; operators should see this in the logs.
        sys.stderr.write(
            "\033[1;33m[REQ-125] startup fsck BYPASSED via --skip-fsck / "
            "ADT_SKIP_FSCK=1. Load-bearing state files were NOT validated. "
            "This is unsafe for anything other than recovery/testing.\033[0m\n"
        )
        sys.stderr.flush()
        return

    problems = run_startup_fsck(candidates)
    if problems:
        sys.stderr.write("ADT-CENTER STARTUP FSCK FAILED:\n")
        for p in problems:
            sys.stderr.write(
                f"  {p.path}: line {p.line} col {p.col}: {p.detail}\n"
            )
        sys.stderr.write(
            "Refusing to bind. Fix the corruption or run "
            "adt_core.state.safe_write.restore_latest_backup("
            "'<file>') to recover from the last known good.\n"
        )
        sys.stderr.flush()
        sys.exit(3)

    # Count files that actually exist (missing files are OK per REQ-125).
    validated = sum(1 for p in candidates if os.path.exists(p))
    print(
        f"[REQ-125] startup fsck OK: {validated} files validated",
        flush=True,
    )


# SPEC-081 §1.2 -- process-wide warm caches populated once at startup.
# Read by governance_routes similar_projects lookup and by any future
# code that wants a "recent enough" snapshot without paying the disk
# cost on the request path.
_WARMUP_TTL_SECONDS = 300  # 5-minute TTL
_warmup_cache = {
    "project_registry": {"value": None, "loaded_at": 0.0},
    "templates": {"value": None, "loaded_at": 0.0},
    "standards_catalog": {"value": None, "loaded_at": 0.0},
}


def _warmup_pre_init():
    """SPEC-081 §1.2 -- pre-load heavy modules + cache hot lookups.

    Called once after startup fsck, before Flask binds. Silent-failure
    on any individual sub-step: warmup is an optimisation, never a
    barrier to boot.
    """
    import time
    import traceback

    matcher_loaded = False
    registry_cached = False
    catalog_cached = False

    # 1) Pre-import the intent matcher so its (heavy) module-level
    #    imports are paid at boot instead of on the first classify call.
    try:
        import adt_core.standards.intent_matcher  # noqa: F401
        matcher_loaded = True
    except Exception:
        print("[warmup] intent_matcher pre-import failed:", flush=True)
        traceback.print_exc()

    # 2) Cache the project registry (used by /api/projects and by the
    #    similar-projects lookup for path resolution).
    try:
        from adt_core.registry import ProjectRegistry
        pr = ProjectRegistry()
        projects = pr.list_projects()
        _warmup_cache["project_registry"] = {
            "value": projects,
            "loaded_at": time.time(),
        }
        registry_cached = True
    except Exception:
        print("[warmup] project registry cache failed:", flush=True)
        traceback.print_exc()

    # 3) Cache templates + standards catalog. Best-effort; the API
    #    endpoints remain the source of truth on cache miss.
    try:
        framework_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        )
        templates_dir = os.path.join(framework_root, "templates")
        templates_list = []
        if os.path.isdir(templates_dir):
            templates_list = sorted(
                d for d in os.listdir(templates_dir)
                if os.path.isdir(os.path.join(templates_dir, d))
            )
        _warmup_cache["templates"] = {
            "value": templates_list,
            "loaded_at": time.time(),
        }
    except Exception:
        pass

    try:
        from adt_core.standards.registry import StandardsRegistry
        sr = StandardsRegistry()
        catalog = []
        for method in ("list_rules", "list_standards", "get_all"):
            if hasattr(sr, method):
                try:
                    catalog = getattr(sr, method)()
                    break
                except Exception:
                    continue
        _warmup_cache["standards_catalog"] = {
            "value": catalog,
            "loaded_at": time.time(),
        }
        catalog_cached = True
    except Exception:
        # Standards registry may raise for framework-root ambiguity;
        # non-fatal for warmup.
        pass

    print(
        f"[warmup] pre-init complete: matcher_loaded={matcher_loaded} "
        f"registry_cached={registry_cached} catalog_cached={catalog_cached}",
        flush=True,
    )
    if matcher_loaded and registry_cached and catalog_cached:
        print(
            "[warmup] INFO warmup pre-init: matcher loaded, registry cached, "
            "catalog cached",
            flush=True,
        )


def get_warm_cache(key: str):
    """Return cached value if fresh (<5min old), else None.

    Public helper for governance_routes to consult without duplicating
    the TTL logic. Returns ``None`` on miss or stale entry.
    """
    import time
    entry = _warmup_cache.get(key)
    if not entry or entry.get("value") is None:
        return None
    if (time.time() - entry.get("loaded_at", 0.0)) > _WARMUP_TTL_SECONDS:
        return None
    return entry["value"]


if __name__ == "__main__":
    import sys as _sys
    _skip_fsck = (
        "--skip-fsck" in _sys.argv
        or os.environ.get("ADT_SKIP_FSCK", "0") == "1"
    )
    _run_startup_fsck(skip=_skip_fsck)
    _finalize_orphan_builds_on_startup()
    _warmup_pre_init()
    _start_zombie_watcher()
    _start_synth_progress()
    _start_reality_audit()
    app = create_app()
    unix_socket = os.environ.get("ADC_UNIX_SOCKET")
    
    if unix_socket:
        # SPEC-045: Run on Unix socket for privilege separation
        from werkzeug.serving import run_simple
        import threading
        import time
        
        # Ensure directory exists
        socket_dir = os.path.dirname(unix_socket)
        if socket_dir and not os.path.exists(socket_dir):
            os.makedirs(socket_dir, exist_ok=True)
            
        # Clean up existing socket if any
        if os.path.exists(unix_socket):
            try:
                os.remove(unix_socket)
            except OSError:
                pass
            
        print(f"Starting Operational Center on Unix socket: {unix_socket}")
        
        def chmod_loop():
            # Wait for socket to be created by run_simple, then chmod it to 0660
            for _ in range(50):
                if os.path.exists(unix_socket):
                    try:
                        os.chmod(unix_socket, 0o660)
                        break
                    except Exception:
                        pass
                time.sleep(0.1)
                
        threading.Thread(target=chmod_loop, daemon=True).start()
        
        run_simple(f"unix://{unix_socket}", 0, app, threaded=True, use_debugger=(os.environ.get("FLASK_DEBUG") == "1"))
    else:
        port = int(os.environ.get("ADC_PORT", 5001))
        debug = os.environ.get("FLASK_DEBUG", "0") == "1"
        app.run(host="::", port=port, debug=debug)

