"""
Tool Output Spill Store Module (DeepSeek Harness dsh-spill Pattern)

Persists massive tool output text to disk or blob storage and returns an opaque
locator with model retrieval guidance, preventing context window bloat and Token exhaustion.
"""

import hashlib
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

logger = logging.getLogger(__name__)


class SpillStore:
    """
    Manages session-scoped spilled tool artifacts.
    """

    def __init__(self, storage_dir: str | None = None, max_inline_bytes: int = 4096):
        if storage_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.storage_dir = os.path.join(base_dir, "data", "spills")
        else:
            self.storage_dir = storage_dir

        self.max_inline_bytes = max_inline_bytes
        os.makedirs(self.storage_dir, exist_ok=True)
        self._lock = threading.Lock()

    def _sanitize_name(self, name: str) -> str:
        """Sanitizes a caller-suggested name into a safe file path segment."""
        safe = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)
        return safe[:64] if safe else "spill.txt"

    def _get_session_dir(self, session_id: str) -> str:
        """Gets deterministic directory for a session."""
        session_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
        session_dir = os.path.join(self.storage_dir, f"session_{session_hash}")
        os.makedirs(session_dir, exist_ok=True)
        return session_dir

    def save_text(
        self,
        session_id: str,
        tool_name: str,
        call_id: str,
        content: str,
        suggested_name: str = "output.txt",
    ) -> dict[str, Any]:
        """
        Persists full text content to disk and returns SpillRef metadata.
        """
        content_bytes = content.encode("utf-8")
        byte_len = len(content_bytes)

        session_dir = self._get_session_dir(session_id)
        safe_name = self._sanitize_name(suggested_name)
        timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp_str}_{tool_name}_{call_id[:8]}_{safe_name}"
        file_path = os.path.join(session_dir, filename)

        with self._lock:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        logger.info(
            f"[SpillStore] Spilled {byte_len} bytes from tool '{tool_name}' (call_id={call_id[:8]}) to {file_path}"
        )

        return {
            "locator": file_path,
            "bytes": byte_len,
            "tool_name": tool_name,
            "call_id": call_id,
            "retrieval_hint": (
                f"Full output ({byte_len} bytes) spilled to '{file_path}'. "
                f"Use grep_search or view_file to query specific portions if needed."
            ),
        }

    def process_tool_output(
        self,
        session_id: str,
        tool_name: str,
        call_id: str,
        output: Any,
        preview_chars: int = 600,
    ) -> Any:
        """
        Checks if tool output exceeds inline threshold; if so, spills it and formats a preview.
        """
        if not isinstance(output, str):
            try:
                output_str = json.dumps(output, ensure_ascii=False)
            except Exception:
                output_str = str(output)
        else:
            output_str = output

        output_bytes = output_str.encode("utf-8")
        if len(output_bytes) <= self.max_inline_bytes:
            return output  # Below threshold, keep verbatim

        # Spill to disk
        spill_ref = self.save_text(
            session_id=session_id,
            tool_name=tool_name,
            call_id=call_id,
            content=output_str,
            suggested_name=f"{tool_name}_result.txt",
        )

        # Generate head / tail preview
        half = preview_chars // 2
        head = output_str[:half]
        tail = output_str[-half:] if len(output_str) > half else ""

        preview_text = (
            f"[TOOL OUTPUT EXCEEDED INLINE LIMIT ({len(output_bytes)} bytes > {self.max_inline_bytes} bytes)]\n"
            f"--- [Preview Head] ---\n{head}\n"
            f"...\n"
            f"--- [Preview Tail] ---\n{tail}\n"
            f"--- [Storage Locator] ---\n{spill_ref['retrieval_hint']}"
        )

        return preview_text

    def read_spill(self, locator: str) -> str | None:
        """Reads content of a spilled locator."""
        if not os.path.exists(locator):
            return None
        with self._lock:
            with open(locator, "r", encoding="utf-8") as f:
                return f.read()


# Singleton instance
spill_store = SpillStore()
