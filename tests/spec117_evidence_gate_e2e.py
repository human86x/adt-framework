"""SPEC-117 Reconciler Completion Verification Hardening -- E2E Evidence Gate Tests.

Task 9 of SPEC-117: DevOps verification that _verify_completion_evidence enforces
the evidence gate across all refusal and acceptance paths.

Six cases are exercised against synthetic project fixtures under /tmp/spec117_e2e_*:

  Case A -- jurisdiction_blocked (spec sec 3.2):
    ADS log contains dtcp_write_denied in-window. Expect refuse/jurisdiction_blocked.
    Proves the deny signal takes hard precedence over artifact presence.

  Case B -- no_artifact_evidence (spec sec 3.1):
    No jurisdiction denies. Task declares an artifact that does NOT exist on disk.
    Expect refuse/no_artifact_evidence.

  Case C -- preflight_passed (spec sec 3.1 fallback):
    No jurisdiction denies. Task has no artifacts. ADS contains
    task_completed_by_preflight in-window.
    Expect accept/preflight_passed, source=preflight.

  Case D -- artifacts_verified (spec sec 3.1):
    No jurisdiction denies. Task declares an artifact that EXISTS with mtime after
    spawned_at. Expect accept/artifacts_verified, source=artifact.

  Case E -- no_artifact_produced_no_preflight (spec sec 3.3):
    No jurisdiction denies. Task has no artifacts. No preflight event. reconciler_summary=None.
    Expect refuse/no_artifact_produced_no_preflight.

  Case F -- feature_flag_off:
    ADT_RECONCILER_EVIDENCE_REQUIRED=false. Same fixture as Case B.
    Expect accept, source=feature_flag_off. Gate is bypassed by design.

All fixtures are isolated under /tmp/spec117_e2e_<case>/. Fixtures are cleaned up
after tests pass (or on each run start for idempotency).

Run: python tests/spec117_evidence_gate_e2e.py
Exit code: 0 if all pass, 1 if any fail.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Bootstrap: add project root to sys.path so adt_center is importable
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from adt_center.api.build_executor import _verify_completion_evidence  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FIXTURE_BASE = "/tmp/spec117_e2e"
_DENY_TYPES = ["dtcp_write_denied", "path_denied", "jurisdiction_violation"]


def _fixture_path(case: str) -> str:
    return f"{_FIXTURE_BASE}_{case}"


def _clean_fixture(case: str) -> None:
    p = _fixture_path(case)
    if os.path.exists(p):
        shutil.rmtree(p)


def _init_fixture(case: str) -> str:
    """Create a fresh fixture project root for the given case. Returns path."""
    _clean_fixture(case)
    root = _fixture_path(case)
    ads_dir = os.path.join(root, "_cortex", "ads")
    os.makedirs(ads_dir, exist_ok=True)
    cortex_dir = os.path.join(root, "_cortex")
    os.makedirs(cortex_dir, exist_ok=True)
    # Empty events.jsonl and tasks.json
    open(os.path.join(ads_dir, "events.jsonl"), "w").close()
    with open(os.path.join(cortex_dir, "tasks.json"), "w") as f:
        json.dump({"tasks": []}, f)
    return root


def _ads_event(action_type: str, ts: float, task_id: str = None,
               extra_action_data: dict = None) -> dict:
    """Build a minimal valid ADS event dict (for writing to fixture events.jsonl)."""
    ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    ev_id = f"evt_fixture_{action_type}_{int(ts * 1000)}"
    ev = {
        "event_id": ev_id,
        "ts": ts_str,
        "agent": "ANTIGRAVITY",
        "role": "Backend_Engineer",
        "action_type": action_type,
        "spec_ref": "SPEC-117",
        "authorized": False,
        "description": f"fixture event {action_type}",
        "prev_hash": "0" * 64,
        "hash": "0" * 64,
    }
    ad = extra_action_data or {}
    if task_id:
        ad["task_id"] = task_id
    if ad:
        ev["action_data"] = ad
    return ev


def _write_ads_events(root: str, events: list) -> None:
    events_path = os.path.join(root, "_cortex", "ads", "events.jsonl")
    with open(events_path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def _write_tasks(root: str, tasks: list) -> None:
    tasks_path = os.path.join(root, "_cortex", "tasks.json")
    with open(tasks_path, "w") as f:
        json.dump({"tasks": tasks}, f, indent=2)


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

_PASS = 0
_FAIL = 0
_RESULTS: list[tuple[str, str, str]] = []  # (case, PASS/FAIL, detail)


def _assert(case: str, label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"[{case}] {label}: {detail}")


def _run_case(name: str, fn) -> None:
    global _PASS, _FAIL
    try:
        result = fn()
        _PASS += 1
        _RESULTS.append((name, "PASS", str(result or "")))
        print(f"  PASS  {name}")
    except AssertionError as exc:
        _FAIL += 1
        _RESULTS.append((name, "FAIL", str(exc)))
        print(f"  FAIL  {name}: {exc}")
    except Exception as exc:
        _FAIL += 1
        msg = f"EXCEPTION: {exc}\n{traceback.format_exc()}"
        _RESULTS.append((name, "FAIL", msg))
        print(f"  FAIL  {name}: {msg}")


# ---------------------------------------------------------------------------
# Case A -- jurisdiction_blocked
# SPEC-117 sec 3.2: a dtcp_write_denied in-window hard-fails regardless of
# artifact presence. The denied_events list must be non-empty.
# ---------------------------------------------------------------------------

def case_A():
    """Case A: jurisdiction_blocked -- deny event in-window forces refuse."""
    root = _init_fixture("A")
    now = _now()
    spawned_at = now - 30
    exited_at = now - 5

    # ADS: write a dtcp_write_denied inside the execution window
    deny_ev = _ads_event("dtcp_write_denied", ts=now - 20)
    _write_ads_events(root, [deny_ev])

    # tasks.json: task_test_A has an artifact that DOES exist (deny must take precedence)
    artifact_rel = "existing_artifact.py"
    artifact_abs = os.path.join(root, artifact_rel)
    with open(artifact_abs, "w") as f:
        f.write("# exists\n")
    # Set mtime to inside the window
    os.utime(artifact_abs, (now - 10, now - 10))
    _write_tasks(root, [{
        "id": "task_test_A",
        "title": "Task A",
        "acceptance_criteria": [{"path": artifact_rel}],
    }])

    result = _verify_completion_evidence(
        project_root=root,
        task_ids=["task_test_A"],
        spawned_at=spawned_at,
        exited_at=exited_at,
        reconciler_summary=None,
    )

    _assert("A", "decision==refuse", result["decision"] == "refuse",
            f"got decision={result['decision']!r}")
    _assert("A", "reason==jurisdiction_blocked", result["reason"] == "jurisdiction_blocked",
            f"got reason={result['reason']!r}")
    ev_list = result.get("evidence", {}).get("denied_events", [])
    _assert("A", "denied_events non-empty", len(ev_list) > 0,
            f"denied_events={ev_list!r}")
    return f"decision={result['decision']} reason={result['reason']} denied={ev_list}"


# ---------------------------------------------------------------------------
# Case B -- no_artifact_evidence
# SPEC-117 sec 3.1: artifact declared in acceptance_criteria but file absent.
# ---------------------------------------------------------------------------

def case_B(flag_val: str = "true"):
    """Case B: no_artifact_evidence -- declared artifact missing from disk."""
    root = _init_fixture("B")
    now = _now()
    spawned_at = now - 30
    exited_at = now - 5

    # ADS: no deny events
    _write_ads_events(root, [])

    nonexistent = "src/nonexistent_file.py"
    _write_tasks(root, [{
        "id": "task_test_B",
        "title": "Task B",
        "acceptance_criteria": [{"path": nonexistent}],
    }])

    env_orig = os.environ.get("ADT_RECONCILER_EVIDENCE_REQUIRED")
    os.environ["ADT_RECONCILER_EVIDENCE_REQUIRED"] = flag_val
    try:
        result = _verify_completion_evidence(
            project_root=root,
            task_ids=["task_test_B"],
            spawned_at=spawned_at,
            exited_at=exited_at,
            reconciler_summary=None,
        )
    finally:
        if env_orig is None:
            os.environ.pop("ADT_RECONCILER_EVIDENCE_REQUIRED", None)
        else:
            os.environ["ADT_RECONCILER_EVIDENCE_REQUIRED"] = env_orig

    return result


def run_case_B():
    """Case B runner (flag on)."""
    result = case_B(flag_val="true")
    _assert("B", "decision==refuse", result["decision"] == "refuse",
            f"got decision={result['decision']!r}")
    _assert("B", "reason==no_artifact_evidence", result["reason"] == "no_artifact_evidence",
            f"got reason={result['reason']!r}")
    missing = result.get("evidence", {}).get("missing_artifacts", [])
    _assert("B", "missing_artifacts non-empty", len(missing) > 0,
            f"missing_artifacts={missing!r}")
    _assert("B", "nonexistent path in missing", any("nonexistent_file.py" in m for m in missing),
            f"missing={missing!r}")
    return f"decision={result['decision']} reason={result['reason']} missing={missing}"


# ---------------------------------------------------------------------------
# Case C -- preflight_passed
# SPEC-117 sec 3.1 fallback: task has no artifacts; preflight event in-window.
# ---------------------------------------------------------------------------

def case_C():
    """Case C: preflight_passed -- task_completed_by_preflight in-window."""
    root = _init_fixture("C")
    now = _now()
    spawned_at = now - 30
    exited_at = now - 5

    # ADS: task_completed_by_preflight for task_test_C inside window
    preflight_ev = _ads_event(
        "task_completed_by_preflight",
        ts=now - 15,
        task_id="task_test_C",
    )
    _write_ads_events(root, [preflight_ev])

    # tasks.json: task_test_C has NO artifacts
    _write_tasks(root, [{
        "id": "task_test_C",
        "title": "Task C (preflight no-op)",
        "acceptance_criteria": [],
    }])

    result = _verify_completion_evidence(
        project_root=root,
        task_ids=["task_test_C"],
        spawned_at=spawned_at,
        exited_at=exited_at,
        reconciler_summary=None,
    )

    _assert("C", "decision==accept", result["decision"] == "accept",
            f"got decision={result['decision']!r}")
    _assert("C", "reason==preflight_passed", result["reason"] == "preflight_passed",
            f"got reason={result['reason']!r}")
    _assert("C", "source==preflight", result.get("source") == "preflight",
            f"got source={result.get('source')!r}")
    return f"decision={result['decision']} reason={result['reason']} source={result.get('source')}"


# ---------------------------------------------------------------------------
# Case D -- artifacts_verified
# SPEC-117 sec 3.1: declared artifact exists with mtime after spawned_at.
# ---------------------------------------------------------------------------

def case_D():
    """Case D: artifacts_verified -- declared artifact present and fresh."""
    root = _init_fixture("D")
    now = _now()
    spawned_at = now - 30
    exited_at = now - 5

    # ADS: no deny events
    _write_ads_events(root, [])

    # Create the artifact with mtime AFTER spawned_at
    artifact_rel = "existing.py"
    artifact_abs = os.path.join(root, artifact_rel)
    with open(artifact_abs, "w") as f:
        f.write("# real output\n")
    fresh_mtime = spawned_at + 10  # 10 seconds after spawn
    os.utime(artifact_abs, (fresh_mtime, fresh_mtime))

    _write_tasks(root, [{
        "id": "task_test_D",
        "title": "Task D",
        "acceptance_criteria": [{"path": artifact_rel}],
    }])

    result = _verify_completion_evidence(
        project_root=root,
        task_ids=["task_test_D"],
        spawned_at=spawned_at,
        exited_at=exited_at,
        reconciler_summary=None,
    )

    _assert("D", "decision==accept", result["decision"] == "accept",
            f"got decision={result['decision']!r}")
    _assert("D", "reason==artifacts_verified", result["reason"] == "artifacts_verified",
            f"got reason={result['reason']!r}")
    _assert("D", "source==artifact", result.get("source") == "artifact",
            f"got source={result.get('source')!r}")
    return f"decision={result['decision']} reason={result['reason']} source={result.get('source')}"


# ---------------------------------------------------------------------------
# Case E -- no_artifact_produced_no_preflight
# SPEC-117 sec 3.3: no denies, task has no artifacts, no preflight, summary=None.
# ---------------------------------------------------------------------------

def case_E():
    """Case E: no_artifact_produced_no_preflight -- empty worker, no preflight."""
    root = _init_fixture("E")
    now = _now()
    spawned_at = now - 30
    exited_at = now - 5

    # ADS: no events at all
    _write_ads_events(root, [])

    # tasks.json: task_test_E has no artifacts
    _write_tasks(root, [{
        "id": "task_test_E",
        "title": "Task E (empty worker)",
        "acceptance_criteria": [],
    }])

    result = _verify_completion_evidence(
        project_root=root,
        task_ids=["task_test_E"],
        spawned_at=spawned_at,
        exited_at=exited_at,
        reconciler_summary=None,
    )

    _assert("E", "decision==refuse", result["decision"] == "refuse",
            f"got decision={result['decision']!r}")
    _assert("E", "reason==no_artifact_produced_no_preflight",
            result["reason"] == "no_artifact_produced_no_preflight",
            f"got reason={result['reason']!r}")
    return f"decision={result['decision']} reason={result['reason']}"


# ---------------------------------------------------------------------------
# Case F -- feature_flag_off
# When ADT_RECONCILER_EVIDENCE_REQUIRED=false the gate is bypassed entirely.
# Same fixture as Case B (artifact missing) but gate accepts.
# ---------------------------------------------------------------------------

def case_F():
    """Case F: feature_flag_off -- gate bypassed, always accept."""
    result = case_B(flag_val="false")
    _assert("F", "decision==accept", result["decision"] == "accept",
            f"got decision={result['decision']!r}")
    _assert("F", "source==feature_flag_off", result.get("source") == "feature_flag_off",
            f"got source={result.get('source')!r}")
    return f"decision={result['decision']} source={result.get('source')}"


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def _cleanup_all():
    for case in ("A", "B", "C", "D", "E", "F"):
        _clean_fixture(case)


# ---------------------------------------------------------------------------
# ADS reporting helper
# ---------------------------------------------------------------------------

def _log_ads_event(action_type: str, description: str, action_data: dict) -> str:
    """Post an ADS event to DTCP at :5002. Returns event_id or '' on failure."""
    import urllib.request
    import urllib.error
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    ev_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
    ev_id = f"evt_{ev_ts}_{action_type[:12]}"
    payload = {
        "event_id": ev_id,
        "ts": ts,
        "agent": "CLAUDE",
        "role": "DevOps_Engineer",
        "action_type": action_type,
        "spec_ref": "SPEC-117",
        "session_id": "sess_devops_20260829_spec117_task9_claude",
        "parent_session_id": "sess_arch_20260829_121818_claude",
        "authorized": True,
        "description": description,
        "action_data": action_data,
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:5002/log",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode())
            return body.get("event_id", ev_id)
    except Exception as exc:
        print(f"  [ADS log warn] {exc}")
        return ev_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("SPEC-117 Evidence Gate E2E Tests")
    print("=" * 60)

    # Idempotent: clean any leftover fixtures from a prior run
    _cleanup_all()

    _run_case("Case A -- jurisdiction_blocked", case_A)
    _run_case("Case B -- no_artifact_evidence", run_case_B)
    _run_case("Case C -- preflight_passed", case_C)
    _run_case("Case D -- artifacts_verified", case_D)
    _run_case("Case E -- no_artifact_produced_no_preflight", case_E)
    _run_case("Case F -- feature_flag_off", case_F)

    print()
    print("=" * 60)
    print(f"Results: {_PASS} PASS, {_FAIL} FAIL")
    print("=" * 60)

    if _FAIL == 0:
        _cleanup_all()
        print("All fixtures cleaned up.")
        verdict = "all_pass"
    else:
        print("Some tests FAILED -- fixtures left in /tmp/spec117_e2e_* for inspection.")
        verdict = "partial_fail"

    # Log session_delegation_complete to ADS
    result_lines = [f"{r[1]} {r[0]}: {r[2]}" for r in _RESULTS]
    _log_ads_event(
        action_type="session_delegation_complete",
        description=f"SPEC-117 task_9 E2E tests complete: {_PASS} PASS {_FAIL} FAIL",
        action_data={
            "task": "task_9",
            "spec": "SPEC-117",
            "authority": "operator_sovereign_override_for_SPEC-117",
            "verdict": verdict,
            "pass_count": _PASS,
            "fail_count": _FAIL,
            "case_results": result_lines,
        },
    )

    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
