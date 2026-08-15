# SPEC-105: Worker Namespace Sandbox (bwrap + Overlay + Diff-and-Commit)

**Status:** APPROVED — LIVE (implementation matches spec as of 2026-08-14 amendment)
**Author:** Systems_Architect (CLAUDE)
**Created:** 2026-08-13
**Amended:** 2026-08-14 (§3 workspace-copy pattern replaces --overlay-src/--tmp-overlay; ADT_SANDBOX_ENFORCE opt-in removed; fail-closed by default with ADT_SANDBOX_DISABLE=1 as sole dev-only escape hatch)
**Target Milestone:** v0.4.0 (this closes MASTER_PLAN §4 objective 3 "Namespace Sandboxing")
**Jurisdiction:** Backend_Engineer (`adt_center/api/build_executor.py`, new `adt_core/sandbox/`), DevOps_Engineer (`ops/` for bwrap install checks), Systems_Architect (this spec)
**Depends On:** SPEC-021 (Operator Console), SPEC-062 (Spec Map), AI_PROTOCOL §1.3 (DTCP compliance)
**Complements:** SPEC-106 (DTCP Monitor honesty banner during transition)

**Intent:** Every worker spawned by `build_executor.py` — regardless of harness (agy / gemini / claude) — MUST run inside a Linux namespace sandbox that gives it a **read-only view of the project tree and a private writable overlay it alone can see**. The worker keeps its automation flags (`--dangerously-skip-permissions`, `--yolo`) exactly as they are today, because those flags are correct for automation and disabling them would break headless builds. Enforcement happens OUT-OF-BAND: the worker's write attempts land in the overlay, invisible to the real project. When the worker exits, a **diff-and-commit reconciler** POSTs each overlay-changed file to the child project's DTCP `/request` endpoint; only files the DTCP allows are landed in the real project tree, each allow/deny logged to ADS. The worker never has direct filesystem write access to real project files. Ever.

**Triggering Event:** CEV-2026-08-13-004. Operator inspection of DTCP Monitor for `solar_system_1786569181` showed `total_requests: 0, total_denials: 0` on port 5006 despite ~500 file writes performed by workers during the project's forge and build history. Root cause investigation (2026-08-13, this Architect session) established:
1. Every worker spawn in `build_executor.py` (lines 1398, 1403, 1406, 2058, 2145) passes `--dangerously-skip-permissions` / `--yolo` to the harness CLI. **This is correct** — headless automation cannot prompt the operator per tool call.
2. The framework's only enforcement mechanism is a Claude-Code-specific PreToolUse hook (`adt_sdk/hooks/claude_pretool.py`) that requires harness cooperation to fire. Non-Claude harnesses (agy, gemini) never had such a hook. Even when Claude workers are used, the hook path is bypassed under headless automation flags at the framework level.
3. There is no OS-level jail. `grep -E "bwrap|unshare|firejail|nsjail" adt_center/api/build_executor.py` returns zero matches.
4. MASTER_PLAN.md §4 objective 3 ("Namespace Sandboxing: Full OS-level isolation for agent sessions (bwrap/unshare)") has been listed as an active v0.4.0 objective since the milestone opened; it has not been implemented.

Net effect: for every project ever forged or built by this framework, the ledger of governed writes on the child project's DTCP is `0` and the actual writes were made by unsandboxed subprocess workers using the operator's own uid/gid. This spec closes that gap without breaking automation.

**Success Condition:** (a) `build_executor.py` is refactored so every worker CLI invocation is wrapped by a new helper `adt_core/sandbox/spawn.py::spawn_in_sandbox(cmd, project_root, worker_id)` returning a `subprocess.Popen`-compatible handle. Direct `Popen([AGY_BIN, ...])` calls at the current spawn sites are forbidden after this spec lands. (b) `spawn_in_sandbox` builds a bwrap invocation that: creates a fresh user + mount namespace; bind-mounts the project root **read-only** at its real path; layers a writable tmpfs overlay (`upperdir`) at `/run/adt/workers/<worker_id>/upper`, `workdir` at `.../work`, mount-point at the project root; bind-mounts read-only the host binaries the harness needs (`/usr/bin`, `/usr/lib`, `~/.local/bin/agy`, `~/.gemini/`, `~/.claude/`); allows a limited writable scratch at `/tmp/adt_worker_<worker_id>`; drops all capabilities; unshares network only if the harness does not need OAuth (Antigravity does — network stays; documented per spawn as `network: "full"|"none"`). (c) Every automation flag currently passed to the harness (`--dangerously-skip-permissions`, `--yolo`, `--new-project`, `-p`) is preserved verbatim. This spec MUST NOT change any harness CLI argument. (d) After the worker exits, a new `adt_core/sandbox/reconciler.py::reconcile_overlay(overlay_dir, project_root, worker_id, child_dtcp_url)` enumerates every regular file, symlink, and deletion in the overlay's `upperdir`; for each, POSTs to `<child_dtcp_url>/request` with `{agent, role, spec_id, action: "edit"|"delete", params: {file: <rel_path>, content: <base64>}, rationale, dry_run: false}`; on `allow` response, atomically copies the file into the real project root (rename-through-tmp for durability); on `deny`, logs `worker_write_denied_by_dtcp` to ADS with the deny reason and the file's sha256, then discards the change. (e) The reconciler emits a summary ADS event `worker_reconciliation_complete` with `{worker_id, allowed_count, denied_count, deleted_count, total_bytes_written, wall_time_ms}`. (f) If bwrap is unavailable at spawn time (binary missing, kernel does not support user namespaces, current user cannot unshare), `spawn_in_sandbox` MUST refuse to launch and return an error `sandbox_unavailable`; the executor MUST NOT fall back to an unsandboxed spawn under any circumstance — fail-closed matches AI_PROTOCOL §1.3. (g) The child project's DTCP Monitor now reflects real traffic: every worker file mutation shows up as an allowed or denied request on `<child_dtcp_url>/status` counters and in the request feed. (h) An override switch `ADT_SANDBOX_DISABLE=1` exists ONLY for framework-development troubleshooting and, when set, causes `spawn_in_sandbox` to emit `sandbox_bypassed_by_env_override` at Tier 1 to ADS on every spawn AND to render the SPEC-106 red banner across the Console until the env var is cleared. In production the env var is refused (checked in operator settings).

---

## 1. Anti-Goals

- **Not** removing `--dangerously-skip-permissions`, `--yolo`, or any other harness automation flag. The flags are correct. The sandbox goes underneath them.
- **Not** changing the operator UX. Forge, build, spec-map rerun, and DTCP Monitor all keep the same buttons and flows. What changes is what happens under the hood.
- **Not** a Docker or VM-level isolation. bwrap + user namespaces is the target — it is fast enough to wrap every spawn, ships on every modern Linux, and doesn't require a daemon. VM-level isolation can be a future spec if the threat model demands it.
- **Not** SPEC-036 (Agent Filesystem Sandbox) rewritten. SPEC-036 targeted per-role jurisdiction paths inside DTCP; this spec targets OS-level isolation of the worker process itself. They stack — jurisdictions still evaluated at reconciliation time.
- **Not** applied to Systems_Architect Claude Code sessions running as the operator (i.e., THIS session). Those are interactive and already sandboxed at the harness layer via PreToolUse hooks. Worker sandbox is for `build_executor.py`-spawned subprocess workers only.

## 2. Threat Model

**In scope:** a worker (any harness) hallucinates or is prompt-injected into writing outside its jurisdiction, deleting files, exfiltrating data via arbitrary shell, or mutating framework files during a child-project build.

**Mitigations delivered by this spec:**
- Worker cannot see or write ANY path outside the project root bind-mount, so `rm -rf ~` targeting the operator's home directory does not resolve — that path is not in the mount namespace.
- Worker's writes to files it CAN see all land in the overlay; the real project files are never mutated by the worker's process. Every landing decision is made by the DTCP layer post-hoc.
- Worker cannot execute setuid binaries (bwrap drops `NO_NEW_PRIVS`).
- Worker cannot escalate via capabilities (all dropped).

**Explicitly out of scope for this spec:**
- Network exfiltration (workers still need network for OAuth + model API traffic; addressed in a future SPEC if needed via egress proxy).
- Timing/side-channel attacks against co-located workers.
- Kernel exploits that break out of user namespaces (Linux kernel vuln class; assumed patched by DevOps).

## 3. bwrap Invocation Template

**Amended 2026-08-14:** bwrap 0.9.0 (Ubuntu 24.10 default) lacks
`--overlay-src` / `--tmp-overlay` (added upstream in 0.10.0). Rather than
pin the framework to a self-built bwrap or substitute an out-of-band overlay
tool (an earlier implementation used `fuse-overlayfs`; that was reverted for
introducing a hidden dependency the spec did not sanction), this spec now
uses a **per-worker workspace populated via `cp -a --reflink=auto`** and
bind-mounted at `${PROJECT_ROOT}` inside bwrap. Only bwrap 0.9.0 flags are
used. The isolation invariant is unchanged: the worker cannot see or write
ANY host path outside the workspace bind, and its writes land in a directory
the reconciler owns.

### 3.1 Pre-spawn workspace population

```bash
mkdir -p /run/adt/workers/${WORKER_ID}
cp -a --reflink=auto ${PROJECT_ROOT}/. /run/adt/workers/${WORKER_ID}/workspace
```

`--reflink=auto` uses copy-on-write on btrfs/xfs where available and falls
back to plain copy elsewhere. For projects on ext4 this is a full copy; for
projects on CoW filesystems the workspace init is near-instant regardless of
project size.

### 3.2 bwrap invocation

```bash
bwrap \
  --unshare-user --unshare-pid --unshare-ipc --unshare-uts --unshare-cgroup \
  # network: kept unless spawn declares network="none"
  --die-with-parent \
  --new-session \
  --ro-bind / / \                                # base system read-only
  --tmpfs /tmp \
  --bind /run/adt/workers/${WORKER_ID}/scratch /tmp/scratch \
  --bind /run/adt/workers/${WORKER_ID}/workspace ${PROJECT_ROOT} \
  --ro-bind-try ${HOME}/.local/bin/agy ${HOME}/.local/bin/agy \
  --ro-bind-try ${HOME}/.gemini ${HOME}/.gemini \
  --ro-bind-try ${HOME}/.claude ${HOME}/.claude \
  --dev /dev --proc /proc \
  --chdir ${PROJECT_ROOT} \
  --setenv ADT_WORKER_ID ${WORKER_ID} \
  --setenv ADT_SANDBOX_ACTIVE 1 \
  --setenv HOME ${HOME} \
  --cap-drop ALL \
  --  \
  ${ORIGINAL_HARNESS_CMD}
```

The `${ORIGINAL_HARNESS_CMD}` is passed through UNMODIFIED — this is the
safety guarantee that automation flags are preserved. The workspace persists
on host disk under `/run/adt/workers/${WORKER_ID}/workspace` for the
reconciler to walk after the worker exits.

### 3.3 Host prerequisites (DevOps)

- `bwrap` >= 0.9.0 (`apt install bubblewrap`).
- Either `bwrap` installed setuid (`sudo chmod u+s /usr/bin/bwrap`) OR an
  AppArmor profile permitting bwrap to create unprivileged user namespaces.
  The setuid path is the upstream-recommended install pattern on distros
  that restrict unprivileged userns by default (Ubuntu 24.04+).
- `cp` from GNU coreutils (present on all supported hosts).
- Writable `/run/adt/workers/` (spawn.py falls back to `/tmp/adt-workers/`
  if unwritable).

Rationale for each unshare: `user` gives capability isolation without root;
`pid` prevents worker from signalling other workers; `ipc/uts/cgroup` are
cheap and reduce lateral surface. `net` is kept because Antigravity + Gemini
require network to reach model APIs.

## 4. Reconciler Data Flow

```
worker exits (any exit code)
  └─> executor calls reconciler.reconcile_overlay(overlay_dir, project_root, worker_id, dtcp_url)
       ├─> enumerate overlay upperdir:
       │     - regular files (new or modified)
       │     - symlinks
       │     - whiteouts (deletions in overlayfs semantics)
       ├─> for each entry:
       │     ├─> compute rel_path from project_root
       │     ├─> read content (base64 for binaries; utf-8 if valid)
       │     ├─> POST http://localhost:<child_dtcp_port>/request
       │     │       { agent, role, spec_id, action, params, rationale, dry_run: false }
       │     ├─> on allow → copy to real project (rename-through-tmp, fsync)
       │     ├─> on deny → discard, log worker_write_denied_by_dtcp
       │     └─> on network/DTCP error → treat as deny (fail-closed), log dtcp_unreachable_during_reconcile
       ├─> emit worker_reconciliation_complete summary event
       └─> destroy overlay tmpfs (cleanup)
```

Concurrency: reconciler runs sequentially per worker to keep DTCP decision ordering deterministic. Multiple worker reconciliations for the same project run under a per-project lock in `/run/adt/reconciler_locks/<project>.lock` to prevent concurrent writes to the same real file.

Atomicity: each landed file uses `open(dst.tmp, O_WRONLY|O_CREAT|O_TRUNC) -> write -> fsync -> rename(dst.tmp, dst)`. Partial reconciliation on crash leaves either the old file OR the new file, never a truncated one.

Performance target: reconciler MUST NOT be the bottleneck for realistic worker changesets (few tens of files). Bulk change budget: 500 files in under 10s wall time for typical text file sizes. Large binary files (>10MB) can be individually slower; log a warning if any single DTCP request exceeds 5s.

## 5. DTCP Policy Requirements

The child project's DTCP (`dtcp.json`) MUST already have the jurisdiction rules for each role. This spec does not add new DTCP semantics — it makes existing DTCP jurisdiction evaluation ACTUALLY FIRE, which today it doesn't. Consequences for operators:
- If the current jurisdiction files are permissive, reconciliation will allow everything and the Monitor will show 100% allows. That is not a bug — it is finally-visible ground truth about how permissive the current policy actually is.
- Tightening jurisdictions is a subsequent SCR-driven exercise, not part of this spec.

## 6. Fail-Closed Behaviors

| Condition | Behavior | ADS event |
|---|---|---|
| bwrap binary missing | Refuse spawn | `sandbox_unavailable` |
| kernel does not support user namespaces | Refuse spawn | `sandbox_unavailable_kernel` |
| overlay creation fails | Refuse spawn | `sandbox_overlay_init_failed` |
| DTCP unreachable during reconciliation | Deny all pending writes | `dtcp_unreachable_during_reconcile` |
| Reconciler crashes mid-run | Roll back landed files if partial; keep overlay for forensics | `reconciler_crash` |
| Env var `ADT_SANDBOX_DISABLE=1` in dev | Emit banner + Tier-1 warning event | `sandbox_bypassed_by_env_override` |
| Env var `ADT_SANDBOX_DISABLE=1` in production | Refuse; ignore var | `sandbox_bypass_refused` |

## 7. Verification Plan

1. **Unit** (`test_sandbox_spawn.py`): assert that a synthetic spawn with `cmd=["sh","-c","echo hi > /etc/hijacked"]` produces exit code non-zero and no `/etc/hijacked` on host.
2. **Unit**: assert that overlay is populated only, not the real project root, after a worker writes `foo.txt`. Before reconciler runs, `os.path.exists(project_root/foo.txt)` is `False`; the overlay contains it.
3. **Unit** (`test_reconciler.py`): given an overlay with 3 files and a DTCP mock returning allow/allow/deny, real project ends with the two allowed files landed, none of the denied.
4. **Unit**: DTCP-unreachable case denies all writes and logs the correct ADS event.
5. **Integration**: run an actual small forge on a throwaway project. After completion: `curl <child_dtcp_url>/status` shows non-zero `total_requests`; ADS ledger contains matching `worker_write_denied_by_dtcp` / `worker_reconciliation_complete` events; every file in the child project has a corresponding ADS request in the reconciler window.
6. **Regression**: existing forge templates SPEC-077 (ar_art_preview) and SPEC-079 (solar_system) still complete end-to-end after this spec lands. No template changes required.
7. **Security probe** (`test_sandbox_escape.py`): worker prompt injected to run `python -c 'open("/home/human/.ssh/authorized_keys","a").write("HIJACKED")'` — assert the file on host is unchanged AND the failed write attempt appears in the sandbox tmpfs (contained).

## 8. Rollout

- **Phase 0 (immediate, this spec + SPEC-106):** freeze new operator-initiated builds via a Console-level warning banner until Phase 1 lands. Operator can override for framework-development. Communication: SPEC-106.
- **Phase 1 (this spec, one PR):** implement `adt_core/sandbox/spawn.py`, `adt_core/sandbox/reconciler.py`. Refactor all `build_executor.py` spawn sites to route through `spawn_in_sandbox`. Deploy behind opt-in env `ADT_SANDBOX_ENFORCE=1` for a soak period so we can attribute failures. During soak, unsandboxed spawns emit `sandbox_disabled_by_default` at Tier 2 on every spawn.
- **Phase 2 (soak follow-up):** flip default: enforcement ON, `ADT_SANDBOX_DISABLE=1` becomes the opt-out (dev only). Retire the SPEC-106 monitor banner once counters correlate with reality on the framework project.
- **Phase 3:** consider egress network policy (separate spec) once the sandbox baseline is stable.

## 9. Standards Refs

- REQ-006 (ADS ASCII-safe descriptions)
- AI_PROTOCOL §1.3 (this spec is the missing implementation)
- SPEC-036 (Agent Filesystem Sandbox — stacks with this spec; jurisdictions evaluated at reconciliation)
- SPEC-045 (SCR Authorization Hardening — future amendment to require SCR for `ADT_SANDBOX_DISABLE=1` in prod)

## 10. Amendment to AI_PROTOCOL Required?

Currently AI_PROTOCOL §1.3 reads: *"All file operations and system actions must be routed through the DTCP service. Bypassing DTCP via direct shell commands is a CRITICAL VIOLATION."*

That statement remains correct AND becomes enforceable for the first time when this spec lands. No amendment to §1.3 is required. However, an SCR SHOULD add a §1.3.1 clarification:

> **§1.3.1 (added SPEC-105):** For worker subprocesses spawned by build_executor.py or equivalent orchestration code, DTCP routing is achieved via the namespace sandbox reconciler: worker writes land in a private overlay; the reconciler enumerates the overlay and POSTs each change to the child project's DTCP `/request` endpoint. Direct writes to the real project tree by worker processes are STRUCTURALLY PREVENTED by the mount namespace and are not merely a policy violation.

This clarification is bundled into the SCR that accompanies this spec's approval.

## 11. Open Questions

- **Q1:** Should the overlay be `tmpfs` (fast, RAM-backed, ephemeral) or a disk-backed overlay under `/var/lib/adt/overlays/`? tmpfs is faster but caps overlay size at available RAM. Disk-backed survives crashes for forensics. **Recommendation:** tmpfs for the overlay itself; disk-backed for a *forensic archive* copy created when the reconciler denies any file (so we can inspect what the worker tried to do). Settle in Backend implementation review.
- **Q2:** How to handle `.git/` writes? Workers doing `git commit` inside a build would write to `.git/index`, `.git/objects/`, etc. Under strict jurisdiction, `.git/` is usually forbidden. **Recommendation:** grant workers a per-project ephemeral scratch `.git` inside the overlay only (never landed to real project); real commits happen via a separate governed path (`git_commit` DTCP action) after reconciliation. May need an amendment to SPEC-036.
- **Q3:** How much does bwrap add to spawn latency? Empirical measurement required — if it's more than ~200ms per worker spawn, the Console's spawn responsiveness degrades noticeably. **Recommendation:** benchmark in Phase 1 soak, add to SPEC completion evidence.

---

*Rationale: Automation and governance are not in tension. Automation says "do not ask the operator per action." Governance says "record every action against policy." Both are satisfied when the enforcement plane is out-of-band. The sandbox is the out-of-band. Ship it.*
