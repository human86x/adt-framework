import logging
import subprocess
import os

logger = logging.getLogger(__name__)

class GitSync:
    def __init__(self, project_root: str):
        self.project_root = os.path.realpath(project_root)

    def _run_git(self, args: list) -> bool:
        try:
            env = os.environ.copy()
            env["GIT_PAGER"] = "cat"
            env["GIT_TERMINAL_PROMPT"] = "0"
            subprocess.run(["git"] + args, cwd=self.project_root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            return True
        except Exception as e:
            logger.error(f"Git error: {e}")
            return False

    def commit_and_push(self, file_path: str, message: str, agent: str = None, role: str = None) -> bool:
        rel_path = os.path.relpath(file_path, self.project_root)
        if not self._run_git(["add", rel_path]): return False
        
        full_message = f"[ADT] {message}"
        if agent and role:
            full_message += f" - {agent} ({role})"
            
        self._run_git(["commit", "-m", full_message])
        if not self._run_git(["push"]):
            logger.warning("Push failed")
            return False
        return True
