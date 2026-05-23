"""Memory system for persistent agent memory (Long-term & Daily Notes)."""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists."""
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    return path


def today_date() -> str:
    """Get today's date string."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


class MemoryStore:
    """
    Memory system for the agent.

    Supports daily notes (memory/YYYY-MM-DD.md) and long-term memory (MEMORY.md).
    Also supports compressed summaries (memory/daily_notes_summary.md).
    """

    def __init__(self, workspace_root: str = None):
        # Default to backend/memory if not specified
        if not workspace_root:
            # Assuming this file is in backend/app/services/
            # We want backend/memory/
            current_file = Path(__file__)
            self.workspace = current_file.parent.parent.parent  # backend/
        else:
            self.workspace = Path(workspace_root)

        self.memory_dir = ensure_dir(self.workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.summary_file = self.memory_dir / "daily_notes_summary.md"
        self.history_summary_file = self.memory_dir / "history_summary.md"
        self.archive_dir = ensure_dir(self.memory_dir / "archive")

        logger.info(f"MemoryStore initialized at {self.memory_dir}")

    def _get_today_date(self) -> str:
        """Get today's date string."""
        return today_date()

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
        today = datetime.now(UTC).date()

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

    def read_summary(self) -> str:
        """Read the compressed summary of old daily notes."""
        if self.summary_file.exists():
            return self.summary_file.read_text(encoding="utf-8")
        return ""

    def write_summary(self, content: str) -> None:
        """Write/update the compressed summary."""
        self.summary_file.write_text(content, encoding="utf-8")
        logger.info(f"Updated daily notes summary: {len(content)} chars")

    def append_summary(self, content: str) -> None:
        """Append to existing summary with date marker."""
        existing = self.read_summary()
        date_marker = f"\n\n---\n### 压缩日期: {today_date()}\n\n"

        if existing:
            # Check if we already have content from today
            if f"压缩日期: {today_date()}" in existing:
                # Append to today's section
                self.summary_file.write_text(existing + "\n" + content, encoding="utf-8")
            else:
                # Add new dated section
                self.summary_file.write_text(existing + date_marker + content, encoding="utf-8")
        else:
            # Create new summary with header
            header = "# Daily Notes 历史摘要\n\n此文件包含已压缩的历史 Daily Notes 摘要。\n原始文件已归档至 `archive/` 目录。\n\n"
            self.summary_file.write_text(header + content, encoding="utf-8")

        logger.info(f"Appended to daily notes summary: +{len(content)} chars")

    def get_old_daily_notes(self, before_days: int = 3) -> list[tuple[str, str, Path]]:
        """
        Get daily notes older than specified days.

        Returns:
            List of tuples: (date_str, content, file_path)
        """
        old_notes = []
        today = datetime.now(UTC).date()
        cutoff_date = today - timedelta(days=before_days)

        # Get all .md files that look like dates
        for file_path in sorted(self.memory_dir.glob("*.md")):
            # Skip MEMORY.md and summary files
            if file_path.name in ["MEMORY.md", "daily_notes_summary.md"]:
                continue

            # Try to parse as date
            try:
                date_str = file_path.stem  # YYYY-MM-DD
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()

                if file_date < cutoff_date:
                    content = file_path.read_text(encoding="utf-8")
                    old_notes.append((date_str, content, file_path))
            except ValueError:
                # Not a date file, skip
                continue

        return old_notes

    def archive_daily_note(self, file_path: Path) -> None:
        """Move a daily note to the archive directory."""
        archive_path = self.archive_dir / file_path.name
        file_path.rename(archive_path)
        logger.info(f"Archived daily note: {file_path.name} -> archive/")

    # ============================================================
    # Compressed History Summary
    # ============================================================

    def read_history_summary(self) -> str:
        """Read the compressed summary of archived conversation history."""
        if self.history_summary_file.exists():
            return self.history_summary_file.read_text(encoding="utf-8")
        return ""

    def write_history_summary(self, content: str) -> None:
        """Overwrite the compressed history summary."""
        self.history_summary_file.write_text(content, encoding="utf-8")
        logger.info(f"Updated history summary: {len(content)} chars")

    def append_history_summary(self, content: str) -> None:
        """Append a new compression section to the history summary."""
        existing = self.read_history_summary()
        date_marker = f"\n\n---\n### 压缩批次: {today_date()}\n\n"

        if existing:
            self.history_summary_file.write_text(
                existing + date_marker + content, encoding="utf-8"
            )
        else:
            header = (
                "# 对话历史压缩摘要\n\n"
                "此文件包含已压缩的历史对话摘要。\n"
                "原始记录保留在 JSONL 文件中，此摘要用于启动时快速加载历史上下文。\n\n"
            )
            self.history_summary_file.write_text(
                header + date_marker + content, encoding="utf-8"
            )

        logger.info(f"Appended to history summary: +{len(content)} chars")


# Global instance
memory_store = MemoryStore()
