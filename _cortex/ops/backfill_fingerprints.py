#!/usr/bin/env python3
"""SPEC-081 §2 -- one-shot backfill of project_fingerprints.jsonl.

Walks ``/home/human/Projects/*`` looking for
``_cortex/ops/forge_brief.json``. For each one it computes the wish
fingerprint (``intent_description``) and appends a line to
``_cortex/ops/project_fingerprints.jsonl`` under the framework root.

Idempotent: projects already present in the file are skipped, so it is
safe to re-run at any time (nightly cron, after a fresh clone, etc.).

Usage:
    python3 _cortex/ops/backfill_fingerprints.py

Exit code:
    0 on success; 1 on unrecoverable IO error.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set


# Make the framework root importable so ``adt_core.reuse`` resolves when
# this script is invoked directly.
_THIS = os.path.abspath(__file__)
_FRAMEWORK_ROOT = os.path.abspath(os.path.join(os.path.dirname(_THIS), "..", ".."))
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from adt_core.reuse.fingerprint import compute_fingerprint  # noqa: E402


PROJECTS_ROOT = "/home/human/Projects"
FINGERPRINTS_PATH = os.path.join(
    _FRAMEWORK_ROOT, "_cortex", "ops", "project_fingerprints.jsonl"
)


def _last_touched_iso(project_path: str) -> str:
    """Return ISO-8601 UTC mtime of the newest file under ``_cortex/``.

    Falls back to the project dir's own mtime when ``_cortex`` is absent
    or unreadable.
    """
    cortex_dir = os.path.join(project_path, "_cortex")
    newest = 0.0
    if os.path.isdir(cortex_dir):
        for root, _dirs, files in os.walk(cortex_dir):
            for f in files:
                try:
                    m = os.path.getmtime(os.path.join(root, f))
                    if m > newest:
                        newest = m
                except OSError:
                    continue
    if newest == 0.0:
        try:
            newest = os.path.getmtime(project_path)
        except OSError:
            newest = 0.0
    if newest == 0.0:
        return ""
    dt = datetime.fromtimestamp(newest, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _count_specs(project_path: str) -> int:
    d = os.path.join(project_path, "_cortex", "specs")
    if not os.path.isdir(d):
        return 0
    return sum(
        1 for f in os.listdir(d)
        if f.startswith("SPEC-") and f.endswith(".md")
    )


def _count_tasks(project_path: str) -> int:
    p = os.path.join(project_path, "_cortex", "tasks.json")
    if not os.path.isfile(p):
        return 0
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        tasks = data.get("tasks")
        if isinstance(tasks, list):
            return len(tasks)
    return 0


def _existing_project_names(path: str) -> Set[str]:
    names: Set[str] = set()
    if not os.path.isfile(path):
        return names
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                n = obj.get("project_name")
                if n:
                    names.add(n)
    except OSError:
        return names
    return names


def _load_brief(path: str) -> Optional[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _find_briefs(projects_root: str) -> List[str]:
    out: List[str] = []
    if not os.path.isdir(projects_root):
        return out
    for name in sorted(os.listdir(projects_root)):
        p = os.path.join(projects_root, name)
        if not os.path.isdir(p):
            continue
        brief = os.path.join(p, "_cortex", "ops", "forge_brief.json")
        if os.path.isfile(brief):
            out.append(brief)
    return out


def main() -> int:
    briefs = _find_briefs(PROJECTS_ROOT)
    existing = _existing_project_names(FINGERPRINTS_PATH)

    os.makedirs(os.path.dirname(FINGERPRINTS_PATH), exist_ok=True)

    appended = 0
    skipped = 0
    errored = 0

    try:
        f_out = open(FINGERPRINTS_PATH, "a", encoding="utf-8")
    except OSError as e:
        print(f"[backfill_fingerprints] cannot open {FINGERPRINTS_PATH}: {e}",
              file=sys.stderr)
        return 1

    try:
        for brief_path in briefs:
            project_path = os.path.abspath(
                os.path.join(os.path.dirname(brief_path), "..", "..")
            )
            project_name = os.path.basename(project_path)
            if project_name in existing:
                skipped += 1
                continue
            brief = _load_brief(brief_path)
            if not brief:
                errored += 1
                continue
            wish = brief.get("intent_description") or ""
            if not wish:
                errored += 1
                continue
            fp = compute_fingerprint(wish)
            record = {
                "project_name": project_name,
                "fingerprint_hash": fp["hash"],
                "tokens": fp["tokens"],
                "wish_preview": wish[:200],
                "last_touched": _last_touched_iso(project_path),
                "spec_count": _count_specs(project_path),
                "task_count": _count_tasks(project_path),
            }
            f_out.write(json.dumps(record, ensure_ascii=True) + "\n")
            existing.add(project_name)
            appended += 1
    finally:
        f_out.close()

    print(
        f"[backfill_fingerprints] scanned={len(briefs)} appended={appended} "
        f"skipped_existing={skipped} errored={errored} "
        f"output={FINGERPRINTS_PATH}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
