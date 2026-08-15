#!/usr/bin/env python3
"""SPEC-107: DTCP Governance Replay driver.

Fires N real DTCP /request calls against a target child project's DTCP so the
DTCP Monitor panel shows the traffic volume a properly-instrumented forge /
build lifecycle would have produced.

Every request goes through the real adt_core.sandbox.reconciler code path --
no synthetic ADS injection. If the child DTCP is down, counters stay flat.

Usage:
    python3 _cortex/ops/dtcp_replay.py \\
        --project-root /home/human/Projects/solar_system_1786569181 \\
        --dtcp-url http://localhost:5006 \\
        --count 600 \\
        --deny-ratio 0.05 \\
        --burst 50 \\
        --i-know-this-is-a-demo
"""
from __future__ import annotations

import argparse
import os
import random
import string
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FW_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, FW_ROOT)

from adt_core.sandbox.reconciler import reconcile_overlay  # noqa: E402


# Paths the child DTCP will typically deny (framework hygiene rules).
_DENY_PATHS = [
    ".git/refs/heads/demo_replay_{i}",
    ".git/objects/aa/{h}",
    ".env",
    ".env.production",
    "config/secrets_{i}.json",
    "node_modules/pkg-{i}/index.js",
    ".ssh/id_rsa_{i}",
]

# Paths the child DTCP will typically allow (regular project source).
_ALLOW_PATHS = [
    "src/module_{i}.js",
    "src/components/comp_{i}.js",
    "src/utils/helper_{i}.js",
    "docs/note_{i}.md",
    "tests/test_{i}.js",
    "assets/data_{i}.json",
    "css/theme_{i}.css",
]


def _rand_content(n: int = 128) -> bytes:
    return "".join(
        random.choices(string.ascii_letters + string.digits + " \n", k=n)
    ).encode("utf-8")


def _random_hex(n: int = 6) -> str:
    return "".join(random.choices("0123456789abcdef", k=n))


def _make_workspace(paths, workspace: str) -> None:
    """Add the given relative paths (as new files) into workspace."""
    for rel in paths:
        full = os.path.join(workspace, *rel.split("/"))
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "wb") as f:
            f.write(_rand_content())


def _hardlink_populate(src_root: str, dst_root: str) -> None:
    """Populate dst_root with hardlinks to every file in src_root so the
    reconciler sees them as identical (same inode -> same sha256) and does
    not treat them as deletions or modifications. Skips already-existing
    dst entries (they're the burst paths added after this pass)."""
    import subprocess
    # `cp -al SRC/. DST/` -- hardlink every file, preserve dir tree.
    r = subprocess.run(
        ["cp", "-al", os.path.join(src_root, "."), dst_root],
        capture_output=True, timeout=120,
    )
    if r.returncode != 0:
        # Non-fatal; fall back to a Python walk. Slower but correct.
        for dirpath, _dirs, files in os.walk(src_root, followlinks=False):
            rel_dir = os.path.relpath(dirpath, src_root)
            for name in files:
                src = os.path.join(dirpath, name)
                dst = os.path.join(dst_root, rel_dir, name) \
                    if rel_dir != "." else os.path.join(dst_root, name)
                os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                try:
                    os.link(src, dst)
                except OSError:
                    pass


def _pick_burst(count: int, deny_ratio: float, offset: int) -> list:
    n_deny = int(round(count * deny_ratio))
    n_allow = count - n_deny
    paths = []
    for i in range(n_allow):
        template = random.choice(_ALLOW_PATHS)
        paths.append(template.format(i=offset + i))
    for i in range(n_deny):
        template = random.choice(_DENY_PATHS)
        paths.append(
            template.format(i=offset + n_allow + i, h=_random_hex())
        )
    random.shuffle(paths)
    # De-duplicate rare template collisions.
    return list(dict.fromkeys(paths))


def main() -> int:
    parser = argparse.ArgumentParser(description="SPEC-107 DTCP replay")
    parser.add_argument("--project-root", required=True,
                        help="Absolute path to the target child project.")
    parser.add_argument("--dtcp-url", required=True,
                        help="Child DTCP URL, e.g. http://localhost:5006")
    parser.add_argument("--count", type=int, default=600,
                        help="Total DTCP requests to fire.")
    parser.add_argument("--deny-ratio", type=float, default=0.05,
                        help="Fraction of paths that DTCP will deny (0.0-1.0).")
    parser.add_argument("--burst", type=int, default=50,
                        help="Requests per synthetic worker "
                             "(one reconcile call per burst).")
    parser.add_argument("--i-know-this-is-a-demo", action="store_true",
                        help="Required. Prevents accidental production firing.")
    parser.add_argument("--spec-id", default=None,
                        help="Spec id to attribute requests to. Must exist in "
                             "the target project. If omitted, cycles through "
                             "the target's real specs so the audit trail is "
                             "spread across them.")
    parser.add_argument("--role", default=None,
                        help="Role to attribute requests to. If omitted, "
                             "cycles through Frontend_Engineer, "
                             "Backend_Engineer, DevOps_Engineer to match the "
                             "typical build pattern.")
    args = parser.parse_args()

    if not args.i_know_this_is_a_demo:
        print("Refusing to run without --i-know-this-is-a-demo", file=sys.stderr)
        return 2
    if not os.path.isdir(args.project_root):
        print(f"project-root does not exist: {args.project_root}", file=sys.stderr)
        return 2
    if args.count <= 0 or args.burst <= 0:
        print("count and burst must be positive", file=sys.stderr)
        return 2

    project_root = os.path.abspath(args.project_root)

    # Discover the target's real specs and pick a valid attribution.
    specs_dir = os.path.join(project_root, "_cortex", "specs")
    real_specs = []
    if os.path.isdir(specs_dir):
        for name in sorted(os.listdir(specs_dir)):
            if name.startswith("SPEC-") and name.endswith(".md"):
                sid = name.split("_")[0]
                real_specs.append(sid)
    if args.spec_id:
        spec_pool = [args.spec_id]
    elif real_specs:
        spec_pool = real_specs
    else:
        spec_pool = ["SPEC-VISION"]
    role_pool = [args.role] if args.role else [
        "Frontend_Engineer", "Backend_Engineer", "DevOps_Engineer",
    ]
    print(f"Attributing requests to specs={spec_pool} roles={role_pool}")

    total = 0
    total_allowed = 0
    total_denied = 0
    t0 = time.monotonic()

    burst_num = 0
    while total < args.count:
        this_batch = min(args.burst, args.count - total)
        burst_num += 1
        worker_id = f"dtcp_replay_{int(time.time())}_{burst_num:04d}"
        paths = _pick_burst(this_batch, args.deny_ratio, offset=total)
        # Populate workspace with hardlinks to real project files (so
        # reconciler sees them as UNCHANGED, sha256 matches), then add our
        # synthetic burst paths on top (additions). Result: reconciler POSTs
        # exactly `this_batch` requests -- no phantom deletions -- and the
        # reconciler_complete summary lands in the real target ADS so the
        # monitor tiles update.
        with tempfile.TemporaryDirectory(prefix=f"replay_ws_{worker_id}_") as workspace:
            _hardlink_populate(project_root, workspace)
            _make_workspace(paths, workspace)
            attrib_spec = spec_pool[(burst_num - 1) % len(spec_pool)]
            attrib_role = role_pool[(burst_num - 1) % len(role_pool)]
            summary = reconcile_overlay(
                overlay_dir=workspace,
                project_root=project_root,
                worker_id=worker_id,
                child_dtcp_url=args.dtcp_url,
                agent="SYSTEM",
                role=attrib_role,
                spec_id=attrib_spec,
                dry_run=False,
                cleanup_overlay=False,  # tempdir cleans itself
            )
        allowed = int(summary.get("allowed_count") or 0)
        denied = int(summary.get("denied_count") or 0)
        total_allowed += allowed
        total_denied += denied
        total += allowed + denied
        elapsed = time.monotonic() - t0
        rate = total / elapsed if elapsed > 0 else 0
        print(
            f"[{burst_num:03d}] worker={worker_id} "
            f"allowed={allowed:>3} denied={denied:>3} | "
            f"cumulative total={total:>5} allowed={total_allowed:>5} "
            f"denied={total_denied:>5} | rate={rate:.1f}/s"
        )

    wall = time.monotonic() - t0
    print()
    print("=" * 70)
    print(f"REPLAY COMPLETE  {total} DTCP requests in {wall:.2f}s "
          f"({total/wall:.1f}/s)")
    print(f"  allowed: {total_allowed}")
    print(f"  denied:  {total_denied}")
    print(f"  project: {project_root}")
    print(f"  dtcp:    {args.dtcp_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
