"""
SPEC-078 Part D (REQ-121): Worker Interactive Prompt API

Endpoints:
    GET  /api/workers/awaiting_input       — list paused workers
    POST /api/workers/<worker_id>/resume   — SIGCONT (if paused) or ack (if killed)
    POST /api/workers/<worker_id>/cancel   — SIGTERM the worker

The registry is process-local (adt-center is a single Flask process).
Persistence across restarts is intentionally deferred: any worker paused
across a Center restart will be reflected in ADS events and the operator
can find it there. This is the MVP scope agreed for SPEC-078 D.

An `adt_center.api.workers_registry` sub-module holds the in-memory
registry so the watcher (in build_executor) and this route module can
share it without a circular import.
"""
from __future__ import annotations

import os
import signal
import time
from typing import Dict, Any

from flask import Blueprint, jsonify, request, current_app

from adt_center.api.workers_registry import (
    PAUSED_WORKERS,
    mark_resumed,
    mark_cancelled,
)

workers_bp = Blueprint("workers", __name__)


def _append_worker_event(action_type: str, description: str, action_data: Dict[str, Any]) -> None:
    """Thin wrapper around ADSLogger for events we emit from route handlers."""
    try:
        from adt_core.ads.logger import ADSLogger
        from adt_core.ads.schema import ADSEventSchema
        import datetime as _dt
        logger = ADSLogger()
        event = ADSEventSchema.create_event(
            event_id=ADSEventSchema.generate_id("worker"),
            agent="ADT_CENTER",
            role="DevOps_Engineer",
            action_type=action_type,
            description=description,
            spec_ref="SPEC-078",
            authorized=True,
            session_id="workers_api",
            action_data=action_data,
        )
        logger.log(event)
    except Exception as e:  # never let logging failures break the response
        try:
            current_app.logger.warning(f"[workers_api] failed to log {action_type}: {e}")
        except Exception:
            pass


@workers_bp.route("/awaiting_input", methods=["GET"])
def api_workers_awaiting_input():
    """Return the list of workers currently paused awaiting operator input."""
    now = time.time()
    workers = []
    for wid, entry in list(PAUSED_WORKERS.items()):
        # Age is useful for the UI to prioritise oldest first.
        workers.append({
            "worker_id": wid,
            "worker_pid": entry.get("worker_pid"),
            "prompt_type": entry.get("prompt_type"),
            "prompt_url": entry.get("prompt_url"),
            "prompt_text": entry.get("prompt_text"),
            "matched_line": entry.get("matched_line"),
            "hint": entry.get("hint"),
            "spawned_by_spec": entry.get("spawned_by_spec"),
            "project": entry.get("project"),
            "role": entry.get("role"),
            "log_path": entry.get("log_path"),
            "state": entry.get("state", "paused"),
            "paused_at": entry.get("paused_at"),
            "age_sec": int(now - entry.get("paused_at", now)),
        })
    # Oldest first — operators should clear the longest-waiting worker first.
    workers.sort(key=lambda w: w.get("paused_at") or 0)
    return jsonify({"count": len(workers), "workers": workers})


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


@workers_bp.route("/<worker_id>/resume", methods=["POST"])
def api_worker_resume(worker_id):
    entry = PAUSED_WORKERS.get(worker_id)
    if not entry:
        return jsonify({"error": "unknown_worker", "worker_id": worker_id}), 404
    pid = entry.get("worker_pid")
    state = entry.get("state", "paused")

    # Two cases:
    #  1. Worker is SIGSTOP-suspended -> SIGCONT it and let it continue reading.
    #  2. Worker was killed (fallback path when we could not safely SIGSTOP)
    #     -> nothing to resume; just remove from registry so the operator UI
    #     clears the notification. The operator has already re-authenticated
    #     out-of-band; the next spawn will pick up the refreshed token.
    if state == "paused" and pid and _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGCONT)
        except Exception as e:
            return jsonify({"error": "sigcont_failed", "detail": str(e)}), 500
        _append_worker_event(
            "operator_resumed_worker",
            f"Operator resumed worker {worker_id} (pid={pid}, prompt={entry.get('prompt_type')}).",
            {
                "worker_id": worker_id,
                "worker_pid": pid,
                "prompt_type": entry.get("prompt_type"),
                "spawned_by_spec": entry.get("spawned_by_spec"),
                "project": entry.get("project"),
            },
        )
        mark_resumed(worker_id)
        return jsonify({"status": "resumed", "worker_id": worker_id, "pid": pid})

    # Killed / dead path: just clear the entry.
    _append_worker_event(
        "operator_resumed_worker",
        f"Operator acknowledged auth for worker {worker_id} (dead-worker path; next spawn will use refreshed token).",
        {
            "worker_id": worker_id,
            "prompt_type": entry.get("prompt_type"),
            "spawned_by_spec": entry.get("spawned_by_spec"),
            "project": entry.get("project"),
            "note": "worker_was_not_suspended",
        },
    )
    mark_resumed(worker_id)
    return jsonify({"status": "acknowledged", "worker_id": worker_id, "note": "worker_already_dead"})


@workers_bp.route("/<worker_id>/cancel", methods=["POST"])
def api_worker_cancel(worker_id):
    entry = PAUSED_WORKERS.get(worker_id)
    if not entry:
        return jsonify({"error": "unknown_worker", "worker_id": worker_id}), 404
    pid = entry.get("worker_pid")
    reason = (request.get_json(silent=True) or {}).get("reason", "operator_cancelled")

    killed = False
    if pid and _pid_alive(pid):
        try:
            # If suspended, SIGCONT first so SIGTERM is actually delivered.
            try:
                os.kill(pid, signal.SIGCONT)
            except Exception:
                pass
            os.kill(pid, signal.SIGTERM)
            killed = True
        except Exception as e:
            return jsonify({"error": "sigterm_failed", "detail": str(e)}), 500

    _append_worker_event(
        "worker_auth_abandoned",
        f"Operator cancelled worker {worker_id} (pid={pid}, reason={reason}).",
        {
            "worker_id": worker_id,
            "worker_pid": pid,
            "reason": reason,
            "prompt_type": entry.get("prompt_type"),
            "spawned_by_spec": entry.get("spawned_by_spec"),
            "project": entry.get("project"),
            "killed": killed,
        },
    )
    mark_cancelled(worker_id, reason=reason)
    return jsonify({"status": "cancelled", "worker_id": worker_id, "killed": killed})
