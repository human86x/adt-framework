from flask import Blueprint, request, jsonify, current_app

ads_bp = Blueprint("ads", __name__)

@ads_bp.route("/events", methods=["GET"])
def get_events():
    agent = request.args.get("agent")
    role = request.args.get("role")
    action_type = request.args.get("action_type")
    spec_ref = request.args.get("spec_ref")

    events = current_app.ads_query.filter_events(
        agent=agent,
        role=role,
        action_type=action_type,
        spec_ref=spec_ref
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
