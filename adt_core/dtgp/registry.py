"""DTGP Device Instance Registry.

Reads/writes _cortex/devices.json (per-project). Atomic write via tmpfile+rename.
Every mutating operation emits an ADS event.

SPEC-113 ss3.5.
"""
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REQUIRED_INSTANCE_FIELDS = {"type", "jurisdiction", "tier", "access_path"}


def _registry_path(project_root: Path) -> Path:
    return project_root / "_cortex" / "devices.json"


def load_registry(project_root: Path) -> dict:
    """Read _cortex/devices.json; return {} if missing or malformed."""
    rp = _registry_path(project_root)
    if not rp.exists():
        return {}
    try:
        with open(rp, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Could not load device registry at %s: %s", rp, exc)
        return {}


def save_registry(project_root: Path, data: dict):
    """Atomically write data to _cortex/devices.json."""
    rp = _registry_path(project_root)
    rp.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(rp.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, str(rp))
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def validate_instance(instance: dict, templates: dict) -> list:
    """Return list of validation error strings (empty = valid).

    templates: dict returned by templates.list_templates().
    """
    errors = []
    for field in REQUIRED_INSTANCE_FIELDS:
        if field not in instance:
            errors.append(f"Missing required field: {field}")

    itype = instance.get("type")
    if itype and itype not in templates:
        errors.append(f"Unknown device type: '{itype}'. Available: {list(templates.keys())}")

    tier = instance.get("tier")
    if tier is not None and tier not in (1, 2, 3):
        errors.append(f"tier must be 1, 2, or 3 (got {tier!r})")

    jur = instance.get("jurisdiction")
    if jur is not None and not isinstance(jur, list):
        errors.append("'jurisdiction' must be a list of role strings")

    ap = instance.get("access_path")
    if ap is not None and not isinstance(ap, list):
        errors.append("'access_path' must be a list")

    return errors
