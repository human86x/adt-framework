import json
import os
import re
import logging
from typing import List, Dict, Any, Optional, Tuple

# Cross-platform file locking
try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self, file_path: str, project_name: str = 'unknown'):
        self.file_path = file_path
        self.project_name = project_name
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w') as f:
                json.dump({'project': self.project_name, 'tasks': []}, f, indent=2)

    def list_tasks(self, status: Optional[str] = None, assigned_to: Optional[str] = None) -> List[Dict[str, Any]]:
        with open(self.file_path, 'r') as f:
            self._lock(f)
            try:
                data = json.load(f)
                tasks = data.get('tasks', [])
                if status:
                    tasks = [t for t in tasks if t.get('status') == status]
                if assigned_to:
                    tasks = [t for t in tasks if assigned_to in (t.get('assigned_to') or '')]
                return tasks
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Error reading tasks from {self.file_path}: {e}")
                return []
            finally:
                self._unlock(f)

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        with open(self.file_path, 'r+') as f:
            self._lock(f)
            try:
                data = json.load(f)
                tasks = data.get('tasks', [])
                found = False
                for task in tasks:
                    if task['id'] == task_id:
                        task.update(updates)
                        found = True
                        break
                if found:
                    f.seek(0)
                    json.dump(data, f, indent=2)
                    f.truncate()
                return found
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Error updating task {task_id} in {self.file_path}: {e}")
                return False
            finally:
                self._unlock(f)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        tasks = self.list_tasks()
        for task in tasks:
            if task['id'] == task_id:
                return task
        return None

    def _lock(self, f):
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_EX)
        elif msvcrt:
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(self, f):
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_UN)
        elif msvcrt:
            msvcrt.locking(f.fileno(), msvcrt.LK_ULOCK, 1)

    def get_task_graph(self, spec_id: str, specs_dir: Optional[str] = None) -> Dict[str, Any]:
        """SPEC-062 §2.1: Build a task DAG for *spec_id* using this TaskManager's file.

        Convenience wrapper around the module-level :func:`build_task_graph`.

        Parameters
        ----------
        spec_id:
            The spec to build the graph for.
        specs_dir:
            Optional path to the directory containing spec markdown files.  When
            provided, metadata (title, status, intent) is resolved from the files
            there.  Defaults to the canonical ``_cortex/specs/`` path.
        """
        return build_task_graph(spec_id, tasks_file=self.file_path, specs_dir=specs_dir)


# ---------------------------------------------------------------------------
# SPEC-062 §2.1 — private metadata resolver (no registry dependency)
# ---------------------------------------------------------------------------

def _resolve_spec_metadata(
    spec_id: str,
    specs_dir: str,
) -> Tuple[str, str, str]:
    """Return (title, status, intent) for *spec_id* by scanning *specs_dir*.

    The function scans every ``SPEC-<id>*.md`` file in *specs_dir* looking for
    the one whose filename starts with *spec_id*.  It then extracts:

    * **title** — first ``# SPEC-NNN: …`` heading
    * **status** — first ``**Status:** VALUE`` field
    * **intent** — first ``**Intent:** …`` field (or content after an
      ``## Intent`` / ``## Purpose`` section heading, whichever appears first)

    Returns empty strings for any field that cannot be parsed.
    """
    title = ""
    status = ""
    intent = ""

    if not os.path.isdir(specs_dir):
        return title, status, intent

    # Find the first filename that starts with the spec_id prefix.
    target_path: Optional[str] = None
    for fname in sorted(os.listdir(specs_dir)):
        if fname.startswith(spec_id) and fname.endswith(".md"):
            target_path = os.path.join(specs_dir, fname)
            break

    if target_path is None:
        return title, status, intent

    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as fh:
            # Read up to 4 KB — sufficient to capture all front-matter fields.
            content = fh.read(4096)
    except OSError as exc:
        logger.warning("_resolve_spec_metadata: cannot read %s: %s", target_path, exc)
        return title, status, intent

    # --- title ---------------------------------------------------------------
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()

    # --- status --------------------------------------------------------------
    status_match = re.search(r"\*\*Status:\*\*\s*([A-Z_]+)", content)
    if status_match:
        status = status_match.group(1).strip()

    # --- intent --------------------------------------------------------------
    # Prefer the inline bold-field form: **Intent:** text
    intent_match = re.search(r"\*\*Intent:\*\*\s*(.*)", content)
    if intent_match:
        intent = intent_match.group(1).strip()
    else:
        # Fall back to a section heading: ## Intent or ## Purpose
        section_match = re.search(
            r"^##\s+(?:Intent|Purpose)\s*\n+(.+?)(?:\n##|\Z)",
            content,
            re.DOTALL | re.MULTILINE,
        )
        if section_match:
            # Take only the first non-empty line of the section body.
            for line in section_match.group(1).splitlines():
                line = line.strip()
                if line:
                    intent = line
                    break

    return title, status, intent


# ---------------------------------------------------------------------------
# SPEC-062 §2.1 — standalone helper (no class instance required)
# ---------------------------------------------------------------------------

def build_task_graph(
    spec_id: str,
    tasks_file: Optional[str] = None,
    specs_dir: Optional[str] = None,
    spec_registry=None,
) -> Dict[str, Any]:
    """Return the full task_graph payload for *spec_id* per SPEC-062 §2.1.

    Parameters
    ----------
    spec_id:
        The spec identifier to filter tasks on (e.g. ``"SPEC-062"``).
    tasks_file:
        Absolute path to ``tasks.json``.  Defaults to the canonical ADT
        Framework location ``<project_root>/_cortex/tasks.json`` (resolved
        relative to this module).
    specs_dir:
        Directory containing spec markdown files (``SPEC-NNN_*.md``).  Used
        to resolve title, status, and intent without an external registry.
        Defaults to the canonical ``<project_root>/_cortex/specs/`` path.
    spec_registry:
        Optional :class:`adt_core.sdd.registry.SpecRegistry` instance used
        to enrich the response with spec-level metadata (title, status,
        intent).  When provided its result takes precedence over the
        file-based resolution from *specs_dir*.

    Returns
    -------
    dict
        JSON-serialisable payload matching the schema defined in SPEC-062
        section 2.1::

            {
              "spec_id": str,
              "spec_title": str,
              "spec_status": str,
              "spec_intent": str,
              "rollup": {
                "tasks_total": int,
                "tasks_completed": int,
                "tasks_in_progress": int,
                "tasks_pending": int,
                "percent_complete": int,
              },
              "nodes": [ {task_id, title, role, status, progress,
                           depends_on, spec_section, last_event_id} ],
              "edges": [ {"from": str, "to": str} ],
            }
    """
    # ------------------------------------------------------------------
    # 1. Resolve paths
    # ------------------------------------------------------------------
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.normpath(os.path.join(_this_dir, "..", ".."))

    if tasks_file is None:
        # Canonical location: <repo_root>/_cortex/tasks.json
        tasks_file = os.path.normpath(
            os.path.join(_project_root, "_cortex", "tasks.json")
        )

    if specs_dir is None:
        specs_dir = os.path.normpath(
            os.path.join(_project_root, "_cortex", "specs")
        )

    # ------------------------------------------------------------------
    # 2. Load all tasks
    # ------------------------------------------------------------------
    try:
        with open(tasks_file, "r") as fh:
            raw = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        logger.error("build_task_graph: cannot read %s: %s", tasks_file, exc)
        raw = {}

    all_tasks: List[Dict[str, Any]] = (
        raw.get("tasks", []) if isinstance(raw, dict) else raw
    )

    # ------------------------------------------------------------------
    # 3. Filter to spec_id
    # ------------------------------------------------------------------
    spec_tasks = [t for t in all_tasks if t.get("spec_ref") == spec_id]

    # Index by id for fast lookup
    spec_task_ids = {t["id"] for t in spec_tasks}
    completed_ids = {t["id"] for t in spec_tasks if t.get("status") == "completed"}

    # ------------------------------------------------------------------
    # 4. Derive "ready" status
    #    A task is "ready" if all its depends_on are completed AND
    #    the task itself is still "pending".
    # ------------------------------------------------------------------
    def _effective_status(task: Dict[str, Any]) -> str:
        status = task.get("status", "pending")
        if status != "pending":
            return status
        deps = [d for d in (task.get("depends_on") or []) if d in spec_task_ids]
        if all(d in completed_ids for d in deps):
            return "ready"
        return "pending"

    # ------------------------------------------------------------------
    # 5. Build nodes
    # ------------------------------------------------------------------
    nodes: List[Dict[str, Any]] = []
    for task in spec_tasks:
        effective = _effective_status(task)
        # progress: 100 if completed, else use explicit field, else 0
        progress = 100 if task.get("status") == "completed" else int(
            task.get("progress_pct", task.get("progress", 0)) or 0
        )
        # Only keep intra-spec depends_on for the node metadata
        intra_deps = [d for d in (task.get("depends_on") or []) if d in spec_task_ids]
        nodes.append({
            "task_id": task["id"],
            "title": task.get("title", ""),
            "role": task.get("assigned_to") or task.get("role", ""),
            "status": effective,
            "progress": progress,
            "depends_on": intra_deps,
            "spec_section": task.get("spec_section", ""),
            "last_event_id": task.get("last_event_id", ""),
            # SPEC-062 Amendment D9: per-task progression fields for live map
            "started_at": task.get("started_at"),
            "completed_at": task.get("completed_at"),
            "progress_percent": task.get("progress_percent"),
            "progress_message": task.get("progress_message"),
            "progress_agent": task.get("progress_agent"),
            "progress_updated_at": task.get("progress_updated_at"),
            # SPEC-067-C: routing + escalation state for the spec map UI
            "spec_ref": task.get("spec_ref"),
            "description": task.get("description"),
            "assigned_harness": task.get("assigned_harness"),
            "assigned_model": task.get("assigned_model"),
            "harness_escalation_offered": task.get("harness_escalation_offered"),
            "reconciled_from_failed": task.get("reconciled_from_failed"),
            "auto_retry_count": task.get("auto_retry_count"),
            "last_failed_reason": task.get("last_failed_reason"),
            "risk_level": task.get("risk_level"),
            "acceptance_criteria": task.get("acceptance_criteria"),
        })

    # ------------------------------------------------------------------
    # 6. Build edges (intra-spec only)
    # ------------------------------------------------------------------
    edges: List[Dict[str, str]] = []
    for task in spec_tasks:
        for dep_id in (task.get("depends_on") or []):
            if dep_id in spec_task_ids:
                edges.append({"from": dep_id, "to": task["id"]})

    # ------------------------------------------------------------------
    # 7. Rollup statistics
    # ------------------------------------------------------------------
    total = len(spec_tasks)
    n_completed = sum(1 for t in spec_tasks if t.get("status") == "completed")
    n_in_progress = sum(1 for t in spec_tasks if t.get("status") == "in_progress")
    n_pending = total - n_completed - n_in_progress
    pct = int(100 * n_completed / total) if total else 0

    rollup = {
        "tasks_total": total,
        "tasks_completed": n_completed,
        "tasks_in_progress": n_in_progress,
        "tasks_pending": n_pending,
        "percent_complete": pct,
    }

    # ------------------------------------------------------------------
    # 8. Enrich with spec-level metadata
    #    Primary: parse spec file from specs_dir (no external dependency).
    #    Override: spec_registry, if provided, takes precedence.
    # ------------------------------------------------------------------
    spec_title, spec_status, spec_intent = _resolve_spec_metadata(spec_id, specs_dir)

    if spec_registry is not None:
        try:
            spec_meta = spec_registry.get_spec(spec_id)
            if spec_meta:
                spec_title = spec_meta.get("title", "") or spec_title
                spec_status = spec_meta.get("status", "") or spec_status
                spec_intent = spec_meta.get("intent", "") or spec_intent
        except Exception as exc:  # pragma: no cover
            logger.warning("build_task_graph: spec_registry lookup failed: %s", exc)

    # ------------------------------------------------------------------
    # 9. Assemble and return
    # ------------------------------------------------------------------
    return {
        "spec_id": spec_id,
        "spec_title": spec_title,
        "spec_status": spec_status,
        "spec_intent": spec_intent,
        "rollup": rollup,
        "nodes": nodes,
        "edges": edges,
    }
