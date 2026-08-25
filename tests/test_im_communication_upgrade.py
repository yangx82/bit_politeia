"""
Test Suite for IM-Inspired Inter-Agent Communication Architecture Upgrade

Tests 5 core components:
1. SignedMessage protocol with seq_id, parents, and receipt_status
2. Offline Mailbox (Signal store-and-forward pattern)
3. SyncKey Manager (WeChat monotonic delta sync)
4. Receipt Pipeline (WhatsApp/Signal 4-stage lifecycle and thinking states)
5. Event DAG Resolver (Matrix causal topological sort for multi-agent discussions)
"""

import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
UTC = timezone.utc

import pytest

from app.p2p_community.dag_resolver import EventDAGResolver, dag_resolver
from app.p2p_community.message_protocol import MessageProtocol, MessageType, SignedMessage
from app.p2p_community.offline_mailbox import OfflineMailboxManager
from app.p2p_community.receipt_manager import ReceiptPipeline, ReceiptState
from app.p2p_community.sync_manager import SyncKeyManager


@pytest.fixture
def temp_test_dir():
    dir_path = tempfile.mkdtemp(prefix="test_im_comm_")
    yield dir_path
    shutil.rmtree(dir_path, ignore_errors=True)


def test_signed_message_im_fields():
    """Verify SignedMessage properly serializes and deserializes seq_id, parents, and receipt_status."""
    now = datetime.now(UTC)
    msg = SignedMessage(
        message_id="msg-1001",
        sender_id="sender_alpha",
        recipient_id="recipient_beta",
        message_type=MessageType.DIRECT,
        content={"text": "Hello from IM protocol"},
        timestamp=now,
        signature="dummy_signature_base64",
        nonce="nonce-12345",
        seq_id=42,
        parents=["msg-1000"],
        receipt_status="delivered",
    )

    msg_dict = msg.to_dict()
    assert msg_dict["seq_id"] == 42
    assert msg_dict["parents"] == ["msg-1000"]
    assert msg_dict["receipt_status"] == "delivered"

    # Deserialization check
    reconstructed = SignedMessage.from_dict(msg_dict)
    assert reconstructed.message_id == "msg-1001"
    assert reconstructed.seq_id == 42
    assert reconstructed.parents == ["msg-1000"]
    assert reconstructed.receipt_status == "delivered"


def test_offline_mailbox_store_and_forward(temp_test_dir):
    """Test Offline Mailbox enqueue, persistence, pop_all_for_recipient, and deduplication."""
    mailbox = OfflineMailboxManager(storage_dir=temp_test_dir)
    peer_id = "node_offline_omega"

    msg1 = SignedMessage(
        message_id="msg-01",
        sender_id="node_sender",
        recipient_id=peer_id,
        message_type=MessageType.DIRECT,
        content={"text": "Offline packet 1"},
        timestamp=datetime.now(UTC),
        signature="sig1",
        nonce="n1",
    )
    msg2 = SignedMessage(
        message_id="msg-02",
        sender_id="node_sender",
        recipient_id=peer_id,
        message_type=MessageType.DIRECT,
        content={"text": "Offline packet 2"},
        timestamp=datetime.now(UTC),
        signature="sig2",
        nonce="n2",
    )

    assert mailbox.enqueue(peer_id, msg1) is True
    assert mailbox.enqueue(peer_id, msg2) is True
    # Test deduplication
    assert mailbox.enqueue(peer_id, msg1) is True

    assert mailbox.get_pending_count(peer_id) == 2

    # Verify reloading from disk
    reloaded_mailbox = OfflineMailboxManager(storage_dir=temp_test_dir)
    assert reloaded_mailbox.get_pending_count(peer_id) == 2

    # Pop messages
    popped = reloaded_mailbox.pop_all_for_recipient(peer_id)
    assert len(popped) == 2
    assert popped[0].message_id == "msg-01"
    assert popped[1].message_id == "msg-02"

    # Queue should now be empty
    assert reloaded_mailbox.get_pending_count(peer_id) == 0


def test_synckey_manager_delta_sync(temp_test_dir):
    """Test WeChat-style SyncKey monotonic sequence incrementation and incremental delta slices."""
    sync_mgr = SyncKeyManager(storage_dir=temp_test_dir)
    channel_id = sync_mgr.get_channel_id("alice", "bob")

    messages = []
    for i in range(1, 6):
        m = SignedMessage(
            message_id=f"msg-{i}",
            sender_id="alice",
            recipient_id="bob",
            message_type=MessageType.DIRECT,
            content={"text": f"Message number {i}"},
            timestamp=datetime.now(UTC),
            signature=f"sig-{i}",
            nonce=f"nonce-{i}",
        )
        assigned = sync_mgr.assign_next_seq(channel_id, m)
        assert assigned.seq_id == i
        messages.append(assigned)

    assert sync_mgr.get_latest_seq(channel_id) == 5

    # Simulate Bob reconnecting having only seen up to seq 2
    delta = sync_mgr.get_delta_slice(channel_id, since_seq=2)
    assert len(delta) == 3
    assert [d.seq_id for d in delta] == [3, 4, 5]
    assert [d.message_id for d in delta] == ["msg-3", "msg-4", "msg-5"]


def test_receipt_pipeline_state_transitions():
    """Test 4-stage receipt lifecycle tracking and peer thinking indicators."""
    pipeline = ReceiptPipeline()
    msg_id = "msg-chat-777"
    sender = "agent_x"
    peer = "agent_y"

    # 1. Dispatched
    pipeline.track_sent(msg_id, sender, peer)
    assert pipeline.get_message_state(msg_id) == ReceiptState.SENT
    assert pipeline.is_peer_thinking(peer) is False

    # 2. Delivered
    pipeline.update_receipt(msg_id, "delivered", peer_id=peer)
    assert pipeline.get_message_state(msg_id) == ReceiptState.DELIVERED
    assert pipeline.is_peer_thinking(peer) is False

    # 3. Peer enters LLM reasoning loop (Thinking)
    pipeline.update_receipt(msg_id, "thinking", peer_id=peer)
    assert pipeline.get_message_state(msg_id) == ReceiptState.THINKING
    assert pipeline.is_peer_thinking(peer) is True

    # 4. Peer completes reply
    pipeline.update_receipt(msg_id, "replied", peer_id=peer)
    assert pipeline.get_message_state(msg_id) == ReceiptState.REPLIED
    assert pipeline.is_peer_thinking(peer) is False


def test_event_dag_causal_topological_sort():
    """Test Matrix Event DAG causal ordering when messages arrive out of chronological order."""
    t0 = datetime(2026, 8, 15, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 8, 15, 10, 1, 0, tzinfo=UTC)
    t2 = datetime(2026, 8, 15, 10, 2, 0, tzinfo=UTC)
    t3 = datetime(2026, 8, 15, 10, 3, 0, tzinfo=UTC)

    # Causal dependency graph:
    # m_root -> m_proposal -> m_debate_a & m_debate_b -> m_consensus
    m_root = SignedMessage(
        message_id="m_root",
        sender_id="agent_1",
        recipient_id="group_x",
        message_type=MessageType.GROUP,
        content={"text": "Initiating AIP proposal"},
        timestamp=t0,
        signature="s0",
        nonce="n0",
        parents=[],
    )
    m_proposal = SignedMessage(
        message_id="m_proposal",
        sender_id="agent_1",
        recipient_id="group_x",
        message_type=MessageType.GROUP,
        content={"text": "Drafting proposal details"},
        timestamp=t1,
        signature="s1",
        nonce="n1",
        parents=["m_root"],
    )
    m_debate_a = SignedMessage(
        message_id="m_debate_a",
        sender_id="agent_2",
        recipient_id="group_x",
        message_type=MessageType.GROUP,
        content={"text": "I suggest refining sandbox rules"},
        timestamp=t2,
        signature="s2",
        nonce="n2",
        parents=["m_proposal"],
    )
    m_consensus = SignedMessage(
        message_id="m_consensus",
        sender_id="agent_3",
        recipient_id="group_x",
        message_type=MessageType.GROUP,
        content={"text": "Agreed, all tests pass"},
        timestamp=t3,
        signature="s3",
        nonce="n3",
        parents=["m_debate_a"],
    )

    # Scramble the input order
    scrambled = [m_consensus, m_root, m_debate_a, m_proposal]

    linearized = EventDAGResolver.linearize_messages(scrambled)
    ordered_ids = [m.message_id for m in linearized]

    assert ordered_ids == ["m_root", "m_proposal", "m_debate_a", "m_consensus"]

    # Verify LLM context formatting
    formatted = EventDAGResolver.format_for_llm_context(scrambled)
    assert len(formatted) == 4
    assert formatted[0]["content"] == "Initiating AIP proposal"
    assert formatted[3]["content"] == "Agreed, all tests pass"


def test_offline_backoff_throttling():
    """Test exponential backoff for unreachable nodes up to 3600s (60 min)."""
    from unittest.mock import MagicMock
    from app.p2p_community.message_protocol import MessageProtocol
    from app.p2p_community.network_manager import NetworkManager

    nm = NetworkManager(message_protocol=MessageProtocol(crypto_service=MagicMock()))
    peer_id = "test_offline_peer_001"

    # Initially not in backoff
    in_backoff, _ = nm.is_node_in_backoff(peer_id)
    assert in_backoff is False

    # 1st Failure -> 60s
    b1 = nm.record_node_delivery_failure(peer_id)
    assert b1 == 60.0
    in_backoff, rem = nm.is_node_in_backoff(peer_id)
    assert in_backoff is True
    assert 0 < rem <= 60.0

    # 2nd Failure -> 120s
    b2 = nm.record_node_delivery_failure(peer_id)
    assert b2 == 120.0

    # 3rd Failure -> 240s
    b3 = nm.record_node_delivery_failure(peer_id)
    assert b3 == 240.0

    # 4th Failure -> 480s
    b4 = nm.record_node_delivery_failure(peer_id)
    assert b4 == 480.0

    # 7th Failure -> 3600s (capped at 60 minutes)
    for _ in range(3):
        b_cap = nm.record_node_delivery_failure(peer_id)
    assert b_cap == 3600.0

    # Test recovery clears backoff
    nm.record_node_delivery_success(peer_id)
    in_backoff, _ = nm.is_node_in_backoff(peer_id)
    assert in_backoff is False


def test_online_idle_adaptive_sync_backoff():
    """Test online idle adaptive backoff when no new messages/diffs need syncing, 60min up to 8h."""
    from unittest.mock import MagicMock
    from app.p2p_community.message_protocol import MessageProtocol
    from app.p2p_community.network_manager import NetworkManager

    nm = NetworkManager(message_protocol=MessageProtocol(crypto_service=MagicMock()))
    group_id = "test_steady_group_001"

    # Initially group is ready for sync
    assert nm.should_sync_group(group_id) is True

    # 1st Idle sync completed -> 3600s (60m / 1h)
    i1 = nm.record_group_sync_idle(group_id)
    assert i1 == 3600.0
    assert nm.should_sync_group(group_id) is False

    # 2nd Idle sync completed -> 7200s (120m / 2h)
    i2 = nm.record_group_sync_idle(group_id)
    assert i2 == 7200.0

    # 3rd Idle sync completed -> 14400s (240m / 4h)
    i3 = nm.record_group_sync_idle(group_id)
    assert i3 == 14400.0

    # 4th Idle sync completed -> capped at 28800s (8h)
    i4 = nm.record_group_sync_idle(group_id)
    assert i4 == 28800.0

    # 5th+ Idle sync completed -> still capped at 28800s (8h)
    for _ in range(3):
        i_cap = nm.record_group_sync_idle(group_id)
    assert i_cap == 28800.0

    # Instant activity detection resets idle backoff immediately
    nm.record_group_activity(group_id)
    assert nm.should_sync_group(group_id) is True


@pytest.mark.anyio
async def test_inbox_session_batching_and_formatting():
    """Test grouping raw inbox items by session and formatting multi-message batches."""
    from unittest.mock import MagicMock, AsyncMock
    from app.services.agent_service import AgentService

    agent = AgentService.__new__(AgentService)
    agent.processed_message_ids = set()
    agent.llm = None

    # Helper mock
    def mock_norm(s):
        return s.strip().lower() if s else s
    agent._normalize_session_id = mock_norm

    async def mock_ack(text):
        return "收到" in text or "ACK" in text
    agent.is_pure_acknowledgment = mock_ack

    # 3 messages for peer_1 and 1 message for peer_2
    raw_inbox = [
        {
            "message_id": "msg_001",
            "sender_id": "peer_1",
            "content": {"text": "First question about architecture"},
            "timestamp": "2026-08-25T20:00:00Z",
            "message_type": "DIRECT",
        },
        {
            "message_id": "msg_002",
            "sender_id": "peer_1",
            "content": {"text": "Second question about benchmarks"},
            "timestamp": "2026-08-25T20:01:00Z",
            "message_type": "DIRECT",
        },
        {
            "message_id": "msg_003",
            "sender_id": "peer_2",
            "content": {"text": "Hello from peer 2"},
            "timestamp": "2026-08-25T20:02:00Z",
            "message_type": "DIRECT",
        },
        {
            "message_id": "msg_004",
            "sender_id": "peer_1",
            "content": {"text": "Third question about dataset"},
            "timestamp": "2026-08-25T20:03:00Z",
            "message_type": "DIRECT",
        },
    ]

    # Group by session
    groups = await agent._group_inbox_by_session(raw_inbox)
    assert len(groups) == 2
    assert "peer_1" in groups
    assert "peer_2" in groups
    assert len(groups["peer_1"]) == 3
    assert len(groups["peer_2"]) == 1

    # Format batch for peer_1 (multi-message)
    msg_obj1, m_ids1, senders1, is_ack1 = await agent._format_session_backlog_batch("peer_1", groups["peer_1"])
    assert msg_obj1.metadata["batched_count"] == 3
    assert m_ids1 == ["msg_001", "msg_002", "msg_004"]
    assert senders1 == ["peer_1"]
    assert is_ack1 is False
    assert "合并了会话积存的 3 条待处理消息" in msg_obj1.content
    assert "First question about architecture" in msg_obj1.content
    assert "Third question about dataset" in msg_obj1.content

    # Format batch for peer_2 (single message)
    msg_obj2, m_ids2, senders2, is_ack2 = await agent._format_session_backlog_batch("peer_2", groups["peer_2"])
    assert msg_obj2.metadata["batched_count"] == 1
    assert m_ids2 == ["msg_003"]
    assert msg_obj2.content == "Hello from peer 2"
