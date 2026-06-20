"""
SPEC-056 Amendment B: Gemini Worker Harness

Spawns role workers as subprocesses. Systems_Architect uses Claude.
All other roles (Backend_Engineer, Frontend_Engineer, DevOps_Engineer, Overseer)
default to the Gemini CLI harness to preserve Claude token reserves.
No ANTHROPIC_API_KEY or GEMINI_API_KEY required — both use local CLI auth.
"""
import os
import json
import hashlib
import datetime
import glob
import subprocess
import shutil

# Resolve claude binary: runtime env var set by Claude Code, fallback to PATH
CLAUDE_BIN = os.environ.get("CLAUDE_CODE_EXECPATH") or shutil.which("claude") or "claude"

# Resolve gemini binary
GEMINI_BIN = (
    os.environ.get("GEMINI_EXECPATH")
    or shutil.which("gemini")
    or "/home/human/.npm-global/bin/gemini"
)

AGY_BIN = (os.environ.get('AGY_EXECPATH') or shutil.which('agy') or '/home/human/.local/bin/agy')

# Default harness per role — Systems_Architect stays on Claude; workers use Gemini
ROLE_HARNESS_DEFAULTS = {
    "Systems_Architect": "claude",
    "Backend_Engineer":  "antigravity",
    "Frontend_Engineer": "antigravity",
    "DevOps_Engineer":   "antigravity",
    "Overseer":          "antigravity",
    "All":               "antigravity",
}

ROLE_MODEL_DEFAULTS = {
    "Systems_Architect": None,
    "Backend_Engineer":  "Claude Sonnet 4.6 (Thinking)",
    "Frontend_Engineer": "Gemini 3.1 Pro (High)",
    "DevOps_Engineer":   "Gemini 3.5 Flash (High)",
    "Overseer":          "Claude Opus 4.6 (Thinking)",
}


# ---------------------------------------------------------------------------
# ADS helpers
# ---------------------------------------------------------------------------

def _append_ads_event(role, spec_id, build_id, action_type, description, action_data, project_root):
    ads_path = os.path.join(project_root, "_cortex", "ads", "events.jsonl")
    prev_hash = "0" * 64
    try:
        with open(ads_path, "rb") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        prev_hash = json.loads(line).get("hash", prev_hash)
                    except Exception:
                        pass
    except Exception:
        pass

    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    event_id = f"evt_{ts[:10].replace('-', '')}_sdk_{role[:2].lower()}_{action_type[:8]}"
    event = {
        "event_id": event_id, "ts": ts, "agent": "CLAUDE", "role": role,
        "action_type": action_type, "spec_ref": spec_id, "authorized": True,
        "description": description, "action_data": {**action_data, "build_id": build_id},
        "prev_hash": prev_hash,
    }
    content = json.dumps(event, separators=(",", ":"))
    event["hash"] = hashlib.sha256(content.encode()).hexdigest()
    with open(ads_path, "a") as f:
        f.write(json.dumps(event) + "\n")


def _load_builds(project_root):
    path = os.path.join(project_root, "_cortex", "ops", "builds.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_builds(project_root, builds):
    path = os.path.join(project_root, "_cortex", "ops", "builds.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(builds, f, indent=2)


def _get_jurisdiction_paths(role, project_root):
    try:
        with open(os.path.join(project_root, "config", "jurisdictions.json")) as f:
            jur = json.load(f)
        return jur.get("jurisdictions", {}).get(role, {}).get("paths", [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Wave executor: topological sort on depends_on
# ---------------------------------------------------------------------------

def _topological_waves(tasks):
    """Group tasks into dependency-ordered waves.

    Tasks in the same wave have no mutual dependencies. v1 runs roles
    sequentially within a wave to avoid active_role.txt race conditions.
    """
    task_ids = {t["id"] for t in tasks}
    completed = set()
    waves = []
    remaining = list(tasks)

    while remaining:
        ready = [
            t for t in remaining
            if all(dep in completed or dep not in task_ids
                   for dep in t.get("depends_on", []))
        ]
        if not ready:
            ready = remaining  # break circular deps
        waves.append(ready)
        completed.update(t["id"] for t in ready)
        remaining = [t for t in remaining if t["id"] not in completed]

    return waves


# ---------------------------------------------------------------------------
# DTCP role identity management
# ---------------------------------------------------------------------------

def _set_active_role(project_root, role, spec_id):
    """Write active_role.txt + active_spec.txt so the DTCP pre-tool hook
    uses the correct identity for the worker subprocess about to run."""
    ops_dir = os.path.join(project_root, "_cortex", "ops")
    os.makedirs(ops_dir, exist_ok=True)
    with open(os.path.join(ops_dir, "active_role.txt"), "w") as f:
        f.write(role)
    with open(os.path.join(ops_dir, "active_spec.txt"), "w") as f:
        f.write(spec_id)


# ---------------------------------------------------------------------------
# Signal file: lets an active SA session detect the build
# ---------------------------------------------------------------------------

def _signal_pending_build(build_id, spec_id, status, project_root):
    path = os.path.join(project_root, "_cortex", "ops", "pending_builds.json")
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        data = {"pending": []}

    found = False
    for entry in data["pending"]:
        if entry.get("build_id") == build_id:
            entry["status"] = status
            found = True
            break
    if not found:
        data["pending"].append({
            "build_id": build_id,
            "spec_id": spec_id,
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": status,
        })

    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Worker prompt builder
# ---------------------------------------------------------------------------

def _build_worker_prompt(role, tasks, spec_id, project_root):
    spec_files = glob.glob(
        os.path.join(project_root, "_cortex", "specs", f"{spec_id}_*.md")
    )
    spec_content = ""
    if spec_files:
        with open(spec_files[0]) as f:
            spec_content = f.read()[:12000]

    jur_paths = _get_jurisdiction_paths(role, project_root)
    task_list = "\n".join(
        "  [%s] %s\n    %s" % (t["id"], t["title"], t.get("description", "")[:400])
        for t in tasks
    )
    task_ids = [t["id"] for t in tasks]

    lines = [
        "You are %s in the ADT Framework Hivemind, executing an automated build." % role,
        "",
        "Spec     : %s" % spec_id,
        "Jurisdiction (files you may edit): %s" % (", ".join(jur_paths) or "see config/jurisdictions.json"),
        "",
        "--- SPEC CONTENT ---",
        spec_content,
        "--- END SPEC ---",
        "",
        "YOUR ASSIGNED TASKS:",
        task_list,
        "",
        "INSTRUCTIONS:",
        "1. Read existing code with the Read tool before editing anything.",
        "2. Implement ALL tasks listed above. Stay within your jurisdiction paths.",
        "3. When ALL tasks are complete, use the Bash tool to run:",
        "   python3 _cortex/log_event.py --type task_completed --description 'Completed tasks %s for %s' --spec %s" % (task_ids, spec_id, spec_id),
        "",
        "Implement now. No clarification needed. Start with step 1.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Worker subprocess runner
# ---------------------------------------------------------------------------

def _run_worker(role, tasks, build_id, spec_id, project_root, task_harness=None, task_model=None):
    """Spawn a harness worker for one role and wait for completion.

    Harness selection order: task_harness override → ROLE_HARNESS_DEFAULTS → antigravity.
    """
    prompt = _build_worker_prompt(role, tasks, spec_id, project_root)
    harness = task_harness or ROLE_HARNESS_DEFAULTS.get(role, "antigravity")

    if harness == 'antigravity':
        model = task_model or ROLE_MODEL_DEFAULTS.get(role)
        cmd = [AGY_BIN, '-p', prompt, '--dangerously-skip-permissions']
        if model:
            cmd.extend(['--model', model])
        agent_label = 'ANTIGRAVITY'
    elif harness == 'gemini':  # break-glass fallback
        cmd = [GEMINI_BIN, '-p', prompt, '--yolo']
        agent_label = 'GEMINI'
    else:
        cmd = [CLAUDE_BIN, '-p', prompt, '--dangerously-skip-permissions']
        agent_label = 'CLAUDE'

    import uuid
    session_id = os.environ.get("ADT_SESSION_ID") or str(uuid.uuid4())
    actual_model = task_model or ROLE_MODEL_DEFAULTS.get(role) if harness == 'antigravity' else None

    env = {
        **os.environ,
        "ADT_ROLE": role,
        "ADT_SPEC_ID": spec_id,
        "ADT_BUILD_ID": build_id,
        "ADT_SESSION_ID": session_id,
        "ADT_MODE": "worker",
        "CLAUDE_PROJECT_DIR": project_root,
    }
    if actual_model:
        env["AGY_MODEL"] = actual_model

    try:
        result = subprocess.run(
            cmd,
            env=env,
            cwd=project_root,
            stdin=subprocess.DEVNULL,  # Gemini calls readStdin() when stdin is not TTY;
            capture_output=True,       # DEVNULL gives EOF immediately so it doesn't block.
            text=True,
            timeout=1800,
        )
        if result.returncode != 0:
            _append_ads_event(
                role, spec_id, build_id, "build_role_failed",
                f"Worker {role} ({agent_label}) exited {result.returncode}: {result.stderr[:500]}",
                {"exit_code": result.returncode, "stderr": result.stderr[:500], "harness": harness},
                project_root,
            )
            return False
        return True
    except subprocess.TimeoutExpired:
        _append_ads_event(
            role, spec_id, build_id, "build_role_failed",
            f"Worker {role} ({agent_label}) timed out after 1800s",
            {"error": "timeout", "harness": harness},
            project_root,
        )
        return False
    except Exception as e:
        _append_ads_event(
            role, spec_id, build_id, "build_role_failed",
            f"Worker {role} ({agent_label}) failed: {e}",
            {"error": str(e), "harness": harness},
            project_root,
        )
        return False


# ---------------------------------------------------------------------------
# BuildExecutor
# ---------------------------------------------------------------------------

class BuildExecutor:
    """SPEC-056 Amendment A: Wave executor using claude --print subprocesses."""

    @staticmethod
    def spawn_swarm(build_id: str, spec_id: str, project_root: str, dtcp_url: str):
        """Entry point — called in a background thread from the build API."""
        original_role = "Systems_Architect"
        original_spec = spec_id

        try:
            # ------------------------------------------------------------------
            # Pre-flight: verify required harness binaries exist
            # ------------------------------------------------------------------
            claude_ok = (
                (os.path.isfile(CLAUDE_BIN) and os.access(CLAUDE_BIN, os.X_OK))
                or bool(shutil.which("claude"))
            )
            gemini_ok = (
                (os.path.isfile(GEMINI_BIN) and os.access(GEMINI_BIN, os.X_OK))
                or bool(shutil.which("gemini"))
            )
            if not claude_ok:
                builds = _load_builds(project_root)
                if build_id in builds:
                    builds[build_id]["status"] = "blocked"
                    builds[build_id]["error"] = (
                        f"claude CLI not found (CLAUDE_CODE_EXECPATH={CLAUDE_BIN}). "
                        "Ensure Claude Code is installed."
                    )
                    _save_builds(project_root, builds)
                _append_ads_event(
                    "Systems_Architect", spec_id, build_id, "build_blocked",
                    f"Build {build_id} blocked: claude CLI not found at {CLAUDE_BIN}.",
                    {"error": "harness_missing", "harness": "claude", "claude_bin": CLAUDE_BIN},
                    project_root,
                )
                _signal_pending_build(build_id, spec_id, "blocked", project_root)
                return
            if not gemini_ok:
                builds = _load_builds(project_root)
                if build_id in builds:
                    builds[build_id]["status"] = "blocked"
                    builds[build_id]["error"] = (
                        f"gemini CLI not found at {GEMINI_BIN}. "
                        "Install via: npm install -g @google/gemini-cli"
                    )
                    _save_builds(project_root, builds)
                _append_ads_event(
                    "Systems_Architect", spec_id, build_id, "build_blocked",
                    f"Build {build_id} blocked: gemini CLI not found at {GEMINI_BIN}.",
                    {"error": "harness_missing", "harness": "gemini", "gemini_bin": GEMINI_BIN},
                    project_root,
                )
                _signal_pending_build(build_id, spec_id, "blocked", project_root)
                return

            # ------------------------------------------------------------------
            # Load tasks for this spec
            # ------------------------------------------------------------------
            tasks_path = os.path.join(project_root, "_cortex", "tasks.json")
            with open(tasks_path) as f:
                all_tasks = json.load(f).get("tasks", [])

            spec_tasks = [
                t for t in all_tasks
                if t.get("spec_ref") == spec_id and t.get("status") != "completed"
            ]

            if not spec_tasks:
                builds = _load_builds(project_root)
                if build_id in builds:
                    builds[build_id]["status"] = "complete"
                    builds[build_id]["sessions"] = []
                    _save_builds(project_root, builds)
                _signal_pending_build(build_id, spec_id, "complete", project_root)
                return

            # ------------------------------------------------------------------
            # Build dependency waves (topological sort)
            # ------------------------------------------------------------------
            waves = _topological_waves(spec_tasks)

            all_roles = list(dict.fromkeys(
                t.get("assigned_to", "")
                for wave in waves
                for t in wave
                if t.get("assigned_to")
            ))

            builds = _load_builds(project_root)
            if build_id in builds:
                builds[build_id]["status"] = "running"
                builds[build_id]["sessions"] = [
                    {"role": r, "status": "pending", "is_orchestrator": False}
                    for r in all_roles
                ]
                builds[build_id]["waves"] = len(waves)
                _save_builds(project_root, builds)

            _append_ads_event(
                "Systems_Architect", spec_id, build_id, "build_started",
                (
                    f"Build {build_id} started for {spec_id}. "
                    f"{len(waves)} wave(s), {len(spec_tasks)} tasks, roles: {all_roles}"
                ),
                {"roles": all_roles, "task_count": len(spec_tasks), "waves": len(waves)},
                project_root,
            )
            _signal_pending_build(build_id, spec_id, "running", project_root)

            # ------------------------------------------------------------------
            # Execute waves in order
            # ------------------------------------------------------------------
            failed_roles = set()

            for wave_idx, wave_tasks in enumerate(waves):
                wave_by_role: dict = {}
                for t in wave_tasks:
                    role = t.get("assigned_to", "")
                    if role:
                        wave_by_role.setdefault(role, []).append(t)

                if not wave_by_role:
                    continue

                _append_ads_event(
                    "Systems_Architect", spec_id, build_id, "build_wave_start",
                    f"Wave {wave_idx + 1}/{len(waves)}: {list(wave_by_role.keys())}",
                    {"wave": wave_idx + 1, "total_waves": len(waves),
                     "roles": list(wave_by_role.keys())},
                    project_root,
                )

                for role, tasks in wave_by_role.items():
                    # Set DTCP identity for this worker before spawning
                    _set_active_role(project_root, role, spec_id)

                    builds = _load_builds(project_root)
                    if build_id in builds:
                        for s in builds[build_id].get("sessions", []):
                            if s["role"] == role:
                                s["status"] = "active"
                        _save_builds(project_root, builds)

                    task_harness = next(
                        (t.get("harness") for t in tasks if t.get("harness")), None
                    )
                    success = _run_worker(role, tasks, build_id, spec_id, project_root, task_harness=task_harness)

                    builds = _load_builds(project_root)
                    if build_id in builds:
                        for s in builds[build_id].get("sessions", []):
                            if s["role"] == role:
                                s["status"] = "done" if success else "failed"
                        _save_builds(project_root, builds)

                    if not success:
                        failed_roles.add(role)

                # Restore SA identity after each wave
                _set_active_role(project_root, original_role, original_spec)

            # ------------------------------------------------------------------
            # Final outcome
            # ------------------------------------------------------------------
            all_failed = bool(all_roles) and all(r in failed_roles for r in all_roles)
            final_status = "blocked" if all_failed else "complete"

            builds = _load_builds(project_root)
            if build_id in builds:
                builds[build_id]["status"] = final_status
                _save_builds(project_root, builds)

            partial = f" Partial: {list(failed_roles)} failed." if failed_roles else ""
            _append_ads_event(
                "Systems_Architect", spec_id, build_id,
                "build_blocked" if all_failed else "build_complete",
                (
                    f"Build {build_id} {'blocked' if all_failed else 'complete'} "
                    f"for {spec_id}.{partial}"
                ),
                {"roles": all_roles, "failed": list(failed_roles)},
                project_root,
            )
            _signal_pending_build(build_id, spec_id, final_status, project_root)

        except Exception as e:
            try:
                _set_active_role(project_root, original_role, original_spec)
            except Exception:
                pass
            builds = _load_builds(project_root)
            if build_id in builds:
                builds[build_id]["status"] = "blocked"
                builds[build_id]["error"] = str(e)
                _save_builds(project_root, builds)
            _append_ads_event(
                "Systems_Architect", spec_id, build_id, "build_blocked",
                f"Build {build_id} blocked: {e}", {"error": str(e)},
                project_root,
            )
            _signal_pending_build(build_id, spec_id, "blocked", project_root)
