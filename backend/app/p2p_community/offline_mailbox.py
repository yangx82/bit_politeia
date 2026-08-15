"""
Offline Mailbox Module (Signal / Telegram Store & Forward Pattern)

Provides asynchronous offline message caching and deferred delivery for P2P agent nodes.
When a target peer is offline or unreachable via direct WebRTC/TCP, messages are safely
persisted in the local or relay mailbox and flushed immediately upon peer reconnection.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
UTC = timezone.utc
from typing import Any

from app.p2p_community.message_protocol import SignedMessage

logger = logging.getLogger(__name__)


class OfflineMailboxManager:
    """
    Manages offline message store and forward queues.
    """

    def __init__(self, storage_dir: str | None = None, retention_days: int = 7):
        if storage_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.storage_dir = os.path.join(base_dir, "data", "offline_mailbox")
        else:
            self.storage_dir = storage_dir

        self.retention_days = retention_days
        os.makedirs(self.storage_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._mailbox_file = os.path.join(self.storage_dir, "pending_mailbox.json")
        # recipient_id -> list of raw SignedMessage dicts
        self._queues: dict[str, list[dict[str, Any]]] = {}
        self._load_mailbox()

    def _load_mailbox(self):
        """Loads persistent offline queues from disk."""
        with self._lock:
            if os.path.exists(self._mailbox_file):
                try:
                    with open(self._mailbox_file, "r", encoding="utf-8") as f:
                        self._queues = json.load(f)
                except Exception as e:
                    logger.error(f"[OfflineMailbox] Failed to load mailbox: {e}")
                    self._queues = {}

    def _save_mailbox(self):
        """Persists offline queues to disk."""
        with self._lock:
            try:
                with open(self._mailbox_file, "w", encoding="utf-8") as f:
                    json.dump(self._queues, f, indent=2)
            except Exception as e:
                logger.error(f"[OfflineMailbox] Failed to save mailbox: {e}")

    def enqueue(self, recipient_id: str, message: SignedMessage) -> bool:
        """
        Stores a message in the offline queue for recipient_id.
        """
        with self._lock:
            if recipient_id not in self._queues:
                self._queues[recipient_id] = []

            # Avoid duplicates
            msg_dict = message.to_dict()
            for existing in self._queues[recipient_id]:
                if existing.get("message_id") == message.message_id:
                    return True

            self._queues[recipient_id].append(msg_dict)
            logger.info(
                f"[OfflineMailbox] Enqueued message {message.message_id} "
                f"(type={message.message_type.value}) for offline recipient {recipient_id[:12]}"
            )

        self._save_mailbox()
        return True

    def get_pending_count(self, recipient_id: str) -> int:
        """Returns number of queued messages for recipient_id."""
        with self._lock:
            return len(self._queues.get(recipient_id, []))

    def pop_all_for_recipient(self, recipient_id: str) -> list[SignedMessage]:
        """
        Extracts and clears all pending messages for a newly reconnected recipient.
        """
        raw_msgs = []
        with self._lock:
            if recipient_id in self._queues:
                raw_msgs = self._queues.pop(recipient_id)

        if raw_msgs:
            self._save_mailbox()
            logger.info(f"[OfflineMailbox] Flushed {len(raw_msgs)} offline messages for recipient {recipient_id[:12]}")

        parsed: list[SignedMessage] = []
        for d in raw_msgs:
            try:
                parsed.append(SignedMessage.from_dict(d))
            except Exception as e:
                logger.error(f"[OfflineMailbox] Failed to parse queued message: {e}")
        return parsed

    def purge_expired(self):
        """Removes messages exceeding the retention period."""
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        purged = 0
        with self._lock:
            for recipient_id in list(self._queues.keys()):
                valid_msgs = []
                for msg_dict in self._queues[recipient_id]:
                    try:
                        ts = datetime.fromisoformat(msg_dict["timestamp"])
                        if ts > cutoff:
                            valid_msgs.append(msg_dict)
                        else:
                            purged += 1
                    except Exception:
                        valid_msgs.append(msg_dict)
                self._queues[recipient_id] = valid_msgs

        if purged > 0:
            self._save_mailbox()
            logger.info(f"[OfflineMailbox] Purged {purged} expired messages")


# Singleton instance
offline_mailbox = OfflineMailboxManager()
