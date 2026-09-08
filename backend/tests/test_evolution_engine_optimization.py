import ast
import hashlib
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

UTC = timezone.utc

from app.p2p_community.governance import AIPProposal
from app.services.evolution_service import EvolutionService


@pytest.fixture
def temp_evo_dir():
    temp_dir = tempfile.mkdtemp(prefix="test_evo_opt_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def evo_service(temp_evo_dir):
    return EvolutionService(data_dir=temp_evo_dir)


def test_ast_syntax_error_scores_zero(evo_service):
    """Verify that truncated code or syntax errors strictly score 0.0 in draft importance ranking."""
    local_id = "node_local_5a40"

    # 1. Truncated assertion (identical to AIP-0DA9 truncation)
    truncated_assert_draft = AIPProposal(
        aip_id="AIP-TRUNC-1",
        initiator_id=local_id,
        title="Truncated Assert",
        description="Truncated diff",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff="def foo():\n    assert stats['total_entries'] ==",
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="draft",
    )
    score_1 = evo_service.calculate_draft_importance_score(truncated_assert_draft)
    assert score_1 == 0.0

    # 2. Incomplete statement
    broken_syntax_draft = AIPProposal(
        aip_id="AIP-TRUNC-2B",
        initiator_id=local_id,
        title="Broken Syntax",
        description="Broken syntax",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff="import time\ndef bar():\n    now = time.",
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="draft",
    )
    assert evo_service.calculate_draft_importance_score(broken_syntax_draft) == 0.0

    # 3. Truncated function definition (identical to AIP-5FAA truncation: 'def put(...) -> None:')
    truncated_func_draft = AIPProposal(
        aip_id="AIP-TRUNC-3",
        initiator_id=local_id,
        title="Truncated Function",
        description="Truncated at def put",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff="class Foo:\n    def put(self, key: str, val: int) -> None:",
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="draft",
    )
    score_3 = evo_service.calculate_draft_importance_score(truncated_func_draft)
    assert score_3 == 0.0

    # 4. Valid syntax draft should receive positive score
    valid_draft = AIPProposal(
        aip_id="AIP-VALID-1",
        initiator_id=local_id,
        title="Valid Atomic Helper",
        description="Complete valid atomic helper with assertion",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff="def helper(x: int) -> int:\n    assert x > 0\n    return x * 2\n",
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="draft",
    )
    score_valid = evo_service.calculate_draft_importance_score(valid_draft)
    assert score_valid > 30.0


def test_preflight_rejected_scores_zero(evo_service):
    """Verify that proposals flagged as preflight_rejected receive 0.0 score."""
    local_id = "node_local_5a40"
    rejected_draft = AIPProposal(
        aip_id="AIP-REJ-1",
        initiator_id=local_id,
        title="Preflight Rejected Proposal",
        description="Rejected by consistency audit",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff="def add(a, b): return a + b\ndef test_add(): assert add(1, 2) == 3",
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="preflight_rejected",
    )
    assert evo_service.calculate_draft_importance_score(rejected_draft) == 0.0


def test_atomic_loc_incentive_curve(evo_service):
    """Verify that atomic implementation (40-180 LOC) gets optimal score, and >300 LOC is penalized."""
    local_id = "node_local_5a40"

    # Atomic 50 lines
    atomic_lines = ["import threading", "class AtomicComponent:"]
    for i in range(48):
        atomic_lines.append(f"    def m_{i}(self): return {i}")
    atomic_lines.append("def test_comp(): assert True")
    atomic_code = "\n".join(atomic_lines)

    atomic_draft = AIPProposal(
        aip_id="AIP-ATOMIC",
        initiator_id=local_id,
        title="Atomic Component",
        description="Atomic 50 LOC",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff=atomic_code,
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="draft",
    )

    # Bloated 350 lines (high truncation risk)
    bloated_lines = ["import threading", "class BloatedComponent:"]
    for i in range(348):
        bloated_lines.append(f"    def bloated_{i}(self): return {i}")
    bloated_lines.append("def test_bloated(): assert True")
    bloated_code = "\n".join(bloated_lines)

    bloated_draft = AIPProposal(
        aip_id="AIP-BLOATED",
        initiator_id=local_id,
        title="Bloated Component",
        description="Bloated 350 LOC",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff=bloated_code,
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="draft",
    )

    score_atomic = evo_service.calculate_draft_importance_score(atomic_draft)
    score_bloated = evo_service.calculate_draft_importance_score(bloated_draft)

    # Atomic code should score higher than bloated code due to conciseness bonus vs truncation penalty
    assert score_atomic > score_bloated


def test_get_most_important_draft_rejects_truncated_candidates(evo_service):
    """Verify get_most_important_draft returns None if all candidates are truncated/invalid."""
    local_id = "node_local_5a40"

    draft_bad = AIPProposal(
        aip_id="AIP-5A40-BAD1",
        initiator_id=local_id,
        title="Broken Truncated Proposal",
        description="Truncated syntax",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff="def broken(x:\n    assert",
        status="draft",
    )
    evo_service.aips[draft_bad.aip_id] = draft_bad

    top = evo_service.get_most_important_draft(hours=24, initiator_id=local_id)
    assert top is None


def test_five_evolution_tracks_diversity(evo_service):
    """Verify that different node IDs are assigned diverse evolution tracks and rotate over time."""
    assert len(evo_service.EVOLUTION_TRACKS) == 5

    # 4 active network nodes
    nodes = [
        "node_5a40d9e6",  # Bit Plato (Local)
        "node_0da9e18d",  # Viki
        "node_5faa8871",  # Aristocles
        "node_9778108a",  # Aarron
    ]

    selected_tracks = {n: evo_service._select_evolution_track(n) for n in nodes}
    track_ids = [t["track_id"] for t in selected_tracks.values()]

    # Verify tracks have complete metadata
    for t in selected_tracks.values():
        assert "track_id" in t
        assert "name" in t
        assert "focus" in t
        assert len(t["citations"]) >= 2
        assert len(t["target_files"]) >= 1

    # Verify that not all 4 nodes are stuck on the same track (diversity guaranteed)
    unique_tracks = set(track_ids)
    assert len(unique_tracks) >= 2


def test_fetch_real_literature_inspiration_track_grounding(evo_service):
    """Verify that literature inspiration is grounded in real academic citations for each track."""
    for track in evo_service.EVOLUTION_TRACKS:
        lit = evo_service._fetch_real_literature_inspiration(track=track)
        assert lit["title"]
        assert lit["url"].startswith("http")
        assert lit["topic"]
        assert "arxiv.org" in lit["url"] or "doi.org" in lit["url"]
