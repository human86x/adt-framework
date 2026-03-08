import json
import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

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
                    try: events.append(json.loads(line))
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
                        try: events.append(json.loads(line))
                        except json.JSONDecodeError: continue
        except FileNotFoundError: pass
        except (OSError, Exception) as e:
            logger.error(f"Error tailing events from {self.file_path}: {e}")
        return events

    def filter_events(self, agent=None, role=None, action_type=None, spec_ref=None, limit=None, offset=None) -> List[Dict[str, Any]]:
        all_events = self.get_all_events()
        filtered = []
        for event in all_events:
            if agent and event.get('agent') != agent: continue
            if role and event.get('role') != role: continue
            if action_type and event.get('action_type') != action_type: continue
            if spec_ref and event.get('spec_ref') != spec_ref: continue
            filtered.append(event)
        start = offset if offset else 0
        end = start + limit if limit else len(filtered)
        return filtered[start:end]

    def get_last_event(self) -> Optional[Dict[str, Any]]:
        events = self._tail_events(1)
        return events[0] if events else None

    def get_active_sessions(self) -> int:
        """
        Counts active sessions by matching session_start and session_end events.
        """
        details = self.get_active_sessions_details()
        return len(details)

    def get_active_sessions_details(self) -> List[Dict[str, Any]]:
        """
        Returns a list of details for all currently active sessions.
        """
        all_events = self.get_all_events()
        active_sessions = {}  # agent -> session_detail_dict

        for event in all_events:
            agent = event.get('agent')
            action = event.get('action_type')
            if not agent or not action:
                continue
            
            if action == 'session_start':
                active_sessions[agent] = {
                    "agent": agent,
                    "role": event.get("role"),
                    "spec_id": event.get("spec_ref"),
                    "session_id": event.get("session_id"),
                    "ts": event.get("ts"),
                    "sandbox": event.get("action_data", {}).get("sandbox", False)
                }
            elif action == 'session_end':
                if agent in active_sessions:
                    del active_sessions[agent]
        
        return list(active_sessions.values())
