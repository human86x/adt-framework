import json
import os
from typing import List, Dict, Any, Optional

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
        except (FileNotFoundError, OSError): pass
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
        A session is active if there is a session_start with no subsequent session_end
        for the same agent.
        """
        all_events = self.get_all_events()
        agent_sessions = {}  # agent -> last_event_type

        for event in all_events:
            agent = event.get('agent')
            action = event.get('action_type')
            if not agent or not action:
                continue
            
            if action == 'session_start':
                agent_sessions[agent] = 'start'
            elif action == 'session_end':
                agent_sessions[agent] = 'end'
        
        return sum(1 for status in agent_sessions.values() if status == 'start')
