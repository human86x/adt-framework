import os
import re
import json
import subprocess
import requests as http_client
from datetime import datetime, timezone
from flask import Blueprint, jsonify, current_app, request
from adt_core.ads.schema import ADSEventSchema

governance_bp = Blueprint("governance", __name__)

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
                "date": date,
                "summary": summary[:200]
            })
    return requests_list

@governance_bp.route("/tasks", methods=["GET"])
def get_tasks():
    status = request.args.get("status")
    assigned_to = request.args.get("assigned_to")
    tasks = current_app.task_manager.list_tasks(status=status, assigned_to=assigned_to)
    return jsonify({"tasks": tasks})

@governance_bp.route("/specs", methods=["GET"])
def get_specs():
    specs = current_app.spec_registry.list_specs()
    return jsonify({"specs": specs})

@governance_bp.route("/specs/<spec_id>", methods=["GET"])
def get_spec_detail(spec_id):
    detail = current_app.spec_registry.get_spec_detail(spec_id)
    if not detail:
        return jsonify({"error": "Spec not found"}), 404
    return jsonify(detail)

@governance_bp.route("/sessions/start", methods=["POST"])
def session_start():
    data = request.get_json()
    if not data or not all(k in data for k in ["agent", "role", "spec_id"]):
        return jsonify({"error": "Missing agent, role, or spec_id"}), 400
    
    session_id = data.get("session_id", "unknown")
    event_id = ADSEventSchema.generate_id("session_start")
    event = ADSEventSchema.create_event(
        event_id=event_id,
        agent=data["agent"],
        role=data["role"],
        action_type="session_start",
        description=f"Session started: {session_id} for agent {data['agent']} as {data['role']}.",
        spec_ref=data["spec_id"],
        session_id=session_id
    )
    current_app.ads_logger.log(event)
    return jsonify({"status": "success", "event_id": event_id})

@governance_bp.route("/sessions/end", methods=["POST"])
def session_end():
    print("DEBUG: session_end called")
    data = request.get_json()
    if not data or not all(k in data for k in ["agent", "role", "spec_id"]):
        return jsonify({"error": "Missing agent, role, or spec_id"}), 400
    
    session_id = data.get("session_id", "unknown")
    
    # SPEC-023: Mandatory commit enforcement
    force = data.get("force", False)
    if not force:
        try:
            root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
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
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
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
    current_app.ads_logger.log(event)
    return jsonify({"status": "success", "event_id": event_id, "commit_hash": commit_hash})


@governance_bp.route("/specs", methods=["POST"])
def create_spec():
    """SPEC-025: Create a new spec via Panel UI."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

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
    spec_path = os.path.join(current_app.spec_registry.specs_dir, filename)

    for existing in os.listdir(current_app.spec_registry.specs_dir):
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
    current_app.ads_logger.log(event)

    return jsonify({"status": "success", "spec_id": spec_id, "filename": filename, "event_id": event_id}), 201


@governance_bp.route("/requests", methods=["POST"])
def submit_request():
    """SPEC-025: Submit feedback/request via Panel UI."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    author = data.get("author", "Anonymous").strip()
    req_type = data.get("type", "improvement").strip()
    description = data.get("description", "").strip()

    if not description:
        return jsonify({"error": "Description is required"}), 400

    valid_types = ["feature", "bug", "improvement"]
    if req_type not in valid_types:
        req_type = "improvement"

    requests_path = os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
        "_cortex", "requests.md"
    )

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
    current_app.ads_logger.log(event)

    return jsonify({"status": "success", "request_id": req_id, "event_id": event_id}), 201


@governance_bp.route("/governance/roles", methods=["GET"])
def get_governance_roles():
    """SPEC-026: Unified view of role jurisdictions and spec bindings."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
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

    new_status = data.get("status")
    agent = data.get("agent", "unknown")
    role = data.get("role", "unknown")
    evidence = data.get("evidence", "")

    if new_status not in ["completed", "in_progress"]:
        return jsonify({"error": "Agents can only set status to completed or in_progress"}), 400

    task = current_app.task_manager.get_task(task_id)
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

    if current_app.task_manager.update_task(task_id, updates):
        event_id = ADSEventSchema.generate_id("task_upd")
        event = ADSEventSchema.create_event(
            event_id=event_id, agent=agent, role=role, action_type="task_status_updated",
            description=f"Task {task_id} marked as {new_status} by {role}.",
            spec_ref=task.get("spec_ref", "SPEC-026"),
            authorized=True, tier=3,
            action_data={"task_id": task_id, "status": new_status, "evidence": evidence}
        )
        current_app.ads_logger.log(event)
        return jsonify({"status": "success", "task_id": task_id, "event_id": event_id})
    
    return jsonify({"error": "Failed to update task"}), 500


@governance_bp.route("/tasks/<task_id>/override", methods=["PUT"])
def override_task_status(task_id):
    """SPEC-026: Human override of task status (reject/approve/reassign/reopen)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    # Human-only check (simple localhost/agent header check)
    if request.headers.get("X-Agent"):
        return jsonify({"error": "Override endpoint is human-only"}), 403

    action = data.get("action")
    reason = data.get("reason", "")
    reassign_to = data.get("reassign_to")
    
    task = current_app.task_manager.get_task(task_id)
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

    if current_app.task_manager.update_task(task_id, updates):
        event_id = ADSEventSchema.generate_id("task_ovr")
        event = ADSEventSchema.create_event(
            event_id=event_id, agent="HUMAN", role="Collaborator", action_type=event_type,
            description=desc, spec_ref=task.get("spec_ref", "SPEC-026"),
            authorized=True, tier=1,
            action_data={"task_id": task_id, "action": action, "reason": reason}
        )
        current_app.ads_logger.log(event)
        return jsonify({"status": "success", "task_id": task_id, "event_id": event_id})
    
    return jsonify({"error": "Failed to update task"}), 500


@governance_bp.route("/governance/enforcement", methods=["GET"])
def get_enforcement_status():
    """SPEC-026: DTTP state and recent denials."""
    dttp_url = current_app.config.get("DTTP_URL", "http://localhost:5002")
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
        
    events = current_app.ads_query.get_all_events()
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
    current_app.ads_logger.log(event)
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
    current_app.ads_logger.log(event)
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
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    requests_path = os.path.join(root, "_cortex", "requests.md")
    requests_list = _parse_requests(requests_path)
    return jsonify({"requests": requests_list})

@governance_bp.route("/delegations", methods=["GET"])
@governance_bp.route("/governance/delegations", methods=["GET"])
def get_delegations():
    """SPEC-028: Get delegation history from ADS + tasks.json."""
    # 1. Get from ADS
    events = current_app.ads_query.get_all_events()
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
    tasks = current_app.task_manager.list_tasks()
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
