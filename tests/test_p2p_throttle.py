import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.models.session import Session
from app.services.agent_service import AgentService


async def run_test():
    print("Starting P2P Message Throttle Verification...")

    # 1. Setup Mock AgentService
    agent = AgentService()
    agent.history = []

    # Mock p2p_service
    mock_p2p = MagicMock()
    mock_p2p._initialized = True
    mock_p2p.local_node.node_id = "node_agent"
    mock_p2p.network_manager.nodes = {}
    mock_p2p.network_manager.groups = {}

    # Mock message_bus (Must be AsyncMock for awaitable calls)
    from unittest.mock import AsyncMock

    mock_bus = AsyncMock()
    agent.message_bus = mock_bus

    # Mock compliance check to always pass (and be awaitable)
    agent._check_compliance = AsyncMock(return_value=(True, ""))

    # Mock session_service
    mock_session = Session(entity_id="peer_123", channel="p2p")
    mock_session_manager = MagicMock()
    mock_session_manager.get_session.return_value = mock_session
    mock_session_manager.sessions = {"peer_123": mock_session}

    with (
        patch("app.services.agent_service.p2p_service", mock_p2p),
        patch("app.services.agent_service.session_manager", mock_session_manager),
    ):
        print("\n--- TEST 1: First Message (Immediate Send) ---")
        recipient = "peer_123"
        content_1 = "Hello from agent!"

        result_1 = await agent.send_p2p_message(recipient, content_1)
        print(f"Result 1 Status: {result_1.get('status') or 'success'}")

        last_reply_iso = mock_session.metadata.get("last_p2p_reply_at")
        print(f"Last Reply Recorded: {last_reply_iso}")
        assert last_reply_iso is not None
        assert mock_session.metadata.get("pending_reply") is None

        print("\n--- TEST 2: Rapid Second Message (Throttled/Buffered) ---")
        content_2 = "Wait, I forgot to say something!"

        result_2 = await agent.send_p2p_message(recipient, content_2)
        print(f"Result 2 Status: {result_2.get('status')}")

        assert result_2.get("status") == "buffered"
        assert mock_session.metadata.get("pending_reply") == content_2
        print(f"Buffered Content: {mock_session.metadata.get('pending_reply')}")

        print("\n--- TEST 3: Context Awareness ---")
        # Simulate building messages for the next interaction
        from app.agent.context import ContextBuilder

        cb = ContextBuilder()

        messages = cb.build_messages(
            history=[],
            current_message="New user ping",
            pending_reply=mock_session.metadata.get("pending_reply"),
        )

        # Check if the pending reply is in the system prompt
        found_inhibition = False
        for m in messages:
            if "[PENDING REPLY INHIBITION]" in m.content:
                found_inhibition = True
                print(f"Context Injection Verified: {m.content[:100]}...")
                break
        assert found_inhibition

        print("\n--- TEST 4: Background Flush (Manual Trigger) ---")
        # Set the time back artificially to simulate 5 minutes passing
        Five_mins_ago = (datetime.now(UTC) - timedelta(minutes=6)).isoformat()
        mock_session.metadata["last_p2p_reply_at"] = Five_mins_ago

        print("Simulating time passed. Cooldown expired.")

        # Track if send_p2p_message is called with bypass_throttle=True
        # Instead of AsyncMock which can be tricky with wraps/side_effect,
        # we manually wrap it in a tracker.
        original_send = agent.send_p2p_message
        call_registry = []

        async def tracked_send(*args, **kwargs):
            call_registry.append(kwargs)
            return await original_send(*args, **kwargs)

        agent.send_p2p_message = tracked_send

        await agent._flush_throttled_messages()

        # Verify send_p2p_message was called with bypass_throttle=True
        called_with_bypass = False
        for kwargs in call_registry:
            if kwargs.get("bypass_throttle"):
                called_with_bypass = True
                break
        assert called_with_bypass
        print("Flush Logic Verified: bypass_throttle used.")

        assert mock_session.metadata.get("pending_reply") is None
        print("Success: Pending reply cleared after flush.")

    print("\nALL THROTTLE TESTS PASSED.")


if __name__ == "__main__":
    asyncio.run(run_test())
