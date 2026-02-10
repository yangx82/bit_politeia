import pytest
from datetime import datetime, timedelta
from backend.app.p2p_community.governance import GovernanceManager, Vote, ElectionType, Election

@pytest.fixture
def governance_manager():
    return GovernanceManager(node_id="initiator_node")

def test_election_lifecycle(governance_manager):
    # 1. Start Election
    candidates = ["cand1", "cand2"]
    election = governance_manager.initiate_election("group_1", candidates)
    
    assert election.status == "active"
    assert election.election_type == ElectionType.CORE_NODE
    
    # 2. Setup Eligible Voters (Mocking group set)
    voters = ["voter1", "voter2", "voter3", "voter4", "voter5"] # 5 voters
    election.eligible_voters = set(voters)
    
    # 3. Voting
    # Submit ballots (List[Vote])
    governance_manager.receive_ballot(election.election_id, [Vote("voter1", "cand1", approval=True)])
    governance_manager.receive_ballot(election.election_id, [Vote("voter2", "cand1", approval=True)])
    governance_manager.receive_ballot(election.election_id, [Vote("voter3", "cand1", approval=True)])
    governance_manager.receive_ballot(election.election_id, [Vote("voter4", "cand2", approval=True)])
    governance_manager.receive_ballot(election.election_id, [Vote("voter5", "cand2", approval=True)])
    
    # 4. Tally
    result = election.tally()
    
    assert result["valid"] == True
    assert "cand1" in result["winners"]
    assert "cand2" not in result["winners"]
    assert result["counts"]["cand1"] == 3

def test_quorum_failure(governance_manager):
    candidates = ["cand1"]
    election = governance_manager.initiate_election("group_1", candidates)
    election.eligible_voters = {"v1", "v2", "v3", "v4", "v5"}
    
    # Only 3 votes (60%)
    governance_manager.receive_ballot(election.election_id, [Vote("v1", "cand1", approval=True)])
    governance_manager.receive_ballot(election.election_id, [Vote("v2", "cand1", approval=True)])
    governance_manager.receive_ballot(election.election_id, [Vote("v3", "cand1", approval=True)])
    
    result = election.tally()
    assert result["valid"] == False
    assert "Quorum" in result["reason"]

def test_ballot_validation(governance_manager):
    candidates = ["cand1", "cand2"]
    election = governance_manager.initiate_election("group_v", candidates)
    election.target_positions = 1
    election.eligible_voters = {"v1"}

    # Ballot with too many approvals (2 > 1)
    invalid_ballot = [
        Vote("v1", "cand1", approval=True),
        Vote("v1", "cand2", approval=True)
    ]
    success = governance_manager.receive_ballot(election.election_id, invalid_ballot)
    assert success == False # Should reject

    # Valid ballot (1 approval)
    valid_ballot = [
        Vote("v1", "cand1", approval=True),
        Vote("v1", "cand2", approval=False)
    ]
    success = governance_manager.receive_ballot(election.election_id, valid_ballot)
    assert success == True

def test_majority_rule(governance_manager):
    # Test that winner must have > 50%
    candidates = ["cand1", "cand2"]
    election = governance_manager.initiate_election("group_2", candidates)
    # 5 voters. 5 votes cast.
    election.eligible_voters = {"v1", "v2", "v3", "v4", "v5"}
    
    governance_manager.receive_ballot(election.election_id, [Vote("v1", "cand1")])
    governance_manager.receive_ballot(election.election_id, [Vote("v2", "cand1")])
    governance_manager.receive_ballot(election.election_id, [Vote("v3", "cand2")])
    governance_manager.receive_ballot(election.election_id, [Vote("v4", "cand2")])
    # v5 abstains/rejects all
    governance_manager.receive_ballot(election.election_id, [Vote("v5", "cand1", approval=False)])
    
    result = election.tally()
    assert result["valid"] == True # Quorum (5/5)
    # Threshold 5/2 = 2.5.
    # cand1: 2. cand2: 2.
    # Neither > 2.5.
    assert len(result["winners"]) == 0
