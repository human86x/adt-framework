"""SPEC-105 section 4: diff-and-commit reconciler.

Compares a worker's per-worker workspace against the real project_root after
the worker exits. For each additions / modification / deletion it POSTs a
request to the child project's DTCP `/request` endpoint. Allowed changes are
landed into the real project tree using rename-through-tmp with fsync
(atomic). Denied changes are discarded; a `worker_write_denied_by_dtcp` ADS
event is emitted.

The reconcile_overlay() signature preserves the old parameter names for
callers written against the SPEC-105 draft ("overlay_dir" now carries the
workspace path). Semantics: files present-only-in-workspace or with different
sha256 are candidate writes; files present-only-in-original are candidate
deletions ("whiteout" in the returned tuples, for continuity with the earlier
overlayfs-based implementation).

Concurrency: reconciliation runs sequentially per worker and is guarded by a
per-project lock at /run/adt/reconciler_locks/<project>.lock so two workers
finishing at the same time cannot race on the same real file.

Fail-closed rules (SPEC-105 section 6):
    * DTCP unreachable -> treat as deny for every pending file, log
      dtcp_unreachable_during_reconcile.
    * reconciler crash -> emit reconciler_crash and leave overlay in place
      for forensics.
"""
from __future__ import annotations

import base64
import contextlib
import errno
import hashlib
import json
import logging
import os
import shutil
import stat
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux-only in practice
    fcntl = None

logger = logging.getLogger(__name__)

_SPEC_REF = "SPEC-105"
_LOCK_DIR = "/run/adt/reconciler_locks"
_LARGE_REQUEST_WARN_SEC = 5.0


# --- ADS event helper (shared shape with spawn.py; kept local to avoid cycle) --


def _ads_log(action_type: str, description: str, action_data: Optional[Dict[str, Any]] = None,
             tier: int = 3, spec_ref: str = _SPEC_REF, agent: str = "SYSTEM",
             role: str = "Backend_Engineer",
             project_root: Optional[str] = None) -> Optional[str]:
    """Write to the CHILD project's ADS when project_root is provided (the
    reconciler decision is *about* that project's DTCP). Fall back to the
    framework ADS only when project_root is unknown."""
    try:
        if project_root and os.path.isdir(os.path.join(project_root, "_cortex")):
            ads_path = os.path.join(project_root, "_cortex", "ads", "events.jsonl")
        else:
            here = os.path.dirname(os.path.abspath(__file__))
            fw_root = os.path.abspath(os.path.join(here, "..", ".."))
            ads_path = os.path.join(fw_root, "_cortex", "ads", "events.jsonl")
        from adt_core.ads.logger import ADSLogger  # type: ignore
        from adt_core.ads.schema import ADSEventSchema  # type: ignore
        event_id = ADSEventSchema.generate_id(action_type)
        event = ADSEventSchema.create_event(
            event_id=event_id,
            agent=agent,
            role=role,
            action_type=action_type,
            description=description,
            spec_ref=spec_ref,
            authorized=True,
            tier=tier,
            action_data=action_data or {},
        )
        ADSLogger(ads_path).log(event)
        return event_id
    except Exception:
        return None


# --- workspace vs original diff ---------------------------------------------


def _walk_files(root: str) -> Dict[str, str]:
    """Return {rel_path: kind} for every regular file / symlink under root.

    rel_path uses forward slashes. Directories themselves are not listed;
    files inside them are. Follows no symlinks.
    """
    out: Dict[str, str] = {}
    if not root or not os.path.isdir(root):
        return out
    for dirpath, _dirs, files in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root)
        for name in files:
            rel = name if rel_dir == "." else os.path.join(rel_dir, name)
            rel = rel.replace(os.sep, "/")
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                out[rel] = "symlink"
            else:
                out[rel] = "file"
    return out


def _file_sha256(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _iter_overlay(workspace: str, project_root: Optional[str] = None) -> List[Tuple[str, str]]:
    """Diff `workspace` against `project_root`. Yield (kind, rel_path) tuples.

    kind is one of: "file" (added or modified regular file),
                    "symlink" (added or modified symlink),
                    "whiteout" (file present in original but missing from workspace,
                                i.e. worker deleted it).

    If project_root is None or missing, every workspace entry is treated as new.
    """
    entries: List[Tuple[str, str]] = []
    if not workspace or not os.path.isdir(workspace):
        return entries

    ws_map = _walk_files(workspace)
    orig_map = _walk_files(project_root) if project_root else {}

    # Additions + modifications
    for rel, kind in ws_map.items():
        ws_full = os.path.join(workspace, *rel.split("/"))
        orig_full = os.path.join(project_root, *rel.split("/")) if project_root else None
        if orig_full is None or rel not in orig_map:
            entries.append((kind, rel))
            continue
        # Present in both -> compare
        if kind == "symlink":
            try:
                ws_target = os.readlink(ws_full)
                orig_target = os.readlink(orig_full) if os.path.islink(orig_full) else None
            except OSError:
                ws_target, orig_target = "", None
            if ws_target != orig_target:
                entries.append(("symlink", rel))
        else:
            # file: compare sha256
            ws_sha = _file_sha256(ws_full)
            orig_sha = _file_sha256(orig_full)
            if ws_sha is None or orig_sha is None or ws_sha != orig_sha:
                entries.append(("file", rel))

    # Deletions: in original but not in workspace
    for rel in orig_map.keys():
        if rel not in ws_map:
            entries.append(("whiteout", rel))

    return entries


# --- DTCP round-trip ---------------------------------------------------------


def _dtcp_request(child_dtcp_url: str, payload: Dict[str, Any],
                  timeout: float = 30.0) -> Tuple[str, Dict[str, Any]]:
    """POST to <child_dtcp_url>/request. Returns (verdict, response_json).

    verdict is one of: "allow", "deny", "error".
    """
    import urllib.request as _r
    import urllib.error as _e
    url = child_dtcp_url.rstrip("/") + "/request"
    data = json.dumps(payload).encode("utf-8")
    req = _r.Request(url, data=data, method="POST",
                     headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        with _r.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                j = json.loads(body)
            except Exception:
                j = {"raw": body}
            elapsed = time.monotonic() - t0
            if elapsed >= _LARGE_REQUEST_WARN_SEC:
                logger.warning("reconciler DTCP request slow: %.2fs %s",
                               elapsed, payload.get("params", {}).get("file"))
            # DTCP conventions vary: 200 + {allowed: true|false} OR {verdict:"allow"}
            allowed = None
            if isinstance(j, dict):
                if "allowed" in j:
                    allowed = bool(j["allowed"])
                elif "verdict" in j:
                    allowed = str(j["verdict"]).lower() == "allow"
                elif "status" in j:
                    allowed = str(j["status"]).lower() in ("allow", "allowed", "ok")
            if allowed is True:
                return "allow", j
            if allowed is False:
                return "deny", j
            # Unknown response shape -> treat as deny (fail-closed).
            return "deny", j
    except _e.HTTPError as ehe:
        try:
            body = ehe.read().decode("utf-8", errors="replace")
            j = json.loads(body) if body else {}
        except Exception:
            j = {}
        # 4xx => deny; 5xx => error (retry semantics up to caller).
        if 400 <= ehe.code < 500:
            return "deny", {"http_status": ehe.code, **j}
        return "error", {"http_status": ehe.code, **j}
    except Exception as e:
        return "error", {"error": type(e).__name__, "message": str(e)}


# --- atomic landing ----------------------------------------------------------


def _atomic_land(src: str, dst: str) -> int:
    """Copy src -> dst atomically. Returns bytes written."""
    dst_dir = os.path.dirname(dst) or "."
    os.makedirs(dst_dir, exist_ok=True)
    tmp = dst + ".adt_reconcile_tmp"
    # Copy content
    with open(src, "rb") as rf, open(tmp, "wb") as wf:
        while True:
            chunk = rf.read(64 * 1024)
            if not chunk:
                break
            wf.write(chunk)
        wf.flush()
        os.fsync(wf.fileno())
    # Preserve mode
    try:
        shutil.copystat(src, tmp)
    except Exception:
        pass
    os.replace(tmp, dst)
    # fsync the directory to durably persist rename
    try:
        dfd = os.open(dst_dir, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass
    return os.path.getsize(dst)


def _atomic_land_symlink(src: str, dst: str) -> int:
    target = os.readlink(src)
    dst_dir = os.path.dirname(dst) or "."
    os.makedirs(dst_dir, exist_ok=True)
    tmp = dst + ".adt_reconcile_tmp"
    with contextlib.suppress(FileNotFoundError):
        os.remove(tmp)
    os.symlink(target, tmp)
    os.replace(tmp, dst)
    return len(target)


def _atomic_delete(dst: str) -> None:
    with contextlib.suppress(FileNotFoundError):
        os.remove(dst)


# --- content encoding --------------------------------------------------------


def _encode_content(path: str) -> Tuple[str, str]:
    """Return (content_b64, sha256) for a regular file. Utf-8 preferred where valid;
    we always send base64 for uniformity (DTCP decodes base64 unambiguously)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        data = f.read()
    h.update(data)
    return base64.b64encode(data).decode("ascii"), h.hexdigest()


# --- per-project lock --------------------------------------------------------


def _project_key(project_root: str) -> str:
    """Stable filesystem-safe key from project root path."""
    h = hashlib.sha256(project_root.encode("utf-8")).hexdigest()[:16]
    base = os.path.basename(os.path.normpath(project_root)) or "root"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in base)
    return f"{safe}_{h}"


class _ProjectLock:
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.path = os.path.join(_LOCK_DIR, _project_key(project_root) + ".lock")
        self._fh = None

    def __enter__(self):
        try:
            os.makedirs(_LOCK_DIR, exist_ok=True)
        except Exception:
            # /run may be read-only in test env; fall back to project-local lock.
            fallback = os.path.join(self.project_root, ".adt", "reconciler_locks")
            os.makedirs(fallback, exist_ok=True)
            self.path = os.path.join(fallback, _project_key(self.project_root) + ".lock")
        self._fh = open(self.path, "a+")
        if fcntl is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(self._fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._fh is not None:
            if fcntl is not None:
                with contextlib.suppress(OSError):
                    fcntl.flock(self._fh, fcntl.LOCK_UN)
            with contextlib.suppress(Exception):
                self._fh.close()


# --- public entry point ------------------------------------------------------


def reconcile_overlay(
    overlay_dir: str,
    project_root: str,
    worker_id: str,
    child_dtcp_url: str,
    agent: str = "SYSTEM",
    role: str = "Backend_Engineer",
    spec_id: str = _SPEC_REF,
    *,
    dry_run: bool = False,
    cleanup_overlay: bool = True,
) -> Dict[str, Any]:
    """Enumerate overlay_dir; ask child DTCP per entry; land allowed writes.

    Returns a summary dict:
        {
          worker_id, allowed_count, denied_count, deleted_count,
          total_bytes_written, wall_time_ms, dtcp_reachable
        }
    """
    t0 = time.monotonic()
    project_root = os.path.abspath(project_root)
    allowed_count = 0
    denied_count = 0
    deleted_count = 0
    total_bytes = 0
    dtcp_reachable = True

    if not overlay_dir or not os.path.isdir(overlay_dir):
        # Nothing to reconcile (e.g., sandbox bypassed, worker made no writes).
        summary = {
            "worker_id": worker_id, "allowed_count": 0, "denied_count": 0,
            "deleted_count": 0, "total_bytes_written": 0, "wall_time_ms": 0,
            "dtcp_reachable": True, "reason": "no_overlay_dir",
        }
        _ads_log(
            "worker_reconciliation_complete",
            f"Worker {worker_id}: no overlay to reconcile.",
            summary, tier=3, agent=agent, role=role,
            project_root=project_root,
        )
        return summary

    try:
        with _ProjectLock(project_root):
            entries = _iter_overlay(overlay_dir, project_root)

            for kind, rel_path in entries:
                # Skip .git/ writes per SPEC-105 Q2 recommendation: never land .git/
                # into the real project tree. Ephemeral in overlay only.
                if rel_path.startswith(".git/") or rel_path == ".git":
                    continue

                src = os.path.join(overlay_dir, *rel_path.split("/"))
                dst = os.path.join(project_root, *rel_path.split("/"))

                if kind == "whiteout":
                    action = "delete"
                    params: Dict[str, Any] = {"file": rel_path}
                    payload = {
                        "agent": agent, "role": role, "spec_id": spec_id,
                        "action": action, "params": params,
                        "rationale": f"worker {worker_id} deleted {rel_path}",
                        "dry_run": bool(dry_run),
                    }
                elif kind == "symlink":
                    try:
                        target = os.readlink(src)
                    except OSError:
                        target = ""
                    action = "edit"
                    params = {"file": rel_path, "symlink_target": target,
                              "kind": "symlink"}
                    payload = {
                        "agent": agent, "role": role, "spec_id": spec_id,
                        "action": action, "params": params,
                        "rationale": f"worker {worker_id} symlink {rel_path} -> {target}",
                        "dry_run": bool(dry_run),
                    }
                else:  # regular file
                    try:
                        content_b64, sha256 = _encode_content(src)
                    except OSError as e:
                        _ads_log(
                            "worker_write_denied_by_dtcp",
                            f"Overlay entry unreadable: {rel_path} ({e}); denied.",
                            {"worker_id": worker_id, "file": rel_path,
                             "error": str(e)},
                            tier=2, agent=agent, role=role,
                            project_root=project_root,
                        )
                        denied_count += 1
                        continue
                    action = "edit"
                    params = {"file": rel_path, "content": content_b64,
                              "sha256": sha256}
                    payload = {
                        "agent": agent, "role": role, "spec_id": spec_id,
                        "action": action, "params": params,
                        "rationale": f"worker {worker_id} wrote {rel_path}",
                        "dry_run": bool(dry_run),
                    }

                verdict, resp = _dtcp_request(child_dtcp_url, payload)

                if verdict == "error":
                    dtcp_reachable = False
                    _ads_log(
                        "dtcp_unreachable_during_reconcile",
                        f"DTCP unreachable during reconcile of {rel_path} for worker {worker_id}. "
                        f"Failing closed (deny). resp={resp}",
                        {"worker_id": worker_id, "file": rel_path,
                         "child_dtcp_url": child_dtcp_url, "response": resp},
                        tier=1, agent=agent, role=role,
                        project_root=project_root,
                    )
                    denied_count += 1
                    continue

                if verdict == "deny":
                    sha = params.get("sha256")
                    _ads_log(
                        "worker_write_denied_by_dtcp",
                        f"DTCP denied worker {worker_id} write to {rel_path}.",
                        {"worker_id": worker_id, "file": rel_path,
                         "action": action, "sha256": sha,
                         "deny_reason": resp.get("reason") or resp.get("message") or "unspecified",
                         "response": resp},
                        tier=2, agent=agent, role=role,
                        project_root=project_root,
                    )
                    denied_count += 1
                    continue

                # allowed
                if dry_run:
                    allowed_count += 1
                    continue

                try:
                    if kind == "whiteout":
                        _atomic_delete(dst)
                        deleted_count += 1
                    elif kind == "symlink":
                        n = _atomic_land_symlink(src, dst)
                        total_bytes += n
                        allowed_count += 1
                    else:
                        n = _atomic_land(src, dst)
                        total_bytes += n
                        allowed_count += 1
                except Exception as e:
                    _ads_log(
                        "worker_reconciliation_land_failed",
                        f"Could not land {rel_path} for worker {worker_id}: {type(e).__name__}: {e}",
                        {"worker_id": worker_id, "file": rel_path,
                         "error": str(e)},
                        tier=1, agent=agent, role=role,
                        project_root=project_root,
                    )
                    denied_count += 1
    except Exception as e:
        _ads_log(
            "reconciler_crash",
            f"Reconciler crashed mid-run for worker {worker_id}: {type(e).__name__}: {e}. "
            "Overlay left in place for forensics.",
            {"worker_id": worker_id, "overlay_dir": overlay_dir,
             "error": str(e)},
            tier=1, agent=agent, role=role,
            project_root=project_root,
        )
        cleanup_overlay = False
        raise

    wall_ms = int((time.monotonic() - t0) * 1000)
    summary = {
        "worker_id": worker_id,
        "allowed_count": allowed_count,
        "denied_count": denied_count,
        "deleted_count": deleted_count,
        "total_bytes_written": total_bytes,
        "wall_time_ms": wall_ms,
        "dtcp_reachable": dtcp_reachable,
    }
    _ads_log(
        "worker_reconciliation_complete",
        f"Worker {worker_id}: {allowed_count} allowed, {denied_count} denied, "
        f"{deleted_count} deleted, {total_bytes} bytes, {wall_ms}ms.",
        summary, tier=3, agent=agent, role=role,
            project_root=project_root,
        )

    if cleanup_overlay:
        with contextlib.suppress(Exception):
            shutil.rmtree(overlay_dir, ignore_errors=True)
    return summary
