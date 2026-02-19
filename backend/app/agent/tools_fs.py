
"""
FileSystem tools for Agent.
Ported/Adapted from Nanobot's agent/tools/filesystem.py
"""

import os
import logging
from pathlib import Path
from typing import Optional
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Security: restrict file operations to the project root by default
# In a real deployment, this should be strictly enforced.
PROJECT_ROOT = Path(os.getcwd()).resolve()

def _resolve_path(path: str) -> Path:
    """Resolve path and enforce directory restriction (soft)."""
    resolved = Path(path).expanduser().resolve()
    # For now, we allow access to the whole drive if needed (agent on local machine),
    # but we log warnings if outside project root.
    if not str(resolved).startswith(str(PROJECT_ROOT)):
        logger.warning(f"Agent accessing file outside project root: {resolved}")
    return resolved

@tool
async def list_dir(path: str = ".") -> str:
    """
    List the contents of a directory.
    Args:
        path: Relative or absolute path to the directory. Defaults to current directory.
    """
    try:
        dir_path = _resolve_path(path)
        if not dir_path.exists():
            return f"Error: Directory not found: {path}"
        if not dir_path.is_dir():
            return f"Error: Not a directory: {path}"
        
        items = []
        for item in sorted(dir_path.iterdir()):
            prefix = "📁 " if item.is_dir() else "📄 "
            items.append(f"{prefix}{item.name}")
        
        if not items:
            return f"Directory {dir_path} is empty"
        
        return "\n".join(items)
    except Exception as e:
        return f"Error listing directory: {str(e)}"

@tool
async def read_file(path: str) -> str:
    """
    Read the contents of a file.
    Args:
        path: Path to the file.
    """
    try:
        file_path = _resolve_path(path)
        if not file_path.exists():
            return f"Error: File not found: {path}"
        if not file_path.is_file():
            return f"Error: Not a file: {path}"
        
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"

@tool
async def write_file(path: str, content: str) -> str:
    """
    Write content to a file. Creates parent directories if needed.
    Args:
        path: Path to the target file.
        content: The text content to write.
    """
    try:
        file_path = _resolve_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

@tool
async def edit_file(path: str, old_text: str, new_text: str) -> str:
    """
    Edit a file by replacing specific text.
    Args:
        path: Path to the file.
        old_text: The exact block of text to be replaced.
        new_text: The new text to insert.
    """
    try:
        file_path = _resolve_path(path)
        if not file_path.exists():
            return f"Error: File not found: {path}"
        
        content = file_path.read_text(encoding="utf-8")
        
        if old_text not in content:
            return "Error: old_text not found in file. Make sure it matches exactly (including whitespace)."
        
        count = content.count(old_text)
        if count > 1:
            return f"Warning: old_text appears {count} times. Please provide more context to make it unique."
        
        new_content = content.replace(old_text, new_text, 1)
        file_path.write_text(new_content, encoding="utf-8")
        
        return f"Successfully edited {path}"
    except Exception as e:
        return f"Error editing file: {str(e)}"

@tool
async def copy_files(source: str, destination: str) -> str:
    """
    Copy a file or directory recursively.
    Args:
        source: Source path.
        destination: Destination path.
    """
    import shutil
    try:
        src_path = _resolve_path(source)
        dst_path = _resolve_path(destination)
        
        if not src_path.exists():
            return f"Error: Source not found: {source}"
            
        if src_path.is_dir():
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
        else:
            # Ensure parent dir exists
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            
        return f"Successfully copied {source} to {destination}"
    except Exception as e:
        return f"Error copying files: {str(e)}"

@tool
async def move_files(source: str, destination: str) -> str:
    """
    Move a file or directory.
    Args:
        source: Source path.
        destination: Destination path.
    """
    import shutil
    try:
        src_path = _resolve_path(source)
        dst_path = _resolve_path(destination)
        
        if not src_path.exists():
            return f"Error: Source not found: {source}"
            
        # Ensure parent dir exists
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.move(src_path, dst_path)
        return f"Successfully moved {source} to {destination}"
    except Exception as e:
        return f"Error moving files: {str(e)}"
