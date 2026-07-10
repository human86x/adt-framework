import logging
import requests as http_client
from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger(__name__)
dtcp_bp = Blueprint("dtcp", __name__)

def _get_dtcp_url(project_name=None):
    """Resolve DTCP URL for a specific project."""
    if not project_name:
        return current_app.config["DTCP_URL"]
        
    project = current_app.project_registry.get_project(project_name)
    if project and project.get("dttp_port"):
        return f"http://localhost:{project['dttp_port']}"
    
    return current_app.config["DTCP_URL"]

@dtcp_bp.route("/request", methods=["POST"])
def dtcp_request():
    """Proxy DTCP requests to the standalone DTCP service."""
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "code": "INVALID_BODY", "message": "No data provided"}), 400

    # Project context
    project_name = request.args.get("project") or data.get("project")
    dtcp_url = _get_dtcp_url(project_name)

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
        resp = http_client.post(f"{dtcp_url}/request", json=data, timeout=10)
        return jsonify(resp.json()), resp.status_code
    except http_client.ConnectionError:
        logger.error("DTCP service unreachable at %s", dtcp_url)
        return jsonify({"status": "error", "code": "DTCP_UNREACHABLE", "message": "DTCP service is not running"}), 503
    except http_client.RequestException as e:
        logger.error("DTCP request failed: %s", e)
        return jsonify({"status": "error", "code": "DTCP_ERROR", "message": str(e)}), 502


@dtcp_bp.route("/status", methods=["GET"])
def dtcp_status():
    """Proxy status check to the standalone DTCP service."""
    project_name = request.args.get("project")
    dtcp_url = _get_dtcp_url(project_name)
    
    try:
        resp = http_client.get(f"{dtcp_url}/status", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except http_client.ConnectionError:
        return jsonify({
            "status": "offline",
            "project": project_name or current_app.config.get("PROJECT_NAME", "unknown"),
            "message": "DTCP service is not running",
        }), 503
    except http_client.RequestException as e:
        return jsonify({"status": "error", "message": str(e)}), 502
