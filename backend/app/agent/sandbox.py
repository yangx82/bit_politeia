import asyncio
import os
import shutil
import tempfile
import logging
from typing import Optional, List, Dict, Any, Tuple
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class Sandbox(ABC):
    """Abstract interface for tool execution environments."""
    
    @abstractmethod
    async def execute(self, command: str, working_dir: Optional[str] = None, timeout: int = 60) -> Tuple[str, str, int]:
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
    
    def __init__(self, base_dir: Optional[str] = None):
        self.temp_dir = tempfile.mkdtemp(prefix="agent_sandbox_", dir=base_dir)
        logger.info(f"Initialized LocalSandbox at {self.temp_dir}")
        
    async def execute(self, command: str, working_dir: Optional[str] = None, timeout: int = 60) -> Tuple[str, str, int]:
        cwd = working_dir or self.temp_dir
        
        # Ensure working_dir is within temp_dir or base_dir (security check)
        # For now, we trust the input if it's explicitly provided, 
        # but default to our isolated temp space.
        
        # Prepare Environment (Allow only essential variables)
        safe_env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "TEMP": self.temp_dir,
            "TMP": self.temp_dir,
        }
        
        # Windows requires these to start subprocesses reliably
        if os.name == 'nt':
            for key in ["COMSPEC", "SystemRoot", "SystemDrive"]:
                if os.environ.get(key):
                    safe_env[key] = os.environ.get(key)
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=safe_env
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                exit_code = process.returncode or 0
                return (
                    stdout.decode("utf-8", errors="replace"),
                    stderr.decode("utf-8", errors="replace"),
                    exit_code
                )
            except asyncio.TimeoutError:
                # Robust kill for Windows (kills process tree)
                if os.name == 'nt':
                    try:
                        import subprocess
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], 
                                     capture_output=True, check=False)
                    except Exception:
                        pass
                else:
                    try:
                        process.kill()
                    except Exception:
                        pass
                return ("", "Error: Command timed out", 124)
                
        except Exception as e:
            logger.error(f"Sandbox execution error: {repr(e)}", exc_info=True)
            return ("", f"Sandbox Error ({type(e).__name__}): {str(e)}", -1)

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
