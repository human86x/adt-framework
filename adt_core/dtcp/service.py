"""
DTCP Standalone Service

Thin HTTP wrapper around the DTCPGateway. Runs as an independent process.

Usage:
    python -m adt_core.dtcp.service                          # auto-detect from cwd
    python -m adt_core.dtcp.service --project-root /path     # explicit project root
    python -m adt_core.dtcp.service --port 5002              # custom port
"""
import argparse
import logging
import os
import time
from datetime import datetime, timezone

from flask import Flask, request, jsonify

from adt_core.ads.logger import ADSLogger
from adt_core.sdd.validator import SpecValidator
from adt_core.dtcp.config import DTCPConfig
from adt_core.dtcp.jurisdictions import JurisdictionManager
from adt_core.dtcp.policy import PolicyEngine
from adt_core.dtcp.actions import ActionHandler
from adt_core.dtcp.gateway import DTCPGateway

logger = logging.getLogger(__name__)


def create_dtcp_app(config: DTCPConfig) -> Flask:
    """Create the standalone DTCP Flask application."""
    app = Flask(__name__)
    app.config["DTCP"] = config

    # Initialize engines
    from adt_core.sdd.tasks import TaskManager
    tasks_path = os.path.join(config.project_root, "_cortex", "tasks.json")
    task_manager = TaskManager(tasks_path, project_name=config.project_name)
    
    delegation_policy_path = os.path.join(config.project_root, "config", "delegation_policy.json")

    from adt_core.ads.query import ADSQuery
    ads_query = ADSQuery(config.ads_path)
    
    ads_logger = ADSLogger(config.ads_path)
    validator = SpecValidator(config.specs_config)
    jurisdictions = JurisdictionManager(config.jurisdictions_config)
    policy_engine = PolicyEngine(validator, jurisdictions, task_manager=task_manager, delegation_policy_path=delegation_policy_path, ads_query=ads_query)
    action_handler = ActionHandler(config.project_root)
    gateway = DTCPGateway(policy_engine, action_handler, ads_logger, is_framework=config.is_framework_project)

    # Store on app for access in routes
    app.dtcp_gateway = gateway
    app.dtcp_validator = validator
    app.dtcp_jurisdictions = jurisdictions
    app.dtcp_start_time = time.time()
    app.dtcp_stats = {"total_requests": 0, "total_denials": 0}

    # SPEC-020 Amendment B: Load canonical roles for normalization
    try:
        from adt_core.ads.schema import ADSEventSchema
        import json
        with open(config.jurisdictions_config) as f:
            jur_data = json.load(f)
            ADSEventSchema.CANONICAL_ROLES = list(jur_data.get("jurisdictions", {}).keys())
    except Exception as e:
        pass

    @app.route("/request", methods=["POST"])
    def dtcp_request():
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "code": "INVALID_BODY", "message": "Request body must be JSON"}), 400

        # Validate required fields
        required = ["agent", "role", "spec_id", "action", "params", "rationale"]
        for field in required:
            if field not in data:
                return jsonify({"status": "error", "code": "MISSING_FIELD", "message": f"Missing required field: {field}"}), 400

        # Type validation
        if not isinstance(data["params"], dict):
            return jsonify({"status": "error", "code": "INVALID_TYPE", "message": "params must be an object"}), 400
        if not isinstance(data["rationale"], str) or not data["rationale"].strip():
            return jsonify({"status": "error", "code": "INVALID_TYPE", "message": "rationale must be a non-empty string"}), 400

        app.dtcp_stats["total_requests"] += 1

        dry_run = bool(data.get("dry_run", False))
        session_id = data.get("session_id")
        parent_session_id = data.get("parent_session_id")

        result = app.dtcp_gateway.request(
            agent=data["agent"],
            role=data["role"],
            spec_id=data["spec_id"],
            action=data["action"],
            params=data["params"],
            rationale=data["rationale"],
            dry_run=dry_run,
            session_id=session_id,
            parent_session_id=parent_session_id
        )

        if result["status"] == "denied":
            app.dtcp_stats["total_denials"] += 1
            return jsonify(result), 403

        return jsonify(result), 200

    @app.route("/log", methods=["POST"])
    def dtcp_log():
        """Log an arbitrary event to the ADS."""
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "code": "INVALID_BODY", "message": "Request body must be JSON"}), 400

        try:
            # SPEC-020 Amendment B: Normalize role and agent before logging
            from adt_core.ads.schema import ADSEventSchema
            if "agent" in data:
                data["agent"] = ADSEventSchema.normalize_agent(data["agent"])
            if "role" in data:
                data["role"] = ADSEventSchema.normalize_role(data["role"])

            event_id = app.dtcp_gateway.logger.log(data)
            return jsonify({"status": "success", "event_id": event_id}), 200
        except ValueError as e:
            return jsonify({"status": "error", "code": "INVALID_EVENT", "message": str(e)}), 400

    @app.route("/status", methods=["GET"])
    def dtcp_status():
        return jsonify({
            "service": "dtcp",
            "version": "0.1.0",
            "mode": config.mode,
            "enforcement_mode": config.enforcement_mode,
            "project": config.project_name,
            "uptime_seconds": int(time.time() - app.dtcp_start_time),
            "policy_loaded": bool(app.dtcp_validator.get_all_specs()),
            "specs_count": len(app.dtcp_validator.get_all_specs()),
            "jurisdictions_count": len(app.dtcp_jurisdictions.get_jurisdictions()),
            "total_requests": app.dtcp_stats["total_requests"],
            "total_denials": app.dtcp_stats["total_denials"],
        })

    @app.route("/policy", methods=["GET"])
    def dtcp_policy():
        return jsonify({
            "specs": app.dtcp_validator.get_all_specs(),
            "jurisdictions": app.dtcp_jurisdictions.get_jurisdictions(),
            "last_reload": datetime.now(timezone.utc).isoformat(),
        })

    return app


def main():
    parser = argparse.ArgumentParser(description="DTCP Standalone Service")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (default: 5002)")
    parser.add_argument("--project-root", type=str, default=None, help="Project root directory")
    parser.add_argument("--mode", type=str, default=None, choices=["development", "production"], help="Operating mode")
    parser.add_argument("--enforcement-mode", type=str, default=None, choices=["development", "production"], help="Enforcement mode")
    args = parser.parse_args()

    # Build config: env vars first, then CLI args override
    project_root = args.project_root or os.environ.get("DTCP_PROJECT_ROOT", os.getcwd())
    config = DTCPConfig.from_project_root(project_root)

    # Apply env var overrides
    env_config = DTCPConfig.from_env()
    if env_config.port != 5002:
        config.port = env_config.port
    if env_config.mode != "development":
        config.mode = env_config.mode
    if env_config.enforcement_mode != "development":
        config.enforcement_mode = env_config.enforcement_mode

    # CLI args take highest priority
    if args.port is not None:
        config.port = args.port
    if args.mode is not None:
        config.mode = args.mode
    if args.enforcement_mode is not None:
        config.enforcement_mode = args.enforcement_mode

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [DTCP] %(levelname)s %(name)s: %(message)s",
    )

    logger.info("Starting DTCP service on :%d (mode=%s, enforcement=%s, project=%s)", config.port, config.mode, config.enforcement_mode, config.project_name)
    app = create_dtcp_app(config)
    app.run(host="::", port=config.port, debug=(config.mode == "development"), use_reloader=False)


if __name__ == "__main__":
    main()