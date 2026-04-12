import asyncio
import os
import sys
import uuid
from unittest.mock import patch

# Ensure we can import from backend
sys.path.append(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
)

# Mock out heavy stuff before importing AgentService to avoid side effects
with (
    patch("apscheduler.schedulers.asyncio.AsyncIOScheduler"),
    patch("app.services.agent_service.AgentService._hydrate_history"),
):
    from app.services.agent_service import AgentService


async def test_p2p_handoff_v2():
    print("Initializing P2P Handoff Test V2...")

    agent_a = AgentService()
    agent_b = AgentService()

    # Track received messages
    received_messages = []

    async def mock_send(recipient, payload):
        print(f"[MOCK NETWORK] Sending to {recipient}: {payload.get('type')}")
        received_messages.append((recipient, payload))

        # Route to logic
        if payload.get("type") == "task_handoff":
            # Delegate to agent_b
            asyncio.create_task(agent_b.handle_p2p_handoff("AGENT_A", payload))
        elif payload.get("type") == "task_result":
            # Delegate to agent_a
            asyncio.create_task(agent_a.handle_p2p_result("AGENT_B", payload))

    # Apply mock
    # Need to be careful with where p2p_service is imported
    with patch("app.services.p2p_service.p2p_service.send_message", side_effect=mock_send):
        # 1. Simulate Agent A calling the handoff tool
        print("\n[STEP 1] Agent A delegating task...")
        handoff_id = str(uuid.uuid4())
        payload = {
            "type": "task_handoff",
            "handoff_id": handoff_id,
            "task": "Test Task",
            "context": "Test Context",
            "inputs": {"val": 1},
        }

        # Manually trigger Agent B's receiver (simulating transmission)
        await agent_b.handle_p2p_handoff("AGENT_A", payload)

        # 2. Wait for background processing (Agent B should send result back)
        print("\n[STEP 2] Waiting for response...")
        await asyncio.sleep(0.5)

        # 3. Verify
        # We expect a task_result sent back to AGENT_A
        results = [p for r, p in received_messages if p.get("type") == "task_result"]
        if any(results):
            print("[PASS] Task Result received!")
            print(f"Result Content: {results[0].get('output')}")
        else:
            print("[FAIL] Task Result NOT received.")


if __name__ == "__main__":
    asyncio.run(test_p2p_handoff_v2())
