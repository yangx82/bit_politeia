import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

UTC = timezone.utc

from app.p2p_community.governance import (
    Election,
    ElectionType,
    GovernanceManager,
    Proposal,
    Vote,
)


@pytest.fixture
def governance_manager():
    return GovernanceManager(node_id="node_author", storage_path="backend/data/test_gov_tmp.json")


def test_initiator_recusal_and_self_voting_prevention(governance_manager):
    """Ensure proposal author is recused from voting on their own proposal."""
    proposal, election = governance_manager.initiate_proposal(
        group_id="group_test",
        content="Test Proposal with Initiator Recusal",
        eligible_voters={"node_author", "voter_b", "voter_c", "voter_d"},
    )

    # Initiator must be in excluded_voters
    assert "node_author" in election.excluded_voters
    assert election.effective_voters_count == 3
    assert election.network_voters_count == 4

    # Proposer tries to vote on own proposal -> must be rejected
    ballot = [Vote(voter_id="node_author", approval=True, reason="I love my own proposal")]
    success = governance_manager.receive_ballot(election.election_id, ballot)
    assert success is False
    assert "node_author" not in election.votes


def test_dual_participation_rate_and_early_pass(governance_manager):
    """
    Verify exact mathematical calculation for AIP-5FAA-A9EB73 scenario:
    4 network nodes, 1 author recused -> 3 effective voters.
    2 approvals -> effective turnout 2/3 (66.7%), network turnout 2/4 (50%).
    Triggers early pass (2 > 1.5).
    """
    proposal, election = governance_manager.initiate_proposal(
        group_id="group_test",
        content="ToolExecutionPipeline",
        eligible_voters={"node_author", "node_b", "node_c", "node_d"},
    )

    # Voter B votes Approve
    vote_b = [Vote(voter_id="node_b", approval=True, reason="Passes audit")]
    assert governance_manager.receive_ballot(election.election_id, vote_b) is True

    # Voter C votes Approve
    vote_c = [Vote(voter_id="node_c", approval=True, reason="Passes tests")]
    assert governance_manager.receive_ballot(election.election_id, vote_c) is True

    tally = election.tally()
    # 2 Approvals out of 3 effective voters
    assert round(tally["participation_rate"], 4) == round(2 / 3, 4)
    assert round(tally["network_participation_rate"], 4) == round(2 / 4, 4)
    assert tally["effective_voters_count"] == 3
    assert tally["network_voters_count"] == 4
    assert tally["approvals"] == 2
    assert tally["rejections"] == 0
    # 2 > 3/2 (1.5) triggers early pass
    assert tally["early_passed"] is True
    assert tally["passed"] is True


def test_remote_p2p_election_auto_healing(governance_manager):
    """
    Verify that when a remote peer broadcasts an election missing local node (like Bit Plato),
    ingestion auto-heals and includes local node and network nodes in eligible_voters.
    """
    # Mock remote election that omitted node_author
    remote_election_data = {
        "election_id": "remote_elec_123",
        "group_id": "group_shared",
        "election_type": "proposal_vote",
        "initiator_id": "remote_peer_1",
        "start_time": datetime.now(UTC).isoformat(),
        "end_time": (datetime.now(UTC) + timedelta(minutes=60)).isoformat(),
        "eligible_voters": ["remote_peer_1", "remote_peer_2"],  # Omitted node_author!
        "excluded_voters": [],
        "status": "active",
        "votes": {},
    }

    proposal_data = {
        "proposal_id": "prop_remote_1",
        "initiator_id": "remote_peer_1",
        "group_id": "group_shared",
        "content": "Remote Feature Proposal",
        "timestamp": datetime.now(UTC).isoformat(),
        "scope": "group",
        "status": "discussed",
    }

    # Ingest event
    success = governance_manager.receive_p2p_event(
        "proposal",
        {"proposal": proposal_data, "election": remote_election_data},
    )
    assert success is True

    ingested_election = governance_manager.active_elections.get("remote_elec_123")
    assert ingested_election is not None
    # Local node must be auto-healed into eligible_voters
    assert "node_author" in ingested_election.eligible_voters
    # Remote initiator must be recused in excluded_voters
    assert "remote_peer_1" in ingested_election.excluded_voters


@pytest.mark.asyncio
async def test_agent_service_cast_vote_blocks_recused_author():
    """Verify that agent_service.cast_vote rejects voting if voter is in excluded_voters."""
    from backend.app.services.agent_service import agent_service
    from backend.app.services.p2p_service import p2p_service

    # Setup mock local node
    mock_local = MagicMock()
    mock_local.node_id = "author_xyz"
    p2p_service.local_node = mock_local

    # Ensure governance_manager is initialized
    if not agent_service.governance_manager:
        agent_service.governance_manager = GovernanceManager(
            node_id="author_xyz", storage_path="backend/data/test_gov_tmp_agent.json"
        )

    # Create dummy election where author_xyz is excluded
    mock_election = Election(
        election_id="elec_recusal_test",
        group_id="grp_1",
        election_type=ElectionType.PROPOSAL_VOTE,
        initiator_id="author_xyz",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC) + timedelta(minutes=60),
        eligible_voters={"author_xyz", "voter_1"},
        excluded_voters={"author_xyz"},
    )
    agent_service.governance_manager.active_elections["elec_recusal_test"] = mock_election

    res = await agent_service.cast_vote("elec_recusal_test", approval=True, reason="Self vote")
    assert res["status"] == "failed"
    assert "Conflict of Interest" in res["reason"]
