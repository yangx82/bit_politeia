import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.bus.events import InboundMessage
from app.services.agent_service import AgentService


async def test_timestamp_persistence():
    print("Starting Timestamp Persistence Test...")

    # 1. Initialize AgentService
    agent_service = AgentService()

    # 2. Create a mock P2P message with a BACKDATED timestamp (1 hour ago)
    past_time = datetime.now() - timedelta(hours=1)
    past_time_iso = past_time.isoformat()

    test_id = str(uuid.uuid4())[:8]
    test_content = f"Hello from the past! {test_id}"

    mock_p2p_payload = {
        "message_id": f"test_msg_{test_id}",
        "message_type": "direct",
        "recipient_id": "local_node_id",
        "timestamp": past_time_iso,
        "text": test_content,
    }

    inbound_msg = InboundMessage(
        channel="p2p",
        sender_id="sender_node_abc",
        session_id="sender_node_abc",
        content=test_content,
        metadata=mock_p2p_payload,
    )

    print(f"Injecting message with original timestamp: {past_time_iso}")

    # 3. Process the message
    # We simulate what process_bus_message does but more directly
    await agent_service.process_bus_message(inbound_msg)

    # 4. Verify history
    found = False
    for msg in agent_service.history:
        if msg.content == test_content:
            found = True
            print(f"Found message in history with timestamp: {msg.timestamp}")
            # Check if the difference is small (accounting for ISO parsing)
            diff = abs((msg.timestamp - past_time).total_seconds())
            if diff < 5:  # Within 5 seconds tolerance
                print("SUCCESS: Original timestamp preserved!")
            else:
                print(f"FAILURE: Timestamp mismatch! Diff: {diff}s")
                print(f"Expected: {past_time}")
                print(f"Actual: {msg.timestamp}")
            break

    if not found:
        print("FAILURE: Message not found in history!")


if __name__ == "__main__":
    asyncio.run(test_timestamp_persistence())
