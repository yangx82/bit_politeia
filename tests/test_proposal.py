import pytest

from backend.app.p2p_community.governance import ElectionType, GovernanceManager, Vote


@pytest.fixture
def governance_manager():
    return GovernanceManager(node_id="initiator_node")


def test_proposal_lifecycle(governance_manager):
    # 1. Initiate Proposal
    proposal, election = governance_manager.initiate_proposal("group_1", "Change rule A")

    assert proposal.content == "Change rule A"
    assert election.election_type == ElectionType.PROPOSAL_VOTE
    assert election.proposal_id == proposal.proposal_id

    # 2. Setup Eligible Voters
    voters = ["v1", "v2", "v3", "v4", "v5"]  # 5 voters
    election.eligible_voters = set(voters)

    # 3. Voting (Simulate 5 votes)
    # 3 Approves (Yes), 2 Rejects (No) -> >50% passed
    # Rule: Reason is mandatory

    # Valid votes
    governance_manager.receive_ballot(
        election.election_id, [Vote("v1", approval=True, reason="Good idea")]
    )
    governance_manager.receive_ballot(
        election.election_id, [Vote("v2", approval=True, reason="Support")]
    )
    governance_manager.receive_ballot(
        election.election_id, [Vote("v3", approval=True, reason="Why not")]
    )

    # Rejections
    governance_manager.receive_ballot(
        election.election_id, [Vote("v4", approval=False, reason="Bad idea")]
    )
    governance_manager.receive_ballot(
        election.election_id, [Vote("v5", approval=False, reason="Too costly")]
    )

    # 4. Tally
    result = election.tally()

    assert result["valid"] == True
    assert result["passed"] == True
    assert result["approvals"] == 3
    assert result["rejections"] == 2
    assert result["total_votes"] == 5


def test_proposal_validation_missing_reason(governance_manager):
    proposal, election = governance_manager.initiate_proposal("group_1", "Rule B")
    election.eligible_voters = {"v1"}

    # Ballot missing reason
    invalid_ballot = [Vote("v1", approval=True, reason="")]
    success = governance_manager.receive_ballot(election.election_id, invalid_ballot)
    assert success == False


def test_proposal_failed_majority(governance_manager):
    proposal, election = governance_manager.initiate_proposal("group_1", "Rule C")
    election.eligible_voters = {"v1", "v2", "v3"}

    # 1 Yes, 2 No
    governance_manager.receive_ballot(
        election.election_id, [Vote("v1", approval=True, reason="Yes")]
    )
    governance_manager.receive_ballot(
        election.election_id, [Vote("v2", approval=False, reason="No")]
    )
    governance_manager.receive_ballot(
        election.election_id, [Vote("v3", approval=False, reason="No")]
    )

    result = election.tally()
    assert result["valid"] == True
    assert result["passed"] == False
