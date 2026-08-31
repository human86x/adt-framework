"""DTGP Device Type Template loader and validator.

Templates are YAML files describing a class of devices: capabilities,
identification hints, and procedures. They NEVER contain credentials
or project-specific values.

SPEC-113 ss3.4.
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"id", "name", "capabilities", "procedures"}
REQUIRED_PROCEDURES = {"health"}


def load_template(path: Path) -> dict:
    """Read a YAML template file and return the parsed dict.

    Raises ValueError on parse error or missing file.
    """
    import yaml
    if not path.exists():
        raise ValueError(f"Template file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Template file is not a YAML mapping: {path}")
    return data


def validate_template(data: dict) -> list:
    """Return a list of validation error strings (empty = valid)."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    caps = data.get("capabilities")
    if caps is not None and not isinstance(caps, list):
        errors.append("'capabilities' must be a list")

    procs = data.get("procedures")
    if procs is not None:
        if not isinstance(procs, dict):
            errors.append("'procedures' must be a mapping")
        else:
            for req_proc in REQUIRED_PROCEDURES:
                if req_proc not in procs:
                    errors.append(f"Missing required procedure: {req_proc}")

    return errors


def list_templates(search_dirs: list) -> dict:
    """Walk search_dirs for *.yaml files, return {template_id: template_data}.

    First directory wins on ID collision (higher priority directories listed first).
    Invalid files are logged and skipped.
    """
    templates: dict[str, dict] = {}
    for dir_path in search_dirs:
        p = Path(dir_path)
        if not p.exists():
            continue
        for yaml_file in sorted(p.glob("*.yaml")):
            try:
                data = load_template(yaml_file)
                errs = validate_template(data)
                if errs:
                    logger.warning("Template %s has errors (skipping): %s", yaml_file, errs)
                    continue
                tid = data.get("id")
                if not tid:
                    logger.warning("Template %s has no id field (skipping)", yaml_file)
                    continue
                if tid not in templates:
                    templates[tid] = data
                else:
                    logger.debug(
                        "Template id '%s' already loaded (first-wins), skipping %s",
                        tid, yaml_file,
                    )
            except Exception as exc:
                logger.warning("Failed to load template %s: %s", yaml_file, exc)

    return templates
