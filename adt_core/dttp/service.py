"""
DTTP Standalone Service

Thin HTTP wrapper around the DTTPGateway. Runs as an independent process.

Usage:
    python -m adt_core.dttp.service                          # auto-detect from cwd
    python -m adt_core.dttp.service --project-root /path     # explicit project root
    python -m adt_core.dttp.service --port 5002              # custom port
"""
import argparse
import logging
import os
import time
from datetime import datetime, timezone

from flask import Flask, request, jsonify

from adt_core.ads.logger import ADSLogger
from adt_core.sdd.validator import SpecValidator
from .config import DTTPConfig
from .jurisdictions import JurisdictionManager
from .policy import PolicyEngine
from .actions import ActionHandler
from .gateway import DTTPGateway

logger = logging.getLogger(__name__)


def create_dttp_app(config: DTTPConfig) -> Flask:
    """Create the standalone DTTP Flask application."""
    app = Flask(__name__)
    app.config["DTTP"] = config

    # Initialize engines
    ads_logger = ADSLogger(config.ads_path)
    validator = SpecValidator(config.specs_config)
    jurisdictions = JurisdictionManager(config.jurisdictions_config)
    policy_engine = PolicyEngine(validator, jurisdictions)
    action_handler = ActionHandler(config.project_root)
    gateway = DTTPGateway(policy_engine, action_handler, ads_logger)

    # Store on app for access in routes
    app.dttp_gateway = gateway
    app.dttp_validator = validator
    app.dttp_jurisdictions = jurisdictions
    app.dttp_start_time = time.time()
    app.dttp_stats = {"total_requests": 0, "total_denials": 0}

    @app.route("/request", methods=["POST"])
    def dttp_request():
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

        app.dttp_stats["total_requests"] += 1

        result = app.dttp_gateway.request(
            agent=data["agent"],
            role=data["role"],
            spec_id=data["spec_id"],
            action=data["action"],
            params=data["params"],
            rationale=data["rationale"],
        )

        if result["status"] == "denied":
            app.dttp_stats["total_denials"] += 1
            return jsonify(result), 403

        return jsonify(result), 200

    @app.route("/status", methods=["GET"])
    def dttp_status():
        return jsonify({
            "service": "dttp",
            "version": "0.1.0",
            "mode": config.mode,
            "project": config.project_name,
            "uptime_seconds": int(time.time() - app.dttp_start_time),
            "policy_loaded": bool(app.dttp_validator.get_all_specs()),
            "specs_count": len(app.dttp_validator.get_all_specs()),
            "jurisdictions_count": len(app.dttp_jurisdictions.get_jurisdictions()),
            "total_requests": app.dttp_stats["total_requests"],
            "total_denials": app.dttp_stats["total_denials"],
        })

    @app.route("/policy", methods=["GET"])
    def dttp_policy():
        return jsonify({
            "specs": app.dttp_validator.get_all_specs(),
            "jurisdictions": app.dttp_jurisdictions.get_jurisdictions(),
            "last_reload": datetime.now(timezone.utc).isoformat(),
        })

    return app


def main():
    parser = argparse.ArgumentParser(description="DTTP Standalone Service")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (default: 5002)")
    parser.add_argument("--project-root", type=str, default=None, help="Project root directory")
    parser.add_argument("--mode", type=str, default=None, choices=["development", "production"], help="Operating mode")
    args = parser.parse_args()

    # Build config: env vars first, then CLI args override
    project_root = args.project_root or os.environ.get("DTTP_PROJECT_ROOT", os.getcwd())
    config = DTTPConfig.from_project_root(project_root)

    # Apply env var overrides
    env_config = DTTPConfig.from_env()
    if env_config.port != 5002:
        config.port = env_config.port
    if env_config.mode != "development":
        config.mode = env_config.mode

    # CLI args take highest priority
    if args.port is not None:
        config.port = args.port
    if args.mode is not None:
        config.mode = args.mode

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [DTTP] %(levelname)s %(name)s: %(message)s",
    )

    logger.info("Starting DTTP service on :%d (mode=%s, project=%s)", config.port, config.mode, config.project_name)
    app = create_dttp_app(config)
    app.run(host="0.0.0.0", port=config.port, debug=(config.mode == "development"))


if __name__ == "__main__":
    main()
