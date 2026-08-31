import os
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class SpecRegistry:
    """Manages discovery and lifecycle of specifications."""

    def __init__(self, specs_dir: str):
        self.specs_dir = specs_dir

    @staticmethod
    def _extract_spec_id(filename: str) -> str:
        """Derive a unique spec ID from a filename, distinguishing amendments.

        SPEC-062_SPEC_SKILL_TREE_MAP.md          -> "SPEC-062"
        SPEC-062_AMENDMENT_H_AUTO_FORGE_...md    -> "SPEC-062-H"
        SPEC-062_AMENDMENT_C1_MAP_LEGIBILITY.md  -> "SPEC-062-C1"
        """
        m = re.match(r"(SPEC-\d+)(?:_AMENDMENT_([A-Z0-9]+))?", filename)
        if not m:
            return filename.split("_")[0]
        parent = m.group(1)
        amend = m.group(2)
        return f"{parent}-{amend}" if amend else parent

    def list_specs(self) -> List[Dict[str, str]]:
        """Lists all specs found in the specs directory with their status."""
        specs = []
        if not os.path.exists(self.specs_dir):
            return specs

        for filename in os.listdir(self.specs_dir):
            if filename.endswith(".md") and filename.startswith("SPEC-"):
                spec_id = self._extract_spec_id(filename)
                status = self._parse_status(os.path.join(self.specs_dir, filename))
                path = os.path.join(self.specs_dir, filename)
                specs.append({
                    "id": spec_id,
                    "filename": filename,
                    "status": status or "UNKNOWN",
                    "title": self._parse_title(path),
                    "intent": self._parse_intent(path) or "—",
                    "task_count": self._count_tasks(path),
                    "category": self._parse_category(path)
                })
        return sorted(specs, key=lambda x: x["id"])

    def get_spec_detail(self, spec_id: str) -> Optional[Dict[str, Any]]:
        """Returns detailed metadata for a specific spec.

        Matches on extracted spec ID so amendments (SPEC-062-H) resolve
        to their own file, not the parent SPEC-062.
        """
        for filename in os.listdir(self.specs_dir):
            if not (filename.endswith(".md") and filename.startswith("SPEC-")):
                continue
            if self._extract_spec_id(filename) == spec_id:
                path = os.path.join(self.specs_dir, filename)
                return {
                    "id": spec_id,
                    "filename": filename,
                    "path": path,
                    "status": self._parse_status(path),
                    "title": self._parse_title(path),
                    "category": self._parse_category(path),
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

    def _parse_intent(self, path: str) -> Optional[str]:
        """Parses the intent from the spec markdown."""
        try:
            with open(path, "r") as f:
                content = f.read(2000)
                match = re.search(r"\*\*Intent:\*\*\s*(.*)", content)
                if match:
                    return match.group(1).strip()
        except OSError as e:
            logger.error(f"Error parsing intent from {path}: {e}")
        return None

    def _parse_category(self, path: str) -> Optional[str]:
        """Parses the category from the spec markdown (first ~2000 chars)."""
        try:
            with open(path, "r") as f:
                content = f.read(2000)
                match = re.search(r"\*\*Category:\*\*\s*(.*)", content)
                if match:
                    return match.group(1).strip()
        except OSError as e:
            logger.error(f"Error parsing category from {path}: {e}")
        return None

    def _count_tasks(self, path: str) -> int:
        """Counts tasks in the task breakdown section."""
        try:
            with open(path, "r") as f:
                content = f.read()
                # Find task section
                task_section = re.search(r"## (?:Task Breakdown|Tasks)(.*?)(?:##|$)", content, re.DOTALL | re.IGNORECASE)
                if task_section:
                    return len(re.findall(r"- task_\d+:", task_section.group(1)))
        except OSError as e:
            logger.error(f"Error counting tasks in {path}: {e}")
        return 0

    def _read_content(self, path: str) -> str:
        """Reads the full content of the spec."""
        try:
            with open(path, "r") as f:
                return f.read()
        except OSError as e:
            logger.error(f"Error reading content from {path}: {e}")
            return ""
