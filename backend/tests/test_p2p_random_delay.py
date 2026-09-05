# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.bus.events import InboundMessage
from app.services.agent_service import agent_service


@pytest.fixture(autouse=True)
def setup_agent():
    orig_cm = agent_service.context_manager
    orig_llm = agent_service.llm
    orig_delay = getattr(agent_service, "p2p_reply_delay", 60)
    orig_jitter_max = getattr(agent_service, "p2p_random_delay_max", 10.0)
    orig_bus = agent_service.message_bus

    agent_service.context_manager = MagicMock()
    agent_service.llm = MagicMock()
    agent_service.message_bus = MagicMock()
    agent_service.message_bus.publish_outbound = AsyncMock()

    yield

    agent_service.context_manager = orig_cm
    agent_service.llm = orig_llm
    agent_service.p2p_reply_delay = orig_delay
    agent_service.p2p_random_delay_max = orig_jitter_max
    agent_service.message_bus = orig_bus


@pytest.mark.asyncio
async def test_direct_p2p_message_includes_random_delay():
    agent_service.p2p_reply_delay = 5
    agent_service.p2p_random_delay_max = 10.0

    msg = InboundMessage(
        channel="p2p",
        sender_id="peer_node_abc",
        session_id="peer_node_abc",
        content="Hello peer",
        timestamp=datetime.now(UTC),
    )

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("app.agent.pipeline.SenseStage.run", new_callable=AsyncMock) as mock_sense:

        async def stop_pipe(context, agent):
            context.stop_execution = True
        mock_sense.side_effect = stop_pipe

        await agent_service.run_pipeline(msg)

        mock_sleep.assert_called_once()
        delay_arg = mock_sleep.call_args[0][0]
        # Base delay ~5s + jitter [0, 10s] => total in [4.5, 15.5]
        assert 4.5 <= delay_arg <= 15.5


@pytest.mark.asyncio
async def test_group_message_includes_random_delay():
    agent_service.p2p_reply_delay = 0  # 0 base delay
    agent_service.p2p_random_delay_max = 10.0

    msg = InboundMessage(
        channel="p2p",
        sender_id="peer_node_xyz",
        session_id="grp_governance_board",
        content="Group proposal broadcast",
        metadata={"message_type": "group", "recipient_type": "group"},
        timestamp=datetime.now(UTC),
    )

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("app.agent.pipeline.SenseStage.run", new_callable=AsyncMock) as mock_sense:

        async def stop_pipe(context, agent):
            context.stop_execution = True
        mock_sense.side_effect = stop_pipe

        await agent_service.run_pipeline(msg)

        mock_sleep.assert_called_once()
        delay_arg = mock_sleep.call_args[0][0]
        # Base delay is 0, so total_delay is solely the random jitter in [0.0, 10.0]
        assert 0.0 <= delay_arg <= 10.0


@pytest.mark.asyncio
async def test_continuation_message_skips_delay():
    agent_service.p2p_reply_delay = 10
    agent_service.p2p_random_delay_max = 10.0

    msg = InboundMessage(
        channel="p2p",
        sender_id="peer_node_xyz",
        session_id="grp_governance_board",
        content="Executing tool iteration",
        metadata={"epoch": 1},
        timestamp=datetime.now(UTC),
    )

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("app.agent.pipeline.SenseStage.run", new_callable=AsyncMock) as mock_sense:

        async def stop_pipe(context, agent):
            context.stop_execution = True
        mock_sense.side_effect = stop_pipe

        await agent_service.run_pipeline(msg)

        # Continuation loop should NOT sleep
        mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_resident_message_skips_delay():
    agent_service.p2p_reply_delay = 10
    agent_service.p2p_random_delay_max = 10.0

    msg = InboundMessage(
        channel="resident",
        sender_id="resident_user",
        session_id="resident",
        content="Resident prompt to agent",
        timestamp=datetime.now(UTC),
    )

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("app.agent.pipeline.SenseStage.run", new_callable=AsyncMock) as mock_sense:

        async def stop_pipe(context, agent):
            context.stop_execution = True
        mock_sense.side_effect = stop_pipe

        await agent_service.run_pipeline(msg)

        # Resident message should NOT sleep
        mock_sleep.assert_not_called()
