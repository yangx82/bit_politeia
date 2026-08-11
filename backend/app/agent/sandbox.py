import asyncio
import logging
import os
import shutil
import tempfile
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Sandbox(ABC):
    """Abstract interface for tool execution environments."""

    @abstractmethod
    async def execute(
        self, command: str, working_dir: str | None = None, timeout: int = 300
    ) -> tuple[str, str, int]:
        """
        Execute a command in the sandbox.
        Returns: (stdout, stderr, exit_code)
        """
        pass

    @abstractmethod
    def cleanup(self):
        """Cleanup any resources used by the sandbox."""
        pass


class LocalSandbox(Sandbox):
    """
    Simulated sandbox using local processes with isolation features.
    - Temporary working directory.
    - Cleansed environment variables.
    - Timeout enforcement.
    """

    def __init__(self, base_dir: str | None = None):
        self.temp_dir = tempfile.mkdtemp(prefix="agent_sandbox_", dir=base_dir)
        logger.info(f"Initialized LocalSandbox at {self.temp_dir}")

    def execute_sync(
        self, command: str, working_dir: str | None = None, timeout: int = 300
    ) -> tuple[str, str, int]:
        cwd = working_dir or self.temp_dir

        # Ensure working_dir is within temp_dir or base_dir (security check)
        # For now, we trust the input if it's explicitly provided,
        # but default to our isolated temp space.

        # Prepare Environment (Allow only essential variables)
        safe_env = {
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "TEMP": self.temp_dir,
            "TMP": self.temp_dir,
            # Pass through ResearchClaw context
            "RESEARCHCLAW_HOME": os.environ.get("RESEARCHCLAW_HOME", ""),
            "BAILIAN_SP_KEY": os.environ.get("BAILIAN_SP_KEY", ""),
            "SEMANTIC_SCHOLAR_API_KEY": os.environ.get("SEMANTIC_SCHOLAR_API_KEY", ""),
            "OPENALEX_EMAIL": os.environ.get("OPENALEX_EMAIL", ""),
        }

        # Windows requires these to start subprocesses reliably
        if os.name == "nt":
            for key in ["COMSPEC", "SystemRoot", "SystemDrive"]:
                if os.environ.get(key):
                    safe_env[key] = os.environ.get(key)

        try:
            import subprocess

            # On Windows, we need to hide the console window when creating subprocess
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            try:
                result = subprocess.run(
                    command,
                    shell=True,  # nosec B602 (Internal tool execution in managed sandbox)
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=cwd,
                    env=safe_env,
                    text=True,
                    timeout=timeout,
                    startupinfo=startupinfo,
                    errors="replace",
                )
                return result.stdout, result.stderr, result.returncode
            except subprocess.TimeoutExpired as e:
                stdout_str = (
                    e.stdout.decode("utf-8", errors="replace")
                    if isinstance(e.stdout, bytes)
                    else e.stdout or ""
                )
                stderr_str = (
                    e.stderr.decode("utf-8", errors="replace")
                    if isinstance(e.stderr, bytes)
                    else e.stderr or ""
                )
                return stdout_str, f"{stderr_str}\nError: Command timed out", 124

        except Exception as e:
            logger.error(f"Sandbox execution error: {e!r}", exc_info=True)
            return ("", f"Sandbox Error ({type(e).__name__}): {e!s}", -1)

    async def execute(
        self, command: str, working_dir: str | None = None, timeout: int = 300
    ) -> tuple[str, str, int]:
        # Keep async interface for backwards compatibility if needed elsewhere
        return await asyncio.to_thread(self.execute_sync, command, working_dir, timeout)

    def cleanup(self):
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up Sandbox at {self.temp_dir}")
        except Exception as e:
            logger.error(f"Failed to cleanup sandbox: {e}")


class SandboxManager:
    """Manages sandbox instances."""

    @staticmethod
    def get_sandbox() -> Sandbox:
        # Future: detection of docker and return DockerSandbox
        return LocalSandbox()


# Global accessor pattern used in bit_politeia
def get_default_sandbox() -> Sandbox:
    return LocalSandbox()
