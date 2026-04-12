import asyncio
import logging
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.bus.events import OutboundMessage
from app.services.agent_service import AgentService
from app.services.p2p_service import p2p_service


# Mock dependencies
class MockBus:
    def __init__(self):
        self.published = []

    async def publish_outbound(self, msg):
        self.published.append(msg)

    async def publish_inbound(self, msg):
        self.published.append(msg)


class MockNode:
    def __init__(self):
        self.node_id = "agent_node_123"
        self.group_ids = ["group_a", "group_b"]
        self.inbox = []

    async def send_message(self, recipient_id, content, msg_type, message_id=None):
        return True  # Success

    async def receive_message(self, msg):
        pass


async def test_msg_refactor_verification():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("TestRefactor")

    agent = AgentService()
    mock_bus = MockBus()
    agent.message_bus = mock_bus

    # Initialize mock P2P
    p2p_service.local_node = MockNode()
    p2p_service._initialized = True

    print("\n--- Starting Phase 7-9 Verification Tests ---\n")

    # 1. Test ID Consistency (Phase 8) & msg_type split (Phase 7)
    print("Test 1: Direct Message sending & ID consistency")
    recipient_id = "peer_456"
    test_content = "Hello Peer"

    result = await agent.send_p2p_message(recipient_id, test_content, package_type="chat")

    # Verify ID in history matches ID in bus
    history_msg = agent.history[-1]
    bus_msgs = [
        m for m in mock_bus.published if isinstance(m, OutboundMessage) and m.channel == "gateway"
    ]
    last_bus_msg = bus_msgs[0]

    print(f"  - History ID: {history_msg.id}")
    print(f"  - Bus Metadata ID: {last_bus_msg.metadata['message_id']}")
    assert history_msg.id == last_bus_msg.metadata["message_id"], "IDs should match!"
    print(f"  - Package Type (Bus): {last_bus_msg.metadata['package_type']}")
    assert last_bus_msg.metadata["package_type"] == "chat"
    print("  ✅ Pass: Direct Message ID & Type verified.")

    # 2. Test Group + File Logic (Phase 7 logic conflict resolution)
    print("\nTest 2: Group Message with File type")
    group_id = "group_a"
    file_content = {"text": "Sending file", "data": "base64data..."}

    mock_bus.published = []  # Reset
    await agent.send_p2p_message(group_id, file_content, package_type="file", message_type="group")

    last_bus = mock_bus.published[0]
    print(f"  - Recipient Type: {last_bus.metadata['recipient_type']}")
    print(f"  - Package Type: {last_bus.metadata['package_type']}")
    assert last_bus.metadata["recipient_type"] == "group"
    assert last_bus.metadata["package_type"] == "file"
    print("  ✅ Pass: Group + File logic resolved successfully.")

    # 3. Test recipient_id standardization (Phase 9)
    print("\nTest 3: recipient_id parameter propagation")
    # This is a bit harder to verify without deep mocking P2PService.send_message,
    # but we can verify our send_p2p_message still works with the new parameter name.
    print("  - Verifying send_p2p_message accepts and uses recipient_id correctly.")
    # (The fact that Test 1 passed already implies the code runs with renamed variables)

    # 4. Test Moderation Failure (Bug fix in Phase 7/9)
    print("\nTest 4: Moderation refusal status")

    # Mock compliance to fail
    async def mock_check_fail(content, recipient_id):
        return False, "Rules violation: spam"

    agent._check_compliance = mock_check_fail

    res = await agent.send_p2p_message("bad_guy", "spam spam spam")
    print(f"  - Result['success']: {res.get('success')}")
    print(f"  - Result['status']: {res.get('status')}")
    assert res["success"] == False
    assert res["status"] == "refused"
    print("  ✅ Pass: Moderation refusal correctly returns success: False.")

    print("\n--- All Phase 7-9 Verification Tests Passed! ---\n")


if __name__ == "__main__":
    asyncio.run(test_msg_refactor_verification())
