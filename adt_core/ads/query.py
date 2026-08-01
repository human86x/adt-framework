import json
import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def _normalize_event(e: dict) -> dict:
    """Map legacy ADS event schema keys onto the current schema for read-path
    consumers. The on-disk ledger is never mutated; this only affects in-memory
    dicts. Required because two pre-2026-04-10 events use {timestamp, event,
    spec, rationale} keys and break templates that assume {ts, action_type,
    spec_ref, description} under StrictUndefined. See REQ-059."""
    if not isinstance(e, dict):
        return e
    if "ts" not in e and "timestamp" in e:
        e["ts"] = e["timestamp"]
    if "action_type" not in e and "event" in e:
        e["action_type"] = e["event"]
    if "spec_ref" not in e and "spec" in e:
        e["spec_ref"] = e["spec"]
    if "description" not in e:
        e["description"] = e.get("rationale", "")
    e.setdefault("agent", "UNKNOWN")
    e.setdefault("role", "unknown")
    return e


class ADSQuery:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def get_all_events(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Dict[str, Any]]:
        if limit is not None and offset is None:
            return self._tail_events(limit)
        events = []
        try:
            with open(self.file_path, 'r') as f:
                for i, line in enumerate(f):
                    if not line.strip(): continue
                    if offset is not None and i < offset: continue
                    try: events.append(_normalize_event(json.loads(line)))
                    except json.JSONDecodeError: continue
                    if limit is not None and len(events) >= limit: break
        except FileNotFoundError: pass
        except Exception as e:
            logger.error(f"Error reading all events from {self.file_path}: {e}")
        return events

    def _tail_events(self, limit: int) -> List[Dict[str, Any]]:
        if limit <= 0: return []
        events = []
        try:
            if not os.path.exists(self.file_path): return []
            file_size = os.path.getsize(self.file_path)
            if file_size == 0: return []
            with open(self.file_path, 'rb') as f:
                buffer_size = 4096
                f.seek(0, os.SEEK_END)
                pos = f.tell()
                lines_found = 0
                data = b''
                newline = bytes([10])
                while pos > 0 and lines_found <= limit:
                    seek_pos = max(0, pos - buffer_size)
                    f.seek(seek_pos)
                    chunk = f.read(pos - seek_pos)
                    data = chunk + data
                    lines_found += chunk.count(newline)
                    pos = seek_pos
                all_lines = data.decode('utf-8').splitlines()
                target_lines = all_lines[-limit:] if len(all_lines) > limit else all_lines
                for line in target_lines:
                    if line.strip():
                        try: events.append(_normalize_event(json.loads(line)))
                        except json.JSONDecodeError: continue
        except FileNotFoundError: pass
        except (OSError, Exception) as e:
            logger.error(f"Error tailing events from {self.file_path}: {e}")
        return events

    def filter_events(self, agent=None, role=None, action_type=None, spec_ref=None, standard=None, limit=None, offset=None) -> List[Dict[str, Any]]:
        all_events = self.get_all_events()
        filtered = []
        for event in all_events:
            if agent and event.get('agent') != agent: continue
            if role and event.get('role') != role: continue
            if action_type and event.get('action_type') != action_type: continue
            if spec_ref and event.get('spec_ref') != spec_ref: continue
            if standard:
                # Check action_data for standard_id
                action_data = event.get('action_data', {})
                if action_data.get('standard_id') != standard: continue
            filtered.append(event)
        start = offset if offset else 0
        end = start + limit if limit else len(filtered)
        return filtered[start:end]

    def filter_by_standard(self, standard_id: str) -> List[Dict[str, Any]]:
        """SPEC-047: Return all events associated with a specific standard."""
        return self.filter_events(standard=standard_id)

    def get_last_event(self) -> Optional[Dict[str, Any]]:
        events = self._tail_events(1)
        return events[0] if events else None

    def get_active_sessions(self) -> int:
        """
        Counts active sessions by matching session_start and session_end events.
        """
        details = self.get_active_sessions_details()
        return len(details)

    def get_session_events(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Returns all events belonging to a specific session.
        REQ-113: tail-scan last 20k events instead of full ledger; recent sessions
        dominate the working set, and full-file linear scan is O(N) per request.
        """
        # 20k tail events cover >99% of active session lifetimes on 18MB+ ledgers.
        all_events = self._tail_events(20000)
        return [e for e in all_events if e.get("session_id") == session_id]

    def get_session_details(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Returns details for a specific session by its ID.
        """
        events = self.get_session_events(session_id)
        # Look for session_start
        for event in events:
            if event.get('action_type') == 'session_start':
                return {
                    "agent": event.get('agent'),
                    "role": event.get("role"),
                    "spec_id": event.get("spec_ref"),
                    "session_id": session_id,
                    "parent_session_id": event.get("parent_session_id"),
                    "ts": event.get("ts"),
                    "sandbox": event.get("action_data", {}).get("sandbox", False)
                }
        return None

    def get_active_sessions_details(self) -> List[Dict[str, Any]]:
        """
        Returns a list of details for all currently active sessions.
        REQ-113: tail-scan last 20k events. Sessions from days ago are dead anyway
        (a session_start with no matching session_end is a leak — those events would
        need to be within recent history to be meaningful).
        """
        all_events = self._tail_events(20000)
        # session_id -> session_detail_dict
        active_sessions = {}

        for event in all_events:
            agent = event.get('agent')
            action = event.get('action_type')
            session_id = event.get('session_id')
            
            # Fallback to agent if session_id is missing (legacy)
            sid = session_id or agent
            
            if not sid or not action:
                continue
            
            if action == 'session_start':
                active_sessions[sid] = {
                    "agent": agent,
                    "role": event.get("role"),
                    "spec_id": event.get("spec_ref"),
                    "session_id": session_id,
                    "parent_session_id": event.get("parent_session_id"),
                    "ts": event.get("ts"),
                    "sandbox": event.get("action_data", {}).get("sandbox", False)
                }
            elif action == 'session_end':
                if sid in active_sessions:
                    del active_sessions[sid]
        
        return list(active_sessions.values())
