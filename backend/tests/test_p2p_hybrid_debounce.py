import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.bus.events import InboundMessage, OutboundMessage
from app.services.agent_service import agent_service


@pytest.fixture(autouse=True)
def cleanup_debounce_fixture():
    """Ensure debounce state and pending backlogs are pristine before/after each test."""
    orig_mode = agent_service.p2p_processing_mode
    orig_delay = agent_service.p2p_debounce_delay_seconds
    orig_max_wait = agent_service.p2p_debounce_max_wait_seconds
    orig_rm = agent_service.resident_memory
    orig_ack = agent_service.is_pure_acknowledgment

    agent_service.resident_memory = MagicMock()
    agent_service.is_pure_acknowledgment = AsyncMock(return_value=False)

    for t in list(agent_service._debounce_tasks.values()):
        if t and not t.done():
            t.cancel()
    agent_service._debounce_tasks.clear()
    agent_service._session_first_arrival.clear()
    agent_service._pending_p2p_backlog.clear()

    yield

    for t in list(agent_service._debounce_tasks.values()):
        if t and not t.done():
            t.cancel()
    agent_service._debounce_tasks.clear()
    agent_service._session_first_arrival.clear()
    agent_service._pending_p2p_backlog.clear()
    agent_service.p2p_processing_mode = orig_mode
    agent_service.p2p_debounce_delay_seconds = orig_delay
    agent_service.p2p_debounce_max_wait_seconds = orig_max_wait
    agent_service.resident_memory = orig_rm
    agent_service.is_pure_acknowledgment = orig_ack


def test_default_mode_and_parameters():
    """Verify that hybrid_debounce is the default mode with 30s delay and 300s max wait."""
    from app.services.agent_service import AgentService
    fresh_agent = AgentService()
    assert fresh_agent.p2p_processing_mode == "hybrid_debounce"
    assert fresh_agent.p2p_debounce_delay_seconds == 30.0
    assert fresh_agent.p2p_debounce_max_wait_seconds == 300.0


@pytest.mark.asyncio
async def test_debounce_enqueues_and_does_not_invoke_llm_immediately():
    """Verify that an incoming P2P message in hybrid_debounce mode starts a task and does not call LLM right away."""
    agent_service.p2p_processing_mode = "hybrid_debounce"
    agent_service.p2p_debounce_delay_seconds = 10.0
    agent_service.p2p_debounce_max_wait_seconds = 300.0

    msg = InboundMessage(
        channel="p2p",
        sender_id="peer_node_1",
        session_id="p2p_session_deb_1",
        content="Hello from debounce test",
        metadata={"message_id": "msg_deb_1", "package_type": "chat"},
    )

    with patch.object(
        agent_service, "_run_ralph_wiggum_loop", new_callable=AsyncMock
    ) as mock_loop:
        await agent_service.process_bus_message(msg)

        # Must not invoke LLM immediately
        assert mock_loop.await_count == 0
        norm_session = agent_service._normalize_session_id("p2p_session_deb_1", channel="p2p")
        # Must be in pending backlog
        assert len(agent_service._pending_p2p_backlog[norm_session]) == 1
        # Debounce task must be registered
        assert norm_session in agent_service._debounce_tasks
        assert not agent_service._debounce_tasks[norm_session].done()


@pytest.mark.asyncio
async def test_sliding_window_debounce_resets_on_new_message():
    """Verify that incoming messages within the quiet window reset the timer and merge into a single LLM call."""
    agent_service.p2p_processing_mode = "hybrid_debounce"
    agent_service.p2p_debounce_delay_seconds = 0.15
    agent_service.p2p_debounce_max_wait_seconds = 5.0
    session_id = "grp_debounce_session"
    norm_session = agent_service._normalize_session_id(session_id, channel="group")

    msg1 = InboundMessage(
        channel="group",
        sender_id="peer_alpha",
        session_id=session_id,
        content="Part 1 of thought.",
        metadata={"message_id": "m1", "package_type": "chat"},
    )
    msg2 = InboundMessage(
        channel="group",
        sender_id="peer_alpha",
        session_id=session_id,
        content="Part 2 of thought.",
        metadata={"message_id": "m2", "package_type": "chat"},
    )

    with patch.object(
        agent_service, "_run_ralph_wiggum_loop", new_callable=AsyncMock
    ) as mock_loop, patch.object(
        agent_service.message_bus, "publish_outbound", new_callable=AsyncMock
    ) as mock_outbound:
        mock_loop.return_value = ("Unified synthesis of both parts.", False, "None")

        # 1. Send first message
        await agent_service.process_bus_message(msg1)
        first_task = agent_service._debounce_tasks.get(norm_session)
        assert first_task is not None

        # 2. Sleep 0.08s (before the 0.15s quiet window expires)
        await asyncio.sleep(0.08)
        assert mock_loop.await_count == 0

        # 3. Send second message -> resets the timer
        await agent_service.process_bus_message(msg2)
        second_task = agent_service._debounce_tasks.get(norm_session)
        # Previous task must be cancelled
        await asyncio.sleep(0)
        assert first_task.cancelled()
        assert second_task is not first_task

        # 4. Wait another 0.08s (0.16s total since msg1, but only 0.08s since msg2). Still no LLM invocation!
        await asyncio.sleep(0.08)
        assert mock_loop.await_count == 0

        # 5. Wait for the new quiet window to expire (0.10s more)
        await asyncio.sleep(0.12)

        # Now LLM must have been called exactly ONCE
        assert mock_loop.await_count == 1
        batched_input = mock_loop.call_args[0][0]
        assert "Part 1 of thought." in batched_input.content
        assert "Part 2 of thought." in batched_input.content

        # Backlog must be cleared
        assert len(agent_service._pending_p2p_backlog.get(norm_session, [])) == 0


@pytest.mark.asyncio
async def test_max_wait_timeout_forces_processing():
    """Verify that when messages keep arriving, max_wait limits starvation and triggers processing."""
    agent_service.p2p_processing_mode = "hybrid_debounce"
    agent_service.p2p_debounce_delay_seconds = 0.15
    agent_service.p2p_debounce_max_wait_seconds = 0.25
    session_id = "grp_max_wait_session"
    norm_session = agent_service._normalize_session_id(session_id, channel="group")

    with patch.object(
        agent_service, "_run_ralph_wiggum_loop", new_callable=AsyncMock
    ) as mock_loop, patch.object(
        agent_service.message_bus, "publish_outbound", new_callable=AsyncMock
    ):
        mock_loop.return_value = ("Forced batch response.", False, "None")

        # t=0
        await agent_service.process_bus_message(
            InboundMessage(
                channel="group",
                sender_id="node_a",
                session_id=session_id,
                content="Message 1",
                metadata={"message_id": "mw1", "package_type": "chat"},
            )
        )

        # t=0.10
        await asyncio.sleep(0.10)
        await agent_service.process_bus_message(
            InboundMessage(
                channel="group",
                sender_id="node_a",
                session_id=session_id,
                content="Message 2",
                metadata={"message_id": "mw2", "package_type": "chat"},
            )
        )

        # t=0.18
        await asyncio.sleep(0.08)
        await agent_service.process_bus_message(
            InboundMessage(
                channel="group",
                sender_id="node_a",
                session_id=session_id,
                content="Message 3",
                metadata={"message_id": "mw3", "package_type": "chat"},
            )
        )

        # Since max_wait is 0.25s, at t=0.27s it must have fired despite continuous message stream
        await asyncio.sleep(0.12)

        assert mock_loop.await_count == 1
        batched_input = mock_loop.call_args[0][0]
        assert "Message 1" in batched_input.content
        assert "Message 2" in batched_input.content
        assert "Message 3" in batched_input.content


@pytest.mark.asyncio
async def test_resident_channel_bypasses_debounce():
    """Verify that resident messages are never debounced or delayed."""
    agent_service.p2p_processing_mode = "hybrid_debounce"
    agent_service.p2p_debounce_delay_seconds = 30.0

    msg = InboundMessage(
        channel="resident",
        sender_id="resident_user",
        session_id="resident_session",
        content="Human query requiring immediate answer",
        metadata={"message_id": "res_m1", "package_type": "chat"},
    )

    with patch.object(
        agent_service, "_run_ralph_wiggum_loop", new_callable=AsyncMock
    ) as mock_loop:
        mock_loop.return_value = ("Immediate human response", False, "None")
        await agent_service.process_bus_message(msg)

        assert mock_loop.await_count == 1
        assert "resident_session" not in agent_service._pending_p2p_backlog
        assert "resident_session" not in agent_service._debounce_tasks


@pytest.mark.asyncio
async def test_pure_ack_and_429_filtered_in_debounce_batch():
    """Verify that if a debounced batch contains only 429 error and ack messages, LLM is skipped."""
    agent_service.p2p_processing_mode = "hybrid_debounce"
    agent_service.p2p_debounce_delay_seconds = 0.05
    session_id = "grp_error_session"

    with patch.object(
        agent_service, "_run_ralph_wiggum_loop", new_callable=AsyncMock
    ) as mock_loop:
        await agent_service.process_bus_message(
            InboundMessage(
                channel="group",
                sender_id="node_b",
                session_id=session_id,
                content="Error code: 429 Too Many Requests (rate limit exceeded)",
                metadata={"message_id": "err_1", "package_type": "chat"},
            )
        )
        await asyncio.sleep(0.08)

        # Must not invoke LLM for 429 error
        assert mock_loop.await_count == 0


@pytest.mark.asyncio
async def test_set_p2p_processing_mode_dynamic_switch():
    """Verify dynamic switching between hybrid_debounce, periodic, and instant modes."""
    res = agent_service.set_p2p_processing_mode("periodic", interval_minutes=10)
    assert res["mode"] == "periodic"
    assert res["interval_minutes"] == 10

    res = agent_service.set_p2p_processing_mode(
        "hybrid_debounce",
        debounce_delay_seconds=45.0,
        debounce_max_wait_seconds=360.0,
    )
    assert res["mode"] == "hybrid_debounce"
    assert res["debounce_delay_seconds"] == 45.0
    assert res["debounce_max_wait_seconds"] == 360.0

    res = agent_service.set_p2p_processing_mode("instant")
    assert res["mode"] == "instant"

    with pytest.raises(ValueError):
        agent_service.set_p2p_processing_mode("invalid_mode")
