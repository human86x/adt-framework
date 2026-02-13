import logging
import os
import shutil
from typing import Dict, Any

from adt_core.dttp.sync import GitSync

logger = logging.getLogger(__name__)


class ActionHandler:
    """Handles execution of authorized DTTP actions."""

    def __init__(self, project_root: str):
        self.project_root = os.path.realpath(project_root)
        self.git_sync = GitSync(self.project_root)

    def _resolve_path(self, relative_path: str) -> str:
        """Resolves a relative path and ensures it stays within project_root."""
        resolved = os.path.realpath(os.path.join(self.project_root, relative_path))
        if not (resolved == self.project_root or resolved.startswith(self.project_root + os.sep)):
            raise PermissionError(f"Path escapes project root: {relative_path}")
        return resolved

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches action to the appropriate handler."""
        handler_name = f"_handle_{action}"
        if hasattr(self, handler_name):
            handler = getattr(self, handler_name)
            try:
                return handler(params)
            except PermissionError as e:
                logger.warning("Permission denied: %s", e)
                return {"status": "denied", "message": str(e)}
            except Exception as e:
                logger.error("Action %s failed: %s", action, e)
                return {"status": "error", "message": str(e)}
        return {"status": "error", "message": f"Unknown action: {action}"}

    def _handle_edit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        file_path = self._resolve_path(params["file"])
        content = params["content"]
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
        
        # Auto-Sync
        self.git_sync.commit_and_push(file_path, f"edit {params["file"]}")
        
        return {"status": "success", "result": "file_written", "bytes": len(content)}

    def _handle_create(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._handle_edit(params)

    def _handle_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        file_path = self._resolve_path(params["file"])
        if os.path.isdir(file_path):
            shutil.rmtree(file_path)
        else:
            os.remove(file_path)
            
        # Auto-Sync
        self.git_sync.commit_and_push(params["file"], f"delete {params["file"]}")
        
        return {"status": "success", "result": "file_deleted"}

    def _handle_patch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handles partial file edits (old_string -> new_string replacement)."""
        file_path = self._resolve_path(params["file"])
        old_string = params["old_string"]
        new_string = params["new_string"]

        if not os.path.isfile(file_path):
            return {"status": "error", "message": f"File not found: {params['file']}"}

        with open(file_path, "r") as f:
            content = f.read()

        count = content.count(old_string)
        if count == 0:
            return {"status": "error", "message": "old_string not found in file"}
        if count > 1:
            return {"status": "error", "message": f"old_string is ambiguous ({count} matches)"}

        new_content = content.replace(old_string, new_string, 1)
        with open(file_path, "w") as f:
            f.write(new_content)
            
        # Auto-Sync
        self.git_sync.commit_and_push(file_path, f"patch {params["file"]}")

        return {"status": "success", "result": "file_patched", "bytes": len(new_content)}

    def _handle_deploy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "success", "result": "deploy_simulated", "target": params.get("target")}

    def _handle_ftp_sync(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "success", "result": "ftp_sync_simulated", "target": params.get("target")}
