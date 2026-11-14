"""
Test Suite: 5-Layer Autonomous Evolution Engine Quality Defense
===============================================================
Verifies the research-backed 5-layer quality upgrade for Bit Politeia's
Autonomous Evolution Engine:
1. Layer 1: RepoSymbolInspector & ASTConsistencyAuditor deep semantic/algorithmic checks
2. Layer 2: MAP-Elites / AlphaEvolve niche saturation & AST 3-gram shingle fuzzy deduplication
3. Layer 3: CodeT dual-blind specification & mathematical invariants contract
4. Layer 4: Meta TestGen-LLM / MuTAP AST micro-mutation sandbox gate
5. Layer 5: Real-world regression tests against the 3 flawed archived proposals in
   backend/data/passed_aips/ (AIP-0DA9-26D629, AIP-0DA9-DABA8D, AIP-0DA9-1A7DBE)
"""

import json
import os
import sys
from pathlib import Path

import pytest

_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path or sys.path[0] != _backend_dir:
    sys.path.insert(0, _backend_dir)

from app.services.aip_quality_gate import (
    ASTConsistencyAuditor,
    ASTMutationTester,
    QualityGateService,
    RepoSymbolInspector,
    Severity,
    StructuralDuplicateDetector,
)
from app.services.evolution_service import EvolutionService


NEGATIVE_AIPS_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "negative_aips"


def _load_archived_aip(filename: str) -> dict:
    filepath = NEGATIVE_AIPS_FIXTURES_DIR / filename
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_archived_aip_26d629_caught_by_quality_gate(tmp_path):
    """
    AIP-0DA9-26D629 (QuadraticVotingHelper with Reputation-Weighted Tally Verification):
    - Redefines existing class QuadraticVotingHelper already present in
      target_files=['backend/app/p2p_community/governance.py'] (repo_symbol_collision)
    - Calls time.time() inside calculate_vote_weight without a deterministic reference_time
      parameter, breaking consensus tally determinism across nodes (non_deterministic_audit)
    """
    data = _load_archived_aip("AIP-0DA9-26D629.json")
    qg = QualityGateService(data_dir=str(tmp_path))

    # Pre-warm citation cache so test runs offline deterministically
    qg.citation_verifier._cache["1809.06421"] = {
        "exists": True,
        "title": "A Flexible Design for Funding Public Goods",
        "abstract": "Quadratic funding mechanism for public goods.",
        "relevant": True,
        "is_unreachable": False,
        "discipline_mismatch": False,
        "error": None,
    }

    report = await qg.evaluate_proposal(
        aip_id=data["aip_id"],
        initiator_id=data["initiator_id"],
        title=data["title"],
        description=data["description"],
        proposed_diff=data["proposed_diff"],
        research_sources=data["research_sources"],
        require_signature=False,
        target_files=data["target_files"],
    )

    assert report.passed is False
    p0_categories = {i.category for i in report.issues if i.severity == Severity.P0}
    assert "repo_symbol_collision" in p0_categories
    assert "non_deterministic_audit" in p0_categories


@pytest.mark.asyncio
async def test_archived_aip_daba8d_caught_by_quality_gate(tmp_path):
    """
    AIP-0DA9-DABA8D (QuadraticVotingHelper & ProposalTallyAuditor):
    - Redefines existing classes (QuadraticVotingHelper, ProposalTallyAuditor) in
      target_files=['backend/app/p2p_community/governance.py'] (repo_symbol_collision)
    - Initializes self._lock in QuadraticVotingHelper.__init__ with zero mutable state
      (stateless_lock_theatre)
    - Sums duplicate voter_ids in verify_tally via Counter += weight instead of deduplicating
      ballots per voter (tally_sybil_duplicate_ballot)
    """
    data = _load_archived_aip("AIP-0DA9-DABA8D.json")
    qg = QualityGateService(data_dir=str(tmp_path))

    qg.citation_verifier._cache["1809.06421"] = {
        "exists": True,
        "title": "A Flexible Design for Funding Public Goods",
        "abstract": "Quadratic funding mechanism for public goods.",
        "relevant": True,
        "is_unreachable": False,
        "discipline_mismatch": False,
        "error": None,
    }

    report = await qg.evaluate_proposal(
        aip_id=data["aip_id"],
        initiator_id=data["initiator_id"],
        title=data["title"],
        description=data["description"],
        proposed_diff=data["proposed_diff"],
        research_sources=data["research_sources"],
        require_signature=False,
        target_files=data["target_files"],
    )

    assert report.passed is False
    p0_categories = {i.category for i in report.issues if i.severity == Severity.P0}
    assert "repo_symbol_collision" in p0_categories
    assert "stateless_lock_theatre" in p0_categories
    assert "tally_sybil_duplicate_ballot" in p0_categories


@pytest.mark.asyncio
async def test_archived_aip_1a7dbe_caught_by_quality_gate_and_mutation_tester(tmp_path):
    """
    AIP-0DA9-1A7DBE (QuadraticVotingHelper with Sybil-Resistant Subsidy Pool):
    - Violates CLR Quadratic Funding formula by summing raw contributions per project before
      sqrt/squaring (mathematical_fidelity_violation)
    - Redefines QuadraticVotingHelper in target_files=['backend/app/p2p_community/governance.py']
      (repo_symbol_collision)
    - Silently clamps negative contributions via max(0.0, float(amount)) instead of raising
      ValueError (silent_negative_clamping)
    - Defines 4 test_* functions but NEVER invokes them at top-level or in __main__
      (uninvoked_test_suite)
    """
    data = _load_archived_aip("AIP-0DA9-1A7DBE.json")
    qg = QualityGateService(data_dir=str(tmp_path))

    qg.citation_verifier._cache["1809.06421"] = {
        "exists": True,
        "title": "A Flexible Design for Funding Public Goods",
        "abstract": "Quadratic funding mechanism for public goods.",
        "relevant": True,
        "is_unreachable": False,
        "discipline_mismatch": False,
        "error": None,
    }

    report = await qg.evaluate_proposal(
        aip_id=data["aip_id"],
        initiator_id=data["initiator_id"],
        title=data["title"],
        description=data["description"],
        proposed_diff=data["proposed_diff"],
        research_sources=data["research_sources"],
        require_signature=False,
        target_files=data["target_files"],
    )

    assert report.passed is False
    p0_categories = {i.category for i in report.issues if i.severity == Severity.P0}
    assert "mathematical_fidelity_violation" in p0_categories
    assert "repo_symbol_collision" in p0_categories
    assert "silent_negative_clamping" in p0_categories
    assert "uninvoked_test_suite" in p0_categories

    # Also verify ASTMutationTester rejects uninvoked test suites in sandbox verification
    mut_res = ASTMutationTester.run_in_process_verification(data["proposed_diff"])
    assert mut_res["passed"] is False
    assert "test_quadratic_voting_helper" in mut_res["uninvoked_tests"]


def test_ast_mutation_tester_kills_mutants_and_rejects_tautological_tests():
    """
    Verifies Layer 4 (Meta TestGen-LLM / MuTAP AST Micro-Mutation Sandbox Gate):
    - Rejects scripts with tautological tests (e.g., assert True) that fail to kill AST mutants
    - Passes scripts with strong assertions that kill >= 50% of AST mutants and invoke their tests
    """
    weak_code = (
        "def compute_quadratic_cost(votes: int) -> int:\n"
        "    if votes < 0:\n"
        "        raise ValueError('negative votes')\n"
        "    return votes * votes + 2 * votes\n\n"
        "def test_weak():\n"
        "    compute_quadratic_cost(3)\n"
        "    assert True\n\n"
        "test_weak()\n"
    )
    weak_res = ASTMutationTester.run_in_process_verification(weak_code, min_kill_rate=0.50)
    assert weak_res["passed"] is False
    assert weak_res["mutation_kill_rate"] < 0.50

    strong_code = (
        "def compute_quadratic_cost(votes: int) -> int:\n"
        "    if votes < 0:\n"
        "        raise ValueError('negative votes')\n"
        "    return votes * votes + 2 * votes\n\n"
        "def test_strong():\n"
        "    assert compute_quadratic_cost(0) == 0\n"
        "    assert compute_quadratic_cost(3) == 15\n"
        "    assert compute_quadratic_cost(5) == 35\n"
        "    try:\n"
        "        compute_quadratic_cost(-1)\n"
        "        assert False\n"
        "    except ValueError:\n"
        "        pass\n\n"
        "if __name__ == '__main__':\n"
        "    test_strong()\n"
    )
    strong_res = ASTMutationTester.run_in_process_verification(strong_code, min_kill_rate=0.50)
    assert strong_res["passed"] is True
    assert strong_res["mutation_kill_rate"] >= 0.75
    assert "test_strong" in strong_res["tests_executed"]


def test_fuzzy_ast_shingle_deduplication_and_track_niche_rotation(tmp_path):
    """
    Verifies Layer 2 (MAP-Elites / AlphaEvolve Niche Saturation & Fuzzy AST Shingle Deduplication):
    - Near-duplicate proposals with minor variable/method tweaks are caught by check_fuzzy_duplicate
    - Consecutive same-day calls with advance_step=True rotate across different evolution tracks
    """
    code_v1 = (
        "import math\n"
        "class SybilReputationWeigher:\n"
        "    def __init__(self, half_life: float = 86400.0):\n"
        "        self.half_life = half_life\n"
        "    def compute_weight(self, stake: float, age: float, ref_time: float) -> float:\n"
        "        if stake < 0:\n"
        "            raise ValueError('Negative stake')\n"
        "        elapsed = max(0.0, ref_time - age)\n"
        "        decay = math.exp(-math.log(2.0) * elapsed / self.half_life)\n"
        "        return math.sqrt(stake) * decay\n"
    )
    code_v2_near_dup = (
        "import math\n"
        "class GovernanceWeightCalculator:\n"
        "    def __init__(self, decay_window: float = 3600.0):\n"
        "        self.decay_window = decay_window\n"
        "    def calc_voter_score(self, tokens: float, ts: float, now_ts: float) -> float:\n"
        "        if tokens < 0:\n"
        "            raise ValueError('Invalid tokens')\n"
        "        delta = max(0.0, now_ts - ts)\n"
        "        factor = math.exp(-math.log(2.0) * delta / self.decay_window)\n"
        "        return math.sqrt(tokens) * factor\n"
    )

    is_dup, matched_id, sim = StructuralDuplicateDetector.check_fuzzy_duplicate(
        code_v2_near_dup,
        known_codes={"AIP-ORIG-1": code_v1},
        threshold=0.72,
    )
    assert is_dup is True
    assert matched_id == "AIP-ORIG-1"
    assert sim >= 0.72

    # Track rotation & niche saturation test
    evo = EvolutionService(data_dir=str(tmp_path / "evo"))
    visited_tracks = []
    for _ in range(5):
        t = evo._select_evolution_track(node_id="node_0da9e18d", advance_step=True)
        visited_tracks.append(t["track_id"])

    # Advancing 5 times must explore all 5 tracks instead of getting stuck on Track 5 all day
    assert len(set(visited_tracks)) == 5
