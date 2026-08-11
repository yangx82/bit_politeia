import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.models.schemas import Message
from app.services.agent_service import AgentService


async def test_message_retry():
    print("Starting Message Retry Test...")

    # 1. Initialize AgentService
    agent_service = AgentService()

    # 2. Mock p2p_service to track calls and simulate success
    from app.services.p2p_service import p2p_service

    p2p_service._initialized = True
    p2p_service.send_message = AsyncMock(return_value=True)
    p2p_service.webrtc_manager = MagicMock()
    p2p_service.webrtc_manager.send_message = AsyncMock(
        return_value=False
    )  # Force HTTP/Relay path for simplicity

    # 3. Inject a FAILED message into history from 15 minutes ago
    past_time = datetime.now() - timedelta(minutes=15)
    test_id = "retry_test_123"
    test_content = "Retry me please!"
    recipient_id = "target_node_xyz"

    failed_msg = Message(
        id=test_id,
        content=test_content,
        sender="agent",
        timestamp=past_time,
        session_id=recipient_id,
        status="failed",
    )
    agent_service.history.append(failed_msg)

    print(f"Injected failed message {test_id} from {past_time}")

    # 4. Run the retry logic manually
    await agent_service._retry_failed_messages()

    # 5. Verify results
    # Check if p2p_service.send_message was called
    if p2p_service.send_message.called:
        print("SUCCESS: p2p_service.send_message was called!")
        # Check arguments
        args, kwargs = p2p_service.send_message.call_args
        if args[0] == recipient_id and kwargs.get("message_id") == test_id:
            print("SUCCESS: Correct recipient and message_id used for retry!")
        else:
            print(f"FAILURE: Unexpected call args: {args}, {kwargs}")
    else:
        print("FAILURE: p2p_service.send_message was NOT called!")

    # Check if status was updated in history
    if failed_msg.status == "sent":
        print("SUCCESS: Message status updated to 'sent' in history!")
    else:
        print(f"FAILURE: Message status is '{failed_msg.status}', expected 'sent'!")

    # Verify timestamp is unchanged
    if failed_msg.timestamp == past_time:
        print("SUCCESS: Original timestamp preserved!")
    else:
        print(f"FAILURE: Timestamp changed! Original: {past_time}, Current: {failed_msg.timestamp}")


if __name__ == "__main__":
    asyncio.run(test_message_retry())
