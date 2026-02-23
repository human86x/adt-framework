import os
import re
from datetime import datetime
from flask import Blueprint, jsonify, current_app, request
from adt_core.ads.schema import ADSEventSchema

governance_bp = Blueprint("governance", __name__)

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
    data = request.get_json()
    if not data or not all(k in data for k in ["agent", "role", "spec_id"]):
        return jsonify({"error": "Missing agent, role, or spec_id"}), 400
    
    session_id = data.get("session_id", "unknown")
    event_id = ADSEventSchema.generate_id("session_end")
    event = ADSEventSchema.create_event(
        event_id=event_id,
        agent=data["agent"],
        role=data["role"],
        action_type="session_end",
        description=f"Session ended: {session_id} for agent {data['agent']} as {data['role']}.",
        spec_ref=data["spec_id"],
        session_id=session_id
    )
    current_app.ads_logger.log(event)
    return jsonify({"status": "success", "event_id": event_id})


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

    # Validate spec ID format
    if not re.match(r"^SPEC-\d{3}$", spec_id):
        return jsonify({"error": "Invalid spec ID format. Use SPEC-NNN (e.g. SPEC-026)"}), 400

    if not title:
        return jsonify({"error": "Title is required"}), 400

    # Build filename
    safe_title = re.sub(r"[^a-zA-Z0-9_\- ]", "", title).replace(" ", "_").upper()
    filename = f"{spec_id}_{safe_title}.md"
    spec_path = os.path.join(current_app.spec_registry.specs_dir, filename)

    # Prevent overwriting existing specs
    for existing in os.listdir(current_app.spec_registry.specs_dir):
        if existing.startswith(spec_id):
            return jsonify({"error": f"Spec {spec_id} already exists"}), 409

    # Build content if not provided
    if not body:
        body = f"# {spec_id}: {title}\n\n**Status:** {status}\n**Created:** {datetime.utcnow().strftime('%Y-%m-%d')}\n\n---\n\n## 1. Purpose\n\n(Describe the purpose here)\n"

    # Write the spec file
    os.makedirs(os.path.dirname(spec_path), exist_ok=True)
    with open(spec_path, "w") as f:
        f.write(body)

    # Log to ADS
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

    # Determine next REQ number
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
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Build request entry
    entry = f"""

---

## {req_id}: {req_type.title()} Request

**From:** {author}
**Date:** {timestamp}
**Type:** {req_type.upper()}
**Priority:** MEDIUM

### Description

{description}

### Status

**OPEN** -- Submitted via ADT Panel.
"""

    # Append to requests.md
    os.makedirs(os.path.dirname(requests_path), exist_ok=True)
    with open(requests_path, "a") as f:
        f.write(entry)

    # Log to ADS
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
