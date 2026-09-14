"""
Test Suite: P2P Governance Rules & Evolution Quality Gate Enforcement
====================================================================
Verifies that all 5 governance specifications are enforced as hard code constraints:
1. Voting stance schema normalization and ambiguity rejection
2. Voting read-back assertion in tools
3. Initiator recusal enforcement (anti-conflict of interest)
4. QualityGate claims_coverage P0 hard blocking (anti-inflation)
5. Academic citation title mismatch P0 blocking (anti-hallucination)
6. Rejected AST fingerprint deduplication (anti-resubmission)
7. Evolution broadcast QualityGate barrier
"""

import ast
import asyncio
import os
import pytest
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
UTC = timezone.utc

from app.p2p_community.governance import GovernanceManager, Proposal, Election, ElectionType, Vote
from app.services.agent_service import AgentService
from app.services.aip_quality_gate import (
    QualityGateService,
    AsyncCitationVerifier,
    ASTConsistencyAuditor,
    Severity,
    StructuralDuplicateDetector,
)
from app.services.evolution_service import EvolutionService, AIPProposal
from app.agent.tools import cast_ballot, cast_vote


@pytest.fixture
def temp_gov_store(tmp_path):
    store_file = tmp_path / "governance_store.json"
    gm = GovernanceManager(node_id="node_plato_5a40", storage_path=str(store_file))
    return gm, store_file


@pytest.mark.asyncio
async def test_voting_schema_normalization_and_validation(temp_gov_store):
    """Verifies that vote_election normalizes various voting stance keys and rejects ambiguous inputs."""
    gm, _ = temp_gov_store
    agent_service = AgentService()
    agent_service.governance_manager = gm

    # Create a proposal where author is someone else
    prop, elec = gm.initiate_proposal(
        group_id="test_group",
        content="Test Proposal",
        eligible_voters={"node_plato_5a40", "node_viki_0da9"},
    )
    # Set initiator to someone else so plato can vote
    elec.initiator_id = "node_viki_0da9"
    elec.excluded_voters = {"node_viki_0da9"}

    # 1. Test valid variants: approval=True, position="APPROVE", decision="support"
    res1 = await agent_service.vote_election(
        elec.election_id,
        [{"position": "APPROVE", "reason": "Looks good"}]
    )
    assert "registered" in res1
    assert elec.votes["node_plato_5a40"][0].approval is True

    # 2. Clear vote for next test
    elec.votes.clear()

    # Test rejection variants: position="REJECT", approve=False, decision="no"
    res2 = await agent_service.vote_election(
        elec.election_id,
        [{"decision": "oppose", "reason": "Not ready"}]
    )
    assert "registered" in res2
    assert elec.votes["node_plato_5a40"][0].approval is False

    # 3. Clear vote for ambiguous test
    elec.votes.clear()

    # Ambiguous input must be rejected with schema error (NOT silently defaulted to False)
    res_ambig = await agent_service.vote_election(
        elec.election_id,
        [{"position": "maybe", "reason": "Uncertain"}]
    )
    assert "schema error" in res_ambig.lower() or "rejected" in res_ambig.lower()
    assert "node_plato_5a40" not in elec.votes


@pytest.mark.asyncio
async def test_initiator_recusal_enforcement(temp_gov_store):
    """Verifies that proposal initiator cannot vote on their own proposal."""
    gm, _ = temp_gov_store
    agent_service = AgentService()
    agent_service.governance_manager = gm

    # Initiate proposal by node_plato_5a40
    prop, elec = gm.initiate_proposal(
        group_id="test_group",
        content="Self-authored proposal",
        eligible_voters={"node_plato_5a40", "node_viki_0da9"},
    )
    assert "node_plato_5a40" in elec.excluded_voters

    # Attempt to vote on own proposal via agent_service
    res = await agent_service.vote_election(
        elec.election_id,
        [{"approve": True, "reason": "Voting on my own"}]
    )
    assert "recusal" in res.lower()
    assert "node_plato_5a40" not in elec.votes


@pytest.mark.asyncio
async def test_quality_gate_claims_coverage_p0_blocking(tmp_path):
    """Verifies that an inflated description with low claims coverage is blocked as P0."""
    qg = QualityGateService(data_dir=str(tmp_path))

    # Recreate the 26 LOC AdaptiveCacheHint claiming multi-tier vector architecture
    inflated_description = (
        "HierarchicalMemoryCompactor with Semantic Importance Scoring and LRU Vector Cache.\n"
        "Features:\n"
        "- (1) Three-tier hierarchical memory compaction\n"
        "- (2) MemoryRecord with numpy vector operations\n"
        "- (3) HierarchicalMemoryCompactor engine\n"
        "- (4) LRUVectorCache with cosine similarity eviction\n"
        "- (5) Dynamic context pruner\n"
        "- (6) Semantic importance scoring\n"
        "[Scope-Corrected | Atomic Enhancement: This proposal strictly implements helper logic]"
    )

    minimal_diff = (
        "class AdaptiveCacheHint:\n"
        "    def __init__(self, ttl: int = 300):\n"
        "        self.ttl = max(60, min(3600, int(ttl)))\n"
        "    def compute_ttl(self, hits: int) -> int:\n"
        "        return self.ttl if hits > 5 else self.ttl // 2\n"
    )

    report = await qg.evaluate_proposal(
        aip_id="AIP-5A40-26FA7C",
        initiator_id="node_plato_5a40",
        title="HierarchicalMemoryCompactor with LRU Vector Cache",
        description=inflated_description,
        proposed_diff=minimal_diff,
        require_signature=False,
    )

    # Must fail quality gate
    assert report.passed is False
    p0_categories = [i.category for i in report.issues if i.severity == Severity.P0]
    assert any("inflation" in cat or "consistency" in cat for cat in p0_categories)


@pytest.mark.asyncio
async def test_citation_title_mismatch_p0_blocking(tmp_path):
    """Verifies that mismatched academic citation titles trigger P0 citation_title_mismatch."""
    qg = QualityGateService(data_dir=str(tmp_path))

    # Mock the arXiv verification in AsyncCitationVerifier cache to simulate 1809.06421
    # 1809.06421 actual title is "A Flexible Design for Funding Public Goods"
    qg.citation_verifier._cache["1809.06421"] = {
        "exists": True,
        "title": "A Flexible Design for Funding Public Goods",
        "abstract": "We propose a design for funding public goods...",
        "relevant": True,
        "is_unreachable": False,
        "discipline_mismatch": False,
        "error": None,
    }

    # Description claims the paper is "Quadratic Voting: How Mechanism Design Can Radicalize Democracy"
    claimed_description = (
        "Proposes quadratic voting calculation for Bit Politeia.\n"
        "arXiv:1809.06421: Quadratic Voting: How Mechanism Design Can Radicalize Democracy\n"
    )

    valid_diff = (
        "class QuadraticVotingHelper:\n"
        "    def calculate_cost(self, votes: int) -> int:\n"
        "        return max(0, votes) ** 2\n"
    )

    report = await qg.evaluate_proposal(
        aip_id="AIP-TEST-QV",
        initiator_id="node_plato_5a40",
        title="Quadratic Voting Helper",
        description=claimed_description,
        proposed_diff=valid_diff,
        research_sources=["https://arxiv.org/abs/1809.06421 (Quadratic Voting: How Mechanism Design Can Radicalize Democracy)"],
        require_signature=False,
    )

    assert report.passed is False
    p0_categories = [i.category for i in report.issues if i.severity == Severity.P0]
    assert "citation_title_mismatch" in p0_categories


@pytest.mark.asyncio
async def test_rejected_ast_fingerprint_deduplication(tmp_path):
    """Verifies that code templates from rejected proposals cannot be resubmitted with changed IDs."""
    qg = QualityGateService(data_dir=str(tmp_path))

    code_template = (
        "class AdaptiveTTLHelper:\n"
        "    def __init__(self, base_ttl: int = 60):\n"
        "        self.base_ttl = base_ttl\n"
        "    def get_ttl(self, multiplier: int) -> int:\n"
        "        return self.base_ttl * multiplier\n"
    )

    # Register initial proposal as rejected
    qg.register_rejected_fingerprint(
        aip_id="AIP-5A40-ORIGINAL",
        code=code_template,
        reason="Rejected due to lack of tests and trivial utility"
    )

    # Attempt to submit an identical code template under a completely different AIP ID and title
    renamed_code = (
        "class DynamicTTLCalculator:\n"
        "    def __init__(self, base_ttl: int = 60):\n"
        "        self.base_ttl = base_ttl\n"
        "    def get_ttl(self, multiplier: int) -> int:\n"
        "        return self.base_ttl * multiplier\n"
    )

    report = await qg.evaluate_proposal(
        aip_id="AIP-5A40-RESUBMIT",
        initiator_id="node_plato_5a40",
        title="Dynamic TTL Calculator",
        description="Implements dynamic TTL calculation for agent memory.",
        proposed_diff=renamed_code,
        require_signature=False,
    )

    assert report.passed is False
    p0_categories = [i.category for i in report.issues if i.severity == Severity.P0]
    assert "duplicate_of_rejected_proposal" in p0_categories


@pytest.mark.asyncio
async def test_evolution_service_broadcast_blocked_by_quality_gate(tmp_path):
    """Verifies that broadcast_aip enforces QualityGate hard barrier and blocks invalid proposals."""
    evo = EvolutionService(data_dir=str(tmp_path))

    # Create a vacuous proposal
    aip = evo.create_aip(
        initiator_id="node_5a40",
        title="Empty Proposal",
        description="A completely empty proposal with no code",
        proposed_diff="   ",
    )
    assert aip.status == "preflight_rejected"

    # Attempt to broadcast
    success = await evo.broadcast_aip(aip.aip_id)
    assert success is False
    assert aip.status == "preflight_rejected"


@pytest.mark.asyncio
async def test_tools_read_back_verification(temp_gov_store):
    """Verifies that cast_vote and cast_ballot tools perform automated read-back assertions."""
    gm, _ = temp_gov_store
    from app.services.agent_service import agent_service
    agent_service.governance_manager = gm

    prop, elec = gm.initiate_proposal(
        group_id="test_group",
        content="Test Proposal for Tools",
        eligible_voters={"node_plato_5a40", "node_other"},
    )
    elec.initiator_id = "node_other"
    elec.excluded_voters = {"node_other"}

    # Test cast_vote tool
    res_vote = await cast_vote.ainvoke({"election_id": elec.election_id, "approval": True, "reason": "Support through tool"})
    assert "[VERIFIED:" in res_vote
    assert "position=APPROVE" in res_vote

    # Reset votes for cast_ballot tool
    elec.votes.clear()

    # Test cast_ballot tool with JSON
    res_ballot = await cast_ballot.ainvoke({"election_id": elec.election_id, "ballot_json": '[{"position": "REJECT", "reason": "Oppose through tool"}]'})
    assert "[VERIFIED:" in res_ballot
    assert "position=REJECT" in res_ballot
