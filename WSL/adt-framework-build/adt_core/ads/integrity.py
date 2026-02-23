import json
import logging
from typing import List, Tuple

from .crypto import GENESIS_HASH, calculate_event_hash

logger = logging.getLogger(__name__)


class ADSIntegrity:
    """Tools for verifying the integrity of the ADS hash chain."""

    @staticmethod
    def verify_chain(file_path: str) -> Tuple[bool, List[str]]:
        """
        Verifies the entire hash chain in the ADS file.
        Returns (is_valid, list_of_errors).
        """
        errors = []
        is_valid = True
        prev_hash = GENESIS_HASH

        try:
            with open(file_path, "r") as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue

                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        errors.append(f"Line {line_num}: Invalid JSON")
                        is_valid = False
                        continue

                    if event.get("prev_hash") != prev_hash:
                        errors.append(f"Line {line_num}: Broken chain link (expected prev_hash {prev_hash})")
                        is_valid = False

                    expected_hash = calculate_event_hash(event, prev_hash)
                    if event.get("hash") != expected_hash:
                        errors.append(f"Line {line_num}: Invalid hash (expected {expected_hash})")
                        is_valid = False

                    prev_hash = event.get("hash", "")

        except FileNotFoundError:
            errors.append("ADS file not found")
            return False, errors

        return is_valid, errors
