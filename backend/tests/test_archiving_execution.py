import asyncio
from datetime import datetime, timedelta, UTC
import pytest

from app.p2p_community.economy import Ledger, Transaction
from app.p2p_community.governance import Election, ElectionType, Vote, Proposal
from app.p2p_community.blockchain import ArchiveManager
from app.models.schemas import Message
from app.services.agent_service import agent_service
from app.services.p2p_service import p2p_service


@pytest.mark.asyncio
async def test_archiving_gathering_logic():
    """Verify that messages (chats/discussions), proposals, votes, and transactions are gathered and hashed."""
    
    # 1. Mock Governance Manager
    class MockGovernanceManager:
        def __init__(self):
            self.node_id = "agent_node"
            self.proposals = {}
            self.active_elections = {}
            self.finished_elections = {}
            self.saved = False

        def finalize_expired_elections(self):
            return []

        def save_state(self):
            self.saved = True

    # 2. Mock Ledger
    class MockLedger:
        def __init__(self):
            self.transactions = []

    # 3. Setup mock services
    original_gov = agent_service.governance_manager
    original_ledger = agent_service.ledger
    original_archive = agent_service.archive_manager
    original_history = agent_service.history
    
    mock_gov = MockGovernanceManager()
    mock_ledger = MockLedger()
    mock_archive = ArchiveManager("test_node")
    
    # Reset block chain data to Genesis for clean test
    mock_archive.chain.chain = mock_archive.chain.chain[:1]
    last_block = mock_archive.chain.latest_block
    last_ts = datetime.fromtimestamp(last_block.timestamp, tz=UTC)

    agent_service.governance_manager = mock_gov
    agent_service.ledger = mock_ledger
    agent_service.archive_manager = mock_archive
    agent_service.history = []

    try:
        # --- A. Mock Messages ---
        # Chat 1: P2P chat (should be archived)
        msg_p2p_chat = Message(
            id="msg_p2p_1",
            content="Hello peer, let's discuss research",
            sender="peer_1",
            timestamp=datetime.now(UTC),
            session_id="peer_1",
            metadata={"is_p2p": True}
        )
        # Chat 2: Group chat/discussion (should be archived)
        msg_group_chat = Message(
            id="msg_group_1",
            content="Who approves budget proposal 1?",
            sender="peer_2",
            timestamp=datetime.now(UTC),
            session_id="group_1",
            metadata={"is_p2p": True}
        )
        # Chat 3: Resident conversation (should NOT be archived)
        msg_resident = Message(
            id="msg_res_1",
            content="Human owner instruction",
            sender="user",
            timestamp=datetime.now(UTC),
            session_id="resident"
        )
        # Chat 4: System internal poke message (should NOT be archived)
        msg_system = Message(
            id="msg_sys_1",
            content="Internal task alert",
            sender="system",
            timestamp=datetime.now(UTC),
            session_id="resident"
        )

        agent_service.history = [msg_p2p_chat, msg_group_chat, msg_resident, msg_system]

        # --- B. Mock Proposals (Discussions & Research) ---
        proposal_gov = Proposal(
            proposal_id="proposal_1",
            initiator_id="peer_1",
            group_id="group_1",
            content="funding: 200 stater for server",
            timestamp=datetime.now(UTC)
        )
        proposal_res = Proposal(
            proposal_id="research_1",
            initiator_id="author_1",
            group_id="group_1",
            content="Academic paper on P2P",
            timestamp=datetime.now(UTC),
            pdf_hash="hash123"
        )
        # Old Proposal (should NOT be archived)
        proposal_old = Proposal(
            proposal_id="old_proposal_1",
            initiator_id="peer_1",
            group_id="group_1",
            content="very old discussion",
            timestamp=last_ts - timedelta(hours=5)
        )

        mock_gov.proposals = {
            "proposal_1": proposal_gov,
            "research_1": proposal_res,
            "old_proposal_1": proposal_old
        }

        # --- C. Mock Votes ---
        election = Election(
            election_id="elect_1",
            group_id="group_1",
            election_type=ElectionType.PROPOSAL_VOTE,
            initiator_id="peer_1",
            start_time=datetime.now(UTC) - timedelta(hours=2),
            end_time=datetime.now(UTC) - timedelta(hours=1),
            eligible_voters={"voter1", "voter2"},
            proposal_id="proposal_1",
            payout_status="pending"
        )
        vote_new = Vote(voter_id="voter1", approval=True, timestamp=datetime.now(UTC))
        vote_old = Vote(voter_id="voter2", approval=False, timestamp=last_ts - timedelta(hours=5))
        election.votes = {
            "voter1": [vote_new],
            "voter2": [vote_old]
        }
        mock_gov.finished_elections["elect_1"] = election

        # --- D. Mock Transactions ---
        tx_reward = Transaction(
            transaction_id="tx_1",
            payer_id="system",
            payee_id="author_1",
            amount=150.0,
            details="Research reward payout",
            category="REWARD",
            context_id="research_1",
            timestamp=datetime.now(UTC)
        )
        tx_old = Transaction(
            transaction_id="tx_2",
            payer_id="alice",
            payee_id="bob",
            amount=50.0,
            details="old transfer",
            timestamp=last_ts - timedelta(hours=5)
        )
        mock_ledger.transactions = [tx_reward, tx_old]

        # --- Execute Archiving ---
        result = await agent_service.run_archiving()
        
        # --- Verifications ---
        assert "SUCCESS" in result
        
        # Verify block was created
        assert len(mock_archive.chain.chain) == 2
        latest_block = mock_archive.chain.latest_block
        assert latest_block.index == 1
        
        # Check summary metrics
        summary = latest_block.data
        assert summary["message_count"] == 2      # P2P and Group chats
        assert summary["research_count"] == 2     # Research and Governance proposals since last_ts
        assert summary["vote_count"] == 1         # Only vote_new
        assert summary["tx_count"] == 1           # Only tx_reward
        
        # Verify hashes are present
        assert summary["messages_hash"] != ""
        assert summary["research_hash"] != ""
        assert summary["votes_hash"] != ""
        assert summary["tx_hash"] != ""

    finally:
        # Restore original state
        agent_service.governance_manager = original_gov
        agent_service.ledger = original_ledger
        agent_service.archive_manager = original_archive
        agent_service.history = original_history


if __name__ == "__main__":
    # Run test suite directly if executed as script
    import sys
    sys.exit(pytest.main(["-v", __file__]))
