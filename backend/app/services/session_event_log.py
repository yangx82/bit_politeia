"""
Event-Sourced Session Log Module (DeepSeek Harness dsh-session Pattern)

Implements an append-only immutable SessionEvent log where "Model-visible means logged".
Provides deterministic state projection (derive_messages) and exact execution replay.
"""

import hashlib
import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SessionEvent:
    event_id: str
    seq: int
    session_id: str
    event_type: str  # e.g., 'turn/start', 'user/message', 'tool/call', 'tool/result', 'assistant/message', 'turn/end', 'compaction/summary'
    payload: dict[str, Any]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionEvent":
        return cls(**data)


class SessionEventLog:
    """
    Append-only event-sourced log manager with deterministic replay.
    """

    def __init__(self, storage_dir: str | None = None):
        if storage_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.storage_dir = os.path.join(base_dir, "data", "session_events")
        else:
            self.storage_dir = storage_dir

        os.makedirs(self.storage_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._latest_seqs: dict[str, int] = {}

    def _get_log_file(self, session_id: str) -> str:
        s_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
        return os.path.join(self.storage_dir, f"session_{s_hash}.jsonl")

    def append_event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> SessionEvent:
        """
        Appends an immutable event to the session's append-only log.
        """
        with self._lock:
            current_seq = self._latest_seqs.get(session_id, 0)
            next_seq = current_seq + 1
            self._latest_seqs[session_id] = next_seq

            event_id = f"evt_{session_id[:8]}_{next_seq}_{datetime.now(UTC).strftime('%H%M%S%f')}"
            event = SessionEvent(
                event_id=event_id,
                seq=next_seq,
                session_id=session_id,
                event_type=event_type,
                payload=payload,
                timestamp=datetime.now(UTC).isoformat(),
            )

            log_file = self._get_log_file(session_id)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

        return event

    def get_events(self, session_id: str) -> list[SessionEvent]:
        """Reads all events for a session in order."""
        log_file = self._get_log_file(session_id)
        if not os.path.exists(log_file):
            return []

        events = []
        with self._lock:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(SessionEvent.from_dict(json.loads(line)))
                        except Exception as e:
                            logger.error(f"[SessionEventLog] Corrupted event line: {e}")
        return events

    def derive_messages(self, session_id: str) -> list[dict[str, Any]]:
        """
        Pure projection function: Reconstructs model-visible conversation history from the event log.
        """
        events = self.get_events(session_id)
        messages: list[dict[str, Any]] = []

        for event in events:
            if event.event_type == "user/message":
                messages.append({
                    "role": "user",
                    "content": event.payload.get("content", ""),
                    "timestamp": event.timestamp,
                })
            elif event.event_type == "assistant/message":
                messages.append({
                    "role": "assistant",
                    "content": event.payload.get("content", ""),
                    "tool_calls": event.payload.get("tool_calls", []),
                    "timestamp": event.timestamp,
                })
            elif event.event_type == "tool/result":
                messages.append({
                    "role": "tool",
                    "tool_name": event.payload.get("tool_name", ""),
                    "call_id": event.payload.get("call_id", ""),
                    "content": event.payload.get("content", ""),
                    "timestamp": event.timestamp,
                })
            elif event.event_type == "compaction/summary":
                # Replace earlier history with summary checkpoint if specified
                summary = event.payload.get("summary", "")
                messages = [{
                    "role": "user",
                    "content": f"[SYSTEM COMPACTION CHECKPOINT]\n{summary}",
                    "timestamp": event.timestamp,
                }]

        return messages


# Singleton instance
session_event_log = SessionEventLog()
