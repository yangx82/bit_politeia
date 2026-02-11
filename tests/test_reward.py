import pytest
from backend.app.p2p_community.governance import GovernanceManager, Vote, ElectionType, Proposal

@pytest.fixture
def governance_manager():
    return GovernanceManager(node_id="author_node")

def test_research_publication(governance_manager):
    # 1. Publish Research
    proposal, election = governance_manager.initiate_research_publication(
        group_id="group_research", 
        content="Quantum Consensus", 
        pdf_hash="hash_123"
    )
    
    assert proposal.pdf_hash == "hash_123"
    assert election.election_type == ElectionType.RESEARCH_EVALUATION
    assert election.proposal_id == proposal.proposal_id
    assert "author_node" in election.excluded_voters

def test_research_evaluation_quorum(governance_manager):
    proposal, election = governance_manager.initiate_research_publication("g1", "Paper", "h1")
    
    # Setup Voters: Author + 5 others
    # Total members = 6. 
    # Eligible = {v1...v5, author}
    # Excluded = {author}
    # Effective voters = 5
    # Quorum > 0.8 * 5 = 4 votes needed.
    
    election.eligible_voters = {"v1", "v2", "v3", "v4", "v5", "author_node"}
    
    # 1. Author tries to vote -> Should fail/be rejected (or logged and ignored, receive_ballot returns False)
    success = governance_manager.receive_ballot(election.election_id, [Vote("author_node", reward_amount=100)])
    assert success == False
    
    # 2. Others vote
    governance_manager.receive_ballot(election.election_id, [Vote("v1", reward_amount=100.0, reason="Good")])
    governance_manager.receive_ballot(election.election_id, [Vote("v2", reward_amount=200.0, reason="Excellent")])
    governance_manager.receive_ballot(election.election_id, [Vote("v3", reward_amount=100.0, reason="Okay")])
    governance_manager.receive_ballot(election.election_id, [Vote("v4", reward_amount=0.0, reason="Bad")])
    
    # 4 votes out of 5 effective. 4/5 = 0.8. 
    # Logic in code is `> 0.8`. So 0.8 is NOT met.
    # Need 5/5? 
    # Wait, `participation_rate > 0.8`. 4/5 = 0.8. 0.8 > 0.8 is False.
    # So if I only cast 4 votes, it should fail quorum.
    
    result = election.tally()
    assert result["valid"] == False
    
    # Cast 5th vote
    governance_manager.receive_ballot(election.election_id, [Vote("v5", reward_amount=100.0, reason="Pass")])
    
    result = election.tally()
    assert result["valid"] == True
    assert result["total_evaluators"] == 5
    # Avg: (100+200+100+0+100)/5 = 500/5 = 100.0
    assert result["average_amount"] == 100.0

def test_negative_reward_validation(governance_manager):
    proposal, election = governance_manager.initiate_research_publication("g1", "P", "h")
    election.eligible_voters = {"v1"}
    
    # Negative amount
    success = governance_manager.receive_ballot(election.election_id, [Vote("v1", reward_amount=-50, reason="Bad")])
    assert success == False

def test_missing_reason_validation(governance_manager):
    proposal, election = governance_manager.initiate_research_publication("g1", "P", "h")
    election.eligible_voters = {"v1"}
    
    # Missing reason
    success = governance_manager.receive_ballot(election.election_id, [Vote("v1", reward_amount=50, reason="")])
    assert success == False
