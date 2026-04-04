import json
import logging
import os
import sys
from typing import Dict, Any, Optional

# Cross-platform file locking
try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

from adt_core.ads.crypto import GENESIS_HASH, calculate_event_hash
from adt_core.ads.schema import ADSEventSchema

logger = logging.getLogger(__name__)

class ADSLogger:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w') as f:
                pass

    def _get_last_event(self) -> Optional[Dict[str, Any]]:
        if os.path.getsize(self.file_path) == 0:
            return None
        with open(self.file_path, 'rb') as f:
            try:
                f.seek(0, os.SEEK_END)
                pos = f.tell()
                while pos > 0:
                    pos -= 1
                    f.seek(pos)
                    if f.read(1) == bytes([10]):
                        line = f.readline()
                        if line.strip(): return json.loads(line.decode('utf-8'))
                f.seek(0)
                line = f.readline()
                if line.strip(): return json.loads(line.decode('utf-8'))
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Error reading last event from {self.file_path}: {e}")
                return None
        return None

    def log(self, event: Dict[str, Any]) -> str:
        if not ADSEventSchema.validate(event):
            raise ValueError('Event does not match schema')
        
        with open(self.file_path, 'a+') as f:
            self._lock(f)
            try:
                last_event = self._get_last_event()
                prev_hash = last_event.get('hash', GENESIS_HASH) if last_event else GENESIS_HASH
                event['prev_hash'] = prev_hash
                event['hash'] = calculate_event_hash(event, prev_hash)
                nl = chr(10)
                f.write(json.dumps(event) + nl)
                f.flush()
                os.fsync(f.fileno())
            finally:
                self._unlock(f)
        return event['event_id']

    def _lock(self, f):
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_EX)
        elif msvcrt:
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(self, f):
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_UN)
        elif msvcrt:
            msvcrt.locking(f.fileno(), msvcrt.LK_ULOCK, 1)

    def log_delegation(self, agent: str, role: str, spec_ref: str, child_session_id: str, 
                       child_role: str, child_harness: str, task_id: str, 
                       strategy: str = "serial", skip_permissions: bool = False,
                       session_id: Optional[str] = None, parent_session_id: Optional[str] = None) -> str:
        """SPEC-042: Log a session_delegated event when spawning a child."""
        event_id = ADSEventSchema.generate_id("session_delegated")
        action_data = {
            "child_session_id": child_session_id,
            "child_role": child_role,
            "child_harness": child_harness,
            "task_id": task_id,
            "strategy": strategy,
            "skip_permissions": skip_permissions
        }
        event = ADSEventSchema.create_event(
            event_id=event_id,
            agent=agent,
            role=role,
            action_type="session_delegated",
            description=f"Delegated task {task_id} to child session {child_session_id} ({child_role})",
            spec_ref=spec_ref,
            session_id=session_id,
            parent_session_id=parent_session_id,
            action_data=action_data
        )
        return self.log(event)

    def log_delegation_complete(self, agent: str, role: str, spec_ref: str, 
                                child_session_id: str, parent_session_id: str, 
                                outcome: str, task_id: str, turns: int = 0) -> str:
        """SPEC-042: Log a session_delegation_complete event when a child session ends."""
        event_id = ADSEventSchema.generate_id("session_delegation_complete")
        action_data = {
            "parent_session_id": parent_session_id,
            "outcome": outcome,
            "turns": turns,
            "task_id": task_id
        }
        event = ADSEventSchema.create_event(
            event_id=event_id,
            agent=agent,
            role=role,
            action_type="session_delegation_complete",
            description=f"Child session {child_session_id} completed task {task_id} with outcome: {outcome}",
            spec_ref=spec_ref,
            session_id=child_session_id,
            parent_session_id=parent_session_id,
            action_data=action_data
        )
        return self.log(event)

    def log_group_created(self, agent: str, role: str, spec_ref: str, group_id: str, 
                          label: str, strategy: str, child_session_ids: List[str], 
                          child_roles: List[str], session_id: Optional[str] = None) -> str:
        """SPEC-042: Log a session_group_created event when spawning parallel children."""
        event_id = ADSEventSchema.generate_id("session_group_created")
        action_data = {
            "group_id": group_id,
            "label": label,
            "strategy": strategy,
            "child_session_ids": child_session_ids,
            "child_roles": child_roles
        }
        event = ADSEventSchema.create_event(
            event_id=event_id,
            agent=agent,
            role=role,
            action_type="session_group_created",
            description=f"Spawned parallel group {group_id} with {len(child_session_ids)} children: {label}",
            spec_ref=spec_ref,
            session_id=session_id,
            action_data=action_data
        )
        return self.log(event)
    def log_session_delegated(self, parent_session_id: str, child_session_id: str, child_role: str, child_harness: str, task_id: str, spec_ref: str, agent: str, role: str, rationale: str = "", **kwargs):
        event = ADSEventSchema.create_event(
            event_id=ADSEventSchema.generate_id("session_del"),
            agent=agent,
            role=role,
            action_type="session_delegated",
            description=f"Delegated {task_id} to {child_role} ({child_harness}).",
            spec_ref=spec_ref,
            session_id=parent_session_id,
            action_data={
                "child_session_id": child_session_id,
                "child_role": child_role,
                "child_harness": child_harness,
                "task_id": task_id,
                "rationale": rationale,
                **kwargs
            }
        )
        return self.log(event)

    def log_session_delegation_complete(self, session_id: str, status: str, outcome: str = "", agent: str = "SYSTEM", role: str = "Sentry", **kwargs):
        event = ADSEventSchema.create_event(
            event_id=ADSEventSchema.generate_id("session_end"),
            agent=agent,
            role=role,
            action_type="session_delegation_complete",
            description=f"Delegation session {session_id} completed with status: {status}",
            spec_ref="SPEC-042",
            session_id=session_id,
            action_data={
                "status": status,
                "outcome": outcome,
                **kwargs
            }
        )
        return self.log(event)