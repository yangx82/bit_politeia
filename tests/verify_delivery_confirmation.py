import asyncio

# Mocking the environment
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.append(str(Path(__file__).parent.parent / "backend"))


async def test_delivery_failure():
    print("Testing P2P Delivery Failure Reporting...")

    # Mock RelayClient
    mock_relay = AsyncMock()
    mock_relay.send.return_value = False  # Simulate failure
    mock_relay.websocket = MagicMock()

    # Mock NetworkManager
    from app.p2p_community.message_protocol import MessageProtocol
    from app.p2p_community.network_manager import NetworkManager

    protocol = MessageProtocol(MagicMock())
    nm = NetworkManager(protocol)
    nm.relay_client = mock_relay
    nm.local_node_id = "test_node"

    # Test routing to unknown node (should hit relay and fail)
    print("Step 1: Testing NetworkManager.route_message failure...")
    from app.p2p_community.message_protocol import MessageType

    msg = protocol.create_message("test_node", "target_node", MessageType.DIRECT, {"text": "hello"})

    success = await nm.route_message(msg)
    print(f"NetworkManager Success: {success} (Expected: False)")
    assert success is False

    # Mock P2PService
    from app.services.p2p_service import p2p_service

    p2p_service.network_manager = nm
    p2p_service.local_node = MagicMock()
    p2p_service.local_node.send_message = AsyncMock(side_effect=nm.send_signed_message)

    # Test AgentService
    from app.services.agent_service import AgentService

    agent = AgentService()
    agent.llm = AsyncMock()
    agent.llm.ainvoke.return_value = MagicMock(content="APPROVED")

    print("Step 2: Testing AgentService.send_p2p_message failure...")
    result = await agent.send_p2p_message("target_node", "hello")
    print(f"AgentService Result: {result}")
    assert result["success"] is False
    assert "Transport failure" in result["error"]

    # Test Tool
    from app.agent.tools import send_p2p_message

    print("Step 3: Testing Tool feedback...")
    tool_result = await send_p2p_message("target_node", "hello")
    print(f"Tool Result: {tool_result}")
    assert "FAILED" in tool_result

    print("\nVerification Complete: All layers correctly report delivery failure.")


if __name__ == "__main__":
    asyncio.run(test_delivery_failure())
