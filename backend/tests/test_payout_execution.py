import asyncio
import re
from datetime import datetime, timedelta, UTC
import pytest

from app.p2p_community.economy import Ledger, Transaction
from app.p2p_community.governance import Election, ElectionType, Vote, Proposal
from app.services.agent_service import agent_service
from app.services.p2p_service import p2p_service


def parse_budget(content):
    match = re.search(r'(?:budget|funding|reward|金额|金額|预算):\s*(\d+(?:\.\d+)?)', content, re.IGNORECASE)
    return float(match.group(1)) if match else None


def test_ledger_system_bypass():
    """Verify that transactions with payer_id 'system' bypass balance checks and don't deduct system balance."""
    ledger = Ledger(storage_path=None)
    
    # Normally, system has 0 balance. Let's verify a normal payer fails with insufficient balance
    tx_normal = Transaction(
        transaction_id="tx1",
        payer_id="alice",
        payee_id="bob",
        amount=100.0,
        details="normal payment"
    )
    assert not ledger.verify_transaction(tx_normal)
    assert not ledger.record_transaction(tx_normal)
    
    # System payer should bypass balance checks
    tx_system = Transaction(
        transaction_id="tx2",
        payer_id="system",
        payee_id="bob",
        amount=250.0,
        details="system reward"
    )
    assert ledger.verify_transaction(tx_system)
    assert ledger.record_transaction(tx_system)
    
    # Payee balance should increase, and system balance shouldn't go negative (since deduction is bypassed)
    assert ledger.get_balance("bob") == 250.0
    assert ledger.get_balance("system") == 0.0


def test_proposal_budget_parsing():
    """Test regex parsing of funding/budget/rewards from proposal content."""
    assert parse_budget("budget: 250") == 250.0
    assert parse_budget("funding: 120.5") == 120.5
    assert parse_budget("reward: 50 STATER") == 50.0
    assert parse_budget("预算: 3000") == 3000.0
    assert parse_budget("金额: 500") == 500.0
    assert parse_budget("No budget here, just change a rule") is None


def test_election_payout_status_serialization():
    """Verify that payout_status is preserved during serialization and defaults to 'pending'."""
    election = Election(
        election_id="e1",
        group_id="g1",
        election_type=ElectionType.RESEARCH_EVALUATION,
        initiator_id="author1",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC) + timedelta(hours=1),
        candidates=[],
        payout_status="paid"
    )
    
    data = election.to_dict()
    assert data["payout_status"] == "paid"
    
    # Deserializing back
    restored = Election.from_dict(data)
    assert restored.payout_status == "paid"
    
    # Defaults to pending if missing
    del data["payout_status"]
    restored_default = Election.from_dict(data)
    assert restored_default.payout_status == "pending"


@pytest.mark.asyncio
async def test_agent_service_check_governance_payouts_detection():
    """Test that check_governance_proposals detects finished elections and pokes the agent."""
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

    # Setup mocked services
    original_gov = agent_service.governance_manager
    original_llm = agent_service.llm
    original_local_node = p2p_service.local_node
    
    mock_gov = MockGovernanceManager()
    agent_service.governance_manager = mock_gov
    agent_service.llm = "mock_llm"
    
    class MockNode:
        node_id = "agent_node"
    p2p_service.local_node = MockNode()

    pokes = []
    async def mock_run_loop(msg):
        pokes.append(msg)

    original_run_loop = agent_service._run_ralph_wiggum_loop
    agent_service._run_ralph_wiggum_loop = mock_run_loop

    try:
        # Create a mock finished election for research evaluation
        election = Election(
            election_id="eval_1",
            group_id="g1",
            election_type=ElectionType.RESEARCH_EVALUATION,
            initiator_id="author_1",
            start_time=datetime.now(UTC) - timedelta(hours=2),
            end_time=datetime.now(UTC) - timedelta(hours=1),
            proposal_id="proposal_1",
            eligible_voters={"voter1"},
            payout_status="pending"
        )
        # Mock tally yielding 150 stater average
        election.votes = {
            "voter1": [Vote(voter_id="voter1", reward_amount=150.0, reason="great paper")]
        }
        mock_gov.finished_elections["eval_1"] = election

        # Clear notifications
        agent_service.notified_governance_ids.discard("payout_eval_1")

        # Execute check
        await agent_service.check_governance_proposals()
        await asyncio.sleep(0.1)

        # Check that agent was poked with the payout instruction
        assert len(pokes) == 1
        poke_msg = pokes[0]
        assert "计算结算金额: 150.0" in poke_msg.content
        assert "pay_resident" in poke_msg.content
        assert "payer_id='system'" in poke_msg.content
        assert "payout_eval_1" in agent_service.notified_governance_ids

    finally:
        # Restore original state
        agent_service.governance_manager = original_gov
        agent_service.llm = original_llm
        p2p_service.local_node = original_local_node
        agent_service._run_ralph_wiggum_loop = original_run_loop


@pytest.mark.asyncio
async def test_pay_resident_system_integration():
    """Test that transfer_funds with system payer works and updates the election's payout_status."""
    class MockGovernanceManager:
        def __init__(self):
            self.node_id = "agent_node"
            self.finished_elections = {}
            self.saved = False

        def save_state(self):
            self.saved = True

    # Setup mocked services
    original_gov = agent_service.governance_manager
    original_ledger = agent_service.ledger
    
    mock_gov = MockGovernanceManager()
    agent_service.governance_manager = mock_gov
    
    # Create clean ledger
    ledger = Ledger(storage_path=None)
    agent_service.ledger = ledger

    try:
        # Create a mock finished election
        election = Election(
            election_id="elect_payout_1",
            group_id="g1",
            election_type=ElectionType.RESEARCH_EVALUATION,
            initiator_id="author_1",
            start_time=datetime.now(UTC) - timedelta(hours=2),
            end_time=datetime.now(UTC) - timedelta(hours=1),
            proposal_id="proposal_2",
            payout_status="pending"
        )
        mock_gov.finished_elections["elect_payout_1"] = election

        # Perform system transfer
        result = await agent_service.transfer_funds(
            payee_id="author_1",
            amount=500.0,
            details="System payout",
            category="REWARD",
            context_id="elect_payout_1",
            payer_id="system"
        )
        
        # Verify transaction recorded
        assert "Transfer successful" in result
        assert ledger.get_balance("author_1") == 500.0
        
        # Verify election payout_status updated to paid and saved
        assert election.payout_status == "paid"
        assert mock_gov.saved

    finally:
        agent_service.governance_manager = original_gov
        agent_service.ledger = original_ledger


if __name__ == "__main__":
    # Run test suite directly if executed as script
    import sys
    sys.exit(pytest.main(["-v", __file__]))
