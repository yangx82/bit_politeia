
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

from .sandbox import get_default_sandbox

@tool
def execute_shell_command(command: str, working_dir: Optional[str] = None) -> str:
    """
    Execute a shell command.
    Use this to run Python scripts (e.g., `python script.py`), install packages, or manage files.
    
    CRITICAL ANTI-HALLUCINATION DIRECTIVE: 
    - This execution environment DOES NOT block external network connections (curl, wget, requests all work).
    - This execution environment DOES NOT block file system access.
    - If your command fails (e.g. timeout, package not found, syntax error), DO NOT blame "sandbox limitations" or "network isolation". Fix your code and try again.
    
    Args:
        command: The command line string to execute.
        working_dir: Optional directory to execute within.
    """
    try:
        # Safety Check
        error = _guard_command(command)
        if error:
            return error
            
        logger.info(f"Executing Sandboxed Command: {command}")
        
        # We invoke the synchronous sandbox directly
        from .sandbox import get_default_sandbox
        sandbox = get_default_sandbox()
        
        # To bypass all async event loop bugs (NotImplementedError on Windows),
        # we run the subprocess synchronously here. Langchain will handle threading.
        stdout, stderr, exit_code = sandbox.execute_sync(command, working_dir=working_dir)
        
        output_parts = []
        if stdout:
            output_parts.append(stdout)
            
        if stderr:
             output_parts.append(f"STDERR:\n{stderr}")
             
        result = "\n".join(output_parts)
        if not result:
            result = "(no output)"
            
        if exit_code != 0:
            result += f"\n[Exit Code: {exit_code}]"
            
        return result
        
    except Exception as e:
        return f"Error executing command: {str(e)}"
