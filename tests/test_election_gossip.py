import asyncio
import os
import sys

# Set PYTHONPATH to both root and backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from unittest.mock import MagicMock, patch

from app.services.p2p_service import P2PService


async def run_test():
    print("Starting Election Gossip Verification...")

    # 1. Setup Mocks
    mock_node = MagicMock()
    mock_node.node_id = "node_a"

    mock_net_manager = MagicMock()
    mock_net_manager.groups = {"group_1": MagicMock()}

    p2p_service = P2PService()
    p2p_service.local_node = mock_node
    p2p_service.network_manager = mock_net_manager

    # Mock GovernanceManager
    mock_gov_manager = MagicMock()

    # 2. Construct Mock Election Message
    election_data = {
        "election": {
            "election_id": "elect_123",
            "group_id": "group_1",
            "election_type": "core_node_election",
            "initiator_id": "node_b",
            "start_time": "2026-04-07T14:00:00Z",
            "end_time": "2026-04-07T15:00:00Z",
            "candidates": ["node_b", "node_c"],
            "eligible_voters": ["node_a", "node_b", "node_c"],
            "status": "active",
        }
    }

    raw_message = {
        "message_id": "msg_001",
        "sender_id": "node_b",
        "recipient_id": "group_1",
        "message_type": "election",  # New type
        "content": election_data,
        "timestamp": "2026-04-07T14:00:00Z",
        "signature": "fake_sig",
        "nonce": "fake_nonce",
    }

    # 3. Patch and Run
    # Use the full path for the mock to avoid registry issues
    with patch("app.services.agent_service.agent_service.governance_manager", mock_gov_manager):
        print("Patching GovernanceManager...")
        with patch.object(
            p2p_service, "_forward_governance_message", return_value=None
        ) as mock_forward:
            print("Injecting P2P message...")
            handled = await p2p_service.handle_p2p_message(raw_message)

            # 4. Assertions
            print(f"Message Handled: {handled}")
            if not handled:
                print("FAIL: Message NOT handled")
                sys.exit(1)

            # Verify Ingestion
            print("Verifying Governance Ingestion...")
            try:
                mock_gov_manager.receive_p2p_event.assert_called_once_with(
                    "election", election_data
                )
                print("SUCCESS: Governance Ingestion verified")
            except AssertionError as e:
                print(f"FAIL: Governance Ingestion verification failed: {e}")
                sys.exit(1)

            # Verify Gossip Forwarding
            print("Verifying Gossip Forwarding...")
            try:
                mock_forward.assert_called_once()
                args, _ = mock_forward.call_args
                if args[0]["message_id"] == "msg_001" and args[1] == "election":
                    print("SUCCESS: Gossip Forwarding verified")
                else:
                    print(f"FAIL: Unexpected forwarding args: {args}")
                    sys.exit(1)
            except AssertionError as e:
                print(f"FAIL: Gossip Forwarding verification failed: {e}")
                sys.exit(1)

    print("ALL TESTS PASSED: Election Gossip Fix is functional.")


if __name__ == "__main__":
    asyncio.run(run_test())
