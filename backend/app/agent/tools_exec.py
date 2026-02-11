
"""
Shell execution tool for Agent.
Ported/Adapted from Nanobot's agent/tools/shell.py
"""

import asyncio
import os
import re
import logging
from pathlib import Path
from typing import Optional
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

ALLOWED_COMMANDS_REGEX = [
    r"^python",
    r"^pip",
    r"^echo",
    r"^dir",
    r"^ls",
    r"^type",
    r"^cat",
    r"^mkdir",
    r"^cd", # Note: cd in subprocess doesn't persist, but we can allow it for chaining like 'cd x && y'
]

DENY_PATTERNS = [
    r"\brm\s+-[rf]{1,2}\b",          # rm -r, rm -rf
    r"\bdel\s+/[fq]\b",              # del /f, del /q
    r"\brmdir\s+/s\b",               # rmdir /s
    r"\b(format|mkfs|diskpart)\b",
]

def _guard_command(command: str) -> Optional[str]:
    """Check command against safety rules."""
    cmd = command.strip()
    lower = cmd.lower()
    
    # 1. Deny List
    for pattern in DENY_PATTERNS:
        if re.search(pattern, lower):
            return "Error: Command blocked by safety guard (dangerous pattern detected)"
            
    # 2. Allow List (Optional - usually we want to be permissive for an agent)
    # For now, we rely on the agent being run in a container or controlled env.
    # But if we strictly follow Nanobot, we might verify commonly used tools.
    # Let's trust the agent for now but log heavily.
    
    return None

@tool
async def execute_shell_command(command: str, working_dir: Optional[str] = None) -> str:
    """
    Execute a shell command. 
    Use this to run Python scripts (e.g., `python script.py`), install packages, or manage files.
    
    Args:
        command: The command line string to execute.
        working_dir: Optional directory to execute within.
    """
    try:
        # Safety Check
        error = _guard_command(command)
        if error:
            return error
            
        cwd = working_dir or os.getcwd()
        logger.info(f"Executing Shell Command: {command} in {cwd}")
        
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60 # 60s timeout
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            return "Error: Command timed out after 60 seconds."
            
        output_parts = []
        if stdout:
            output_parts.append(stdout.decode("utf-8", errors="replace"))
            
        if stderr:
             output_parts.append(f"STDERR:\n{stderr.decode('utf-8', errors='replace')}")
             
        result = "\n".join(output_parts)
        if not result:
            result = "(no output)"
            
        return result
        
    except Exception as e:
        return f"Error executing command: {str(e)}"
