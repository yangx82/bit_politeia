# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock

from app.p2p_community.message_protocol import MessageProtocol, MessageType
from app.p2p_community.governance import Proposal, Election, ElectionType
from app.services.agent_service import agent_service
from app.services.p2p_service import p2p_service


@pytest.mark.asyncio
async def test_delta_state_sync():
    """Verify that state sync request filtering (delta state sync) correctly identifies updates."""
    # Store originals
    original_initialized = p2p_service._initialized
    original_local_node = p2p_service.local_node
    original_network_manager = p2p_service.network_manager
    original_gov = agent_service.governance_manager

    # Setup mocks
    p2p_service._initialized = True
    
    mock_local_node = MagicMock()
    mock_local_node.node_id = "local_node_id"
    p2p_service.local_node = mock_local_node
    
    mock_network_manager = MagicMock()
    mock_network_manager.local_node_id = "local_node_id"
    mock_crypto = MagicMock()
    mock_crypto.sign_message.return_value = "fake_signature"
    mock_network_manager.message_protocol = MessageProtocol(mock_crypto)
    
    # Track routed messages
    routed_messages = []
    async def mock_route(msg, gossip_forward=False):
        routed_messages.append((msg, gossip_forward))
        return True
    
    mock_network_manager.route_message = mock_route
    p2p_service.network_manager = mock_network_manager

    # Setup mock GovernanceManager
    mock_gm = MagicMock()
    
    # Create two proposals in local state
    prop_1 = Proposal(
        proposal_id="prop_1",
        initiator_id="initiator_1",
        group_id="group_test",
        content="Proposal 1 content",
        timestamp=datetime.now(timezone.utc),
        status="discussed"
    )
    prop_2 = Proposal(
        proposal_id="prop_2",
        initiator_id="initiator_2",
        group_id="group_test",
        content="Proposal 2 content",
        timestamp=datetime.now(timezone.utc),
        status="voting"
    )
    
    # Create election for proposal 2
    elec_2 = Election(
        election_id="prop_2",
        group_id="group_test",
        election_type=ElectionType.PROPOSAL_VOTE,
        initiator_id="initiator_2",
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        proposal_id="prop_2",
        votes={"voter_a": []}  # 1 vote
    )
    
    mock_gm.proposals = {"prop_1": prop_1, "prop_2": prop_2}
    mock_gm.active_elections = {"prop_2": elec_2}
    agent_service.governance_manager = mock_gm

    try:
        # 1. Sync Request 1: Requester knows nothing
        # It should return both prop_1 and prop_2
        sync_req_1 = mock_network_manager.message_protocol.create_message(
            sender_id="requester_node",
            recipient_id="group_test",
            message_type=MessageType.SYNC,
            content={
                "sync_type": "state_request",
                "requester_id": "requester_node",
                "known_proposals": {}
            }
        )
        
        from app.p2p_community.network_manager import NetworkManager
        
        # Call handle_state_sync_request bound to mock_network_manager
        await NetworkManager.handle_state_sync_request(mock_network_manager, sync_req_1)
        
        # Should have routed 2 messages (prop_1 and prop_2) directly to requester
        assert len(routed_messages) == 2
        pids = [msg[0].content["proposal"]["proposal_id"] for msg in routed_messages]
        assert "prop_1" in pids
        assert "prop_2" in pids
        # Verify they are unicast (gossip_forward=False) and sent to requester_node
        assert all(msg[0].recipient_id == "requester_node" for msg in routed_messages)
        assert all(msg[1] is False for msg in routed_messages)
        
        # Clear routed messages
        routed_messages.clear()
        
        # 2. Sync Request 2: Requester has prop_1 (matching) and prop_2 (status matching but vote count 0 instead of 1)
        # It should skip prop_1, but send prop_2
        sync_req_2 = mock_network_manager.message_protocol.create_message(
            sender_id="requester_node",
            recipient_id="group_test",
            message_type=MessageType.SYNC,
            content={
                "sync_type": "state_request",
                "requester_id": "requester_node",
                "known_proposals": {
                    "prop_1": {"status": "discussed", "vote_count": 0},
                    "prop_2": {"status": "voting", "vote_count": 0}  # Local has 1 vote
                }
            }
        )
        
        await NetworkManager.handle_state_sync_request(mock_network_manager, sync_req_2)
        
        # Should only send prop_2 because vote_count differs (0 vs 1)
        assert len(routed_messages) == 1
        assert routed_messages[0][0].content["proposal"]["proposal_id"] == "prop_2"
        
        # Clear routed messages
        routed_messages.clear()

        # 3. Sync Request 3: Requester has everything matching
        # It should skip both and send 0 messages
        sync_req_3 = mock_network_manager.message_protocol.create_message(
            sender_id="requester_node",
            recipient_id="group_test",
            message_type=MessageType.SYNC,
            content={
                "sync_type": "state_request",
                "requester_id": "requester_node",
                "known_proposals": {
                    "prop_1": {"status": "discussed", "vote_count": 0},
                    "prop_2": {"status": "voting", "vote_count": 1}
                }
            }
        )
        
        await NetworkManager.handle_state_sync_request(mock_network_manager, sync_req_3)
        assert len(routed_messages) == 0

    finally:
        # Restore original objects
        p2p_service._initialized = original_initialized
        p2p_service.local_node = original_local_node
        p2p_service.network_manager = original_network_manager
        agent_service.governance_manager = original_gov


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main(["-v", __file__]))
