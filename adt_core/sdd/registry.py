import os
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class SpecRegistry:
    """Manages discovery and lifecycle of specifications."""

    def __init__(self, specs_dir: str):
        self.specs_dir = specs_dir

    def list_specs(self) -> List[Dict[str, str]]:
        """Lists all specs found in the specs directory with their status."""
        specs = []
        if not os.path.exists(self.specs_dir):
            return specs

        for filename in os.listdir(self.specs_dir):
            if filename.endswith(".md") and filename.startswith("SPEC-"):
                spec_id = filename.split("_")[0]
                status = self._parse_status(os.path.join(self.specs_dir, filename))
                specs.append({
                    "id": spec_id,
                    "filename": filename,
                    "status": status or "UNKNOWN"
                })
        return sorted(specs, key=lambda x: x["id"])

    def get_spec_detail(self, spec_id: str) -> Optional[Dict[str, Any]]:
        """Returns detailed metadata for a specific spec."""
        for filename in os.listdir(self.specs_dir):
            if filename.startswith(spec_id):
                path = os.path.join(self.specs_dir, filename)
                return {
                    "id": spec_id,
                    "filename": filename,
                    "path": path,
                    "status": self._parse_status(path),
                    "title": self._parse_title(path),
                    "content": self._read_content(path)
                }
        return None

    def _parse_status(self, path: str) -> Optional[str]:
        """Parses the status from the spec markdown."""
        try:
            with open(path, "r") as f:
                content = f.read(1000) # Read first 1000 chars
                match = re.search(r"\*\*Status:\*\*\s*([A-Z]+)", content)
                if match:
                    return match.group(1)
        except OSError as e:
            logger.error(f"Error parsing status from {path}: {e}")
        return None

    def _parse_title(self, path: str) -> Optional[str]:
        """Parses the title from the spec markdown."""
        try:
            with open(path, "r") as f:
                line = f.readline()
                if line.startswith("# "):
                    return line[2:].strip()
        except OSError as e:
            logger.error(f"Error parsing title from {path}: {e}")
        return None

    def _read_content(self, path: str) -> str:
        """Reads the full content of the spec."""
        try:
            with open(path, "r") as f:
                return f.read()
        except OSError as e:
            logger.error(f"Error reading content from {path}: {e}")
            return ""
