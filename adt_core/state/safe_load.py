"""REQ-125 Priority 1: per-read JSON validation with structured errors.

Root cause reference: 2026-08-06 solar_system_1786032782 SPEC-004 build --
workers POSTed to /api/tasks/<id>/progress WITHOUT ?project=, the endpoint
fell back to the framework's own tasks.json (which had two lurking syntax
corruptions), and returned HTTP 500 with a bare parser error. Workers
narrated success because HTTP 500 is indistinguishable from any other
transient failure. Result: 3 tasks marked failed, 1 orphaned in_progress
for 3 hours.

The fix: every read of a load-bearing state file must be wrapped in a
validator that (a) raises ``StateCorruptionError`` carrying the offending
file, parser line/col, and detail, and (b) emits a
``state_corruption_detected`` ADS event with the same payload. Route
handlers convert the exception into an HTTP 503 body with the same shape,
so agents and operators see a structured "state is broken, do not press
on" signal instead of a bare 500.
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterable, List, Optional


class StateCorruptionError(Exception):
    """Raised when a load-bearing JSON file fails to parse.

    Carries structured detail so Flask handlers can render an HTTP 503
    body of the shape:
        {"error":"corrupt_state","file":"<abs_path>","line":X,"col":Y,
         "detail":"<parser message>"}
    """

    def __init__(self, path: str, line: int, col: int, detail: str):
        self.path = os.path.abspath(path) if path else path
        self.line = int(line)
        self.col = int(col)
        self.detail = str(detail)
        super().__init__(
            f"corrupt_state file={self.path} line={self.line} col={self.col}: "
            f"{self.detail}"
        )

    def to_dict(self) -> dict:
        return {
            "error": "corrupt_state",
            "file": self.path,
            "line": self.line,
            "col": self.col,
            "detail": self.detail,
        }


def _emit_ads_event(exc: StateCorruptionError) -> None:
    """Best-effort ADS emit -- never raises. If ADS itself is broken (which
    can happen: the ADS jsonl append path is on the same disk as the state
    files), we swallow the secondary failure. The primary signal to the
    caller is the raised ``StateCorruptionError``.
    """
    try:
        # Local imports to avoid circular deps at module import time.
        from adt_core.ads.logger import ADSLogger
        from adt_core.ads.schema import ADSEventSchema

        framework_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        ads_path = os.path.join(
            framework_root, "_cortex", "ads", "events.jsonl"
        )
        logger = ADSLogger(ads_path)
        event = ADSEventSchema.create_event(
            event_id=ADSEventSchema.generate_id("state_corruption"),
            agent=os.environ.get("ADT_AGENT_LABEL", "SERVER"),
            role="Backend_Engineer",
            action_type="state_corruption_detected",
            description=(
                f"Load-bearing JSON parse failed at "
                f"{os.path.basename(exc.path)}:{exc.line}:{exc.col}"
            ),
            spec_ref="REQ-125",
            action_data=exc.to_dict(),
            tier=3,
        )
        logger.log(event, authorized=True)
    except Exception:
        # State is corrupt AND ADS is broken -- log to stderr and move on.
        # The endpoint 503 is the operator-visible signal that matters.
        import sys
        print(
            f"[REQ-125] state_corruption_detected: {exc}",
            file=sys.stderr,
            flush=True,
        )


def safe_json_load(path: str, default: Any = None) -> Any:
    """Validated read of a load-bearing JSON file.

    Behaviour:

    - File missing: return ``default`` (do NOT raise -- an absent
      tasks.json is a legitimate "empty project" state, not corruption).
    - File present and parses cleanly: return the parsed object.
    - File present but corrupt (JSONDecodeError): emit
      ``state_corruption_detected`` ADS event, raise
      ``StateCorruptionError`` with line/col/detail so the caller returns
      HTTP 503, not 500.

    Any other exception (OSError etc) is left to propagate; those are
    infrastructure failures the caller should see as a 500.
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        exc = StateCorruptionError(
            path=path,
            line=getattr(e, "lineno", 0) or 0,
            col=getattr(e, "colno", 0) or 0,
            detail=e.msg,
        )
        _emit_ads_event(exc)
        raise exc


def validate_json_file(path: str) -> Optional[StateCorruptionError]:
    """Parse a file and return ``None`` if OK, ``StateCorruptionError`` if
    corrupt. Used by ``run_startup_fsck``. Missing files are treated as OK
    (nothing to corrupt yet)."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            json.load(f)
        return None
    except json.JSONDecodeError as e:
        return StateCorruptionError(
            path=path,
            line=getattr(e, "lineno", 0) or 0,
            col=getattr(e, "colno", 0) or 0,
            detail=e.msg,
        )


def run_startup_fsck(paths: Iterable[str]) -> List[StateCorruptionError]:
    """REQ-125 Priority 4 (deferred but scaffolded): walk ``paths`` and
    return a list of ``StateCorruptionError`` for any that fail to parse.
    Callers decide whether to refuse to bind on a non-empty list.
    """
    problems: List[StateCorruptionError] = []
    for p in paths:
        err = validate_json_file(p)
        if err is not None:
            problems.append(err)
    return problems
