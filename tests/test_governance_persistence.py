import logging
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.p2p_community.governance import GovernanceManager, Vote

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_DB = "test_governance_store.json"


def test_persistence():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    print(f"\n[Test] Initializing Manager with {TEST_DB}...")
    manager = GovernanceManager("node_test_1", storage_path=TEST_DB)

    # 1. Create Proposal
    print("[Test] Creating Proposal...")
    proposal, election = manager.initiate_proposal(
        group_id="group_1", content="Test Proposal for Persistence", duration_minutes=30
    )

    print(f"Created Proposal: {proposal.proposal_id}")
    print(f"Created Election: {election.election_id}")

    # 2. Vote
    print("[Test] Casting Vote...")
    vote = Vote(voter_id="voter_1", approval=True, reason="Looks good", timestamp=datetime.now())
    success = manager.receive_ballot(election.election_id, [vote])
    assert success, "Vote failed"
    print("Vote cast successfully.")

    # Verify state in memory
    assert len(manager.proposals) == 1
    assert len(manager.active_elections) == 1
    assert len(list(manager.active_elections.values())[0].votes) == 1

    # 3. Simulate Restart
    print("[Test] Simulating Restart (Reloading from disk)...")
    del manager

    new_manager = GovernanceManager("node_test_1", storage_path=TEST_DB)

    # Verify state recovered
    assert len(new_manager.proposals) == 1
    p = list(new_manager.proposals.values())[0]
    assert p.content == "Test Proposal for Persistence"

    assert len(new_manager.active_elections) == 1
    e = list(new_manager.active_elections.values())[0]
    assert e.election_id == election.election_id
    assert len(e.votes) == 1
    assert "voter_1" in e.votes

    print("[PASS] Persistence Verified!")

    # Cleanup
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


if __name__ == "__main__":
    test_persistence()
