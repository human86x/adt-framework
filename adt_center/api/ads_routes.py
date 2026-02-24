from flask import Blueprint, request, jsonify, current_app
from adt_core.ads.query import ADSQuery

ads_bp = Blueprint("ads", __name__)

@ads_bp.route("/events", methods=["GET"])
def get_events():
    project_name = request.args.get("project")
    paths = current_app.get_project_paths(project_name)
    query = ADSQuery(paths["ads"])
    
    agent = request.args.get("agent")
    try:
        limit = request.args.get("limit", type=int)
        if limit is not None and (limit < 1 or limit > 1000):
            return jsonify({"error": "limit must be between 1 and 1000"}), 400
            
        offset = request.args.get("offset", type=int)
        if offset is not None and offset < 0:
            return jsonify({"error": "offset must be non-negative"}), 400
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    role = request.args.get("role")
    action_type = request.args.get("action_type")
    spec_ref = request.args.get("spec_ref")

    events = query.filter_events(
        agent=agent,
        role=role,
        action_type=action_type,
        spec_ref=spec_ref,
        limit=limit,
        offset=offset
    )
    
    return jsonify(events)

@ads_bp.route("/integrity", methods=["GET"])
def check_integrity():
    project_name = request.args.get("project")
    paths = current_app.get_project_paths(project_name)
    from adt_core.ads.integrity import ADSIntegrity
    is_valid, errors = ADSIntegrity.verify_chain(paths["ads"])
    return jsonify({
        "valid": is_valid,
        "errors": errors
    })
