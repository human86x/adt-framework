"""
SPEC-118: Task-Artifact Binding Derivation Module.

Computes the bound_files list for a task from three sources:
  declared  -- acceptance_criteria.artifacts[]
  detected  -- files whose mtime falls in the worker execution window
  reconciler_landed -- files from build_worker_completed_via_reconciler events

Public API:
    compute_bound_files(task, project_root, ads_events_iter) -> list[dict]
"""

import fnmatch
import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Hard size cap for over-size flag (5 MB)
_DEFAULT_SIZE_CAP = 5 * 1024 * 1024

# Directories to skip entirely during mtime scanning
_SKIP_DIRS = {"venv", "node_modules", ".git", "target", "__pycache__",
              ".tox", ".mypy_cache", "dist", "build", ".cache"}

# Default ignore glob patterns (applied to rel_path)
_DEFAULT_IGNORES = [
    "*.log",
    "*.pyc",
    "__pycache__/**",
    "venv/**",
    "node_modules/**",
    ".git/**",
    "target/**",
    "*.egg-info/**",
    "*.egg-info",
    ".mypy_cache/**",
    ".tox/**",
    "dist/**",
    "build/**",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_bound_files(
    task: Dict[str, Any],
    project_root: str,
    ads_events_iter: Iterator[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return list of bound-file entries for *task*.

    Each entry:
    {
      "path":             <relative to project_root>,
      "sources":          list of "declared" | "detected" | "reconciler_landed",
      "exists":           bool,
      "size":             int,      # bytes; 0 if not exists
      "mtime":            float,    # epoch; 0.0 if not exists
      "sha256_short":     str,      # first 12 chars of sha256; "" if not exists/binary
      "is_binary":        bool,
      "is_over_size_cap": bool,
    }
    Multiple sources for the same path are merged into one entry.
    """
    events = list(ads_events_iter)  # materialise once

    task_id = task.get("id") or task.get("task_id") or ""

    declared = _extract_declared(task)
    window = _find_worker_window(events, task_id)
    detected = _scan_mtimes_in_window(project_root, window) if window else []
    landed = _extract_reconciler_landed(events, task_id)
    ignore_patterns = _load_ignore_list(project_root)

    # Merge into path -> sources dict
    by_path: Dict[str, List[str]] = {}

    for p in declared:
        by_path.setdefault(p, [])
        if "declared" not in by_path[p]:
            by_path[p].append("declared")

    for p in detected:
        by_path.setdefault(p, [])
        if "detected" not in by_path[p]:
            by_path[p].append("detected")

    for p in landed:
        by_path.setdefault(p, [])
        if "reconciler_landed" not in by_path[p]:
            by_path[p].append("reconciler_landed")

    # Filter and annotate
    result = []
    for rel_path, sources in by_path.items():
        if _is_ignored(rel_path, ignore_patterns):
            continue
        meta = _file_metadata(project_root, rel_path)
        result.append({
            "path": rel_path,
            "sources": sources,
            **meta,
        })

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_declared(task: Dict[str, Any]) -> List[str]:
    """Extract declared artifact paths from task.acceptance_criteria."""
    ac = task.get("acceptance_criteria")
    if not ac:
        return []
    out = []
    if isinstance(ac, dict):
        arts = ac.get("artifacts") or []
        for a in arts:
            if isinstance(a, str):
                out.append(a)
            elif isinstance(a, dict):
                p = a.get("path") or a.get("artifact") or a.get("file")
                if p:
                    out.append(p)
    elif isinstance(ac, list):
        for entry in ac:
            if isinstance(entry, str):
                # Heuristic: looks like a path if it has / or a dotted extension
                if "/" in entry or ("." in entry and " " not in entry[:60]):
                    out.append(entry)
            elif isinstance(entry, dict):
                p = entry.get("path") or entry.get("artifact") or entry.get("file")
                if p:
                    out.append(p)
                # Nested artifacts list
                arts = entry.get("artifacts") or []
                for a in arts:
                    if isinstance(a, str):
                        out.append(a)
                    elif isinstance(a, dict):
                        q = a.get("path") or a.get("file")
                        if q:
                            out.append(q)
    return out


def _find_worker_window(
    events: List[Dict[str, Any]],
    task_id: str,
) -> Optional[Tuple[float, float]]:
    """Locate build_worker_spawned and completion events for task_id.

    Returns (spawn_ts_epoch, exit_ts_epoch + 30) or None if not found.
    """
    if not task_id:
        return None

    spawn_ts: Optional[float] = None
    exit_ts: Optional[float] = None

    COMPLETION_TYPES = {
        "build_worker_completed",
        "build_worker_completed_via_reconciler",
        "build_worker_already_done",
        "build_worker_timeout",
        "build_worker_failed",
        "build_worker_silent_exit",
    }

    for ev in events:
        ad = ev.get("action_data") or {}
        ev_task_ids = ad.get("task_ids") or []
        ev_task_id_single = ad.get("task_id")
        mentioned = (task_id in ev_task_ids) or (ev_task_id_single == task_id)

        action = ev.get("action_type", "")

        if action == "build_worker_spawned" and mentioned and spawn_ts is None:
            spawn_ts = _parse_ts(ev.get("ts"))

        if action in COMPLETION_TYPES and mentioned and exit_ts is None:
            exit_ts = _parse_ts(ev.get("ts"))

    if spawn_ts is not None and exit_ts is not None:
        return (spawn_ts, exit_ts + 30.0)
    if spawn_ts is not None:
        # Worker spawned but no completion seen; use now as exit
        return (spawn_ts, time.time() + 30.0)
    return None


def _parse_ts(ts_str: Optional[str]) -> Optional[float]:
    """Parse an ISO-8601 timestamp string to epoch float."""
    if not ts_str:
        return None
    try:
        from datetime import datetime as _dt
        return _dt.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _scan_mtimes_in_window(
    project_root: str,
    window: Tuple[float, float],
) -> List[str]:
    """Walk project files; return rel paths whose mtime is within window."""
    if window is None:
        return []
    start_ts, end_ts = window
    result = []
    for dirpath, dirnames, filenames in os.walk(project_root):
        # Skip heavy directories in-place
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                continue
            if start_ts <= mtime <= end_ts:
                rel = os.path.relpath(full, project_root)
                result.append(rel)
    return result


def _extract_reconciler_landed(
    events: List[Dict[str, Any]],
    task_id: str,
) -> List[str]:
    """Find build_worker_completed_via_reconciler events for task_id.

    Extract landed file paths from action_data if present.
    """
    if not task_id:
        return []
    out = []
    for ev in events:
        if ev.get("action_type") != "build_worker_completed_via_reconciler":
            continue
        ad = ev.get("action_data") or {}
        ev_task_ids = ad.get("task_ids") or []
        ev_task_id_single = ad.get("task_id")
        if task_id not in ev_task_ids and ev_task_id_single != task_id:
            continue
        # Extract file paths if present
        files = ad.get("landed_files") or ad.get("allowed_files") or []
        for f in files:
            if isinstance(f, str):
                out.append(f)
            elif isinstance(f, dict):
                p = f.get("path") or f.get("file")
                if p:
                    out.append(p)
    return out


def _load_ignore_list(project_root: str) -> List[str]:
    """Read _cortex/config/task_bindings_ignore.txt (one glob per line).

    Falls back to _DEFAULT_IGNORES if the file does not exist.
    """
    config_path = os.path.join(project_root, "_cortex", "config", "task_bindings_ignore.txt")
    if not os.path.exists(config_path):
        return list(_DEFAULT_IGNORES)
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        return lines or list(_DEFAULT_IGNORES)
    except Exception:
        return list(_DEFAULT_IGNORES)


def _is_ignored(rel_path: str, patterns: List[str]) -> bool:
    """Return True if rel_path matches any ignore glob pattern."""
    # Normalise separators
    rel_norm = rel_path.replace(os.sep, "/")
    fname = os.path.basename(rel_path)
    for pat in patterns:
        # Pattern with ** matches any depth
        if fnmatch.fnmatch(rel_norm, pat):
            return True
        # Also try matching just the filename
        if fnmatch.fnmatch(fname, pat):
            return True
    return False


def _file_metadata(project_root: str, rel_path: str) -> Dict[str, Any]:
    """Compute file metadata fields.

    Returns:
      exists, size, mtime, sha256_short, is_binary, is_over_size_cap
    """
    full_path = os.path.join(project_root, rel_path)
    if not os.path.exists(full_path):
        return {
            "exists": False,
            "size": 0,
            "mtime": 0.0,
            "sha256_short": "",
            "is_binary": False,
            "is_over_size_cap": False,
        }
    try:
        stat = os.stat(full_path)
        size = stat.st_size
        mtime = stat.st_mtime
    except OSError:
        return {
            "exists": True,
            "size": 0,
            "mtime": 0.0,
            "sha256_short": "",
            "is_binary": False,
            "is_over_size_cap": False,
        }

    is_over_size_cap = size > _DEFAULT_SIZE_CAP

    # Binary detection: NUL byte in first 1024 bytes
    is_binary = False
    sha256_short = ""
    try:
        with open(full_path, "rb") as f:
            header = f.read(1024)
            is_binary = b"\x00" in header
            if not is_binary and not is_over_size_cap:
                # Compute sha256 of entire file
                h = hashlib.sha256(header)
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
                sha256_short = h.hexdigest()[:12]
    except OSError:
        pass

    return {
        "exists": True,
        "size": size,
        "mtime": mtime,
        "sha256_short": sha256_short,
        "is_binary": is_binary,
        "is_over_size_cap": is_over_size_cap,
    }
