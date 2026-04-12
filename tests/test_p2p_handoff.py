import asyncio
import os
import sys
import uuid
from unittest.mock import MagicMock

# Ensure we can import from backend
sys.path.append(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
)

from app.services.agent_service import AgentService
from app.services.p2p_service import p2p_service


async def test_p2p_handoff():
    print("Initializing P2P Handoff Test...")

    agent_a = AgentService()
    agent_b = AgentService()

    # Mock P2P Service to simulate network transmission
    # Instead of real network, we just pipe messages directly to handlers
    async def mock_send(recipient, payload):
        print(f"[NETWORK] Sending to {recipient}: {payload.get('type')}")
        # Routing logic:
        # payload['type'] == 'task_handoff' -> agent_b.handle_p2p_handoff
        # payload['type'] == 'task_result' -> agent_a.handle_p2p_result
        if payload.get("type") == "task_handoff":
            asyncio.create_task(agent_b.handle_p2p_handoff("AGENT_A", payload))
        elif payload.get("type") == "task_result":
            asyncio.create_task(agent_a.handle_p2p_result("AGENT_B", payload))

    p2p_service.send_message = mock_send

    # 1. Agent A delegates a task to Agent B
    print("\n[STEP 1] Agent A delegating task...")
    handoff_id = str(uuid.uuid4())
    payload = {
        "type": "task_handoff",
        "handoff_id": handoff_id,
        "task": "Please analyze the impact of DAO on group governance.",
        "context": "Focus on the 'Bit Politeia' rules specifically.",
        "inputs": {"depth": "detailed"},
    }

    agent_a.handle_p2p_handoff = MagicMock()  # Mock out if we want to test tool call

    # Simulate Agent A calling the tool (which calls p2p_service.send_message)
    await p2p_service.send_message("AGENT_B", payload)

    # 2. Wait for background processing
    print("\n[STEP 2] Waiting for processing...")
    await asyncio.sleep(1)

    print("\nTest completed. Check logs for delegation and result messages.")


if __name__ == "__main__":
    asyncio.run(test_p2p_handoff())
