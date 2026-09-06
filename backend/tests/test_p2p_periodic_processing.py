import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.bus.events import InboundMessage, OutboundMessage
from app.services.agent_service import agent_service


@pytest.fixture(autouse=True)
def reset_p2p_mode():
    """Reset agent_service processing mode and backlog before and after each test."""
    original_mode = agent_service.p2p_processing_mode
    original_interval = agent_service.p2p_periodic_interval_minutes
    agent_service._pending_p2p_backlog.clear()
    for t in agent_service._debounce_tasks.values():
        if t and not t.done():
            t.cancel()
    agent_service._debounce_tasks.clear()
    agent_service._session_first_arrival.clear()
    agent_service.p2p_processing_mode = "instant"
    yield
    agent_service.p2p_processing_mode = original_mode
    agent_service.p2p_periodic_interval_minutes = original_interval
    agent_service._pending_p2p_backlog.clear()
    for t in agent_service._debounce_tasks.values():
        if t and not t.done():
            t.cancel()
    agent_service._debounce_tasks.clear()
    agent_service._session_first_arrival.clear()


@pytest.mark.asyncio
async def test_instant_mode_processes_immediately():
    """Verify that in 'instant' mode, P2P messages trigger _run_ralph_wiggum_loop immediately."""
    agent_service.p2p_processing_mode = "instant"

    msg = InboundMessage(
        channel="p2p",
        sender_id="node_sender_1",
        session_id="p2p_session_1",
        content="Hello from instant mode",
        metadata={"message_id": "msg_inst_1", "package_type": "chat"},
    )

    with patch.object(
        agent_service, "_run_ralph_wiggum_loop", new_callable=AsyncMock
    ) as mock_loop:
        mock_loop.return_value = ("Instant response", False, "None")
        await agent_service.process_bus_message(msg)

        assert mock_loop.await_count == 1
        assert "p2p_session_1" not in agent_service._pending_p2p_backlog


@pytest.mark.asyncio
async def test_periodic_mode_enqueues_and_skips_immediate_llm():
    """Verify that in 'periodic' mode, P2P messages are enqueued and LLM is NOT called immediately."""
    agent_service.p2p_processing_mode = "periodic"

    msg = InboundMessage(
        channel="p2p",
        sender_id="node_sender_2",
        session_id="p2p_session_2",
        content="First message in periodic queue",
        metadata={"message_id": "msg_per_1", "package_type": "chat"},
    )

    with patch.object(
        agent_service, "_run_ralph_wiggum_loop", new_callable=AsyncMock
    ) as mock_loop:
        await agent_service.process_bus_message(msg)

        # LLM must NOT be called immediately
        assert mock_loop.await_count == 0

        # Message must be queued in backlog
        norm_session = agent_service._normalize_session_id("p2p_session_2", channel="p2p")
        assert norm_session in agent_service._pending_p2p_backlog
        queued = agent_service._pending_p2p_backlog[norm_session]
        assert len(queued) == 1
        assert queued[0]["text_content"] == "First message in periodic queue"


@pytest.mark.asyncio
async def test_resident_channel_bypasses_periodic_mode():
    """Verify that human resident messages ALWAYS process immediately even in periodic mode."""
    agent_service.p2p_processing_mode = "periodic"

    msg = InboundMessage(
        channel="resident",
        sender_id="resident_user",
        session_id="resident_chat",
        content="Human resident asking for assistance",
        metadata={"message_id": "msg_res_1"},
    )

    with patch.object(
        agent_service, "_run_ralph_wiggum_loop", new_callable=AsyncMock
    ) as mock_loop:
        mock_loop.return_value = ("Resident answer", False, "None")
        await agent_service.process_bus_message(msg)

        # Resident message must bypass periodic queue and run immediately
        assert mock_loop.await_count == 1
        assert "resident_chat" not in agent_service._pending_p2p_backlog


@pytest.mark.asyncio
async def test_periodic_batch_processing_multiple_messages_merged():
    """Verify that multiple messages in the same session are merged into 1 prompt and processed in 1 LLM call."""
    agent_service.p2p_processing_mode = "periodic"
    session_id = "grp_test_collective_01"

    # Send 3 distinct messages into the same session
    messages = [
        "First point: we need to evaluate caching strategies.",
        "Second point: MemGPT hierarchical tiering is worth testing.",
        "Third point: please synthesize a recommended TTL strategy.",
    ]

    for idx, text in enumerate(messages, 1):
        msg = InboundMessage(
            channel="group",
            sender_id=f"node_peer_{idx}",
            session_id=session_id,
            content=text,
            metadata={
                "message_id": f"msg_batch_{idx}",
                "package_type": "group",
                "recipient_type": "group",
            },
        )
        await agent_service.process_bus_message(msg)

    # Verify all 3 are in the backlog
    norm_session = agent_service._normalize_session_id(session_id, channel="group")
    assert len(agent_service._pending_p2p_backlog[norm_session]) == 3

    # Trigger periodic batch processing
    with patch.object(
        agent_service, "_run_ralph_wiggum_loop", new_callable=AsyncMock
    ) as mock_loop, patch.object(
        agent_service.message_bus, "publish_outbound", new_callable=AsyncMock
    ) as mock_outbound:
        mock_loop.return_value = ("Comprehensive synthesis of all 3 points.", False, "None")

        await agent_service.process_periodic_p2p_backlog()

        # LLM must have been invoked exactly ONCE for the entire batch
        assert mock_loop.await_count == 1
        batched_inbound = mock_loop.call_args[0][0]

        # The batched prompt must contain content from all 3 messages
        for text in messages:
            assert text in batched_inbound.content

        # Backlog must now be cleared
        assert len(agent_service._pending_p2p_backlog.get(norm_session, [])) == 0

        # An outbound reply must have been published to the bus
        published_contents = [call[0][0].content for call in mock_outbound.call_args_list]
        assert any("Comprehensive synthesis" in str(c) for c in published_contents)


@pytest.mark.asyncio
async def test_periodic_batch_filters_429_and_pure_ack():
    """Verify that 429 rate limits and pure acks in a batch are filtered out cleanly."""
    agent_service.p2p_processing_mode = "periodic"
    session_id = "grp_filtered_session"

    items = [
        InboundMessage(
            channel="group",
            sender_id="node_a",
            session_id=session_id,
            content="Real actionable research question: What is the optimal quorum?",
            metadata={"message_id": "m1"},
        ),
        InboundMessage(
            channel="group",
            sender_id="node_b",
            session_id=session_id,
            content="Error code: 429 Too Many Requests concurrency limit reached",
            metadata={"message_id": "m2"},
        ),
        InboundMessage(
            channel="group",
            sender_id="node_c",
            session_id=session_id,
            content="收到",
            metadata={"message_id": "m3"},
        ),
    ]

    for m in items:
        await agent_service.process_bus_message(m)

    with patch.object(
        agent_service, "_run_ralph_wiggum_loop", new_callable=AsyncMock
    ) as mock_loop:
        mock_loop.return_value = ("Optimal quorum is 80%.", False, "None")
        await agent_service.process_periodic_p2p_backlog()

        assert mock_loop.await_count == 1
        batched_inbound = mock_loop.call_args[0][0]
        # Actionable content should be present
        assert "What is the optimal quorum?" in batched_inbound.content
        # 429 error and pure ack should be stripped from actionable batch
        assert "Error code: 429" not in batched_inbound.content


def test_set_p2p_processing_mode_dynamic_switch():
    """Verify dynamic switching between modes and argument validation."""
    # 1. Switch to periodic 10 min
    res = agent_service.set_p2p_processing_mode("periodic", 10)
    assert res["mode"] == "periodic"
    assert res["interval_minutes"] == 10
    assert agent_service.p2p_processing_mode == "periodic"
    assert agent_service.p2p_periodic_interval_minutes == 10

    # 2. Switch back to instant
    res2 = agent_service.set_p2p_processing_mode("instant")
    assert res2["mode"] == "instant"
    assert agent_service.p2p_processing_mode == "instant"

    # 3. Invalid mode raises ValueError
    with pytest.raises(ValueError, match="Invalid mode"):
        agent_service.set_p2p_processing_mode("invalid_mode")
