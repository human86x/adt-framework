import fcntl
import json
import logging
import os
from typing import Dict, Any, Optional

from .crypto import GENESIS_HASH, calculate_event_hash
from .schema import ADSEventSchema

logger = logging.getLogger(__name__)


class ADSLogger:
    """Atomic logger for the Authoritative Data Source (ADS)."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Creates the ADS file and its directory if they don't exist."""
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w") as f:
                pass

    def _get_last_event(self) -> Optional[Dict[str, Any]]:
        """Reads the last line of the ADS file to get the previous event."""
        if os.path.getsize(self.file_path) == 0:
            return None

        with open(self.file_path, "r") as f:
            try:
                f.seek(0, os.SEEK_END)
                pos = f.tell()
                while pos > 0:
                    pos -= 1
                    f.seek(pos)
                    if f.read(1) == "\n":
                        line = f.readline()
                        if line.strip():
                            return json.loads(line)

                f.seek(0)
                line = f.readline()
                if line.strip():
                    return json.loads(line)
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to read last ADS event from %s", self.file_path)
                return None
        return None

    def log(self, event: Dict[str, Any]) -> str:
        """
        Validates, hashes, and appends an event to the ADS file atomically.
        Returns the event_id.
        """
        if not ADSEventSchema.validate(event):
            raise ValueError("Event does not match schema")

        with open(self.file_path, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                last_event = self._get_last_event()
                prev_hash = last_event.get("hash", GENESIS_HASH) if last_event else GENESIS_HASH

                event["prev_hash"] = prev_hash
                event["hash"] = calculate_event_hash(event, prev_hash)

                f.write(json.dumps(event) + "\n")
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        return event["event_id"]
