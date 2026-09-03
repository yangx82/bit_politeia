import os
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
import pytest

from app.services.evolution_service import EvolutionService
from backend.app.p2p_community.governance import GovernanceManager, Vote, ElectionType


@pytest.fixture
def temp_evolution_service():
    temp_dir = tempfile.mkdtemp()
    service = EvolutionService(data_dir=temp_dir)
    yield service
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_ast_code_fingerprint(temp_evolution_service):
    """Verify that AST fingerprint is invariant to docstrings, variable names, and formatting."""
    service = temp_evolution_service

    code1 = '''
def calculate_adaptive_ttl(hit_rate: float) -> int:
    """Calculates adaptive TTL based on hit rate."""
    # First check boundary
    rate = max(0.0, min(1.0, float(hit_rate)))
    return int(300 + rate * 300)
'''

    code2 = '''
def get_ttl(ratio: float) -> int:
    """Completely different docstring here."""
    # Different comments
    r = max(0.0, min(1.0, float(ratio)))
    return int(300 + r * 300)
'''

    code3 = '''
def different_logic(x: int) -> int:
    return x * 42
'''

    fp1 = service._compute_ast_fingerprint(code1)
    fp2 = service._compute_ast_fingerprint(code2)
    fp3 = service._compute_ast_fingerprint(code3)

    assert fp1 == fp2, "Fingerprint must match despite variable renames, docstring and comment changes"
    assert fp1 != fp3, "Different code logic must produce different fingerprints"


def test_duplicate_proposal_detection(temp_evolution_service):
    """Verify that submitting duplicate code structure is intercepted by pre-flight audit."""
    service = temp_evolution_service

    code_original = '''
import threading

class AdaptiveCacheHint:
    def __init__(self, base_ttl=300):
        self.base_ttl = base_ttl
        self._lock = threading.Lock()

    def get_ttl(self, rate):
        with self._lock:
            return self.base_ttl + int(rate * 300)
'''

    code_duplicate_renamed = '''
import threading

class CustomCacheHintManager:
    """Renamed class and method."""
    def __init__(self, start_ttl=300):
        self.start_ttl = start_ttl
        self._lock = threading.Lock()

    def get_ttl(self, factor):
        with self._lock:
            return self.start_ttl + int(factor * 300)
'''

    # First proposal succeeds
    aip1 = service.create_aip(
        initiator_id="node_test1",
        title="Initial Cache Hint",
        description="First implementation [Scope-Corrected]",
        proposed_diff=code_original,
    )
    assert aip1.status == "draft"

    # Second proposal with duplicate AST logic is rejected by pre-flight
    is_valid, _, reason = service._pre_flight_consistency_audit(
        title="Renamed Duplicate Cache Hint",
        description="Attempt to submit same code [Scope-Corrected]",
        proposed_diff=code_duplicate_renamed,
        target_files=["backend/app/services/agent_service.py"],
    )
    assert is_valid is False
    assert "duplicate" in reason.lower()


def test_cooldown_ladder(temp_evolution_service):
    """Verify user-configured cooldown ladder: 1h -> 2h -> 6h."""
    service = temp_evolution_service

    # Strike 1 -> 1 hour
    service.record_rejection_strike(reason="Missing thread lock", aip_id="AIP-001")
    assert service.consecutive_rejections == 1
    in_cd1, msg1 = service.is_in_cooldown()
    assert in_cd1 is True
    remaining1 = (service.cooldown_until - datetime.now(timezone.utc)).total_seconds() / 3600
    assert 0.9 <= remaining1 <= 1.05

    # Strike 2 -> 2 hours
    service.record_rejection_strike(reason="Duplicate code", aip_id="AIP-002")
    assert service.consecutive_rejections == 2
    remaining2 = (service.cooldown_until - datetime.now(timezone.utc)).total_seconds() / 3600
    assert 1.9 <= remaining2 <= 2.05

    # Strike 3 -> 6 hours
    service.record_rejection_strike(reason="Description inflation", aip_id="AIP-003")
    assert service.consecutive_rejections == 3
    remaining3 = (service.cooldown_until - datetime.now(timezone.utc)).total_seconds() / 3600
    assert 5.9 <= remaining3 <= 6.05

    # Reset on approval
    service.record_approval_success()
    assert service.consecutive_rejections == 0
    in_cd_reset, _ = service.is_in_cooldown()
    assert in_cd_reset is False


def test_governance_fast_reject():
    """Verify that receiving rejections > 50% eligible voters triggers early_rejected immediately."""
    gov = GovernanceManager(node_id="node_test_gov")
    candidates = ["cand1"]
    election = gov.initiate_election("group_fast_reject", candidates)
    election.election_type = ElectionType.PROPOSAL_VOTE
    election.eligible_voters = {"v1", "v2", "v3", "v4", "v5"}

    # 1st vote: Rejection (1/5) -> Not yet fast rejected
    gov.receive_ballot(election.election_id, [Vote("v1", "cand1", approval=False, reason="Too short")])
    res1 = election.tally()
    assert res1.get("early_rejected") is False

    # 2nd vote: Rejection (2/5) -> Not yet fast rejected
    gov.receive_ballot(election.election_id, [Vote("v2", "cand1", approval=False, reason="Inflation")])
    res2 = election.tally()
    assert res2.get("early_rejected") is False

    # 3rd vote: Rejection (3/5, > 50%) -> Fast-Reject MUST trigger immediately before deadline!
    gov.receive_ballot(election.election_id, [Vote("v3", "cand1", approval=False, reason="Fake citation")])
    res3 = election.tally()
    assert res3.get("early_rejected") is True
    assert res3.get("passed") is False
    assert election.status == "early_rejected"


def test_governance_early_pass_and_aip_landing():
    """Verify that receiving approvals > 50% triggers early_passed and marks proposal as passed."""
    import json
    from backend.app.p2p_community.governance import Proposal

    gov = GovernanceManager(node_id="node_test_gov")
    candidates = ["cand1"]
    election = gov.initiate_election("group_early_pass", candidates)
    election.election_type = ElectionType.PROPOSAL_VOTE
    election.eligible_voters = {"v1", "v2", "v3", "v4", "v5"}

    # Create proposal associated with election
    prop = Proposal(
        proposal_id="prop_test_123",
        initiator_id="node_test_gov",
        group_id="group_early_pass",
        content=json.dumps({
            "type": "architecture_evolution",
            "aip": {
                "aip_id": "AIP-TEST-999",
                "title": "Test Auto Landing",
            }
        }),
        timestamp="2026-09-03T00:00:00Z",
    )
    gov.proposals[prop.proposal_id] = prop
    election.proposal_id = prop.proposal_id

    # 1st vote: Approval (1/5)
    gov.receive_ballot(election.election_id, [Vote("v1", "cand1", approval=True, reason="Great spec")])
    assert election.tally().get("early_passed") is False

    # 2nd vote: Approval (2/5)
    gov.receive_ballot(election.election_id, [Vote("v2", "cand1", approval=True, reason="Solid thread-safety")])
    assert election.tally().get("early_passed") is False

    # 3rd vote: Approval (3/5, > 50%) -> Early-Pass MUST trigger immediately!
    gov.receive_ballot(election.election_id, [Vote("v3", "cand1", approval=True, reason="Well tested")])
    res3 = election.tally()
    assert res3.get("early_passed") is True
    assert res3.get("passed") is True
    assert election.status == "early_passed"

    # Finalization moves election to finished and marks proposal as passed
    gov.finalize_expired_elections()
    assert prop.status == "passed"

