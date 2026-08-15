"""SPEC-105: bwrap-based worker sandbox.

Every worker subprocess spawned by adt_center/api/build_executor.py is wrapped
by bwrap. The worker sees a per-worker copy of the project tree at the real
project_root path; its writes land in that copy and NEVER touch the real
project. After the worker exits, adt_core/sandbox/reconciler.py diffs the copy
against the original project_root and POSTs each change to the child project's
DTCP, landing only allowed writes.

Bwrap-only implementation (no fuse-overlayfs):
    bwrap 0.9.0 (Ubuntu 24.10) lacks --overlay-src / --tmp-overlay (added
    upstream in 0.10.0). SPEC-105 3 was amended (2026-08-14) to use a
    per-worker workspace populated via `cp -a --reflink=auto` and bind-mounted
    at project_root inside bwrap. The isolation invariant is unchanged: the
    worker cannot see or write ANY host path outside project_root, and its
    writes land in a directory the reconciler owns.

Automation flags on the harness CLI (--dangerously-skip-permissions, --yolo,
--new-project, -p) are preserved verbatim -- the sandbox is out-of-band.

Fail-closed rules (SPEC-105 6):
    * bwrap missing              -> raise SandboxUnavailableError
    * kernel userns unsupported  -> raise SandboxUnavailableError
    * workspace init fails       -> raise SandboxWorkspaceInitError

Env override (SPEC-105 6h):
    ADT_SANDBOX_DISABLE=1  Dev-only escape hatch. Emit Tier-1
                           `sandbox_bypassed_by_env_override` ADS event and
                           return an unsandboxed Popen. NEVER set this in
                           production. There is NO opt-in env var; the sandbox
                           is always on.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, Iterable, List, Optional

# --- constants ---------------------------------------------------------------

BWRAP_BIN = shutil.which("bwrap") or "/usr/bin/bwrap"
CP_BIN = shutil.which("cp") or "/usr/bin/cp"

_WORKER_ROOT = "/run/adt/workers"
_HOME = os.path.expanduser("~")
_EXTRA_RO_BINDS: List[str] = [
    os.path.join(_HOME, ".local", "bin", "agy"),
    os.path.join(_HOME, ".local", "bin"),
    os.path.join(_HOME, ".config", "gcloud"),
    os.path.join(_HOME, ".npm-global"),
    os.path.join(_HOME, ".nvm"),
    os.path.join(_HOME, ".cache", "gemini"),
]
# Auth/state dirs the agent MUST be able to WRITE to. Read-only causes
# agy to fail at log/crash writes AND fall into a token-refresh loop that
# reports "not logged into Antigravity" (2026-08-15 diagnosis). Same
# pattern the Console sandbox in adt-console/src-tauri/src/pty.rs uses.
_EXTRA_RW_BINDS: List[str] = [
    os.path.join(_HOME, ".gemini"),
    os.path.join(_HOME, ".claude"),
    os.path.join(_HOME, ".claude.json"),
    os.path.join(_HOME, ".claude.json.backup"),
    os.path.join(_HOME, ".antigravity"),
]

_SPEC_REF = "SPEC-105"


# --- exceptions --------------------------------------------------------------


class SandboxUnavailableError(RuntimeError):
    """bwrap missing, or kernel does not support user namespaces."""


class SandboxWorkspaceInitError(RuntimeError):
    """Could not create/populate the per-worker workspace."""


# --- ADS event helper --------------------------------------------------------


def _ads_log(action_type: str, description: str,
             action_data: Optional[Dict[str, Any]] = None,
             tier: int = 3, spec_ref: str = _SPEC_REF,
             agent: str = "SYSTEM", role: str = "Backend_Engineer",
             project_root: Optional[str] = None) -> Optional[str]:
    """Best-effort ADS log. Never raises. When `project_root` is provided
    and looks like a real project, writes to the CHILD project's ADS so the
    DTCP monitor for that project sees the event. Otherwise falls back to the
    framework's ADS."""
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
            agent=agent, role=role,
            action_type=action_type, description=description,
            spec_ref=spec_ref, authorized=True, tier=tier,
            action_data=action_data or {},
        )
        ADSLogger(ads_path).log(event)
        return event_id
    except Exception:
        return None


# --- capability probes -------------------------------------------------------


def _bwrap_available() -> bool:
    return bool(BWRAP_BIN) and os.path.exists(BWRAP_BIN) and os.access(BWRAP_BIN, os.X_OK)


def _kernel_userns_supported() -> bool:
    """Cheap real bwrap invocation. If bwrap can create a user namespace,
    returns True. This catches AppArmor / setuid / kernel issues in one shot."""
    if not _bwrap_available():
        return False
    try:
        r = subprocess.run(
            [BWRAP_BIN, "--unshare-user", "--unshare-pid",
             "--ro-bind", "/", "/", "--dev", "/dev", "--tmpfs", "/tmp",
             "--", "true"],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def is_sandbox_supported() -> bool:
    """Cheap probe used by SPEC-106 status endpoint."""
    return _bwrap_available() and _kernel_userns_supported()


def sandbox_enforcement_active() -> bool:
    """Post-SPEC-105 amendment (2026-08-14): sandbox is ALWAYS enforced unless
    the operator sets ADT_SANDBOX_DISABLE=1 (dev-only escape hatch). Returns
    True whenever the next spawn will engage the sandbox."""
    return not _sandbox_disabled_by_env()


def _sandbox_disabled_by_env() -> bool:
    return os.environ.get("ADT_SANDBOX_DISABLE", "").strip() == "1"


# --- workspace layout --------------------------------------------------------


def _worker_dir(worker_id: str) -> str:
    root = _WORKER_ROOT
    try:
        os.makedirs(root, exist_ok=True)
        probe = os.path.join(root, f".probe_{os.getpid()}")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
    except Exception:
        root = os.path.join(tempfile.gettempdir(), "adt-workers")
        os.makedirs(root, exist_ok=True)
    return os.path.join(root, worker_id)


def _init_workspace(project_root: str, worker_id: str) -> Dict[str, str]:
    """Populate <worker_dir>/workspace with `cp -a --reflink=auto project_root`.

    Returns descriptor: {worker_dir, workspace, scratch, upper}.

    `workspace` is what bwrap binds at project_root inside the sandbox.
    `upper` aliases `workspace` so the reconciler walks the same tree.
    """
    try:
        wdir = _worker_dir(worker_id)
        workspace = os.path.join(wdir, "workspace")
        scratch = os.path.join(wdir, "scratch")
        os.makedirs(wdir, exist_ok=True)
        os.makedirs(scratch, exist_ok=True)
        if os.path.exists(workspace):
            shutil.rmtree(workspace, ignore_errors=True)
        # `cp -a --reflink=auto SRC/. DST/` copies CONTENTS of SRC into DST.
        # --reflink=auto uses CoW on btrfs/xfs; falls back to plain copy.
        src = os.path.join(project_root, ".")
        os.makedirs(workspace, exist_ok=True)
        r = subprocess.run(
            [CP_BIN, "-a", "--reflink=auto", src, workspace],
            capture_output=True, timeout=600,
        )
        if r.returncode != 0:
            raise SandboxWorkspaceInitError(
                f"cp -a workspace failed rc={r.returncode}: "
                f"{r.stderr.decode('utf-8', errors='replace')[:400]}"
            )
        return {"worker_dir": wdir, "workspace": workspace,
                "scratch": scratch, "upper": workspace}
    except SandboxWorkspaceInitError:
        raise
    except Exception as e:
        raise SandboxWorkspaceInitError(
            f"could not init workspace for {worker_id}: {e}"
        )


# --- bwrap command builder ---------------------------------------------------


def _build_bwrap_cmd(
    inner_cmd: List[str],
    project_root: str,
    worker_id: str,
    desc: Dict[str, str],
    network: str = "full",
) -> List[str]:
    """Build the bwrap invocation using only bwrap 0.9.0-compatible flags."""
    bwrap = [BWRAP_BIN]
    bwrap += ["--unshare-user", "--unshare-pid", "--unshare-ipc",
              "--unshare-uts", "--unshare-cgroup"]
    if network == "none":
        bwrap += ["--unshare-net"]
    bwrap += ["--die-with-parent", "--new-session"]

    # base system read-only
    bwrap += ["--ro-bind", "/", "/"]
    bwrap += ["--tmpfs", "/tmp"]
    bwrap += ["--bind", desc["scratch"], "/tmp/scratch"]

    project_root_abs = os.path.abspath(project_root)
    # Workspace bind-mounted rw over project_root path INSIDE the sandbox.
    # Worker writes land in desc["workspace"] on the host; real project_root
    # is not visible or writable to the worker.
    bwrap += ["--bind", desc["workspace"], project_root_abs]

    for src in _EXTRA_RO_BINDS:
        if os.path.exists(src):
            bwrap += ["--ro-bind-try", src, src]

    for src in _EXTRA_RW_BINDS:
        if os.path.exists(src):
            bwrap += ["--bind-try", src, src]

    # DNS: resolv.conf is a symlink to /run/systemd/resolve on modern Ubuntu.
    if os.path.isdir("/run/systemd/resolve"):
        bwrap += ["--ro-bind", "/run/systemd/resolve", "/run/systemd/resolve"]

    # Keyring socket dir for OAuth token retrieval (agy libsecret).
    uid = os.getuid()
    keyring_dir = f"/run/user/{uid}"
    if os.path.isdir(keyring_dir):
        bwrap += ["--bind", keyring_dir, keyring_dir]

    bwrap += ["--dev", "/dev", "--proc", "/proc"]
    bwrap += ["--chdir", project_root_abs]
    bwrap += ["--setenv", "ADT_WORKER_ID", worker_id]
    bwrap += ["--setenv", "ADT_SANDBOX_ACTIVE", "1"]
    bwrap += ["--setenv", "HOME", _HOME]
    bwrap += ["--cap-drop", "ALL"]
    bwrap += ["--"]
    bwrap += list(inner_cmd)
    return bwrap


# --- Popen-compatible handle -------------------------------------------------


class _SandboxedPopen(subprocess.Popen):
    overlay_dir: str
    worker_id: str
    original_cmd: List[str]
    sandboxed: bool
    project_root: str
    _sandbox_desc: Dict[str, str]


# --- public entry point ------------------------------------------------------


def spawn_in_sandbox(
    cmd: Iterable[str],
    project_root: str,
    worker_id: str,
    network: str = "full",
    *,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[str] = None,
    stdin: Any = subprocess.DEVNULL,
    stdout: Any = None,
    stderr: Any = None,
) -> _SandboxedPopen:
    """Spawn `cmd` inside a bwrap namespace sandbox rooted at project_root.

    Fail-closed: raises SandboxUnavailableError if bwrap missing / userns
    blocked / workspace init fails. Callers MUST NOT fall back to an
    unsandboxed spawn -- that would violate SPEC-105 6(f) and AI_PROTOCOL 1.3.
    """
    cmd_list = list(cmd)
    project_root = os.path.abspath(project_root)

    # SPEC-105 6h: dev-only escape hatch.
    if _sandbox_disabled_by_env():
        _ads_log(
            "sandbox_bypassed_by_env_override",
            f"Sandbox bypassed by ADT_SANDBOX_DISABLE=1 for worker {worker_id}. "
            "Worker runs without namespace isolation. Dev-only path.",
            {"worker_id": worker_id,
             "cmd_preview": " ".join(cmd_list[:3]) + " ...",
             "network": network, "project_root": project_root},
            tier=1,
            project_root=project_root,
        )
        proc = _SandboxedPopen(
            cmd_list, env=env, cwd=cwd or project_root,
            stdin=stdin, stdout=stdout, stderr=stderr,
        )
        proc.overlay_dir = ""
        proc.worker_id = worker_id
        proc.original_cmd = cmd_list
        proc.sandboxed = False
        proc.project_root = project_root
        proc._sandbox_desc = {}
        return proc

    # Fail-closed probes.
    if not _bwrap_available():
        _ads_log(
            "sandbox_unavailable",
            f"bwrap binary missing at {BWRAP_BIN}; refusing to spawn worker {worker_id}.",
            {"worker_id": worker_id, "bwrap_path": BWRAP_BIN,
             "cmd_preview": " ".join(cmd_list[:3]) + " ..."},
            tier=1,
            project_root=project_root,
        )
        raise SandboxUnavailableError(
            f"bwrap not installed or not executable at {BWRAP_BIN}"
        )
    if not _kernel_userns_supported():
        _ads_log(
            "sandbox_unavailable_kernel",
            f"bwrap cannot create a user namespace on this host "
            f"(setuid missing? AppArmor blocking? kernel userns off?). "
            f"Refusing to spawn worker {worker_id}. "
            "Fix: sudo chmod u+s /usr/bin/bwrap, or install an AppArmor "
            "profile permitting bwrap unpriv userns.",
            {"worker_id": worker_id,
             "cmd_preview": " ".join(cmd_list[:3]) + " ..."},
            tier=1,
            project_root=project_root,
        )
        raise SandboxUnavailableError(
            "bwrap userns creation failed; check setuid bit and AppArmor policy"
        )

    try:
        desc = _init_workspace(project_root, worker_id)
    except SandboxWorkspaceInitError as e:
        _ads_log(
            "sandbox_workspace_init_failed",
            f"Workspace init failed for worker {worker_id}: {e}",
            {"worker_id": worker_id, "error": str(e),
             "project_root": project_root,
             "cmd_preview": " ".join(cmd_list[:3]) + " ..."},
            tier=1,
            project_root=project_root,
        )
        raise

    bwrap_cmd = _build_bwrap_cmd(cmd_list, project_root, worker_id, desc,
                                 network=network)

    _ads_log(
        "sandbox_worker_spawned",
        f"Worker {worker_id} spawned inside bwrap namespace sandbox "
        f"(network={network}, workspace={desc['workspace']}).",
        {"worker_id": worker_id,
         "workspace": desc["workspace"],
         "project_root": project_root,
         "network": network,
         "cmd_preview": " ".join(cmd_list[:3]) + " ..."},
        project_root=project_root,
    )

    try:
        proc = _SandboxedPopen(
            bwrap_cmd,
            env=env,
            cwd=None,  # --chdir handles it inside sandbox
            stdin=stdin, stdout=stdout, stderr=stderr,
        )
    except Exception as e:
        _ads_log(
            "sandbox_spawn_failed",
            f"Failed to launch bwrap for worker {worker_id}: {type(e).__name__}: {e}",
            {"worker_id": worker_id, "error": str(e),
             "cmd_preview": " ".join(cmd_list[:3]) + " ..."},
            tier=1,
            project_root=project_root,
        )
        raise SandboxUnavailableError(f"bwrap launch failed: {e}") from e

    proc.overlay_dir = desc["workspace"]
    proc.worker_id = worker_id
    proc.original_cmd = cmd_list
    proc.sandboxed = True
    proc.project_root = project_root
    proc._sandbox_desc = desc
    return proc
