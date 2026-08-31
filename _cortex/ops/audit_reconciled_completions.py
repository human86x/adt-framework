#!/usr/bin/env python3
"""SPEC-117 retroactive audit tool: re-verify tasks marked completed via
reconciler in the era before the evidence gate landed.

Walks <project>/_cortex/tasks.json, selects tasks marked completed via
reconciliation, and re-checks each for artifact presence (or preflight pass, or
jurisdiction-deny evidence in the worker's execution window). Emits
task_completion_reaudit_pass / task_completion_reaudit_fail ADS events. With
--commit, reverts failing tasks from 'completed' to 'failed' with the audit
event as authority.

Default is --dry-run. First real target is ADT-framework itself.

Usage:
    python audit_reconciled_completions.py --project . --dry-run
    python audit_reconciled_completions.py --project . --commit
    python audit_reconciled_completions.py --project . --since 2026-08-15
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make adt_core importable when run from anywhere.
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent  # _cortex/ops/ -> repo root
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _iso_utc(epoch=None):
    dt = datetime.fromtimestamp(epoch, timezone.utc) if epoch else datetime.now(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _read_tasks(project_root):
    path = project_root / "_cortex" / "tasks.json"
    if not path.exists():
        return path, {"tasks": []}, []
    with open(path) as f:
        data = json.load(f)
    all_tasks = data.get("tasks", []) if isinstance(data, dict) else data
    return path, data, all_tasks


def _iter_events(project_root):
    """Stream ADS events one at a time. Skips malformed lines."""
    path = project_root / "_cortex" / "ads" / "events.jsonl"
    if not path.exists():
        return
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln or not ln.startswith("{"):
                continue
            try:
                yield json.loads(ln)
            except Exception:
                continue


def _ts_epoch(ts_str):
    if not ts_str:
        return None
    try:
        s = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


DENY_ACTION_TYPES = {
    "dtcp_write_denied", "path_denied",
    "jurisdiction_violation", "sovereign_path_violation",
}


def _build_worker_index(project_root):
    """Index every worker's spawn/exit events by task_id.

    Returns dict[task_id] -> {spawned_at, exited_at, exit_event_id,
                              exit_action_type, role}
    Only keeps the LATEST spawn/exit pair per task_id.
    """
    idx = {}
    spawn_by_key = {}
    for ev in _iter_events(project_root):
        at = ev.get("action_type") or ""
        ad = ev.get("action_data") or {}
        ts = _ts_epoch(ev.get("ts"))
        if ts is None:
            continue
        task_ids = ad.get("task_ids") or ([ad.get("task_id")] if ad.get("task_id") else [])
        if at == "build_worker_spawned":
            for tid in task_ids:
                if not tid:
                    continue
                spawn_by_key[tid] = {"spawned_at": ts, "role": ad.get("role")}
        elif at in ("build_worker_completed_via_reconciler",
                    "build_worker_completed",
                    "build_worker_already_done"):
            for tid in task_ids:
                if not tid:
                    continue
                spawn = spawn_by_key.get(tid) or {}
                idx[tid] = {
                    "spawned_at": spawn.get("spawned_at", ts - 60),
                    "exited_at": ts,
                    "exit_event_id": ev.get("event_id"),
                    "exit_action_type": at,
                    "role": spawn.get("role") or ad.get("role"),
                }
    return idx


def _find_denies_in_window(project_root, start, end):
    hits = []
    for ev in _iter_events(project_root):
        if ev.get("action_type") not in DENY_ACTION_TYPES:
            continue
        ts = _ts_epoch(ev.get("ts"))
        if ts is None:
            continue
        if start <= ts <= end:
            hits.append(ev)
    return hits


def _find_preflight_in_window(project_root, task_id, start, end):
    hits = []
    for ev in _iter_events(project_root):
        if ev.get("action_type") != "task_completed_by_preflight":
            continue
        ts = _ts_epoch(ev.get("ts"))
        if ts is None or not (start <= ts <= end):
            continue
        ad = ev.get("action_data") or {}
        if (ad.get("task_id") or ad.get("id")) == task_id:
            hits.append(ev)
    return hits


def _extract_artifact_paths(acceptance_criteria):
    """Same shape as build_executor._spec117_extract_artifact_paths."""
    if not acceptance_criteria:
        return []
    out = []
    if isinstance(acceptance_criteria, dict):
        arts = acceptance_criteria.get("artifacts") or []
        for a in arts:
            if isinstance(a, str):
                out.append(a)
            elif isinstance(a, dict):
                p = a.get("path") or a.get("artifact") or a.get("file")
                if p:
                    out.append(p)
    elif isinstance(acceptance_criteria, list):
        for entry in acceptance_criteria:
            if isinstance(entry, str):
                if "/" in entry or ("." in entry and " " not in entry[:60]):
                    out.append(entry)
            elif isinstance(entry, dict):
                p = entry.get("path") or entry.get("artifact") or entry.get("file")
                if p:
                    out.append(p)
                arts = entry.get("artifacts") or []
                for a in arts:
                    if isinstance(a, str):
                        out.append(a)
                    elif isinstance(a, dict) and (a.get("path") or a.get("file")):
                        out.append(a.get("path") or a.get("file"))
    return out


def _is_reconciler_completion(task):
    """Detect the reconciler completion pattern in a task record."""
    if task.get("status") != "completed":
        return False
    if task.get("reconciled_from_failed"):
        return True
    for ev in (task.get("reconciliation_evidence") or []):
        if isinstance(ev, dict) and ev.get("source") == "spec105_reconciler":
            return True
    return False


def _audit_one_task(task, worker_ctx, project_root):
    """Return dict describing verdict for a single task."""
    tid = task.get("id") or task.get("task_id")
    verdict = {
        "task_id": tid,
        "role": worker_ctx.get("role") if worker_ctx else task.get("role"),
        "worker_exit_event_id": worker_ctx.get("exit_event_id") if worker_ctx else None,
        "verdict": None,
        "reason": None,
        "detail": {},
    }

    if not worker_ctx:
        # Fallback: no ADS worker events (task pre-dates lifecycle events, or was
        # hand-rescued). Check reconciliation_evidence paths directly.
        rec_evidence = task.get("reconciliation_evidence") or []
        ev_paths = []
        for e in rec_evidence:
            if isinstance(e, dict):
                p = e.get("path") or e.get("artifact") or e.get("file")
                if p and not p.endswith(".log"):
                    ev_paths.append(p)
        if ev_paths:
            missing = [p for p in ev_paths
                       if not (project_root / p).exists()
                       or (project_root / p).stat().st_size == 0]
            if missing:
                verdict["verdict"] = "fail"
                verdict["reason"] = "recorded_evidence_missing"
                verdict["detail"] = {"evidence_paths": ev_paths, "missing": missing}
                return verdict
            verdict["verdict"] = "pass"
            verdict["reason"] = "recorded_evidence_files_present"
            verdict["detail"] = {"evidence_paths": ev_paths}
            return verdict
        verdict["verdict"] = "unknown"
        verdict["reason"] = "no_worker_events_and_no_recorded_evidence"
        verdict["detail"] = {"note": "No worker events located AND task record has no reconciliation_evidence paths."}
        return verdict

    start = worker_ctx["spawned_at"]
    end = worker_ctx["exited_at"] + 30

    # Layer 1: jurisdiction denies in the historical window
    denies = _find_denies_in_window(project_root, start, end)
    if denies:
        verdict["verdict"] = "fail"
        verdict["reason"] = "jurisdiction_blocked"
        verdict["detail"] = {
            "denied_count": len(denies),
            "denied_event_ids": [d.get("event_id") for d in denies[:5]],
            "window_start": _iso_utc(start),
            "window_end": _iso_utc(end),
        }
        return verdict

    # Layer 2: artifact presence (existence-only for retro-audit;
    # mtime may have drifted long since)
    artifacts = _extract_artifact_paths(task.get("acceptance_criteria"))
    if artifacts:
        missing = [a for a in artifacts if not (project_root / a).exists()]
        if missing:
            verdict["verdict"] = "fail"
            verdict["reason"] = "artifacts_missing"
            verdict["detail"] = {"required_artifacts": artifacts, "missing": missing}
            return verdict
        verdict["verdict"] = "pass"
        verdict["reason"] = "artifacts_present"
        verdict["detail"] = {"artifacts_verified": artifacts}
        return verdict

    # Layer 3: preflight pass
    preflight = _find_preflight_in_window(project_root, tid, start, end)
    if preflight:
        verdict["verdict"] = "pass"
        verdict["reason"] = "preflight_recorded"
        verdict["detail"] = {"preflight_event_ids": [p.get("event_id") for p in preflight[:3]]}
        return verdict

    # Layer 4: reconciliation_evidence with allowed_count > 0 already on task
    for ev in (task.get("reconciliation_evidence") or []):
        if isinstance(ev, dict):
            ac = ev.get("allowed_count") or 0
            if ac > 0:
                verdict["verdict"] = "pass"
                verdict["reason"] = "reconciler_evidence_recorded"
                verdict["detail"] = {"allowed_count": ac}
                return verdict

    # Layer 5: nothing
    verdict["verdict"] = "fail"
    verdict["reason"] = "no_artifact_evidence"
    verdict["detail"] = {"note": "No declared artifacts, no preflight pass, no reconciler landed count."}
    return verdict


def _emit_ads_event(project_root, action_type, description, action_data,
                    role="Systems_Architect"):
    """Best-effort ADS emission via local DTCP; falls back to file append."""
    event_id = f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')[:-3]}_{action_type[:12]}"
    payload = {
        "event_id": event_id,
        "ts": _iso_utc(),
        "agent": "CLAUDE",
        "role": role,
        "action_type": action_type,
        "description": description,
        "spec_ref": "SPEC-117",
        "authorized": True,
        "tier": 3,
        "action_data": action_data or {},
    }
    # Try DTCP first
    try:
        import urllib.request as _req
        req = _req.Request(
            "http://localhost:5002/log",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with _req.urlopen(req, timeout=5) as _r:
            _ = _r.read()
        return event_id
    except Exception:
        pass
    # Fallback: append to events.jsonl directly
    try:
        events_path = project_root / "_cortex" / "ads" / "events.jsonl"
        with open(events_path, "a") as f:
            f.write(json.dumps(payload) + "\n")
        return event_id
    except Exception:
        return event_id


def _write_report(project_root, verdicts, mode, since):
    reports_dir = project_root / "_cortex" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"reaudit_{ts_str}.md"

    n = len(verdicts)
    passes = [v for v in verdicts if v["verdict"] == "pass"]
    fails = [v for v in verdicts if v["verdict"] == "fail"]
    unknowns = [v for v in verdicts if v["verdict"] == "unknown"]

    with open(report_path, "w") as f:
        f.write(f"# SPEC-117 Reconciler Completion Re-Audit Report\n\n")
        f.write(f"- Timestamp: {_iso_utc()}\n")
        f.write(f"- Project: {project_root}\n")
        f.write(f"- Mode: {mode}\n")
        f.write(f"- Since filter: {since or 'none'}\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"- Total reconciler-completed tasks scanned: {n}\n")
        f.write(f"- PASS: {len(passes)}\n")
        f.write(f"- FAIL: {len(fails)}\n")
        f.write(f"- UNKNOWN (no worker events found): {len(unknowns)}\n\n")

        if fails:
            f.write(f"## Failures ({len(fails)})\n\n")
            f.write(f"| task_id | role | reason | detail |\n|---|---|---|---|\n")
            for v in fails:
                detail = json.dumps(v["detail"])
                if len(detail) > 200:
                    detail = detail[:197] + "..."
                f.write(f"| {v['task_id']} | {v.get('role','')} | {v['reason']} | {detail} |\n")
            f.write("\n")

        if unknowns:
            f.write(f"## Unknowns ({len(unknowns)})\n\n")
            for v in unknowns:
                f.write(f"- {v['task_id']} ({v.get('role','')}): {v['reason']}\n")
            f.write("\n")

        if passes:
            f.write(f"## Passes ({len(passes)}) — summary only\n\n")
            reasons = {}
            for v in passes:
                reasons[v["reason"]] = reasons.get(v["reason"], 0) + 1
            for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
                f.write(f"- {r}: {c}\n")

    return report_path


def main():
    p = argparse.ArgumentParser(description="SPEC-117 retroactive reconciler audit")
    p.add_argument("--project", default=".", help="Project root (default: cwd)")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Emit audit events only, do NOT revert (default)")
    p.add_argument("--commit", action="store_true",
                   help="Also revert failing tasks from completed to failed")
    p.add_argument("--since", default=None,
                   help="Only audit tasks completed on or after this ISO date (e.g. 2026-08-15)")
    args = p.parse_args()

    if args.commit:
        args.dry_run = False

    project_root = Path(args.project).resolve()
    tasks_path, tasks_data, all_tasks = _read_tasks(project_root)

    since_epoch = None
    if args.since:
        try:
            since_epoch = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            print(f"WARN: could not parse --since '{args.since}'; ignoring")

    candidates = [t for t in all_tasks if _is_reconciler_completion(t)]
    if since_epoch is not None:
        def _completed_at_ok(t):
            ts = t.get("completed_at") or t.get("updated_at")
            e = _ts_epoch(ts) if ts else None
            return e is None or e >= since_epoch
        candidates = [t for t in candidates if _completed_at_ok(t)]

    print(f"[SPEC-117] Project: {project_root}")
    print(f"[SPEC-117] Total tasks in tasks.json: {len(all_tasks)}")
    print(f"[SPEC-117] Reconciler-completed candidates: {len(candidates)}")
    if not candidates:
        print("[SPEC-117] Nothing to audit. Exiting.")
        return 0

    print(f"[SPEC-117] Building worker event index ...")
    worker_index = _build_worker_index(project_root)
    print(f"[SPEC-117] Worker index size: {len(worker_index)}")

    print(f"[SPEC-117] Auditing tasks ...")
    verdicts = []
    for t in candidates:
        tid = t.get("id") or t.get("task_id")
        ctx = worker_index.get(tid)
        v = _audit_one_task(t, ctx, project_root)
        verdicts.append(v)

    mode = "commit" if args.commit else "dry-run"
    report_path = _write_report(project_root, verdicts, mode, args.since)

    # Emit per-task ADS events
    pass_ids, fail_ids, unknown_ids = [], [], []
    reverted = 0
    for v in verdicts:
        if v["verdict"] == "pass":
            evid = _emit_ads_event(
                project_root, "task_completion_reaudit_pass",
                f"Re-audit pass for task {v['task_id']}: reason={v['reason']}.",
                {"task_id": v["task_id"], "reason": v["reason"], "detail": v["detail"]},
            )
            pass_ids.append(v["task_id"])
        elif v["verdict"] == "fail":
            fail_evid = _emit_ads_event(
                project_root, "task_completion_reaudit_fail",
                f"Re-audit FAIL for task {v['task_id']}: reason={v['reason']}.",
                {"task_id": v["task_id"], "reason": v["reason"], "detail": v["detail"]},
            )
            fail_ids.append(v["task_id"])
            if args.commit:
                # Revert the task
                for orig in all_tasks:
                    if (orig.get("id") or orig.get("task_id")) == v["task_id"]:
                        orig["status"] = "failed"
                        orig["reaudit_verdict"] = "reverted"
                        orig["reaudit_reason"] = v["reason"]
                        orig["reaudit_authority_event_id"] = fail_evid
                        reverted += 1
                        _emit_ads_event(
                            project_root, "task_completion_reaudit_reverted",
                            f"Task {v['task_id']} reverted from completed to failed by SPEC-117 audit.",
                            {"task_id": v["task_id"], "previous_status": "completed",
                             "new_status": "failed", "authority_event_id": fail_evid,
                             "reason": v["reason"]},
                        )
                        break
        else:
            unknown_ids.append(v["task_id"])

    if args.commit and reverted:
        # Atomic write back
        tmp = tasks_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            if isinstance(tasks_data, dict):
                tasks_data["tasks"] = all_tasks
                json.dump(tasks_data, f, indent=2)
            else:
                json.dump(all_tasks, f, indent=2)
        os.replace(tmp, tasks_path)

    print(f"[SPEC-117] Report: {report_path}")
    print(f"[SPEC-117] Scanned: {len(verdicts)}. "
          f"PASS: {len(pass_ids)}. FAIL: {len(fail_ids)}. UNKNOWN: {len(unknown_ids)}.")
    if args.commit:
        print(f"[SPEC-117] REVERTED: {reverted} tasks from completed to failed.")
    else:
        print(f"[SPEC-117] Dry-run: NO reverts applied. Re-run with --commit to apply.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
