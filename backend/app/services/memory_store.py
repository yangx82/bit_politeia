"""Memory system for persistent agent memory (Long-term & Daily Notes)."""

import os
from pathlib import Path
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

def ensure_dir(path: Path) -> Path:
    """Ensure directory exists."""
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    return path

def today_date() -> str:
    """Get today's date string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

class MemoryStore:
    """
    Memory system for the agent.
    
    Supports daily notes (memory/YYYY-MM-DD.md) and long-term memory (MEMORY.md).
    """
    
    def __init__(self, workspace_root: str = None):
        # Default to backend/memory if not specified
        if not workspace_root:
            # Assuming this file is in backend/app/services/
            # We want backend/memory/
            current_file = Path(__file__)
            self.workspace = current_file.parent.parent.parent # backend/
        else:
            self.workspace = Path(workspace_root)
            
        self.memory_dir = ensure_dir(self.workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        
        logger.info(f"MemoryStore initialized at {self.memory_dir}")
    
    def get_today_file(self) -> Path:
        """Get path to today's memory file."""
        return self.memory_dir / f"{today_date()}.md"
    
    def read_today(self) -> str:
        """Read today's memory notes."""
        today_file = self.get_today_file()
        if today_file.exists():
            return today_file.read_text(encoding="utf-8")
        return ""
    
    def append_today(self, content: str) -> None:
        """Append content to today's memory notes."""
        today_file = self.get_today_file()
        
        if today_file.exists():
            existing = today_file.read_text(encoding="utf-8")
            content = existing + "\n" + content
        else:
            # Add header for new day
            header = f"# {today_date()}\n\n"
            content = header + content
        
        today_file.write_text(content, encoding="utf-8")
    
    def read_long_term(self) -> str:
        """Read long-term memory (MEMORY.md)."""
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""
    
    def write_long_term(self, content: str) -> None:
        """Write to long-term memory (MEMORY.md)."""
        self.memory_file.write_text(content, encoding="utf-8")
    
    def get_recent_memories(self, days: int = 7) -> str:
        """Get memories from the last N days."""
        from datetime import timedelta
        
        memories = []
        today = datetime.now(timezone.utc).date()
        
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            file_path = self.memory_dir / f"{date_str}.md"
            
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                memories.append(f"## {date_str}\n{content}")
        
        return "\n\n".join(memories)
    
    def get_memory_context(self) -> str:
        """Get formatted memory context including long-term and recent memories."""
        parts = []
        
        # Long-term memory
        long_term = self.read_long_term()
        if long_term:
            parts.append("## Long-term Memory\n" + long_term)
        
        # Today's notes
        today = self.read_today()
        if today:
            parts.append("## Today's Notes\n" + today)
        
        return "\n\n".join(parts) if parts else ""

# Global instance
memory_store = MemoryStore()
