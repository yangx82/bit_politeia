# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime, UTC
import pytest
import uuid

from app.p2p_community.models import Node
from app.services.agent_service import agent_service
from app.services.p2p_service import p2p_service
from app.bus.events import InboundMessage


def test_is_pure_acknowledgment_base_cases():
    """Verify that basic acknowledgment phrases are correctly classified."""
    # Setup node names in p2p_service for mock node name stripping
    original_initialized = p2p_service._initialized
    original_network_manager = p2p_service.network_manager
    
    p2p_service._initialized = True
    
    class MockNetworkManager:
        def __init__(self):
            self.nodes = {
                "node_aarron": Node("node_aarron", self, "pk1", "Aarron"),
                "node_plato": Node("node_plato", self, "pk2", "Bit Plato")
            }
            
    p2p_service.network_manager = MockNetworkManager()
    agent_service.name = "Aarron"

    try:
        # 1. Pure ack cases (Should return True)
        assert agent_service.is_pure_acknowledgment("好的，收到") is True
        assert agent_service.is_pure_acknowledgment("OK, got it") is True
        assert agent_service.is_pure_acknowledgment("收悉") is True
        assert agent_service.is_pure_acknowledgment("roger") is True
        assert agent_service.is_pure_acknowledgment("copy that") is True
        assert agent_service.is_pure_acknowledgment("同步确认") is True
        assert agent_service.is_pure_acknowledgment("[no_response_needed]") is True
        
        # 2. Combined status + ack cases (Should return True)
        assert agent_service.is_pure_acknowledgment("收悉，维持standby状态") is True
        assert agent_service.is_pure_acknowledgment("好的，继续保持") is True
        assert agent_service.is_pure_acknowledgment("OK, maintaining standby") is True
        
        # 3. User message example with signature block (Should return True)
        user_msg = (
            "[Agent completed P2P task]: 收悉 Aarron ✅\n\n"
            "同步确认。维持 Standby。\n\n"
            "— Bit Plato (5a40d9e6)\n"
            "2026-05-25 21:19"
        )
        assert agent_service.is_pure_acknowledgment(user_msg) is True
        
        # 4. Action/Instruction/Questions (Should return False)
        assert agent_service.is_pure_acknowledgment("维持standby状态") is False
        assert agent_service.is_pure_acknowledgment("请维持standby状态") is False
        assert agent_service.is_pure_acknowledgment("我需要你维持standby状态") is False
        assert agent_service.is_pure_acknowledgment("我们切换到active状态吗？") is False
        assert agent_service.is_pure_acknowledgment("我发现了代码中的一处错误：...") is False
        assert agent_service.is_pure_acknowledgment("好的，但请更新你的状态") is False
        assert agent_service.is_pure_acknowledgment("请执行测试") is False

    finally:
        p2p_service._initialized = original_initialized
        p2p_service.network_manager = original_network_manager


@pytest.mark.asyncio
async def test_process_network_inbox_loop_prevention():
    """Verify that process_network_inbox filters pure acknowledgements and does not trigger LLM pipeline."""
    # Setup mocks
    original_initialized = p2p_service._initialized
    original_local_node = p2p_service.local_node
    original_network_manager = p2p_service.network_manager
    original_history = list(agent_service.history)
    original_run_loop = agent_service._run_ralph_wiggum_loop
    
    p2p_service._initialized = True
    
    class MockNetworkManager:
        def __init__(self):
            self.nodes = {
                "node_aarron": Node("node_aarron", self, "pk1", "Aarron"),
                "node_plato": Node("node_plato", self, "pk2", "Bit Plato")
            }
    
    p2p_service.network_manager = MockNetworkManager()
    
    class MockLocalNode:
        def __init__(self):
            self.node_id = "agent_node"
            self.group_ids = set()
            self.inbox = []
            
    mock_node = MockLocalNode()
    p2p_service.local_node = mock_node
    
    agent_service._is_processing_inbox = False
    agent_service.processed_message_ids.clear()
    
    pipeline_runs = []
    async def mock_run_loop(msg_obj):
        pipeline_runs.append(msg_obj)
        return "No response generated.", None, None
        
    agent_service._run_ralph_wiggum_loop = mock_run_loop
    agent_service.history.clear()
    
    try:
        # Message 1: Normal statement/question (should be processed by LLM pipeline)
        msg_normal = {
            "sender_id": "node_plato",
            "content": "我们今天下午需要更新提案吗？",
            "message_type": "DIRECT",
            "message_id": "msg_normal_1",
            "timestamp": datetime.now(UTC).isoformat()
        }
        
        # Message 2: Pure acknowledgment (should be skipped by pipeline, but recorded in history)
        msg_ack = {
            "sender_id": "node_plato",
            "content": "[Agent completed P2P task]: 收悉 Aarron ✅\n\n同步确认。维持 Standby。\n\n— Bit Plato (5a40d9e6)\n2026-05-25 21:19",
            "message_type": "DIRECT",
            "message_id": "msg_ack_1",
            "timestamp": datetime.now(UTC).isoformat()
        }
        
        mock_node.inbox = [msg_normal, msg_ack]
        
        # Run process_network_inbox
        await agent_service.process_network_inbox()
        
        # 1. Check history: both messages should be saved
        history_contents = [msg.content for msg in agent_service.history]
        assert any("我们今天下午需要更新提案吗？" in content for content in history_contents)
        assert any("同步确认。维持 Standby。" in content for content in history_contents)
        
        # 2. Check LLM pipeline runs: only the normal message should have triggered the LLM
        assert len(pipeline_runs) == 1
        assert pipeline_runs[0].content == "我们今天下午需要更新提案吗？"
        
    finally:
        p2p_service._initialized = original_initialized
        p2p_service.local_node = original_local_node
        p2p_service.network_manager = original_network_manager
        agent_service.history = original_history
        agent_service._run_ralph_wiggum_loop = original_run_loop


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main(["-v", __file__]))
