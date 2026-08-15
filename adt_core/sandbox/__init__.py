"""SPEC-105: Worker Namespace Sandbox.

Provides bwrap-based OS-level isolation for build_executor.py-spawned workers.

Exports:
    spawn_in_sandbox(cmd, project_root, worker_id, network="full"): subprocess.Popen-like
    reconcile_overlay(overlay_dir, project_root, worker_id, child_dtcp_url, ...): reconciler
"""

from adt_core.sandbox.spawn import (
    spawn_in_sandbox,
    SandboxUnavailableError,
    SandboxWorkspaceInitError,
    is_sandbox_supported,
    sandbox_enforcement_active,
)
from adt_core.sandbox.reconciler import reconcile_overlay

__all__ = [
    "spawn_in_sandbox",
    "reconcile_overlay",
    "SandboxUnavailableError",
    "SandboxWorkspaceInitError",
    "is_sandbox_supported",
    "sandbox_enforcement_active",
]
