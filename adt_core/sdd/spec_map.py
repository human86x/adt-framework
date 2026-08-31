"""SPEC-111: Spec Map manifest - load, save, validate per-project spec_map.json."""

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default manifest matching SPEC-111 section 3.2.
# NOTE: The example in the spec shows role_categories populated, but section 3.2
# semantics specify that an empty role_categories means "no filter configured".
# The DEFAULT_SPEC_MAP uses empty role_categories so the Bootstrap Wizard fires
# on first open (last_bootstrapped_at is null).
DEFAULT_SPEC_MAP: Dict[str, Any] = {
    "version": 1,
    "role_categories": {},
    "focus_set": [],
    "hide_statuses": ["COMPLETED", "DEPRECATED", "SUPERSEDED"],
    "last_bootstrapped_at": None,
    "last_updated_by": None,
    "last_updated_at": None,
}

_SPEC_MAP_FILENAME = "spec_map.json"


def _spec_map_path(project_root: Path) -> Path:
    return project_root / "_cortex" / _SPEC_MAP_FILENAME


def load_spec_map(project_root: Path) -> Dict[str, Any]:
    """Read _cortex/spec_map.json for the given project root.

    Returns DEFAULT_SPEC_MAP (a deep copy) if the file does not exist or
    cannot be parsed.
    """
    path = _spec_map_path(project_root)
    if not path.exists():
        return dict(DEFAULT_SPEC_MAP)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data
    except Exception as exc:
        logger.warning("spec_map: failed to load %s: %s -- returning defaults", path, exc)
        return dict(DEFAULT_SPEC_MAP)


def validate_spec_map(data: Dict[str, Any]) -> List[str]:
    """Validate a spec_map dict.  Returns a list of error strings (empty if OK)."""
    errors: List[str] = []

    if not isinstance(data, dict):
        errors.append("spec_map must be a JSON object")
        return errors

    if data.get("version") != 1:
        errors.append(f"version must be 1, got {data.get('version')!r}")

    role_categories = data.get("role_categories")
    if not isinstance(role_categories, dict):
        errors.append("role_categories must be an object (dict)")
    else:
        for role, cats in role_categories.items():
            if not isinstance(cats, list):
                errors.append(
                    f"role_categories[{role!r}] must be a list, got {type(cats).__name__}"
                )
            elif not all(isinstance(c, str) for c in cats):
                errors.append(
                    f"role_categories[{role!r}] must be a list of strings"
                )

    focus_set = data.get("focus_set")
    if not isinstance(focus_set, list):
        errors.append("focus_set must be a list")
    elif not all(isinstance(s, str) for s in focus_set):
        errors.append("focus_set must be a list of strings")

    hide_statuses = data.get("hide_statuses")
    if not isinstance(hide_statuses, list):
        errors.append("hide_statuses must be a list")
    elif not all(isinstance(s, str) for s in hide_statuses):
        errors.append("hide_statuses must be a list of strings")

    return errors


def _dict_hash(data: Dict[str, Any]) -> str:
    """Stable SHA-256 hex digest of a JSON-serialised dict."""
    serialised = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()[:16]


def _changed_keys(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    """Return the top-level keys that differ between old and new."""
    all_keys = set(old) | set(new)
    return [k for k in sorted(all_keys) if old.get(k) != new.get(k)]


def save_spec_map(
    project_root: Path,
    data: Dict[str, Any],
    updated_by: str,
) -> Dict[str, Any]:
    """Validate, stamp, and atomically write spec_map.json.

    Raises ValueError listing validation errors if the data is invalid.
    Returns the saved dict (with updated timestamps).
    """
    errors = validate_spec_map(data)
    if errors:
        raise ValueError("Invalid spec_map: " + "; ".join(errors))

    # Stamp provenance fields
    data["last_updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["last_updated_by"] = updated_by

    target = _spec_map_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: write to a temp file in the same directory then rename
    dir_ = str(target.parent)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=dir_,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=True)
        tmp_path = tmp.name

    os.replace(tmp_path, str(target))
    logger.info("spec_map: saved %s by %s", target, updated_by)
    return data
