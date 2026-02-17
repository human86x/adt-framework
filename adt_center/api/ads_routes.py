from flask import Blueprint, request, jsonify, current_app

ads_bp = Blueprint("ads", __name__)

@ads_bp.route("/events", methods=["GET"])
def get_events():
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

    events = current_app.ads_query.filter_events(
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
    from adt_core.ads.integrity import ADSIntegrity
    is_valid, errors = ADSIntegrity.verify_chain(current_app.ads_query.file_path)
    return jsonify({
        "valid": is_valid,
        "errors": errors
    })
