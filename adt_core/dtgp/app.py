"""DTGP Flask Application -- Digital Transformation Gateway Protocol.

Standalone service, port 5003 by default.

Usage:
    python -m adt_core.dtgp.app --port 5003 --project-root /path/to/project

SPEC-113 ss3.1.
"""
import argparse
import logging
import os
import time
from pathlib import Path

from flask import Flask, request, jsonify

from adt_core.dtgp.config import DTGPConfig
from adt_core.dtgp import ads as dtgp_ads
from adt_core.dtgp.templates import list_templates, load_template, validate_template
from adt_core.dtgp.registry import (
    load_registry,
    save_registry,
    validate_instance,
)
from adt_core.dtgp.vault import Vault, VaultError, VaultPermissionError

logger = logging.getLogger(__name__)

_START_TIME = time.time()


def create_dtgp_app(config: DTGPConfig) -> Flask:
    """Construct and return the DTGP Flask application."""
    app = Flask(__name__)
    app.config["DTGP_CONFIG"] = config

    # Initialise vault
    vault = Vault(
        project_id=config.project_id,
        vault_base_dir=config.vault_dir,
        master_key_path=config.master_key_path,
        backend=config.keyring_backend,
    )

    project_root = Path(config.project_root)

    # ------------------------------------------------------------------
    # /health
    # ------------------------------------------------------------------

    @app.route("/health", methods=["GET"])
    def health():
        uptime_s = int(time.time() - _START_TIME)
        return jsonify(
            {
                "status": "ok",
                "version": "0.1.0",
                "service": "dtgp",
                "uptime_s": uptime_s,
                "vault_status": vault.status,
                "project": config.project_name,
                "port": config.port,
            }
        ), 200

    # ------------------------------------------------------------------
    # /templates
    # ------------------------------------------------------------------

    @app.route("/templates", methods=["GET"])
    def get_templates():
        tmpl_map = list_templates(config.template_dirs)
        result = [
            {"id": t["id"], "name": t["name"], "capabilities": t.get("capabilities", [])}
            for t in tmpl_map.values()
        ]
        return jsonify({"templates": result}), 200

    @app.route("/templates/<template_id>", methods=["GET"])
    def get_template(template_id: str):
        tmpl_map = list_templates(config.template_dirs)
        if template_id not in tmpl_map:
            return jsonify({"error": f"Template not found: {template_id}"}), 404
        return jsonify(tmpl_map[template_id]), 200

    # ------------------------------------------------------------------
    # /devices
    # ------------------------------------------------------------------

    @app.route("/devices", methods=["GET"])
    def list_devices():
        devices = load_registry(project_root)
        return jsonify({"devices": devices}), 200

    @app.route("/devices/<target_id>", methods=["GET"])
    def get_device(target_id: str):
        devices = load_registry(project_root)
        if target_id not in devices:
            return jsonify({"error": f"Device not found: {target_id}"}), 404
        return jsonify(devices[target_id]), 200

    @app.route("/devices/<target_id>", methods=["POST"])
    def register_device(target_id: str):
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        tmpl_map = list_templates(config.template_dirs)
        errors = validate_instance(data, tmpl_map)
        if errors:
            return jsonify({"error": "Validation failed", "details": errors}), 422

        devices = load_registry(project_root)
        already_exists = target_id in devices
        devices[target_id] = data
        save_registry(project_root, devices)

        dtgp_ads.log_event(
            "device_registered",
            f"Device registered: {target_id} type={data.get('type','?')}",
            action_data={
                "target_id": target_id,
                "type": data.get("type"),
                "jurisdiction": data.get("jurisdiction"),
                "tier": data.get("tier"),
                "environment": data.get("environment"),
            },
        )

        status_code = 200 if already_exists else 201
        return jsonify({"status": "registered", "target_id": target_id}), status_code

    @app.route("/devices/<target_id>", methods=["PUT"])
    def update_device(target_id: str):
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        devices = load_registry(project_root)
        if target_id not in devices:
            return jsonify({"error": f"Device not found: {target_id}"}), 404

        old = devices[target_id]
        changed_keys = [k for k in data if data[k] != old.get(k)]
        devices[target_id].update(data)
        save_registry(project_root, devices)

        dtgp_ads.log_event(
            "device_updated",
            f"Device updated: {target_id} changed_keys={changed_keys}",
            action_data={"target_id": target_id, "changed_keys": changed_keys},
        )
        return jsonify({"status": "updated", "target_id": target_id, "changed_keys": changed_keys}), 200

    @app.route("/devices/<target_id>", methods=["DELETE"])
    def remove_device(target_id: str):
        devices = load_registry(project_root)
        if target_id not in devices:
            return jsonify({"error": f"Device not found: {target_id}"}), 404

        instance = devices.pop(target_id)

        # Purge any associated credentials from vault
        access_path = instance.get("access_path", [])
        for hop in access_path:
            cref = hop.get("credentials_ref", "")
            if cref.startswith("dtgp://creds/"):
                ref = cref[len("dtgp://creds/"):]
                try:
                    vault.revoke_credential(ref)
                    dtgp_ads.log_event(
                        "credential_revoked",
                        f"Credential auto-revoked on device removal: {ref}",
                        action_data={"ref": ref, "project_id": config.project_id},
                    )
                except Exception as exc:
                    logger.warning("Could not revoke credential %s: %s", ref, exc)

        save_registry(project_root, devices)

        dtgp_ads.log_event(
            "device_removed",
            f"Device removed: {target_id}",
            action_data={"target_id": target_id},
        )
        return jsonify({"status": "removed", "target_id": target_id}), 200

    # ------------------------------------------------------------------
    # /credentials  (write-only -- NO GET)
    # ------------------------------------------------------------------

    @app.route("/credentials", methods=["POST"])
    def store_credential():
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        for field in ("project_id", "ref", "material"):
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        ref = data["ref"]
        material = data["material"]
        project_id = data["project_id"]

        # Use a project-scoped vault when project_id differs from current
        v = _get_vault_for_project(project_id, config)
        try:
            meta = v.store_credential(ref, material)
        except VaultPermissionError as exc:
            return jsonify({"error": str(exc)}), 500
        except VaultError as exc:
            return jsonify({"error": str(exc)}), 500

        target_hint = data.get("target_hint", "")
        dtgp_ads.log_event(
            "credential_stored",
            f"Credential stored: ref={ref} project={project_id}",
            action_data={
                "ref": ref,
                "project_id": project_id,
                "target_hint": target_hint,
                "hash_preview": meta.get("hash_preview"),
                # NEVER log material
            },
        )

        # Return metadata only -- never material
        return jsonify(
            {
                "ref": meta["ref"],
                "created_at": meta["created_at"],
                "hash_preview": meta["hash_preview"],
            }
        ), 201

    @app.route("/credentials/<ref>", methods=["GET"])
    def get_credential_blocked(ref: str):
        """Explicitly blocked -- credentials never leave the vault via HTTP."""
        return jsonify(
            {"error": "Method Not Allowed -- credentials are write-only via HTTP"}
        ), 405

    @app.route("/credentials/<ref>", methods=["PUT"])
    def rotate_credential(ref: str):
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400
        if "material" not in data:
            return jsonify({"error": "Missing required field: material"}), 400
        if "project_id" not in data:
            return jsonify({"error": "Missing required field: project_id"}), 400

        project_id = data["project_id"]
        v = _get_vault_for_project(project_id, config)
        try:
            meta = v.rotate_credential(ref, data["material"])
        except VaultError as exc:
            return jsonify({"error": str(exc)}), 404

        dtgp_ads.log_event(
            "credential_rotated",
            f"Credential rotated: ref={ref} project={project_id}",
            action_data={
                "ref": ref,
                "previous_hash": meta.get("previous_hash"),
                "rotated_at": meta.get("rotated_at"),
            },
        )
        return jsonify(
            {
                "ref": meta["ref"],
                "rotated_at": meta["rotated_at"],
                "previous_hash": meta["previous_hash"],
            }
        ), 200

    @app.route("/credentials/<ref>", methods=["DELETE"])
    def revoke_credential(ref: str):
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400
        if "project_id" not in data:
            return jsonify({"error": "Missing required field: project_id"}), 400

        project_id = data["project_id"]
        v = _get_vault_for_project(project_id, config)
        try:
            meta = v.revoke_credential(ref)
        except VaultError as exc:
            return jsonify({"error": str(exc)}), 404

        dtgp_ads.log_event(
            "credential_revoked",
            f"Credential revoked: ref={ref} project={project_id}",
            action_data={"ref": ref, "revoked_at": meta.get("revoked_at")},
        )
        return jsonify({"ref": meta["ref"], "revoked_at": meta["revoked_at"]}), 200

    return app


def _get_vault_for_project(project_id: str, config: DTGPConfig) -> Vault:
    """Return a Vault instance for the given project_id."""
    return Vault(
        project_id=project_id,
        vault_base_dir=config.vault_dir,
        master_key_path=config.master_key_path,
        backend=config.keyring_backend,
    )


def main():
    parser = argparse.ArgumentParser(description="DTGP Standalone Service")
    parser.add_argument("--port", type=int, default=None, help="Port (default 5003)")
    parser.add_argument("--project-root", type=str, default=None)
    parser.add_argument(
        "--session-id", type=str, default=None,
        help="ADS session ID (auto-generated if omitted)"
    )
    args = parser.parse_args()

    project_root = args.project_root or os.environ.get("DTGP_PROJECT_ROOT", os.getcwd())
    config = DTGPConfig.from_project_root(project_root)

    if args.port is not None:
        config.port = args.port

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [DTGP] %(levelname)s %(name)s: %(message)s",
    )

    # Configure ADS logging
    import uuid
    session_id = (
        args.session_id
        or os.environ.get("DTGP_SESSION_ID")
        or f"dtgp_{uuid.uuid4().hex[:8]}"
    )
    dtgp_ads.configure(session_id=session_id, ads_path=config.ads_path)

    logger.info(
        "Starting DTGP service on port %d (project=%s, vault=%s)",
        config.port, config.project_name, config.vault_dir,
    )

    app = create_dtgp_app(config)
    app.run(
        host="0.0.0.0",
        port=config.port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()
