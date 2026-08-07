"""
SPEC-078 Part D (REQ-121): Interactive-prompt watcher for worker subprocesses.

Runs a lightweight thread per spawned worker that polls the log tail every
2 seconds and matches against `adt_sdk.worker_prompts.SIGNATURES`. When a
match fires:

    1. SIGSTOP the worker (fallback to SIGTERM only if SIGSTOP raises).
    2. Register the worker in `workers_registry.PAUSED_WORKERS`.
    3. Emit `worker_awaiting_operator_input` ADS event with the extracted URL.

The watcher exits when:
    - the worker exits on its own (no prompt was detected before exit), OR
    - a prompt was matched (registration + suspend done, one-shot), OR
    - the log file disappears (rotated), OR
    - a `stop_event` is set externally.

The thread is daemonised so it cannot outlive the Flask process.
"""
from __future__ import annotations

import os
import signal
import threading
import time
from typing import Optional

from adt_sdk.worker_prompts import classify_log_tail
from adt_center.api import workers_registry


POLL_INTERVAL_SEC = 2.0
MAX_LIFETIME_SEC = 24 * 3600  # hard ceiling in case caller forgets to stop


def spawn_prompt_watcher(
    proc,
    log_path: str,
    worker_id: str,
    spec_id: Optional[str],
    project: Optional[str],
    role: Optional[str] = None,
    stop_event: Optional[threading.Event] = None,
) -> threading.Thread:
    """Start a daemon thread that watches `proc`'s log for interactive prompts.

    Returns the thread handle (caller usually discards).
    """
    thread = threading.Thread(
        target=_watch_loop,
        args=(proc, log_path, worker_id, spec_id, project, role, stop_event),
        daemon=True,
        name=f"prompt-watcher-{worker_id[:20]}",
    )
    thread.start()
    return thread


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _watch_loop(
    proc,
    log_path: str,
    worker_id: str,
    spec_id: Optional[str],
    project: Optional[str],
    role: Optional[str],
    stop_event: Optional[threading.Event],
) -> None:
    deadline = time.time() + MAX_LIFETIME_SEC
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        if time.time() > deadline:
            return

        # Exit if the worker is dead — nothing to watch.
        try:
            if proc.poll() is not None:
                return
        except Exception:
            return

        match = classify_log_tail(log_path, tail_bytes=6000)
        if match is not None:
            _handle_match(proc, log_path, worker_id, spec_id, project, role, match)
            return  # one-shot: after handling, further watching is redundant.

        time.sleep(POLL_INTERVAL_SEC)


def _handle_match(
    proc,
    log_path: str,
    worker_id: str,
    spec_id: Optional[str],
    project: Optional[str],
    role: Optional[str],
    match,
) -> None:
    """Suspend the worker (or fallback-kill), register it, and emit ADS event."""
    pid = None
    try:
        pid = proc.pid
    except Exception:
        pass

    suspended = False
    kill_fallback = False
    err: Optional[str] = None
    if pid and _pid_alive(pid):
        try:
            # Prefer SIGSTOP so the worker keeps its OAuth session/state and
            # the operator can Resume without a full restart. If it fails
            # (e.g. permissions, unusual harness), fall back to SIGTERM so
            # at LEAST the worker isn't burning its own 60s auth timer.
            os.kill(pid, signal.SIGSTOP)
            suspended = True
        except Exception as e:
            err = f"SIGSTOP failed: {e}"
            try:
                os.kill(pid, signal.SIGTERM)
                kill_fallback = True
            except Exception as e2:
                err = f"SIGSTOP failed ({e}); SIGTERM failed ({e2})"

    state = "paused" if suspended else ("killed" if kill_fallback else "unknown")

    # Register in the paused-worker registry so /api/workers/awaiting_input
    # returns this worker and the Console can surface a modal.
    workers_registry.register(
        worker_id=worker_id,
        worker_pid=pid,
        prompt_type=match.prompt_type,
        prompt_url=match.extracted if match.extracted and match.extracted.startswith("http") else None,
        prompt_text=match.matched_line,
        matched_line=match.matched_line,
        hint=match.hint,
        spawned_by_spec=spec_id,
        project=project,
        role=role,
        log_path=log_path,
        state=state,
    )

    # Emit ADS event. Use adt_core.ads.logger against the project ADS,
    # so it lands in the same events.jsonl the Console already reads.
    _emit_awaiting_event(
        worker_id=worker_id,
        pid=pid,
        match=match,
        spec_id=spec_id,
        project=project,
        role=role,
        state=state,
        err=err,
    )


def _emit_awaiting_event(
    worker_id: str,
    pid: Optional[int],
    match,
    spec_id: Optional[str],
    project: Optional[str],
    role: Optional[str],
    state: str,
    err: Optional[str],
) -> None:
    """Log `worker_awaiting_operator_input` to ADS. Best-effort; never raises."""
    try:
        from adt_core.ads.logger import ADSLogger
        from adt_core.ads.schema import ADSEventSchema
        logger = ADSLogger()  # framework ADS — Console tails this
        desc = (
            f"Worker {worker_id} awaiting operator input "
            f"(prompt_type={match.prompt_type}, state={state}). "
            f"{match.hint}"
        )
        event = ADSEventSchema.create_event(
            event_id=ADSEventSchema.generate_id("worker"),
            agent="ADT_CENTER",
            role=role or "DevOps_Engineer",
            action_type="worker_awaiting_operator_input",
            description=desc,
            spec_ref=spec_id or "SPEC-078",
            authorized=True,
            session_id="workers_watcher",
            action_data={
                "worker_id": worker_id,
                "worker_pid": pid,
                "prompt_type": match.prompt_type,
                "prompt_url": match.extracted if match.extracted and match.extracted.startswith("http") else None,
                "prompt_text": match.matched_line,
                "hint": match.hint,
                "spawned_by_spec": spec_id,
                "project": project,
                "role": role,
                "state": state,
                "suspend_error": err,
            },
        )
        logger.log(event)
    except Exception:
        # Fall back to log_event.py CLI so we still have a record.
        try:
            import subprocess as _sp
            import json as _j
            payload = _j.dumps({
                "worker_id": worker_id,
                "prompt_type": match.prompt_type,
                "prompt_url": match.extracted,
                "hint": match.hint,
                "state": state,
            })
            _sp.run([
                "python3",
                "/home/human/Projects/adt-framework/_cortex/log_event.py",
                "--agent", "ADT_CENTER",
                "--role", role or "DevOps_Engineer",
                "--type", "worker_awaiting_operator_input",
                "--spec", spec_id or "SPEC-078",
                "--description",
                f"Worker {worker_id} awaiting operator input ({match.prompt_type}).",
                "--action_data", payload,
            ], check=False, timeout=15)
        except Exception:
            pass
