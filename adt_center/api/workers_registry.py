"""
SPEC-078 Part D: In-memory registry of workers paused awaiting operator input.

Shared between the watcher (build_executor) that detects prompts and the
route module (workers_routes) that serves the operator UI. Kept as a
separate module to avoid circular imports.

The registry is process-local. When adt-center restarts, any live paused
worker is orphaned — the operator can still see the pause in ADS but
must reap the process manually. This tradeoff is documented; a
persistent registry is a follow-up (not P0).

Auto-cancel: a background reaper checks entries older than
ADT_WORKER_AUTH_TIMEOUT_HOURS (default 24h) and cancels them with a
`worker_auth_abandoned` event. Starts lazily on the first `register()`
call so tests can import the module without side effects.
"""
from __future__ import annotations

import os
import signal
import threading
import time
from typing import Any, Dict, Optional

# worker_id -> entry dict
PAUSED_WORKERS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()
_REAPER_STARTED = False


def _timeout_hours() -> float:
    try:
        return float(os.environ.get("ADT_WORKER_AUTH_TIMEOUT_HOURS", "24"))
    except ValueError:
        return 24.0


def register(
    worker_id: str,
    worker_pid: Optional[int],
    prompt_type: str,
    prompt_url: Optional[str],
    prompt_text: Optional[str],
    matched_line: str,
    hint: str,
    spawned_by_spec: Optional[str],
    project: Optional[str],
    role: Optional[str],
    log_path: Optional[str],
    state: str = "paused",
) -> None:
    """Record a worker that has been paused / killed awaiting operator input."""
    with _LOCK:
        PAUSED_WORKERS[worker_id] = {
            "worker_id": worker_id,
            "worker_pid": worker_pid,
            "prompt_type": prompt_type,
            "prompt_url": prompt_url,
            "prompt_text": prompt_text,
            "matched_line": matched_line,
            "hint": hint,
            "spawned_by_spec": spawned_by_spec,
            "project": project,
            "role": role,
            "log_path": log_path,
            "state": state,
            "paused_at": time.time(),
        }
    _ensure_reaper_started()


def mark_resumed(worker_id: str) -> None:
    with _LOCK:
        PAUSED_WORKERS.pop(worker_id, None)


def mark_cancelled(worker_id: str, reason: str = "operator_cancelled") -> None:
    with _LOCK:
        PAUSED_WORKERS.pop(worker_id, None)


def get(worker_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        entry = PAUSED_WORKERS.get(worker_id)
        return dict(entry) if entry else None


def _ensure_reaper_started() -> None:
    global _REAPER_STARTED
    if _REAPER_STARTED:
        return
    _REAPER_STARTED = True
    t = threading.Thread(target=_reaper_loop, daemon=True, name="worker-auth-reaper")
    t.start()


def _reaper_loop() -> None:
    """Every 5 minutes, cancel entries older than ADT_WORKER_AUTH_TIMEOUT_HOURS."""
    while True:
        try:
            time.sleep(300)
            timeout_sec = _timeout_hours() * 3600.0
            now = time.time()
            expired: list = []
            with _LOCK:
                for wid, entry in list(PAUSED_WORKERS.items()):
                    if (now - entry.get("paused_at", now)) > timeout_sec:
                        expired.append((wid, entry))
            for wid, entry in expired:
                pid = entry.get("worker_pid")
                if pid:
                    try:
                        os.kill(pid, signal.SIGCONT)
                    except Exception:
                        pass
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except Exception:
                        pass
                mark_cancelled(wid, reason="auto_timeout_24h")
                _emit_abandoned(wid, entry)
        except Exception:
            # Never let the reaper die on a transient error.
            time.sleep(30)


def _emit_abandoned(worker_id: str, entry: Dict[str, Any]) -> None:
    try:
        from adt_core.ads.logger import ADSLogger
        from adt_core.ads.schema import ADSEventSchema
        logger = ADSLogger()
        event = ADSEventSchema.create_event(
            event_id=ADSEventSchema.generate_id("worker"),
            agent="ADT_CENTER",
            role="DevOps_Engineer",
            action_type="worker_auth_abandoned",
            description=(
                f"Auto-cancelled worker {worker_id} after "
                f"{_timeout_hours()}h with no operator response."
            ),
            spec_ref="SPEC-078",
            authorized=True,
            session_id="worker_reaper",
            action_data={
                "worker_id": worker_id,
                "worker_pid": entry.get("worker_pid"),
                "prompt_type": entry.get("prompt_type"),
                "spawned_by_spec": entry.get("spawned_by_spec"),
                "project": entry.get("project"),
                "reason": "auto_timeout",
            },
        )
        logger.log(event)
    except Exception:
        pass
