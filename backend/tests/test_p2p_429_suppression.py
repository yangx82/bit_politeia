# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.bus.events import InboundMessage, OutboundMessage
from app.p2p_community.models import Node
from app.services.agent_service import agent_service
from app.services.p2p_service import p2p_service


@pytest.fixture(autouse=True)
def setup_agent_environment():
    orig_initialized = p2p_service._initialized
    orig_local_node = p2p_service.local_node
    orig_network_manager = p2p_service.network_manager
    orig_history = list(agent_service.history)
    orig_run_loop = agent_service._run_ralph_wiggum_loop
    orig_bus = agent_service.message_bus
    orig_cm = agent_service.context_manager
    orig_llm = agent_service.llm

    p2p_service._initialized = True

    class MockNetworkManager:
        def __init__(self):
            self.nodes = {
                "node_aarron": Node("node_aarron", self, "pk1", "Aarron"),
                "node_plato": Node("node_plato", self, "pk2", "Bit Plato"),
            }

    p2p_service.network_manager = MockNetworkManager()

    class MockLocalNode:
        def __init__(self):
            self.node_id = "agent_node"
            self.group_ids = {"grp_governance_board"}
            self.inbox = []

    p2p_service.local_node = MockLocalNode()
    agent_service.context_manager = MagicMock()
    agent_service.llm = MagicMock()
    agent_service.message_bus = MagicMock()
    agent_service.message_bus.publish_outbound = AsyncMock()

    yield

    p2p_service._initialized = orig_initialized
    p2p_service.local_node = orig_local_node
    p2p_service.network_manager = orig_network_manager
    agent_service.history = orig_history
    agent_service._run_ralph_wiggum_loop = orig_run_loop
    agent_service.message_bus = orig_bus
    agent_service.context_manager = orig_cm
    agent_service.llm = orig_llm


def test_is_automated_error_notification_429_variants():
    """Verify that all variants of 429 and rate-limit errors are correctly detected."""
    # 1. Exact phrases and common strings
    assert agent_service._is_automated_error_notification("Error code: 429") is True
    assert agent_service._is_automated_error_notification("Error code: 429 即并发配额超限") is True
    assert agent_service._is_automated_error_notification("error code: 429") is True
    assert agent_service._is_automated_error_notification("error code:429") is True
    assert agent_service._is_automated_error_notification("429 Too Many Requests") is True
    assert agent_service._is_automated_error_notification("HTTP 429 rate limit exceeded") is True
    assert agent_service._is_automated_error_notification("Rate limit reached for model gpt-4o") is True
    assert agent_service._is_automated_error_notification("openai.RateLimitError: Error code: 429 - {'error': {'message': 'Rate limit reached', 'code': 'rate_limit_exceeded'}}") is True
    assert agent_service._is_automated_error_notification("并发配额超限，请稍后重试") is True
    assert agent_service._is_automated_error_notification("LLM 配额限制提示：并发配额超限（429 Too Many Requests）") is True
    assert agent_service._is_automated_error_notification("insufficient_quota") is True
    assert agent_service._is_automated_error_notification("quota exceeded") is True

    # 2. Regular non-error text with 429 should NOT be classified as automated error notification
    assert agent_service._is_automated_error_notification("请查阅论文第 429 页的表格") is False
    assert agent_service._is_automated_error_notification("我们在实验 429 中观察到了正向反馈") is False


@pytest.mark.asyncio
async def test_direct_p2p_message_429_suppressed_without_llm():
    """Verify that direct P2P messages with 429 are stored in history but never trigger LLM."""
    pipeline_runs = []

    async def mock_run_loop(msg_obj):
        pipeline_runs.append(msg_obj)
        return "No response generated.", False, None

    agent_service._run_ralph_wiggum_loop = mock_run_loop
    agent_service.history.clear()

    msg_429 = InboundMessage(
        channel="p2p",
        sender_id="node_plato",
        session_id="node_plato",
        content="Error code: 429 - {'error': {'message': 'Rate limit reached for model gpt-4o', 'code': 'rate_limit_exceeded'}}",
        metadata={"message_id": "msg_429_test_1", "timestamp": datetime.now(UTC).isoformat()},
    )

    await agent_service.process_bus_message(msg_429)

    # 1. Pipeline should NOT be executed
    assert len(pipeline_runs) == 0, "LLM pipeline should NOT have been triggered for 429 message!"

    # 2. Message should be stored in history for audit
    history_contents = [m.content for m in agent_service.history]
    assert any("Error code: 429" in c for c in history_contents), "429 message must be preserved in history!"

    # 3. Thought message dispatched to gateway
    published_calls = agent_service.message_bus.publish_outbound.call_args_list
    assert any(
        isinstance(call[0][0], OutboundMessage)
        and call[0][0].type == "thought"
        and ("429" in str(call[0][0].content) or "Loop prevention" in str(call[0][0].content))
        for call in published_calls
    )


@pytest.mark.asyncio
async def test_group_message_429_suppressed_without_llm():
    """Verify that group broadcast messages with 429 are suppressed without invoking LLM."""
    pipeline_runs = []

    async def mock_run_loop(msg_obj):
        pipeline_runs.append(msg_obj)
        return "No response generated.", False, None

    agent_service._run_ralph_wiggum_loop = mock_run_loop
    agent_service.history.clear()

    group_msg_429 = InboundMessage(
        channel="p2p",
        sender_id="node_plato",
        session_id="grp_governance_board",
        content="[Node Alert]: Error code: 429 即并发配额超限，当前节点暂停协同任务",
        metadata={
            "message_id": "msg_grp_429_1",
            "message_type": "group",
            "recipient_type": "group",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    await agent_service.process_bus_message(group_msg_429)

    # 1. LLM Pipeline should NOT have been triggered
    assert len(pipeline_runs) == 0, "LLM pipeline should NOT trigger for group 429 error messages!"

    # 2. History records the group message
    history_contents = [m.content for m in agent_service.history]
    assert any("并发配额超限" in c for c in history_contents)


@pytest.mark.asyncio
async def test_inbox_backlog_batch_429_suppression():
    """Verify that process_network_inbox handles 429 messages without invoking LLM pipeline."""
    pipeline_runs = []

    async def mock_run_loop(msg_obj):
        pipeline_runs.append(msg_obj)
        return "No response generated.", False, None

    agent_service._run_ralph_wiggum_loop = mock_run_loop
    agent_service.history.clear()
    agent_service._is_processing_inbox = False
    agent_service.processed_message_ids.clear()

    # Backlog with only 429 error message
    msg_429 = {
        "sender_id": "node_plato",
        "content": "Error code: 429 (Too Many Requests / Rate limit exceeded)",
        "message_type": "DIRECT",
        "message_id": "inbox_429_1",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    p2p_service.local_node.inbox = [msg_429]

    await agent_service.process_network_inbox()

    assert len(pipeline_runs) == 0, "Batch with 429 error message must not execute LLM pipeline!"
    history_contents = [m.content for m in agent_service.history]
    assert any("Error code: 429" in c for c in history_contents)


@pytest.mark.asyncio
async def test_run_pipeline_defense_in_depth():
    """Verify that run_pipeline defense-in-depth aborts immediately without delay or LLM."""
    agent_service.p2p_reply_delay = 10
    agent_service.p2p_random_delay_max = 10.0

    msg = InboundMessage(
        channel="p2p",
        sender_id="node_plato",
        session_id="grp_governance_board",
        content="Error code: 429 - Rate limit reached",
        metadata={"package_type": "group", "recipient_type": "group"},
        timestamp=datetime.now(UTC),
    )

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("app.agent.pipeline.SenseStage.run", new_callable=AsyncMock) as mock_sense:

        resp, cont_req, reason = await agent_service.run_pipeline(msg)

        # 1. sleep should NOT be called (no jitter delay waited)
        mock_sleep.assert_not_called()

        # 2. SenseStage (LLM execution) should NOT be called
        mock_sense.assert_not_called()

        # 3. Response should be [NO_RESPONSE_NEEDED]
        assert resp == "[NO_RESPONSE_NEEDED]"
        assert cont_req is False
        assert "SUPPRESSED" in reason


@pytest.mark.asyncio
async def test_resident_chat_with_429_not_suppressed():
    """Verify that normal human user queries asking about 429 in resident chat are NOT suppressed."""
    msg = InboundMessage(
        channel="resident",
        sender_id="resident",
        session_id="resident",
        content="请教一下，如果遇到 Error code: 429 并发超限该如何配置重试？",
        timestamp=datetime.now(UTC),
    )

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("app.agent.pipeline.SenseStage.run", new_callable=AsyncMock) as mock_sense:

        async def stop_pipe(context, agent):
            context.stop_execution = True
            context.final_answer = "处理 429 错误的建议配置..."

        mock_sense.side_effect = stop_pipe

        resp, cont_req, reason = await agent_service.run_pipeline(msg)

        # Should NOT be suppressed
        mock_sense.assert_called_once()
        assert resp == "处理 429 错误的建议配置..."
