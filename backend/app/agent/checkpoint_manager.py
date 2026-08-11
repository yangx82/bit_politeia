"""
Pipeline Checkpoint Manager for Bit Politeia.
Persists in-flight agent reasoning, tasks, thoughts, and executed tool results to disk.
Enables auto-resume of code self-modification tasks after backend reloads/restarts.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc
logger = logging.getLogger(__name__)


class PipelineCheckpointManager:

    def __init__(self, data_dir: Path | None = None):
        if data_dir is None:
            base_dir = Path(__file__).parent.parent.parent
            self.data_dir = base_dir / "data" / "checkpoints"
        else:
            self.data_dir = data_dir

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = self.data_dir / "in_flight_checkpoint.json"

    def save_checkpoint(
        self,
        session_id: str,
        channel: str,
        sender_id: str,
        input_message_content: Any,
        thoughts: list[str],
        tool_results: list[dict[str, Any]],
        pending_tool_calls: list[dict[str, Any]] | None = None,
        task_id: str | None = None,
    ):
        """Save a snapshot of in-flight execution context to disk."""
        try:
            payload = {
                "session_id": session_id,
                "channel": channel,
                "sender_id": sender_id,
                "input_message_content": input_message_content,
                "thoughts": thoughts,
                "tool_results": tool_results,
                "pending_tool_calls": pending_tool_calls or [],
                "task_id": task_id,
                "status": "IN_PROGRESS",
                "timestamp": datetime.now(UTC).isoformat(),
            }

            temp_file = self.checkpoint_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.checkpoint_file)

            logger.info(
                f"[CheckpointManager] Saved execution checkpoint for session {session_id} "
                f"({len(thoughts)} thoughts, {len(tool_results)} tool_results)."
            )
        except Exception as e:
            logger.error(f"[CheckpointManager] Failed to save checkpoint: {e}")

    def load_checkpoint(self) -> dict[str, Any] | None:
        """Load active in-flight checkpoint if exists."""
        if not self.checkpoint_file.exists():
            return None

        try:
            with open(self.checkpoint_file, encoding="utf-8") as f:
                data = json.load(f)

            if data.get("status") == "IN_PROGRESS":
                return data
            return None
        except Exception as e:
            logger.error(f"[CheckpointManager] Failed to load checkpoint: {e}")
            return None

    def clear_checkpoint(self):
        """Clear active checkpoint upon successful task completion."""
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
                logger.info("[CheckpointManager] Cleared in-flight execution checkpoint.")
        except Exception as e:
            logger.error(f"[CheckpointManager] Failed to clear checkpoint: {e}")


# Global Singleton
checkpoint_manager = PipelineCheckpointManager()
