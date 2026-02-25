import os
import re
import json
import subprocess
import requests as http_client
from datetime import datetime, timezone
from flask import Blueprint, jsonify, current_app, request
from adt_core.ads.schema import ADSEventSchema

from adt_core.ads.query import ADSQuery
from adt_core.ads.logger import ADSLogger
from adt_core.sdd.registry import SpecRegistry
from adt_core.sdd.tasks import TaskManager

from adt_core.registry import ProjectRegistry

governance_bp = Blueprint("governance", __name__)

def _init_project(path, name=None, detect=True, port=None):
    """Internal helper for project initialization. Shared with CLI."""
    from adt_core.cli import detect_project_type, install_hooks
    
    path = os.path.abspath(path)
    name = name or os.path.basename(path)
    
    # 1. Project Registry
    registry = ProjectRegistry()
    if registry.get_project(name):
        raise ValueError(f"Project '{name}' already registered.")
    
    port = port or registry.next_available_port()
    
    # 2. Scaffold directories
    cortex_dir = os.path.join(path, "_cortex")
    config_dir = os.path.join(path, "config")
    
    os.makedirs(os.path.join(cortex_dir, "ads"), exist_ok=True)
    os.makedirs(os.path.join(cortex_dir, "specs"), exist_ok=True)
    os.makedirs(os.path.join(cortex_dir, "ops"), exist_ok=True)
    os.makedirs(config_dir, exist_ok=True)
    
    # 3. Generate files
    # config/dttp.json
    dttp_config = {
        "name": name,
        "port": port,
        "mode": "development",
        "enforcement_mode": "development"
    }
    with open(os.path.join(config_dir, "dttp.json"), "w") as f:
        json.dump(dttp_config, f, indent=2)
        
    # config/jurisdictions.json
    proj_type = detect_project_type(path) if detect else "generic"
    
    default_paths = ["src/", "tests/", "docs/", "config/"]
    if proj_type == "python":
        default_paths = ["src/", "tests/", "docs/", "config/", "requirements.txt", "setup.py", "pyproject.toml"]
    elif proj_type == "nodejs":
        default_paths = ["src/", "tests/", "public/", "config/", "package.json"]
    elif proj_type == "rust":
        default_paths = ["src/", "tests/", "benches/", "config/", "Cargo.toml"]
        
    jurisdictions = {
        "jurisdictions": {
            "Architect": {
                "paths": ["_cortex/", "config/", "docs/"],
                "action_types": ["edit", "patch", "create", "delete"],
                "locked": False
            },
            "Developer": {
                "paths": default_paths,
                "action_types": ["edit", "patch", "create", "delete"],
                "locked": False
            }
        }
    }
    with open(os.path.join(config_dir, "jurisdictions.json"), "w") as f:
        json.dump(jurisdictions, f, indent=2)
        
    # config/specs.json
    with open(os.path.join(config_dir, "specs.json"), "w") as f:
        json.dump({"specs": {}}, f, indent=2)
        
    # _cortex/AI_PROTOCOL.md
    with open(os.path.join(cortex_dir, "AI_PROTOCOL.md"), "w") as f:
        f.write(f"# AI PROTOCOL v1.0 ({name})\n\n**Framework:** Advanced Digital Transformation\n\n(Generated via ADT)\n")
        
    # _cortex/MASTER_PLAN.md
    with open(os.path.join(cortex_dir, "MASTER_PLAN.md"), "w") as f:
        f.write(f"# {name}: Master Plan\n\n(Generated via ADT)\n")
        
    # _cortex/tasks.json
    with open(os.path.join(cortex_dir, "tasks.json"), "w") as f:
        json.dump({"project": name, "tasks": []}, f, indent=2)
        
    # _cortex/ops/active_role.txt
    with open(os.path.join(cortex_dir, "ops", "active_role.txt"), "w") as f:
        f.write("Architect")
        
    # 4. ADS Genesis
    ads_path = os.path.join(cortex_dir, "ads", "events.jsonl")
    logger = ADSLogger(ads_path)
    
    event = ADSEventSchema.create_event(
        event_id=ADSEventSchema.generate_id("genesis"),
        agent="HUMAN",
        role="Architect",
        action_type="project_init",
        description=f"Project {name} initialized for ADT governance.",
        spec_ref="GENESIS",
        authorized=True,
        tier=1
    )
    logger.log(event)
    
    # 5. Register
    registry.register_project(name, path, port)
    
    # 6. Hooks
    framework_project = registry.get_project("adt-framework")
    if framework_project:
        install_hooks(path, framework_project["path"])

    # 7. SPEC-027: Apply Shatterglass permissions if production mode is active
    if _is_production_mode():
        _apply_shatterglass_permissions(path)

    return {"name": name, "path": path, "port": port}

@governance_bp.route("/projects/init", methods=["POST"])
def api_init_project():
    """SPEC-031: Initialize a new project."""
    data = request.get_json()
    if not data or "path" not in data:
        return jsonify({"error": "path is required"}), 400
    
    try:
        result = _init_project(
            path=data["path"],
            name=data.get("name"),
            detect=data.get("detect", True),
            port=data.get("port")
        )
        return jsonify({"status": "success", "project": result}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _is_production_mode():
    """Check if Shatterglass production mode is active (SPEC-027).
    Returns True if 'agent' and 'dttp' OS users exist."""
    import pwd
    try:
        pwd.getpwnam('agent')
        pwd.getpwnam('dttp')
        return True
    except KeyError:
        return False

def _apply_shatterglass_permissions(project_path):
    """SPEC-027 task_127: Apply OS-level file permissions to a new external project.
    Tier 1 (sovereign): human:human 644 -- _cortex/AI_PROTOCOL.md, _cortex/MASTER_PLAN.md, config/*.json
    All other files: dttp:dttp 664 (agent in dttp group can write)
    Requires sudo -- skips silently if not available."""
    import pwd, grp, stat

    try:
        human_user = os.environ.get("SUDO_USER", os.environ.get("USER", ""))
        human_uid = pwd.getpwnam(human_user).pw_uid
        human_gid = pwd.getpwnam(human_user).pw_gid
    except (KeyError, TypeError):
        return  # Can't determine human user, skip

    try:
        dttp_uid = pwd.getpwnam('dttp').pw_uid
        dttp_gid = grp.getgrnam('dttp').gr_gid
    except KeyError:
        return  # dttp user/group doesn't exist, skip

    # Tier 1 sovereign paths (relative to project)
    tier1_paths = [
        os.path.join("_cortex", "AI_PROTOCOL.md"),
        os.path.join("_cortex", "MASTER_PLAN.md"),
        os.path.join("config", "specs.json"),
        os.path.join("config", "jurisdictions.json"),
        os.path.join("config", "dttp.json"),
    ]

    # Set base ownership: everything to dttp:dttp 664/775
    for root, dirs, files in os.walk(project_path):
        for d in dirs:
            full = os.path.join(root, d)
            try:
                os.chown(full, dttp_uid, dttp_gid)
                os.chmod(full, 0o775)
            except OSError:
                pass
        for f in files:
            full = os.path.join(root, f)
            try:
                os.chown(full, dttp_uid, dttp_gid)
                os.chmod(full, 0o664)
            except OSError:
                pass

    # Set Tier 1 sovereign paths to human:human 644
    for rel_path in tier1_paths:
        full = os.path.join(project_path, rel_path)
        if os.path.exists(full):
            try:
                os.chown(full, human_uid, human_gid)
                os.chmod(full, 0o644)
            except OSError:
                pass

def _start_project_dttp(name):
    """Internal helper to start DTTP for a project."""
    from adt_core.cli import is_port_in_use, get_pid_by_port
    registry = ProjectRegistry()
    project = registry.get_project(name)
    if not project:
        raise ValueError(f"Project '{name}' not found.")

    port = project.get("dttp_port")
    if not port:
        raise ValueError(f"Project '{name}' has no DTTP port assigned.")

    if is_port_in_use(port):
        return {"status": "already_running", "pid": get_pid_by_port(port)}

    # Use framework's python if available
    python_exe = sys.executable
    framework = registry.get_project("adt-framework")
    if framework:
        venv_python = os.path.join(framework["path"], "venv", "bin", "python3")
        if os.path.exists(venv_python):
            python_exe = venv_python

    log_dir = os.path.join(project["path"], "_cortex", "ops")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "dttp.log")

    # SPEC-027: In production mode, run DTTP as the 'dttp' OS user
    production_mode = _is_production_mode()
    if production_mode:
        cmd = ["sudo", "-u", "dttp", python_exe, "-m", "adt_core.dttp.service", "--port", str(port), "--project-root", project["path"]]
    else:
        cmd = [python_exe, "-m", "adt_core.dttp.service", "--port", str(port), "--project-root", project["path"]]

    with open(log_file, "a") as log:
        subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            start_new_session=True
        )
        
    import time
    time.sleep(2)
    if is_port_in_use(port):
        return {"status": "success", "pid": get_pid_by_port(port)}
    else:
        raise RuntimeError(f"Failed to start DTTP service. Check logs: {log_file}")

def _stop_project_dttp(name):
    """Internal helper to stop DTTP for a project."""
    from adt_core.cli import get_pid_by_port
    registry = ProjectRegistry()
    project = registry.get_project(name)
    if not project:
        raise ValueError(f"Project '{name}' not found.")
        
    port = project.get("dttp_port")
    pid = get_pid_by_port(port)
    if pid:
        try:
            import signal
            os.kill(int(pid), signal.SIGTERM)
            return {"status": "success"}
        except Exception as e:
            raise RuntimeError(f"Failed to stop: {e}")
    else:
        return {"status": "not_running"}

@governance_bp.route("/projects/<name>/start", methods=["POST"])
def api_start_project(name):
    try:
        result = _start_project_dttp(name)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@governance_bp.route("/projects/<name>/stop", methods=["POST"])
def api_stop_project(name):
    try:
        result = _stop_project_dttp(name)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _get_project_resources(project_name):
    """Helper to get project-specific managers and paths."""
    paths = current_app.get_project_paths(project_name)
    return {
        "paths": paths,
        "query": ADSQuery(paths["ads"]),
        "logger": ADSLogger(paths["ads"]),
        "spec_registry": SpecRegistry(paths["specs"]),
        "task_manager": TaskManager(paths["tasks"], project_name=paths["name"])
    }

def _load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def _parse_requests(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r") as f:
        content = f.read()
    
    requests_list = []
    # Split by horizontal rule (three or more dashes)
    sections = re.split(r"\n-+\n", content)
    for section in sections:
        # Match ID and Title
        id_match = re.search(r"## (REQ-\d+): (.*)", section)
        if id_match:
            req_id = id_match.group(1)
            title = id_match.group(2).strip()
            
            # Extract status - look for **STATUS** inside ### Status
            status = "UNKNOWN"
            if "### Status" in section:
                status_part = section.split("### Status")[1]
                status_match = re.search(r"\*\*([A-Z _]+)\*\*", status_part)
                if status_match:
                    status = status_match.group(1).strip()
            elif "**Status:**" in section:
                status_match = re.search(r"\*\*Status:\*\* (.*)", section)
                if status_match:
                    status = status_match.group(1).strip()
            
            # Extract author
            author_match = re.search(r"\*\*From:\*\* (.*)", section)
            author = author_match.group(1).strip() if author_match else "UNKNOWN"
            
            # Extract from_role (e.g. Backend_Engineer from Backend_Engineer (CLAUDE))
            from_role = author
            role_match = re.search(r"^([a-zA-Z_]+)", author)
            if role_match:
                from_role = role_match.group(1).strip()
            
            # Extract To
            to_match = re.search(r"\*\*To:\*\* (.*)", section)
            to = to_match.group(1).strip() if to_match else "ALL"
            # Remove leading @ if present
            to = to.lstrip("@")
            
            # Extract date
            date_match = re.search(r"\*\*Date:\*\* (.*)", section)
            date = date_match.group(1).strip() if date_match else "UNKNOWN"

            # Extract summary/description
            summary = ""
            if "### Description" in section:
                desc_part = section.split("### Description")[1]
                summary = re.split(r"###", desc_part)[0].strip()
            elif "### Status" in section:
                # Text between header/metadata and ### Status
                parts = section.split(id_match.group(0))[1]
                summary = parts.split("### Status")[0]
                # Clean up metadata
                summary = re.sub(r"\*\*From:\*\*.*\n", "", summary)
                summary = re.sub(r"\*\*To:\*\*.*\n", "", summary)
                summary = re.sub(r"\*\*Date:\*\*.*\n", "", summary)
                summary = re.sub(r"\*\*Type:\*\*.*\n", "", summary)
                summary = re.sub(r"\*\*Priority:\*\*.*\n", "", summary)
                summary = re.sub(r"\*\*Related Specs:\*\*.*\n", "", summary)
                summary = summary.strip()

            requests_list.append({
                "id": req_id,
                "title": title,
                "status": status,
                "author": author,
                "from_role": from_role,
                "to": to,
                "date": date,
                "summary": summary[:200]
            })
    return requests_list

@governance_bp.route("/git/status", methods=["GET"])
def get_git_status():
    """SPEC-023: Get current git branch and uncommitted changes count."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    try:
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root).decode().strip()
        status_porcelain = subprocess.check_output(["git", "status", "--porcelain"], cwd=root).decode().strip()
        
        # Count lines in porcelain output to get number of changes
        changes_count = len(status_porcelain.splitlines()) if status_porcelain else 0
        
        return jsonify({
            "branch": branch,
            "changes": changes_count,
            "status": "clean" if changes_count == 0 else "dirty"
        })
    except Exception as e:
        current_app.logger.error(f"Failed to get git status: {e}")
        return jsonify({"error": str(e)}), 500


@governance_bp.route("/tasks", methods=["GET"])
def get_tasks():
    project_name = request.args.get("project")
    res = _get_project_resources(project_name)
    status = request.args.get("status")
    assigned_to = request.args.get("assigned_to")
    tasks = res["task_manager"].list_tasks(status=status, assigned_to=assigned_to)
    return jsonify({"tasks": tasks})

@governance_bp.route("/specs", methods=["GET"])
def get_specs():
    project_name = request.args.get("project")
    res = _get_project_resources(project_name)
    specs = res["spec_registry"].list_specs()
    return jsonify({"specs": specs})

@governance_bp.route("/specs/<spec_id>", methods=["GET"])
def get_spec_detail(spec_id):
    project_name = request.args.get("project")
    res = _get_project_resources(project_name)
    detail = res["spec_registry"].get_spec_detail(spec_id)
    if not detail:
        return jsonify({"error": "Spec not found"}), 404
    return jsonify(detail)

@governance_bp.route("/sessions/start", methods=["POST"])
def session_start():
    data = request.get_json()
    if not data or not all(k in data for k in ["agent", "role", "spec_id"]):
        return jsonify({"error": "Missing agent, role, or spec_id"}), 400
    
    project_name = request.args.get("project") or data.get("project")
    res = _get_project_resources(project_name)
    
    session_id = data.get("session_id", "unknown")
    sandbox = data.get("sandbox", False)
    event_id = ADSEventSchema.generate_id("session_start")
    event = ADSEventSchema.create_event(
        event_id=event_id,
        agent=data["agent"],
        role=data["role"],
        action_type="session_start",
        description=f"Session started: {session_id} for agent {data['agent']} as {data['role']}.",
        spec_ref=data["spec_id"],
        session_id=session_id,
        action_data={"sandbox": sandbox}
    )
    res["logger"].log(event)
    return jsonify({"status": "success", "event_id": event_id})


@governance_bp.route("/sessions", methods=["GET"])
def list_active_sessions():
    """SPEC-036: Return list of active sessions with sandbox status."""
    project_name = request.args.get("project")
    res = _get_project_resources(project_name)
    sessions = res["query"].get_active_sessions_details()
    return jsonify({"sessions": sessions})
    
    
@governance_bp.route("/sessions/end", methods=["POST"])
def session_end():
    data = request.get_json()
    if not data or not all(k in data for k in ["agent", "role", "spec_id"]):
        return jsonify({"error": "Missing agent, role, or spec_id"}), 400
    
    project_name = request.args.get("project") or data.get("project")
    res = _get_project_resources(project_name)
    root = res["paths"]["root"]
    
    session_id = data.get("session_id", "unknown")
    
    # SPEC-023: Mandatory commit enforcement
    force = data.get("force", False)
    if not force:
        try:
            # Check for unstaged/uncommitted changes
            status = subprocess.check_output(["git", "status", "--porcelain"], cwd=root).decode().strip()
            if status:
                return jsonify({
                    "error": "Uncommitted changes detected. Session cannot be closed without a commit.",
                    "git_status": status
                }), 403
        except Exception as e:
            current_app.logger.warning(f"Git status check failed: {e}")

    # Get current commit hash for ADS record
    commit_hash = "unknown"
    try:
        commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    except:
        pass

    event_id = ADSEventSchema.generate_id("session_end")
    event = ADSEventSchema.create_event(
        event_id=event_id,
        agent=data["agent"],
        role=data["role"],
        action_type="session_end",
        description=f"Session ended: {session_id} for agent {data['agent']} as {data['role']}.",
        spec_ref=data["spec_id"],
        session_id=session_id,
        action_data={"commit_hash": commit_hash}
    )
    res["logger"].log(event)
    return jsonify({"status": "success", "event_id": event_id, "commit_hash": commit_hash})


@governance_bp.route("/specs/<spec_id>/status", methods=["PUT"])
def update_spec_status(spec_id):
    """SPEC-015: Update spec status (Approve/Complete)."""
    data = request.get_json()
    if not data or "status" not in data:
        return jsonify({"error": "status is required"}), 400

    new_status = data["status"].upper()
    project_name = request.args.get("project")
    res = _get_project_resources(project_name)
    
    # 1. Update config/specs.json
    root = res["paths"]["root"]
    specs_path = os.path.join(root, "config", "specs.json")
    specs_config = _load_json(specs_path)
    if spec_id in specs_config.get("specs", {}):
        specs_config["specs"][spec_id]["status"] = new_status.lower()
        with open(specs_path, "w") as f:
            json.dump(specs_config, f, indent=2)

    # 2. Update the Markdown file
    detail = res["spec_registry"].get_spec_detail(spec_id)
    if not detail or "filename" not in detail:
        return jsonify({"error": "Spec file not found"}), 404
    
    file_path = os.path.join(res["paths"]["specs"], detail["filename"])
    with open(file_path, "r") as f:
        content = f.read()
    
    # Regex replace **Status:** ... with new status
    updated_content = re.sub(
        r"\*\*Status:\*\* .*", 
        f"**Status:** {new_status}", 
        content, 
        flags=re.IGNORECASE
    )
    
    with open(file_path, "w") as f:
        f.write(updated_content)

    # 3. Log to ADS
    event_type = "spec_approved" if new_status == "APPROVED" else "spec_completed"
    event_id = ADSEventSchema.generate_id("spec_stat")
    event = ADSEventSchema.create_event(
        event_id=event_id,
        agent="HUMAN",
        role="Collaborator",
        action_type=event_type,
        description=f"Spec {spec_id} status updated to {new_status} via Panel UI.",
        spec_ref=spec_id,
        authorized=True,
        tier=1
    )
    res["logger"].log(event)

    return jsonify({"status": "success", "spec_id": spec_id, "new_status": new_status, "event_id": event_id})


@governance_bp.route("/specs", methods=["POST"])
def create_spec():
    """SPEC-025: Create a new spec via Panel UI."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    project_name = request.args.get("project") or data.get("project")
    res = _get_project_resources(project_name)

    spec_id = data.get("id", "").strip()
    title = data.get("title", "").strip()
    status = data.get("status", "DRAFT").strip()
    body = data.get("content", "").strip()

    if not re.match(r"^SPEC-\d{3}$", spec_id):
        return jsonify({"error": "Invalid spec ID format. Use SPEC-NNN (e.g. SPEC-026)"}), 400

    if not title:
        return jsonify({"error": "Title is required"}), 400

    safe_title = re.sub(r"[^a-zA-Z0-9_\- ]", "", title).replace(" ", "_").upper()
    filename = f"{spec_id}_{safe_title}.md"
    spec_path = os.path.join(res["paths"]["specs"], filename)

    for existing in os.listdir(res["paths"]["specs"]):
        if existing.startswith(spec_id):
            return jsonify({"error": f"Spec {spec_id} already exists"}), 409

    if not body:
        body = f"# {spec_id}: {title}\n\n**Status:** {status}\n**Created:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n---\n\n## 1. Purpose\n\n(Describe the purpose here)\n"

    os.makedirs(os.path.dirname(spec_path), exist_ok=True)
    with open(spec_path, "w") as f:
        f.write(body)

    event_id = ADSEventSchema.generate_id("spec_created")
    event = ADSEventSchema.create_event(
        event_id=event_id,
        agent="HUMAN",
        role="Collaborator",
        action_type="spec_created",
        description=f"Created {spec_id}: {title} (status: {status}) via Panel UI.",
        spec_ref=spec_id,
        authorized=True,
        tier=3,
    )
    res["logger"].log(event)

    return jsonify({"status": "success", "spec_id": spec_id, "filename": filename, "event_id": event_id}), 201


@governance_bp.route("/requests", methods=["POST"])
def submit_request():
    """SPEC-025: Submit feedback/request via Panel UI."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    project_name = request.args.get("project") or data.get("project")
    res = _get_project_resources(project_name)

    author = data.get("author", "Anonymous").strip()
    req_type = data.get("type", "improvement").strip()
    description = data.get("description", "").strip()

    if not description:
        return jsonify({"error": "Description is required"}), 400

    valid_types = ["feature", "bug", "improvement"]
    if req_type not in valid_types:
        req_type = "improvement"

    requests_path = os.path.join(res["paths"]["root"], "_cortex", "requests.md")

    next_num = 1
    if os.path.exists(requests_path):
        with open(requests_path, "r") as f:
            existing = f.read()
            nums = re.findall(r"REQ-(\d+)", existing)
            if nums:
                next_num = max(int(n) for n in nums) + 1

    req_id = f"REQ-{next_num:03d}"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    entry = f"\n\n---\n\n## {req_id}: {req_type.title()} Request\n\n**From:** {author}\n**Date:** {timestamp}\n**Type:** {req_type.upper()}\n**Priority:** MEDIUM\n\n### Description\n\n{description}\n\n### Status\n\n**OPEN** -- Submitted via ADT Panel.\n"

    os.makedirs(os.path.dirname(requests_path), exist_ok=True)
    with open(requests_path, "a") as f:
        f.write(entry)

    event_id = ADSEventSchema.generate_id("request_sub")
    event = ADSEventSchema.create_event(
        event_id=event_id,
        agent="HUMAN",
        role="Collaborator",
        action_type="request_submitted",
        description=f"{req_id} ({req_type}) by {author}: {description[:80]}",
        spec_ref="SPEC-025",
        authorized=True,
        tier=3,
    )
    res["logger"].log(event)

    return jsonify({"status": "success", "request_id": req_id, "event_id": event_id}), 201


@governance_bp.route("/governance/requests", methods=["POST"])
def api_file_request():
    """SPEC-037: Governed API for filing cross-role requests."""
    data = request.get_json()
    if not data or not all(k in data for k in ["from_role", "to_role", "title"]):
        return jsonify({"error": "from_role, to_role, and title are required"}), 400

    project_name = request.args.get("project") or data.get("project")
    res = _get_project_resources(project_name)
    requests_path = os.path.join(res["paths"]["root"], "_cortex", "requests.md")

    from_role = data["from_role"]
    from_agent = data.get("from_agent", "AGENT")
    to_role = data["to_role"]
    title = data["title"]
    description = data.get("description", "")
    priority = data.get("priority", "MEDIUM")
    req_type = data.get("type", "SPEC_REQUEST")
    related_specs = data.get("related_specs", [])

    # Generate REQ-ID
    next_num = 1
    if os.path.exists(requests_path):
        with open(requests_path, "r") as f:
            existing = f.read()
            nums = re.findall(r"## REQ-(\d+)", existing)
            if nums:
                next_num = max(int(n) for n in nums) + 1
    req_id = f"REQ-{next_num:03d}"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    # Format entry
    entry = f"\n\n---\n\n## {req_id}: {title}\n\n"
    entry += f"**From:** {from_role} ({from_agent})\n"
    entry += f"**To:** @{to_role}\n"
    entry += f"**Date:** {timestamp}\n"
    entry += f"**Type:** {req_type}\n"
    entry += f"**Priority:** {priority}\n"
    if related_specs:
        entry += f"**Related Specs:** {', '.join(related_specs)}\n"
    entry += f"\n### Description\n\n{description}\n\n### Status\n\n**OPEN**\n"

    os.makedirs(os.path.dirname(requests_path), exist_ok=True)
    with open(requests_path, "a") as f:
        f.write(entry)

    # Log to ADS
    event_id = ADSEventSchema.generate_id("req_filed")
    event = ADSEventSchema.create_event(
        event_id=event_id, agent=from_agent, role=from_role, action_type="request_filed",
        description=f"Filed {req_id}: {title} targeting {to_role}.",
        spec_ref="SPEC-037", authorized=True, tier=3,
        action_data={"req_id": req_id, "to_role": to_role, "title": title}
    )
    res["logger"].log(event)

    return jsonify({"status": "success", "req_id": req_id, "event_id": event_id}), 201


@governance_bp.route("/governance/roles", methods=["GET"])
def get_governance_roles():
    """SPEC-026: Unified view of role jurisdictions and spec bindings."""
    project_name = request.args.get("project")
    res = _get_project_resources(project_name)
    root = res["paths"]["root"]
    
    jur_path = os.path.join(root, "config", "jurisdictions.json")
    specs_path = os.path.join(root, "config", "specs.json")
    
    jurisdictions = _load_json(jur_path).get("jurisdictions", {})
    specs = _load_json(specs_path).get("specs", {})
    
    roles = {}
    for name, config in jurisdictions.items():
        if isinstance(config, list):
            roles[name] = {"paths": config, "action_types": [], "specs": [], "locked": False}
        else:
            roles[name] = {"paths": config.get("paths", []), "action_types": config.get("action_types", []), "specs": [], "locked": config.get("locked", False)}
            
    for spec_id, spec in specs.items():
        for role in spec.get("roles", []):
            if role not in roles:
                roles[role] = {"paths": [], "action_types": [], "specs": [], "locked": False}
            if spec_id not in roles[role]["specs"]:
                roles[role]["specs"].append(spec_id)
            for action in spec.get("action_types", []):
                if action not in roles[role]["action_types"]:
                    roles[role]["action_types"].append(action)
                    
    return jsonify({"roles": roles})


@governance_bp.route("/tasks/<task_id>/status", methods=["PUT"])
def update_task_status(task_id):
    """SPEC-026: Agent self-service task status update."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    project_name = request.args.get("project") or data.get("project")
    res = _get_project_resources(project_name)

    new_status = data.get("status")
    agent = data.get("agent")
    role = data.get("role")
    evidence = data.get("evidence", "")

    if not agent or not isinstance(agent, str):
        return jsonify({"error": "agent name is required"}), 400
    if not role or not isinstance(role, str):
        return jsonify({"error": "role is required"}), 400
    if len(evidence) > 2000:
        return jsonify({"error": "evidence exceeds 2000 characters"}), 400

    if new_status not in ["completed", "in_progress"]:
        return jsonify({"error": "Agents can only set status to completed or in_progress"}), 400

    task = res["task_manager"].get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    # Authorization check: must be assigned to this role
    if task.get("assigned_to") != role:
        return jsonify({"error": f"Task {task_id} is assigned to {task.get('assigned_to')}, not {role}"}), 403

    updates = {
        "status": new_status,
        "evidence": evidence,
        "last_updated_by": f"{agent} ({role})",
        "last_updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    
    if new_status == "completed":
        updates["review_status"] = "pending"

    if res["task_manager"].update_task(task_id, updates):
        event_id = ADSEventSchema.generate_id("task_upd")
        event = ADSEventSchema.create_event(
            event_id=event_id, agent=agent, role=role, action_type="task_status_updated",
            description=f"Task {task_id} marked as {new_status} by {role}.",
            spec_ref=task.get("spec_ref", "SPEC-026"),
            authorized=True, tier=3,
            action_data={"task_id": task_id, "status": new_status, "evidence": evidence}
        )
        res["logger"].log(event)
        return jsonify({"status": "success", "task_id": task_id, "event_id": event_id})
    
    return jsonify({"error": "Failed to update task"}), 500


@governance_bp.route("/governance/requests/<req_id>/status", methods=["PUT"])
@governance_bp.route("/requests/<req_id>/status", methods=["PUT"])
def update_request_status(req_id):
    """SPEC-035: Agent self-service request status update."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    project_name = request.args.get("project") or data.get("project")
    res = _get_project_resources(project_name)
    requests_path = os.path.join(res["paths"]["root"], "_cortex", "requests.md")

    new_status = data.get("status", "COMPLETED").upper()
    agent = data.get("agent")
    role = data.get("role")

    if not agent or not role:
        return jsonify({"error": "agent and role are required"}), 400

    if not os.path.exists(requests_path):
        return jsonify({"error": "requests.md not found"}), 404

    with open(requests_path, "r") as f:
        content = f.read()

    # Find the REQ block
    pattern = rf"## ({req_id}):.*?\n(.*?)\n### Status\n\n\*\*(.*?)\*\*"
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        return jsonify({"error": f"Request {req_id} not found or status section missing"}), 404

    # Extract metadata to check 'To:'
    metadata = match.group(2)
    to_match = re.search(r"\*\*To:\*\* (.*)", metadata)
    to_role = to_match.group(1).strip().lstrip("@") if to_match else "ALL"

    if to_role != "ALL" and to_role.lower() != role.lower():
        return jsonify({"error": f"Request {req_id} is addressed to {to_role}, not {role}"}), 403

    # Update the status
    # We replace the captured status group
    start_of_status = match.start(3)
    end_of_status = match.end(3)
    
    updated_content = content[:start_of_status] + new_status + content[end_of_status:]

    with open(requests_path, "w") as f:
        f.write(updated_content)

    event_id = ADSEventSchema.generate_id("req_upd")
    event = ADSEventSchema.create_event(
        event_id=event_id, agent=agent, role=role, action_type="request_status_updated",
        description=f"Request {req_id} marked as {new_status} by {role}.",
        spec_ref="SPEC-035",
        authorized=True, tier=3,
        action_data={"req_id": req_id, "status": new_status}
    )
    res["logger"].log(event)

    return jsonify({"status": "success", "req_id": req_id, "new_status": new_status, "event_id": event_id})


@governance_bp.route("/tasks/<task_id>/override", methods=["PUT"])
def override_task_status(task_id):
    """SPEC-026: Human override of task status (reject/approve/reassign/reopen)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    # Human-only check (simple localhost/agent header check)
    if request.headers.get("X-Agent"):
        return jsonify({"error": "Override endpoint is human-only"}), 403

    project_name = request.args.get("project")
    res = _get_project_resources(project_name)

    action = data.get("action")
    reason = data.get("reason", "")
    reassign_to = data.get("reassign_to")
    
    task = res["task_manager"].get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    updates = {
        "last_updated_by": "HUMAN",
        "last_updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    event_type = "task_override"

    if action == "approve":
        updates["status"] = "completed"
        updates["review_status"] = "approved"
        event_type = "task_approved"
        desc = f"Human approved completion of {task_id}."
    elif action == "reject":
        if not reason:
            return jsonify({"error": "Reason is required for rejection"}), 400
        updates["status"] = "in_progress"
        updates["review_status"] = "rejected"
        updates["rejection_reason"] = reason
        event_type = "task_rejected"
        desc = f"Human rejected completion of {task_id}: {reason}"
    elif action == "reassign":
        if not reassign_to:
            return jsonify({"error": "reassign_to is required"}), 400
        updates["assigned_to"] = reassign_to
        event_type = "task_reassigned"
        desc = f"Human reassigned {task_id} to {reassign_to}."
    elif action == "reopen":
        updates["status"] = "pending"
        updates.pop("review_status", None)
        event_type = "task_reopened"
        desc = f"Human reopened {task_id}."
    else:
        return jsonify({"error": f"Unknown action: {action}"}), 400

    if res["task_manager"].update_task(task_id, updates):
        event_id = ADSEventSchema.generate_id("task_ovr")
        event = ADSEventSchema.create_event(
            event_id=event_id, agent="HUMAN", role="Collaborator", action_type=event_type,
            description=desc, spec_ref=task.get("spec_ref", "SPEC-026"),
            authorized=True, tier=1,
            action_data={"task_id": task_id, "action": action, "reason": reason}
        )
        res["logger"].log(event)
        return jsonify({"status": "success", "task_id": task_id, "event_id": event_id})
    
    return jsonify({"error": "Failed to update task"}), 500


@governance_bp.route("/governance/enforcement", methods=["GET"])
def get_enforcement_status():
    """SPEC-026: DTTP state and recent denials."""
    project_name = request.args.get("project")
    res = _get_project_resources(project_name)
    
    dttp_url = current_app.config.get("DTTP_URL", "http://localhost:5002")
    # If project is specified and not framework, we should ideally use its DTTP port
    # But for status we might just use the default or derive it
    
    status = {"mode": "unknown", "status": "offline", "protected_paths": {}}
    try:
        resp = http_client.get(f"{dttp_url}/status", timeout=2)
        if resp.ok:
            data = resp.json()
            status["mode"] = data.get("enforcement_mode", "development")
            status["status"] = "active"
    except:
        pass
        
    try:
        policy_resp = http_client.get(f"{dttp_url}/policy", timeout=2)
        if policy_resp.ok:
            status["protected_paths"] = policy_resp.json().get("protected_paths", {})
    except:
        pass
        
    events = res["query"].get_all_events()
    denials = [e for e in events if not e.get("authorized", True)][-10:]
    status["recent_denials"] = denials
    return jsonify(status)

@governance_bp.route("/governance/roles/<role_name>", methods=["PUT"])
def update_role_jurisdiction(role_name):
    """SPEC-026: Update a role's jurisdiction, action types, or lock state."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    jur_path = os.path.join(root, "config", "jurisdictions.json")
    jurisdictions_data = _load_json(jur_path)
    jurisdictions = jurisdictions_data.get("jurisdictions", {})
    
    if role_name not in jurisdictions:
        return jsonify({"error": f"Role {role_name} not found"}), 404
    
    old_config = jurisdictions[role_name]
    if isinstance(old_config, list):
        old_config = {"paths": old_config, "action_types": [], "locked": False}

    if old_config.get("locked", False) and not data.get("unlock", False):
        return jsonify({"error": f"Role {role_name} is locked. Unlock first."}), 403

    new_paths = data.get("paths", old_config.get("paths", []))
    new_actions = data.get("action_types", old_config.get("action_types", []))
    new_locked = data.get("locked", old_config.get("locked", False))

    if not new_paths:
        return jsonify({"error": "Role must have at least one jurisdiction path"}), 400

    sovereign_paths = ["config/specs.json", "config/jurisdictions.json", "config/dttp.json", "_cortex/AI_PROTOCOL.md", "_cortex/MASTER_PLAN.md"]
    for path in new_paths:
        if path in sovereign_paths:
             return jsonify({"error": f"Path {path} is a sovereign path and cannot be assigned to an agent role."}), 400

    jurisdictions[role_name] = {"paths": new_paths, "action_types": new_actions, "locked": new_locked}
    with open(jur_path, "w") as f:
        json.dump({"jurisdictions": jurisdictions}, f, indent=2)

    event_id = ADSEventSchema.generate_id("governance_upd")
    event = ADSEventSchema.create_event(
        event_id=event_id, agent="HUMAN", role="Collaborator", action_type="governance_config_updated",
        description=f"Updated jurisdiction for {role_name}.", spec_ref="SPEC-026",
        authorized=True, tier=1, action_data={"before": old_config, "after": jurisdictions[role_name]}
    )
    res["logger"].log(event)
    return jsonify({"status": "success", "role": role_name, "event_id": event_id})

@governance_bp.route("/governance/specs/<spec_id>/roles", methods=["PUT"])
def update_spec_roles(spec_id):
    """SPEC-026: Update which roles are authorized under a spec."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    specs_path = os.path.join(root, "config", "specs.json")
    specs_config = _load_json(specs_path)
    specs = specs_config.get("specs", {})
    
    if spec_id not in specs:
        return jsonify({"error": f"Spec {spec_id} not found"}), 404
    
    old_spec = specs[spec_id].copy()
    if "roles" in data:
        specs[spec_id]["roles"] = data["roles"]
    if "action_types" in data:
        specs[spec_id]["action_types"] = data["action_types"]

    with open(specs_path, "w") as f:
        json.dump(specs_config, f, indent=2)

    event_id = ADSEventSchema.generate_id("governance_upd")
    event = ADSEventSchema.create_event(
        event_id=event_id, agent="HUMAN", role="Collaborator", action_type="governance_config_updated",
        description=f"Updated role bindings for {spec_id}.", spec_ref="SPEC-026",
        authorized=True, tier=1, action_data={"before": old_spec, "after": specs[spec_id]}
    )
    res["logger"].log(event)
    return jsonify({"status": "success", "spec_id": spec_id, "event_id": event_id})

@governance_bp.route("/governance/conflicts", methods=["GET"])
def get_governance_conflicts():
    """SPEC-026: Detect and return jurisdiction conflicts."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    jur_path = os.path.join(root, "config", "jurisdictions.json")
    specs_path = os.path.join(root, "config", "specs.json")
    jurisdictions = _load_json(jur_path).get("jurisdictions", {})
    specs = _load_json(specs_path).get("specs", {})
    
    conflicts = []
    sovereign_paths = ["config/specs.json", "config/jurisdictions.json", "config/dttp.json", "_cortex/AI_PROTOCOL.md", "_cortex/MASTER_PLAN.md"]
    
    for role, config in jurisdictions.items():
        paths = config if isinstance(config, list) else config.get("paths", [])
        for p in paths:
            if p in sovereign_paths:
                conflicts.append({"type": "sovereign_conflict", "role": role, "path": p, "message": f"Role {role} has access to sovereign path {p}"})
                
    for spec_id, spec in specs.items():
        for role in spec.get("roles", []):
            if role not in jurisdictions:
                conflicts.append({"type": "missing_jurisdiction", "role": role, "spec_id": spec_id, "message": f"Role {role} is authorized in {spec_id} but has no jurisdiction in jurisdictions.json"})
    return jsonify({"conflicts": conflicts})

@governance_bp.route("/requests", methods=["GET"])
@governance_bp.route("/governance/requests", methods=["GET"])
def get_governance_requests():
    """SPEC-028: Get all requests parsed from requests.md."""
    project_name = request.args.get("project")
    role_filter = request.args.get("role")
    
    res = _get_project_resources(project_name)
    requests_path = os.path.join(res["paths"]["root"], "_cortex", "requests.md")
    requests_list = _parse_requests(requests_path)
    
    if role_filter:
        role_filter = role_filter.lower()
        requests_list = [
            r for r in requests_list 
            if r["to"].lower() == role_filter or r["from_role"].lower() == role_filter
        ]
        
    return jsonify({"requests": requests_list})

@governance_bp.route("/delegations", methods=["GET"])
@governance_bp.route("/governance/delegations", methods=["GET"])
def get_delegations():
    """SPEC-028: Get delegation history from ADS + tasks.json."""
    project_name = request.args.get("project")
    res = _get_project_resources(project_name)
    
    # 1. Get from ADS
    events = res["query"].get_all_events()
    delegations = []
    
    for event in events:
        if event.get("action_type") in ["task_status_updated", "task_approved", "task_rejected", "task_reassigned", "task_reopened"]:
            delegations.append({
                "ts": event.get("ts"),
                "task_id": event.get("action_data", {}).get("task_id"),
                "from": event.get("role"),
                "to": event.get("action_data", {}).get("reassign_to") or event.get("role"),
                "action": event.get("action_type"),
                "agent": event.get("agent")
            })
            
    # 2. Get initial delegations from tasks.json
    tasks = res["task_manager"].list_tasks()
    for task in tasks:
        if task.get("delegation"):
            d = task["delegation"]
            delegations.append({
                "ts": d.get("delegated_at"),
                "task_id": task["id"],
                "from": d.get("delegated_by", {}).get("role"),
                "to": d.get("delegated_to", {}).get("role"),
                "action": "task_delegated",
                "agent": d.get("delegated_by", {}).get("agent")
            })
            
    # Sort by timestamp
    delegations.sort(key=lambda x: x.get("ts", ""), reverse=True)
    
    return jsonify({"delegations": delegations})

def _get_scr_path(project_root):
    return os.path.join(project_root, "_cortex", "ops", "sovereign_requests.json")

def _load_scrs(project_root):
    path = _get_scr_path(project_root)
    if not os.path.exists(path):
        return {"requests": []}
    with open(path, "r") as f:
        return json.load(f)

def _save_scrs(project_root, data):
    path = _get_scr_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def _apply_sovereign_change(project_root, request_data):
    """Mechanically applies a sovereign change to a file."""
    target_path = os.path.join(project_root, request_data["target_path"])
    change_type = request_data["change_type"]
    
    if change_type == "patch":
        patch = request_data.get("patch")
        if not patch or "old_string" not in patch or "new_string" not in patch:
            raise ValueError("Invalid patch data")
        
        with open(target_path, "r") as f:
            content = f.read()
            
        if content.count(patch["old_string"]) != 1:
            raise ValueError(f"Patch ambiguity: old_string found {content.count(patch['old_string'])} times")
            
        new_content = content.replace(patch["old_string"], patch["new_string"])
        with open(target_path, "w") as f:
            f.write(new_content)
            
    elif change_type == "append":
        content = request_data.get("content")
        if not content:
            raise ValueError("No content to append")
        with open(target_path, "a") as f:
            f.write(content)
            
    elif change_type == "full_replace":
        content = request_data.get("content")
        if content is None:
            raise ValueError("No content for replacement")
        with open(target_path, "w") as f:
            f.write(content)
            
    elif change_type == "json_merge":
        merge_data = request_data.get("merge_data")
        if not merge_data:
            raise ValueError("No merge data provided")
            
        def deep_merge(base, update):
            for key, value in update.items():
                if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                    deep_merge(base[key], value)
                else:
                    base[key] = value
            return base

        with open(target_path, "r") as f:
            base_data = json.load(f)
            
        updated_data = deep_merge(base_data, merge_data)
        with open(target_path, "w") as f:
            json.dump(updated_data, f, indent=2)
    else:
        raise ValueError(f"Unsupported change type: {change_type}")

@governance_bp.route("/governance/sovereign-requests", methods=["POST"])
def submit_sovereign_request():
    """SPEC-033: Submit a new sovereign change request."""
    data = request.get_json()
    if not data or not all(k in data for k in ["agent", "role", "target_path", "change_type"]):
        return jsonify({"error": "Missing required fields"}), 400
    
    project_name = request.args.get("project") or data.get("project")
    res = _get_project_resources(project_name)
    project_root = res["paths"]["root"]
    
    # Validate target path is actually sovereign
    sovereign_paths = ["config/specs.json", "config/jurisdictions.json", "config/dttp.json", "_cortex/AI_PROTOCOL.md", "_cortex/MASTER_PLAN.md"]
    if data["target_path"] not in sovereign_paths:
        return jsonify({"error": f"Path {data['target_path']} is not a sovereign path"}), 400
        
    scrs = _load_scrs(project_root)
    scr_id = f"scr_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{len(scrs['requests']):03d}"
    
    new_request = {
        "id": scr_id,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "agent": data["agent"],
        "role": data["role"],
        "spec_ref": data.get("spec_ref"),
        "target_path": data["target_path"],
        "change_type": data["change_type"],
        "description": data.get("description", ""),
        "status": "pending",
        "authorized_by": None,
        "authorized_at": None
    }
    
    # Copy payload based on type
    for field in ["patch", "content", "merge_data"]:
        if field in data:
            new_request[field] = data[field]
            
    scrs["requests"].append(new_request)
    _save_scrs(project_root, scrs)
    
    # Log to ADS
    event = ADSEventSchema.create_event(
        event_id=ADSEventSchema.generate_id("scr_prop"),
        agent=data["agent"],
        role=data["role"],
        action_type="sovereign_change_proposed",
        description=f"SCR {scr_id} proposed for {data['target_path']}: {new_request['description']}",
        spec_ref=data.get("spec_ref", "SPEC-033"),
        authorized=True,
        tier=3,
        action_data={"scr_id": scr_id, "target_path": data["target_path"]}
    )
    res["logger"].log(event)
    
    return jsonify({
        "status": "queued",
        "scr_id": scr_id,
        "message": "Change request submitted. Awaiting human authorization in ADT Panel."
    }), 201

@governance_bp.route("/governance/sovereign-requests", methods=["GET"])
def list_sovereign_requests():
    """SPEC-033: List sovereign change requests."""
    project_name = request.args.get("project")
    res = _get_project_resources(project_name)
    scrs = _load_scrs(res["paths"]["root"])
    
    status_filter = request.args.get("status")
    if status_filter:
        filtered = [r for r in scrs["requests"] if r["status"] == status_filter]
        return jsonify({"requests": filtered})
        
    return jsonify(scrs)

@governance_bp.route("/governance/sovereign-requests/<scr_id>", methods=["PUT"])
def manage_sovereign_request(scr_id):
    """SPEC-033: Authorize, reject, or edit a sovereign change request."""
    data = request.get_json()
    if not data or "action" not in data:
        return jsonify({"error": "action is required"}), 400
        
    # Human-only check
    if request.headers.get("X-Agent"):
        return jsonify({"error": "Only humans can manage SCRs"}), 403
        
    project_name = request.args.get("project")
    res = _get_project_resources(project_name)
    project_root = res["paths"]["root"]
    
    scrs = _load_scrs(project_root)
    scr = next((r for r in scrs["requests"] if r["id"] == scr_id), None)
    
    if not scr:
        return jsonify({"error": "SCR not found"}), 404
        
    if scr["status"] != "pending":
        return jsonify({"error": f"SCR is already {scr['status']}"}), 400
        
    action = data["action"]
    if action == "reject":
        scr["status"] = "rejected"
        scr["authorized_by"] = "HUMAN"
        scr["authorized_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        scr["rejection_reason"] = data.get("reason", "")
        
        event = ADSEventSchema.create_event(
            event_id=ADSEventSchema.generate_id("scr_rej"),
            agent="HUMAN",
            role="Collaborator",
            action_type="sovereign_change_rejected",
            description=f"SCR {scr_id} rejected by human. Reason: {scr['rejection_reason']}",
            spec_ref=scr.get("spec_ref", "SPEC-033"),
            authorized=True,
            tier=1,
            action_data={"scr_id": scr_id, "reason": scr["rejection_reason"]}
        )
        res["logger"].log(event)
        
    elif action == "authorize":
        # Check for edited payload
        for field in ["edited_patch", "edited_content", "edited_merge_data"]:
            if field in data:
                original_field = field.replace("edited_", "")
                scr[original_field] = data[field]
                scr["was_edited"] = True
        
        try:
            # Apply the change
            _apply_sovereign_change(project_root, scr)
            
            scr["status"] = "authorized"
            scr["authorized_by"] = "HUMAN"
            scr["authorized_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            
            # Log Authorization
            auth_event = ADSEventSchema.create_event(
                event_id=ADSEventSchema.generate_id("scr_auth"),
                agent="HUMAN",
                role="Collaborator",
                action_type="sovereign_change_authorized",
                description=f"SCR {scr_id} authorized by human for {scr['target_path']}.",
                spec_ref=scr.get("spec_ref", "SPEC-033"),
                authorized=True,
                tier=1,
                action_data={"scr_id": scr_id, "target_path": scr["target_path"]}
            )
            res["logger"].log(auth_event)
            
            # Log Application (as SYSTEM)
            app_event = ADSEventSchema.create_event(
                event_id=ADSEventSchema.generate_id("scr_app"),
                agent="SYSTEM",
                role="Sentry",
                action_type="sovereign_change_applied",
                description=f"File {scr['target_path']} updated via SCR {scr_id}.",
                spec_ref=scr.get("spec_ref", "SPEC-033"),
                authorized=True,
                tier=1,
                action_data={"scr_id": scr_id, "target_path": scr["target_path"]}
            )
            res["logger"].log(app_event)
            
        except Exception as e:
            return jsonify({"error": f"Failed to apply change: {str(e)}"}), 500
    else:
        return jsonify({"error": f"Invalid action: {action}"}), 400
        
    _save_scrs(project_root, scrs)
    return jsonify({"status": "success", "scr_id": scr_id, "new_status": scr["status"]})
