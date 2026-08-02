import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class ADSEventSchema:
    """Schema definition and validation for ADS events."""

    REQUIRED_FIELDS = [
        "event_id",
        "ts",
        "agent",
        "role",
        "action_type",
        "description",
        "spec_ref",
        "authorized"
    ]

    # SPEC-041: Swarm Governance / Session Tracking
    OPTIONAL_FIELDS = [
        "session_id",
        "parent_session_id",
        "tier",
        "action_data",
        "prev_hash",
        "hash",
        "execution_result",
        "escalation",
        "intent_id",
        "gate_id"
    ]

    # SPEC-026: Task Lifecycle Event Types
    TASK_EVENTS = [
        "task_status_updated",  # Agent self-service
        "task_approved",        # Human approval
        "task_rejected",        # Human rejection
        "task_reassigned",      # Human reassignment
        "task_reopened"         # Human reopen
    ]

    # SPEC-038 + SPEC-038A: Capability Governance Event Types
    CAPABILITY_EVENTS = [
        "capability_intent_defined",
        "capability_event_captured",
        "capability_maturity_updated",
        "capability_gate_evaluated",
        "capability_intent_status_changed",
        "capability_gate_refined",
    ]

    # SPEC-039: Orchestration and Steering Event Types
    ORCHESTRATION_EVENTS = [
        "human_steering",
        "pty_write",
        "pty_subscribe",
        "spec_decompose_requested",  # SPEC-062 Amendment D: empty-spec auto-decompose
        "spec_decompose_complete",
    ]

    # SPEC-042: Swarm Governance Event Types
    SWARM_EVENTS = [
        "session_delegated",
        "session_delegation_complete",
        "session_group_created",
        "delegation_denied"
    ]

    # SPEC-046: Standards Governance Layer Event Types
    STANDARDS_EVENTS = [
        "standard_registered",
        "clause_adopted",
        "clause_adapted",
        "clause_dismissed",
        "clause_dispositioned",
        "standards_registry_changed",
        "standards_ref_overridden",
        "standards_override_set"
    ]

    # SPEC-066: Standards Workbench (Rationalised / Machine-Readable Rules)
    STANDARDS_WORKBENCH_EVENTS = [
        "rationalised_rule_created",
        "rationalised_rule_dispositioned",
        "machine_readable_rule_created",
    ]

    # SPEC-054: Console Self-Bootstrap Event Types
    CONSOLE_BOOTSTRAP_EVENTS = [
        "console_bootstrap_start",      # setup() probe begins
        "console_bootstrap_spawned",    # child process spawned (per service)
        "console_bootstrap_ready",      # all services healthy
        "console_bootstrap_failed",     # timeout or spawn error
    ]

    # SPEC-062 Amendment E: Build Worker Lifecycle event types
    BUILD_LIFECYCLE_EVENTS = [
        "build_worker_spawned",       # PID, role, harness, model, log_path, task_ids
        "build_worker_health_check",  # PID, alive, tasks_completed, stall_count
        "build_worker_stalled",       # PID, role, stall_count, completed_age_sec
        "build_worker_timeout",       # PID, role, timeout_sec OR reason
        "build_worker_failed",        # PID, role, returncode, stderr_tail, log_path
        "build_worker_silent_exit",   # PID, role, returncode=0, 0 tasks completed
        "build_worker_orphaned",      # PID disappeared without exit notification
        "build_worker_completed",     # PID, role, tasks_completed, log_path
    ]

    # SPEC-062 Amendment F: Build Verification Loop event types
    VERIFICATION_EVENTS = [
        "build_verification_started",          # build_id, spec_id, iteration, verifier_pid
        "build_verification_finding",          # task_id, criterion, status, evidence, severity
        "build_verification_complete",         # build_id, passed, failed, partial, cannot_verify, recommendation
        "build_fix_dispatched",                # build_id, fix_task_ids, iteration
        "build_verification_max_iterations",   # build_id, last_failed_count
        "build_verified",                      # build_id (terminal success)
        "build_verified_failed",               # build_id (terminal failure after fix loop)
    ]

    # SPEC-055: Build Orchestration Engine Event Types
    BUILD_EVENTS = [
        "build_initiated",      # POST /build received, record created
        "build_started",        # Orchestrator SA begins execution
        "build_role_spawned",   # Worker PTY session spawned for a role
        "build_blocked",        # Task failure blocks the build
        "build_complete",       # All tasks completed successfully
        "build_aborted",        # Build manually aborted
    ]

    # SPEC-049: Cross-AI Orchestration Event Types
    CROSS_AI_EVENTS = [
        "cross_ai_orchestration_start",
        "cross_ai_task_assigned",
        "cross_ai_task_accepted",
        "cross_ai_progress_update",
        "cross_ai_task_complete",
        "cross_ai_task_aborted",
        "cross_ai_orchestration_complete",
        "cross_ai_task_verified",
        "cross_ai_task_rejected",
        "cross_ai_task_retasked",
        "forge_approval_received"
    ]

    # SPEC-057: Agent Mailbox & Messaging Bus Event Types
    AGENT_MAILBOX_EVENTS = [
        "agent_message_sent",
        "agent_message_delivered",
        "agent_message_queued",
        "agent_message_flushed",
        "agent_message_discarded",
        "agent_reply_received",
        "agent_broadcast_sent",
        "agent_mode_changed",
    ]

    # SPEC-045: SCR Authorization Hardening Event Types
    HARDENING_EVENTS = [
        "auth_spoofing_attempt",
    ]

    # SPEC-033: Sovereign Change Request Event Types
    SCR_EVENTS = [
        "sovereign_change_proposed",
        "sovereign_change_authorized",
        "sovereign_change_rejected",
        "sovereign_change_edited",
        "sovereign_change_applied"
    ]

    # SPEC-058: Real-Time Token Telemetry
    TELEMETRY_EVENTS = [
        "token_usage_updated",
        "budget_limit_reached",
        "telemetry_cache_flushed"
    ]

    # SPEC-063: Project Bootstrap Scaffold
    SCAFFOLD_EVENTS = [
        "project_scaffold_extended"
    ]

    # SPEC-067: Forge Wizard lifecycle event types
    # SPEC-074: Forge Live Genesis Stream events
    FORGE_EVENTS = [
        "forge_initiated",          # path, intent, name
        "forge_brief_written",      # forge_session_id, fields_count
        "forge_worker_spawned",     # forge_session_id, pid
        "forge_vision_filled",      # forge_session_id, spec_id="SPEC-001"
        "forge_child_spec_created", # forge_session_id, spec_id, title
        "forge_complete",           # forge_session_id, spec_ids
        "forge_failed",             # forge_session_id, reason, log_path
        "forge_phase_started",      # phase, seq, started_at
        "forge_phase_completed",    # phase, seq, duration_ms, outcome
        "forge_phase_failed",       # phase, seq, duration_ms, outcome, error
        "forge_session_created",    # forge_session_id, project_name, phase_timings
    ]

    # SPEC-020 Amendment B: Canonical values for normalization
    CANONICAL_AGENTS = ["CLAUDE", "GEMINI", "HUMAN", "SYSTEM", "ANTIGRAVITY", "CLI", "UNKNOWN"]
    CANONICAL_ROLES: Optional[List[str]] = None  # Loaded at startup

    @staticmethod
    def normalize_agent(agent: str) -> str:
        """Normalize agent identifier to uppercase canonical form."""
        if not agent:
            return "UNKNOWN"
        for canonical in ADSEventSchema.CANONICAL_AGENTS:
            if agent.upper() == canonical:
                return canonical
        return agent.upper()

    @staticmethod
    def normalize_role(role: str) -> str:
        """Normalize role name to canonical casing from jurisdictions.json."""
        if not role:
            return "unknown"
        if ADSEventSchema.CANONICAL_ROLES is None:
            return role
        for canonical in ADSEventSchema.CANONICAL_ROLES:
            if role.lower() == canonical.lower():
                return canonical
        return role

    @staticmethod
    def generate_id(action_type: str) -> str:
        """Generates a unique event ID based on type and timestamp."""
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
        return f"evt_{ts_str}_{action_type[:10]}"

    @staticmethod
    def validate(event_data: Dict[str, Any]) -> bool:
        """Validates that all required fields are present in the event."""
        for field in ADSEventSchema.REQUIRED_FIELDS:
            if field not in event_data:
                return False
        
        # SPEC-020 Amendment B: Role normalization check (warning only)
        if ADSEventSchema.CANONICAL_ROLES:
            role = event_data.get("role", "")
            if role.lower() not in [r.lower() for r in ADSEventSchema.CANONICAL_ROLES]:
                logger.warning(f"ADS: Unknown role '{role}' not in canonical list")

        # Validate tier if present
        if "tier" in event_data:
            if event_data["tier"] not in [1, 2, 3]:
                return False

        # Validate timestamp format
        try:
            datetime.fromisoformat(event_data["ts"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return False
            
        return True

    @staticmethod
    def create_event(
        event_id: str,
        agent: str,
        role: str,
        action_type: str,
        description: str,
        spec_ref: str,
        authorized: bool = True,
        tier: Optional[int] = None,
        session_id: Optional[str] = None,
        parent_session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Helper to create a standard event dictionary."""
        event = {
            "event_id": event_id,
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "agent": ADSEventSchema.normalize_agent(agent),
            "role": ADSEventSchema.normalize_role(role),
            "action_type": action_type,
            "description": description,
            "spec_ref": spec_ref,
            "authorized": authorized
        }
        if tier is not None:
            event["tier"] = tier
        if session_id:
            event["session_id"] = session_id
        if parent_session_id:
            event["parent_session_id"] = parent_session_id
        
        event.update(kwargs)
        return event

_CANONICAL_AGENTS = {"CLAUDE", "GEMINI", "ANTIGRAVITY", "HUMAN", "SYSTEM", "CLI", "UNKNOWN"}

def resolve_agent(default: str = "UNKNOWN") -> str:
    """Derive the running agent label.

    Order:
      1. ADT_AGENT env var (explicit; wins).
      2. Heuristic on argv[0] / parent binary path.
      3. The supplied default.
    """
    import os
    import sys
    env = os.environ.get("ADT_AGENT", "").strip().upper()
    if env in _CANONICAL_AGENTS:
        return env
    argv0 = (sys.argv[0] if sys.argv else "").lower()
    if "agy" in argv0 or "antigravity" in argv0:
        return "ANTIGRAVITY"
    if "claude" in argv0:
        return "CLAUDE"
    if "gemini" in argv0:
        return "GEMINI"
    return default if default in _CANONICAL_AGENTS else "UNKNOWN"

