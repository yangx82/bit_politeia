import asyncio
import json
from pathlib import Path

from app.services.agent_service import agent_service
from app.services.p2p_service import p2p_service


async def test_atomic_hydration():
    print("Initializing services...")

    # Mocking local node for testing
    class MockNode:
        def __init__(self, node_id):
            self.node_id = node_id
            self.inbox = []
            self.public_key = "test_pub_key"

    node_id = "test_node_id_12345"
    p2p_service.local_node = MockNode(node_id)

    # Setup test file
    p2p_dir = Path("backend/data/p2p")
    p2p_dir.mkdir(parents=True, exist_ok=True)
    inbox_file = p2p_dir / f"inbox_{node_id}.jsonl"
    proc_file = p2p_dir / f"inbox_{node_id}.jsonl.processing"

    test_msg = {"message_id": "msg_1", "content": "hello world"}
    with open(inbox_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(test_msg) + "\n")

    print(f"Created test inbox: {inbox_file}")

    # Trigger hydration
    print("Triggering hydration...")
    agent_service._hydrate_system_state()

    # Verify results
    print(f"Memory Inbox Size: {len(p2p_service.local_node.inbox)}")
    if len(p2p_service.local_node.inbox) > 0:
        print(f"Message in memory: {p2p_service.local_node.inbox[0]['content']}")

    print(f"Inbox file exists: {inbox_file.exists()}")
    print(f"Processing file exists: {proc_file.exists()}")

    if (
        len(p2p_service.local_node.inbox) == 1
        and not inbox_file.exists()
        and not proc_file.exists()
    ):
        print("\nSUCCESS: Atomic hydration worked perfectly!")
    else:
        print("\nFAILURE: State mismatch.")


if __name__ == "__main__":
    asyncio.run(test_atomic_hydration())
