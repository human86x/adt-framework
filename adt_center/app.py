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
        """Returns data paths for a project. Defaults to framework root."""
        project = app.project_registry.get_project(name) if name else None
        root = project["path"] if project else app.FRAMEWORK_ROOT
        return {
            "root": root,
            "ads": os.path.join(root, "_cortex", "ads", "events.jsonl"),
            "specs": os.path.join(root, "_cortex", "specs"),
            "tasks": os.path.join(root, "_cortex", "tasks.json"),
            "name": name or os.path.basename(root)
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
    app.register_blueprint(dtcp_bp, url_prefix="/api/dtcp")
    app.register_blueprint(ads_bp, url_prefix="/api/ads")
    app.register_blueprint(governance_bp, url_prefix="/api")

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
        specs = _enrich_specs(spec_registry.list_specs())
        
        active_sessions = query.get_active_sessions()
        denials = sum(1 for e in events if not e.get("authorized", True))
        
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
            port = config.get("dtcp_port")
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
        """SPEC-031 Amendment A: Return only governed projects."""
        projects = app.project_registry.list_governed_projects()
        return jsonify(_get_enriched_projects(projects))

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
        dtcp_actions = ['pending_edit', 'completed_edit', 'denied_edit']
        dtcp_events = [e for e in events if e.get("action_type") in dtcp_actions]
        dtcp_denied = [e for e in dtcp_events if not e.get("authorized", True)]
        
        # Try to get DTCP service status
        dtcp_status = None
        dtcp_url = app.config['DTCP_URL']
        if project_name:
            project = app.project_registry.get_project(project_name)
            if project and project.get("dtcp_port"):
                dtcp_url = f"http://localhost:{project['dtcp_port']}"
                
        try:
            resp = http_client.get(f"{dtcp_url}/status", timeout=2)
            if resp.ok:
                dtcp_status = resp.json()
        except http_client.RequestException:
            pass
            
        return render_template("dtcp.html",
                               dtcp_events=dtcp_events,
                               dtcp_denied=dtcp_denied,
                               dtcp_status=dtcp_status)

    @app.route("/governance")
    def governance_page():
        return render_template("governance.html")

    @app.route("/about")
    def about_page():
        return render_template("about.html")

    return app


if __name__ == "__main__":
    app = create_app()
    unix_socket = os.environ.get("ADC_UNIX_SOCKET")
    
    if unix_socket:
        # SPEC-045: Run on Unix socket for privilege separation
        import socket
        from werkzeug.serving import run_simple
        
        # Ensure directory exists
        socket_dir = os.path.dirname(unix_socket)
        if socket_dir and not os.path.exists(socket_dir):
            os.makedirs(socket_dir, exist_ok=True)
            
        # Clean up existing socket if any
        if os.path.exists(unix_socket):
            os.remove(unix_socket)
            
        print(f"Starting Operational Center on Unix socket: {unix_socket}")
        # We need to use a custom socket to set permissions
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(unix_socket)
        
        # Set permissions: 0660 (rw-rw----)
        # This allows the bridge (running as adt_human) to connect,
        # but blocks adt_agent (not in group).
        os.chmod(unix_socket, 0o660)
        
        run_simple("unix", 0, app, fd=sock.fileno(), debug=(os.environ.get("FLASK_DEBUG") == "1"))
    else:
        port = int(os.environ.get("ADC_PORT", 5001))
        debug = os.environ.get("FLASK_DEBUG", "0") == "1"
        app.run(host="::", port=port, debug=debug)