import os

import requests as http_client
import markdown
from flask import Flask, render_template, request, abort
from flask_cors import CORS
from markupsafe import Markup

from adt_core.ads.query import ADSQuery
from adt_core.ads.logger import ADSLogger
from adt_core.sdd.registry import SpecRegistry
from adt_core.sdd.tasks import TaskManager


def create_app():
    app = Flask(__name__)
    CORS(app, origins=["tauri://localhost", "http://localhost:*", "http://127.0.0.1:*"])
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
    app.config["DTTP_URL"] = os.environ.get("DTTP_URL", "http://localhost:5002")

    ADS_PATH = os.path.join(PROJECT_ROOT, "_cortex", "ads", "events.jsonl")
    SPECS_DIR = os.path.join(PROJECT_ROOT, "_cortex", "specs")
    TASKS_PATH = os.path.join(PROJECT_ROOT, "_cortex", "tasks.json")

    # Initialize engines
    app.ads_query = ADSQuery(ADS_PATH)
    app.ads_logger = ADSLogger(ADS_PATH)
    app.spec_registry = SpecRegistry(SPECS_DIR)
    app.task_manager = TaskManager(TASKS_PATH, project_name=app.config["PROJECT_NAME"])

    # Register Jinja2 filter for markdown
    @app.template_filter('markdown')
    def markdown_filter(text):
        if not text:
            return ""
        return Markup(markdown.markdown(text, extensions=['fenced_code', 'tables']))

    # Register Blueprints
    from adt_center.api.dttp_routes import dttp_bp
    from adt_center.api.ads_routes import ads_bp
    from adt_center.api.governance_routes import governance_bp
    app.register_blueprint(dttp_bp, url_prefix="/api/dttp")
    app.register_blueprint(ads_bp, url_prefix="/api/ads")
    app.register_blueprint(governance_bp, url_prefix="/api")

    def _enrich_specs(specs):
        for spec in specs:
            name = spec.get("filename", "").replace(".md", "").split("_", 1)
            spec["name"] = name[1].replace("_", " ") if len(name) > 1 else spec["id"]
        return specs

    @app.route("/")
    def dashboard():
        events = app.ads_query.get_all_events()
        tasks = app.task_manager.list_tasks()
        specs = _enrich_specs(app.spec_registry.list_specs())
        # Compute dashboard stats
        session_starts = {e.get("agent") for e in events if e.get("action_type") == "session_start"}
        session_ends = {e.get("agent") for e in events if e.get("action_type") == "session_end"}
        active_sessions = len(session_starts - session_ends)
        denials = sum(1 for e in events if not e.get("authorized", True))
        return render_template("dashboard.html",
                               events=events,
                               tasks=tasks,
                               specs=specs,
                               active_sessions=active_sessions,
                               denials=denials)

    @app.route("/ads")
    def ads_timeline():
        events = app.ads_query.get_all_events()
        return render_template("ads.html", events=events)

    @app.route("/specs")
    def specs_page():
        specs = _enrich_specs(app.spec_registry.list_specs())
        for spec in specs:
            detail = app.spec_registry.get_spec_detail(spec["id"])
            if detail:
                spec["content"] = detail.get("content", "")
        return render_template("specs.html", specs=specs)

    @app.route("/tasks")
    def tasks_page():
        tasks = app.task_manager.list_tasks()
        return render_template("tasks.html", tasks=tasks)

    @app.route("/dttp")
    def dttp_monitor():
        events = app.ads_query.get_all_events()
        dttp_actions = ['pending_edit', 'completed_edit', 'denied_edit']
        dttp_events = [e for e in events if e.get("action_type") in dttp_actions]
        dttp_denied = [e for e in dttp_events if not e.get("authorized", True)]
        # Try to get DTTP service status
        dttp_status = None
        try:
            resp = http_client.get(f"{app.config['DTTP_URL']}/status", timeout=2)
            if resp.ok:
                dttp_status = resp.json()
        except http_client.RequestException:
            pass
        return render_template("dttp.html",
                               dttp_events=dttp_events,
                               dttp_denied=dttp_denied,
                               dttp_status=dttp_status)

    @app.route("/governance")
    def governance_page():
        return render_template("governance.html")

    @app.route("/about")
    def about_page():
        return render_template("about.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5001, debug=False)