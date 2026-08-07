"""REQ-125 Priority 3: auto-backup on write for Tier-3 JSON state files.

Every write to a load-bearing JSON file is preceded by a copy of the
current file to ``<file>.bak.<epoch_ms>``. The most recent 5 backups are
kept; older ones are pruned. Recovery becomes ``cp <file>.bak.<latest>
<file>``.

We deliberately do NOT use ``os.rename`` for atomicity here -- callers of
``safe_json_write`` frequently want to overwrite an existing file whose
last-known-good bytes we must preserve first. Order is:
    1. copy current file (if exists) to timestamped .bak
    2. write new content atomically via tempfile + rename
    3. prune older .bak files down to ``keep`` most recent
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from typing import Any, List


DEFAULT_KEEP = 5


def _list_backups(path: str) -> List[str]:
    d = os.path.dirname(os.path.abspath(path)) or "."
    base = os.path.basename(path) + ".bak."
    if not os.path.isdir(d):
        return []
    out = []
    for name in os.listdir(d):
        if name.startswith(base):
            out.append(os.path.join(d, name))
    # Sort by suffix (epoch_ms); string sort works because zero-padding
    # isn't required for 13-digit epoch_ms within any reasonable window.
    out.sort()
    return out


def prune_backups(path: str, keep: int = DEFAULT_KEEP) -> List[str]:
    """Delete all but the ``keep`` most recent backups. Returns the list
    of paths that were deleted (best-effort; unlink failures are ignored
    so a locked file cannot break a write)."""
    backups = _list_backups(path)
    if len(backups) <= keep:
        return []
    deleted: List[str] = []
    for old in backups[:-keep]:
        try:
            os.unlink(old)
            deleted.append(old)
        except OSError:
            pass
    return deleted


def safe_json_write(
    path: str,
    obj: Any,
    keep: int = DEFAULT_KEEP,
    indent: int = 2,
) -> str:
    """Backup-then-write a JSON file. Returns the backup path (empty
    string if the target did not exist yet).

    Steps:
      1. If ``path`` exists, copy it to ``<path>.bak.<epoch_ms>``.
      2. Write ``obj`` to ``<path>.tmp.<epoch_ms>`` then atomic rename.
      3. Prune older backups down to ``keep`` most recent.

    Never raises for backup-pruning failures. Write failures propagate.
    """
    path = os.path.abspath(path)
    directory = os.path.dirname(path) or "."
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)

    backup_path = ""
    if os.path.exists(path):
        # High-res timestamp so rapid consecutive writes don't collide.
        ts = int(time.time() * 1000)
        backup_path = f"{path}.bak.{ts}"
        # Guard against collisions from same-millisecond writes.
        while os.path.exists(backup_path):
            ts += 1
            backup_path = f"{path}.bak.{ts}"
        try:
            shutil.copy2(path, backup_path)
        except OSError:
            # Backup best-effort. If it fails (e.g. disk full), we still
            # attempt the write -- worst case operator loses one rotation
            # but doesn't lose the write.
            backup_path = ""

    # Atomic write via NamedTemporaryFile in the same dir (so os.replace
    # stays on-device and is truly atomic).
    fd, tmp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".tmp.",
        dir=directory,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        # Clean up the temp on failure so we don't litter the dir.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    prune_backups(path, keep=keep)
    return backup_path
