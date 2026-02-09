import logging
import os
import shutil
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ActionHandler:
    """Handles execution of authorized DTTP actions."""

    def __init__(self, project_root: str):
        self.project_root = os.path.realpath(project_root)

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
        return {"status": "success", "result": "file_written", "bytes": len(content)}

    def _handle_create(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._handle_edit(params)

    def _handle_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        file_path = self._resolve_path(params["file"])
        if os.path.isdir(file_path):
            shutil.rmtree(file_path)
        else:
            os.remove(file_path)
        return {"status": "success", "result": "file_deleted"}

    def _handle_deploy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "success", "result": "deploy_simulated", "target": params.get("target")}

    def _handle_ftp_sync(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "success", "result": "ftp_sync_simulated", "target": params.get("target")}
