"""
SyncKey Incremental Synchronization Module (WeChat Sync Protocol Pattern)

Manages monotonic sequence IDs (SeqId / SyncKey) per peer session and group channel.
Enables lightweight delta-state synchronization: upon reconnecting or receiving an update
notification, agents fetch only the missing message slice [since_seq + 1 ... latest_seq],
eliminating redundant network transmissions and guaranteeing zero message loss.
"""

import json
import logging
import os
import threading
from typing import Any

from app.p2p_community.message_protocol import SignedMessage

logger = logging.getLogger(__name__)


class SyncKeyManager:
    """
    Manages channel sequence IDs, incremental delta slices, and watermark alignment.
    """

    def __init__(self, storage_dir: str | None = None, max_history_per_channel: int = 1000):
        if storage_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.storage_dir = os.path.join(base_dir, "data", "sync_state")
        else:
            self.storage_dir = storage_dir

        self.max_history = max_history_per_channel
        os.makedirs(self.storage_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._state_file = os.path.join(self.storage_dir, "synckey_state.json")

        # channel_id -> latest monotonic seq_id (int)
        self._latest_seq: dict[str, int] = {}
        # channel_id -> list of raw SignedMessage dicts in chronological order
        self._channel_history: dict[str, list[dict[str, Any]]] = {}
        # channel_id -> local watermark (the highest seq_id we have processed from this channel)
        self._local_watermarks: dict[str, int] = {}

        self._load_state()

    def _load_state(self):
        """Loads sync state and history index from disk."""
        with self._lock:
            if os.path.exists(self._state_file):
                try:
                    with open(self._state_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._latest_seq = data.get("latest_seq", {})
                        self._local_watermarks = data.get("local_watermarks", {})
                        self._channel_history = data.get("channel_history", {})
                except Exception as e:
                    logger.error(f"[SyncKeyManager] Failed to load sync state: {e}")

    def _save_state(self):
        """Persists sync state and sequence index to disk."""
        with self._lock:
            try:
                data = {
                    "latest_seq": self._latest_seq,
                    "local_watermarks": self._local_watermarks,
                    "channel_history": self._channel_history,
                }
                with open(self._state_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"[SyncKeyManager] Failed to save sync state: {e}")

    def get_channel_id(self, peer_a: str, peer_b: str) -> str:
        """Returns deterministic channel ID for 1-on-1 direct conversations."""
        sorted_peers = sorted([peer_a, peer_b])
        return f"dm_{sorted_peers[0]}_{sorted_peers[1]}"

    def peek_next_seq(self, channel_id: str) -> int:
        """
        Returns what the next monotonic seq_id will be and advances the counter.
        Used to sign messages with their true seq_id prior to hashing/signing.
        """
        with self._lock:
            current = self._latest_seq.get(channel_id, 0)
            next_seq = current + 1
            self._latest_seq[channel_id] = next_seq
        self._save_state()
        return next_seq

    def record_outbound_message(self, channel_id: str, message: SignedMessage):
        """
        Indexes an outbound message after it has already been created and signed.
        """
        with self._lock:
            if channel_id not in self._channel_history:
                self._channel_history[channel_id] = []

            self._channel_history[channel_id].append(message.to_dict())
            if len(self._channel_history[channel_id]) > self.max_history:
                self._channel_history[channel_id] = self._channel_history[channel_id][-self.max_history:]
        self._save_state()

    def assign_next_seq(self, channel_id: str, message: SignedMessage) -> SignedMessage:
        """
        Assigns the next monotonic sequence ID to an outbound message and indexes it.
        Kept for backward compatibility.
        """
        with self._lock:
            current = self._latest_seq.get(channel_id, 0)
            next_seq = current + 1
            self._latest_seq[channel_id] = next_seq
            message.seq_id = next_seq

            if channel_id not in self._channel_history:
                self._channel_history[channel_id] = []

            self._channel_history[channel_id].append(message.to_dict())
            if len(self._channel_history[channel_id]) > self.max_history:
                self._channel_history[channel_id] = self._channel_history[channel_id][-self.max_history:]

        self._save_state()
        return message

    def record_inbound_message(self, channel_id: str, message: SignedMessage):
        """
        Records an inbound message and updates the local watermark.
        """
        with self._lock:
            if message.seq_id > 0:
                current_watermark = self._local_watermarks.get(channel_id, 0)
                if message.seq_id > current_watermark:
                    self._local_watermarks[channel_id] = message.seq_id

                if channel_id not in self._channel_history:
                    self._channel_history[channel_id] = []

                # Avoid duplicate insertion
                msg_dict = message.to_dict()
                if not any(m.get("message_id") == message.message_id for m in self._channel_history[channel_id]):
                    self._channel_history[channel_id].append(msg_dict)
                    if len(self._channel_history[channel_id]) > self.max_history:
                        self._channel_history[channel_id] = self._channel_history[channel_id][-self.max_history:]

        self._save_state()

    def get_delta_slice(self, channel_id: str, since_seq: int) -> list[SignedMessage]:
        """
        Returns delta slice of messages with seq_id > since_seq.
        """
        raw_slice = []
        with self._lock:
            history = self._channel_history.get(channel_id, [])
            for m in history:
                if m.get("seq_id", 0) > since_seq:
                    raw_slice.append(m)

        delta = []
        for d in raw_slice:
            try:
                delta.append(SignedMessage.from_dict(d))
            except Exception as e:
                logger.error(f"[SyncKeyManager] Failed to parse delta message: {e}")
        return delta

    def get_latest_seq(self, channel_id: str) -> int:
        """Returns the current highest sequence ID for a channel."""
        with self._lock:
            return self._latest_seq.get(channel_id, 0)

    def get_local_watermark(self, channel_id: str) -> int:
        """Returns our processed watermark for a channel."""
        with self._lock:
            return self._local_watermarks.get(channel_id, 0)


# Singleton instance
synckey_manager = SyncKeyManager()
