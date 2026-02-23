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
            except (json.JSONDecodeError, OSError):
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
