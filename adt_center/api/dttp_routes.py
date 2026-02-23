import logging
import requests as http_client
from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger(__name__)
dttp_bp = Blueprint("dttp", __name__)

def _get_dttp_url(project_name=None):
    """Resolve DTTP URL for a specific project."""
    if not project_name:
        return current_app.config["DTTP_URL"]
        
    project = current_app.project_registry.get_project(project_name)
    if project and project.get("dttp_port"):
        return f"http://localhost:{project['dttp_port']}"
    
    return current_app.config["DTTP_URL"]

@dttp_bp.route("/request", methods=["POST"])
def dttp_request():
    """Proxy DTTP requests to the standalone DTTP service."""
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "code": "INVALID_BODY", "message": "No data provided"}), 400

    # Project context
    project_name = request.args.get("project") or data.get("project")
    dttp_url = _get_dttp_url(project_name)

    # SPEC-018 Section 3.5: API Input Validation
    rationale = data.get("rationale")
    if not rationale or not isinstance(rationale, str) or len(rationale.strip()) == 0:
        return jsonify({"status": "error", "code": "INVALID_RATIONALE", "message": "Rationale must be a non-empty string"}), 400
    if len(rationale) > 500:
        return jsonify({"status": "error", "code": "RATIONALE_TOO_LONG", "message": "Rationale exceeds 500 characters"}), 400
    
    params = data.get("params")
    if params is not None and not isinstance(params, dict):
        return jsonify({"status": "error", "code": "INVALID_PARAMS", "message": "Params must be a dictionary"}), 400

    try:
        resp = http_client.post(f"{dttp_url}/request", json=data, timeout=10)
        return jsonify(resp.json()), resp.status_code
    except http_client.ConnectionError:
        logger.error("DTTP service unreachable at %s", dttp_url)
        return jsonify({"status": "error", "code": "DTTP_UNREACHABLE", "message": "DTTP service is not running"}), 503
    except http_client.RequestException as e:
        logger.error("DTTP request failed: %s", e)
        return jsonify({"status": "error", "code": "DTTP_ERROR", "message": str(e)}), 502


@dttp_bp.route("/status", methods=["GET"])
def dttp_status():
    """Proxy status check to the standalone DTTP service."""
    project_name = request.args.get("project")
    dttp_url = _get_dttp_url(project_name)
    
    try:
        resp = http_client.get(f"{dttp_url}/status", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except http_client.ConnectionError:
        return jsonify({
            "status": "offline",
            "project": project_name or current_app.config.get("PROJECT_NAME", "unknown"),
            "message": "DTTP service is not running",
        }), 503
    except http_client.RequestException as e:
        return jsonify({"status": "error", "message": str(e)}), 502
