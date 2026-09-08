import threading
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.p2p_dedup_batcher import GossipDeduplicationBatcher, canonical_content_hash
from app.services.p2p_service import P2PService


def test_canonical_content_hash_ignores_volatile_fields():
    """Verify that volatile metadata fields (timestamps, IDs, nonces) do not alter semantic hash."""
    msg1 = {
        "text": "Hello Politeia",
        "group_id": "L1-G1",
        "message_id": "uuid-1111",
        "timestamp": 1725700000.0,
        "created_at": "2026-09-08T00:00:00Z",
    }
    msg2 = {
        "text": "Hello Politeia",
        "group_id": "L1-G1",
        "message_id": "uuid-2222",
        "timestamp": 1725709999.0,
        "created_at": "2026-09-08T05:00:00Z",
    }
    msg3 = {
        "text": "Different message",
        "group_id": "L1-G1",
    }

    hash1 = canonical_content_hash(msg1)
    hash2 = canonical_content_hash(msg2)
    hash3 = canonical_content_hash(msg3)

    assert hash1 == hash2, "Messages with same semantic content must have identical hashes"
    assert hash1 != hash3, "Different content must produce different hashes"


def test_novel_message_allowed_first_time():
    """First-time novel payload must be accepted with zero backoff delay."""
    batcher = GossipDeduplicationBatcher(base_backoff_seconds=5.0)
    payload = {"type": "proposal", "title": "AIP-001"}

    allowed, delay, c_hash = batcher.should_broadcast(payload)
    assert allowed is True
    assert delay == 0.0
    assert len(c_hash) == 64

    stats = batcher.stats()
    assert stats["total_submitted"] == 1
    assert stats["total_accepted"] == 1
    assert stats["total_suppressed"] == 0
    assert stats["seen_hashes_count"] == 1


def test_duplicate_message_triggers_exponential_backoff():
    """Immediate re-submission of same content triggers exponential backoff."""
    batcher = GossipDeduplicationBatcher(base_backoff_seconds=2.0, max_backoff_seconds=60.0)
    payload = {"event": "heartbeat_announcement"}

    # 1st attempt: allowed
    allowed1, delay1, _ = batcher.should_broadcast(payload)
    assert allowed1 is True
    assert delay1 == 0.0

    # 2nd attempt immediately: suppressed
    allowed2, delay2, _ = batcher.should_broadcast(payload)
    assert allowed2 is False
    assert delay2 > 0.0

    # 3rd attempt immediately: delay increases
    allowed3, delay3, _ = batcher.should_broadcast(payload)
    assert allowed3 is False

    stats = batcher.stats()
    assert stats["total_submitted"] == 3
    assert stats["total_accepted"] == 1
    assert stats["total_suppressed"] == 2


def test_backoff_window_expiration_allows_resubmit():
    """Once the backoff window elapses, the payload is allowed to broadcast again."""
    batcher = GossipDeduplicationBatcher(base_backoff_seconds=0.1)
    payload = {"ping": "pong"}

    # 1st attempt
    allowed1, _, _ = batcher.should_broadcast(payload)
    assert allowed1 is True

    # 2nd attempt immediately: suppressed
    allowed2, _, _ = batcher.should_broadcast(payload)
    assert allowed2 is False

    # Sleep past backoff window
    time.sleep(0.3)

    # 3rd attempt after backoff window: allowed
    allowed3, delay3, _ = batcher.should_broadcast(payload)
    assert allowed3 is True
    assert delay3 == 0.0


def test_submit_and_flush_batch():
    """Test batch enqueuing, auto_flush on capacity, and manual flush_batch."""
    batcher = GossipDeduplicationBatcher(max_batch_size=3, base_backoff_seconds=1.0)

    msg1 = {"item": 1}
    msg2 = {"item": 2}
    msg3 = {"item": 3}

    # Submit 1 & 2
    acc1, _, flushed1 = batcher.submit(msg1, auto_flush=True)
    assert acc1 is True
    assert flushed1 is None
    assert batcher.stats()["queue_length"] == 1

    acc2, _, flushed2 = batcher.submit(msg2, auto_flush=True)
    assert acc2 is True
    assert flushed2 is None
    assert batcher.stats()["queue_length"] == 2

    # Submit 3 hits max_batch_size=3 -> triggers auto_flush
    acc3, _, flushed3 = batcher.submit(msg3, auto_flush=True)
    assert acc3 is True
    assert flushed3 is not None
    assert len(flushed3) == 3
    assert [m["item"] for m in flushed3] == [1, 2, 3]
    assert batcher.stats()["queue_length"] == 0


def test_cleanup_stale_hashes():
    """Verify that old seen hashes are purged after max_age_seconds."""
    batcher = GossipDeduplicationBatcher(base_backoff_seconds=0.1)
    batcher.should_broadcast({"msg": "stale"})

    # Artificially age the record
    h = list(batcher._seen_hashes.keys())[0]
    batcher._seen_hashes[h]["last_backoff"] = time.time() - 5000

    assert batcher.stats()["seen_hashes_count"] == 1

    purged = batcher.cleanup_stale_hashes(max_age_seconds=60)
    assert purged == 1
    assert batcher.stats()["seen_hashes_count"] == 0


def test_thread_safety_no_deadlock():
    """Concurrent submissions across multiple threads must not deadlock or corrupt state."""
    batcher = GossipDeduplicationBatcher(base_backoff_seconds=0.01)
    errors = []

    def worker(worker_id: int):
        try:
            for i in range(25):
                # Half unique, half duplicate
                payload = {"key": f"unique_{worker_id}_{i}" if i % 2 == 0 else "shared_duplicate"}
                batcher.should_broadcast(payload)
                batcher.submit({"text": f"item_{i}"})
                batcher.get_backoff_delay("nonexistent")
                if i % 10 == 0:
                    batcher.flush_batch()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
        assert not t.is_alive(), "Worker thread timed out - possible deadlock!"

    assert not errors, f"Errors occurred during concurrent execution: {errors}"
    assert batcher.stats()["total_submitted"] > 0


@pytest.mark.asyncio
async def test_p2p_service_broadcast_suppresses_duplicate():
    """Verify P2PService.broadcast_to_group suppresses duplicate broadcasts using GDB."""
    service = P2PService()
    service.local_node = MagicMock()
    service.local_node.send_message = AsyncMock(return_value=True)

    # 1st broadcast: allowed
    res1 = await service.broadcast_to_group("group-1", "Notice: Network update", "Update")
    assert res1 is True
    assert service.local_node.send_message.call_count == 1

    # 2nd broadcast with exact same text immediately: suppressed
    res2 = await service.broadcast_to_group("group-1", "Notice: Network update", "Update")
    assert isinstance(res2, dict)
    assert res2["success"] is False
    assert res2["reason"] == "suppressed_by_gdb"
    assert res2["backoff_delay"] > 0
    # send_message should not be called again
    assert service.local_node.send_message.call_count == 1

    # 3rd broadcast with novel text: allowed
    res3 = await service.broadcast_to_group("group-1", "Different novel text", "Update")
    assert res3 is True
    assert service.local_node.send_message.call_count == 2
