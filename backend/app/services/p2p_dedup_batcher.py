"""
GossipDeduplicationBatcher (GDB) - Outbound P2P Gossip Deduplication & Exponential Backoff.

Eliminates redundant broadcasts, protects against network broadcast storms, and
applies exponential backoff on repeated identical content without deadlocks or silent drops.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


def canonical_content_hash(payload: Any) -> str:
    """
    Compute a normalized SHA-256 hash for a payload.
    Strips transient / ephemeral fields like message_id, timestamp, signature,
    and nonces to compare semantic message content.
    """
    if payload is None:
        return hashlib.sha256(b"").hexdigest()

    # If it's a SignedMessage or object with to_dict / dict
    if hasattr(payload, "to_dict") and callable(payload.to_dict):
        data = payload.to_dict()
    elif hasattr(payload, "__dict__"):
        data = dict(payload.__dict__)
    elif isinstance(payload, dict):
        data = dict(payload)
    else:
        # String or primitive
        s = str(payload).strip()
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    # If dict has nested "content", also examine if it's the core payload
    cleaned = {}
    volatile_keys = {
        "message_id",
        "timestamp",
        "created_at",
        "_submitted_at",
        "_content_hash",
        "signature",
        "nonce",
    }

    for k, v in data.items():
        if k in volatile_keys:
            continue
        cleaned[k] = v

    try:
        serialized = json.dumps(cleaned, sort_keys=True, default=str)
    except Exception:
        serialized = str(sorted(cleaned.items()))

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class GossipDeduplicationBatcher:
    """
    Thread-safe deduplicator and batcher for outbound P2P gossip & broadcast traffic.

    Features:
    1. Canonical content hashing via SHA-256.
    2. Exponential backoff on identical payload:
       delay = min(base_backoff * (2 ** min(count - 1, 8)), max_backoff)
    3. Uses threading.RLock() to prevent re-entrant deadlocks.
    4. Explicit queue management without silent drops.
    5. Safe periodic cleanup for stale hashes.
    """

    def __init__(
        self,
        max_batch_size: int = 20,
        base_backoff_seconds: float = 5.0,
        max_backoff_seconds: float = 300.0,
        flush_interval_seconds: float = 15.0,
    ) -> None:
        if not isinstance(max_batch_size, int) or not (1 <= max_batch_size <= 1000):
            raise ValueError(f"max_batch_size must be in [1, 1000], got {max_batch_size!r}")
        if not isinstance(base_backoff_seconds, (int, float)) or not (0.001 <= float(base_backoff_seconds) <= 3600.0):
            raise ValueError(f"base_backoff_seconds must be in [0.001, 3600.0], got {base_backoff_seconds!r}")
        if not isinstance(max_backoff_seconds, (int, float)) or float(max_backoff_seconds) < float(base_backoff_seconds):
            raise ValueError(f"max_backoff_seconds must be >= base_backoff_seconds, got {max_backoff_seconds!r}")
        if not isinstance(flush_interval_seconds, (int, float)) or float(flush_interval_seconds) <= 0:
            raise ValueError(f"flush_interval_seconds must be > 0, got {flush_interval_seconds!r}")

        self.max_batch_size: int = max_batch_size
        self.base_backoff_seconds: float = float(base_backoff_seconds)
        self.max_backoff_seconds: float = float(max_backoff_seconds)
        self.flush_interval_seconds: float = float(flush_interval_seconds)

        self._lock: threading.RLock = threading.RLock()
        self._seen_hashes: dict[str, dict[str, Any]] = {}
        self._batch_queue: list[dict[str, Any]] = []

        # Operational metrics
        self._total_submitted: int = 0
        self._total_accepted: int = 0
        self._total_suppressed: int = 0
        self._total_flushes: int = 0

    def compute_hash(self, message: Any) -> str:
        """Compute canonical hash for message payload."""
        return canonical_content_hash(message)

    def get_backoff_delay(self, content_hash: str) -> float:
        """
        Calculate current backoff delay in seconds for a content hash.
        Returns 0.0 if the hash has not been seen.
        """
        if not content_hash:
            return 0.0

        with self._lock:
            record = self._seen_hashes.get(content_hash)
            if not record:
                return 0.0

            count = record.get("count", 1)
            capped_exponent = min(count - 1, 8)
            delay = self.base_backoff_seconds * (2 ** capped_exponent)
            return min(float(delay), self.max_backoff_seconds)

    def should_broadcast(self, message: Any) -> tuple[bool, float, str]:
        """
        Check whether a message is allowed to be broadcasted right now.
        Does not enqueue into batch queue; used as a gatekeeper for direct broadcasts.

        Returns:
            (allowed: bool, backoff_remaining: float, content_hash: str)
        """
        content_hash = self.compute_hash(message)
        now = time.time()

        with self._lock:
            self._total_submitted += 1
            if content_hash in self._seen_hashes:
                record = self._seen_hashes[content_hash]
                backoff_delay = self.get_backoff_delay(content_hash)
                elapsed = now - record["last_backoff"]

                if elapsed < backoff_delay:
                    # Still in suppression window
                    record["count"] += 1
                    self._total_suppressed += 1
                    remaining = backoff_delay - elapsed
                    return False, remaining, content_hash

                # Window expired: allow re-submission, update backoff timestamp
                record["count"] += 1
                record["last_backoff"] = now
                self._total_accepted += 1
                return True, 0.0, content_hash

            # Novel content hash
            self._seen_hashes[content_hash] = {
                "first_seen": now,
                "count": 1,
                "last_backoff": now,
            }
            self._total_accepted += 1
            return True, 0.0, content_hash

    def submit(self, message: dict[str, Any], auto_flush: bool = False) -> tuple[bool, float, list[dict[str, Any]] | None]:
        """
        Submit a message for batching.

        Returns:
            (accepted: bool, backoff_delay: float, flushed_batch: list[dict] | None)
            - accepted: True if novel / window expired and enqueued; False if suppressed.
            - backoff_delay: Remaining seconds if suppressed, 0.0 if accepted.
            - flushed_batch: Non-empty list if queue reached capacity and auto_flush=True, else None.
        """
        if not isinstance(message, dict):
            raise ValueError(f"message must be a dict, got {type(message)}")

        allowed, delay, c_hash = self.should_broadcast(message)
        if not allowed:
            return False, delay, None

        flushed = None
        with self._lock:
            now = time.time()
            msg_copy = dict(message)
            msg_copy["_content_hash"] = c_hash
            msg_copy["_submitted_at"] = now
            self._batch_queue.append(msg_copy)

            if auto_flush and len(self._batch_queue) >= self.max_batch_size:
                flushed = self.flush_batch()

        return True, 0.0, flushed

    def flush_batch(self) -> list[dict[str, Any]]:
        """
        Return and clear all queued messages in the batch.
        Thread-safe snapshot.
        """
        with self._lock:
            if not self._batch_queue:
                return []
            batch = list(self._batch_queue)
            self._batch_queue.clear()
            self._total_flushes += 1
            return batch

    def cleanup_stale_hashes(self, max_age_seconds: int = 3600) -> int:
        """
        Purge hash records that have not been seen for longer than max_age_seconds.

        Args:
            max_age_seconds: Maximum age in seconds before a seen hash record is pruned.

        Returns:
            Number of pruned records.
        """
        if max_age_seconds < 10:
            raise ValueError(f"max_age_seconds must be >= 10, got {max_age_seconds}")

        now = time.time()
        purged = 0

        with self._lock:
            stale_keys = []
            for h, rec in self._seen_hashes.items():
                if (now - rec.get("last_backoff", now)) > max_age_seconds:
                    stale_keys.append(h)

            for h in stale_keys:
                del self._seen_hashes[h]
                purged += 1

        if purged > 0:
            logger.debug(f"[GDB] Purged {purged} stale hash records (older than {max_age_seconds}s)")
        return purged

    def stats(self) -> dict[str, Any]:
        """Return runtime statistics snapshot."""
        with self._lock:
            return {
                "queue_length": len(self._batch_queue),
                "seen_hashes_count": len(self._seen_hashes),
                "total_submitted": self._total_submitted,
                "total_accepted": self._total_accepted,
                "total_suppressed": self._total_suppressed,
                "total_flushes": self._total_flushes,
                "max_batch_size": self.max_batch_size,
                "base_backoff_seconds": self.base_backoff_seconds,
                "max_backoff_seconds": self.max_backoff_seconds,
            }
