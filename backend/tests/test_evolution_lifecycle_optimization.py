import os
import shutil
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

UTC = timezone.utc

from app.p2p_community.governance import AIPProposal, Vote
from app.services.evolution_service import EvolutionService


@pytest.fixture
def temp_evo_dir():
    temp_dir = tempfile.mkdtemp(prefix="test_evo_lifecycle_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def evo_service(temp_evo_dir):
    return EvolutionService(data_dir=temp_evo_dir)


def test_aip_proposal_failure_count_serialization():
    """Verify failure_count serialization and backward compatibility."""
    # Default is 0
    aip = AIPProposal(
        aip_id="AIP-TEST-1",
        initiator_id="node_1234",
        title="Test Proposal",
        description="Test desc",
    )
    assert aip.failure_count == 0

    # Serialization
    d = aip.to_dict()
    assert "failure_count" in d
    assert d["failure_count"] == 0

    # Deserialization with failure_count
    d["failure_count"] = 3
    restored = AIPProposal.from_dict(d)
    assert restored.failure_count == 3

    # Backward compatibility: legacy dict without failure_count defaults to 0
    legacy_dict = {
        "aip_id": "AIP-LEGACY",
        "initiator_id": "node_legacy",
        "title": "Legacy Proposal",
        "description": "Legacy desc",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    legacy_aip = AIPProposal.from_dict(legacy_dict)
    assert legacy_aip.failure_count == 0


def test_abandoned_proposal_scores_zero_and_excluded_from_drafts(evo_service):
    """Verify that abandoned proposals receive 0.0 score and are never selected for group discussion."""
    local_id = "node_local_5a40"

    abandoned_aip = AIPProposal(
        aip_id="AIP-ABANDONED-1",
        initiator_id=local_id,
        title="Dead-End Proposal",
        description="Failed 2 evolution cycles",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff="def helper(x: int) -> int:\n    assert x > 0\n    return x * 2\n",
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="abandoned",
        failure_count=2,
    )
    evo_service.aips[abandoned_aip.aip_id] = abandoned_aip

    # Importance score should be 0.0
    score = evo_service.calculate_draft_importance_score(abandoned_aip)
    assert score == 0.0

    # get_most_important_draft should return None if only abandoned drafts exist
    top = evo_service.get_most_important_draft(hours=24, initiator_id=local_id)
    assert top is None


@pytest.mark.asyncio
async def test_run_aip_evolution_loop_transitions_to_stalled_then_abandoned(evo_service):
    """Verify that failing all rounds transitions to 'stalled' on cycle 1, and 'abandoned' on cycle 2."""
    aip = AIPProposal(
        aip_id="AIP-CYCLE-TEST",
        initiator_id="node_5a40",
        title="Cycle Test Proposal",
        description="Testing failure transitions",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff="def failing_code(): assert False\n",
        status="draft",
        failure_count=0,
    )
    evo_service.aips[aip.aip_id] = aip

    # Mock audit_aip to always reject
    mock_audit = AsyncMock(return_value=Vote(voter_id="auditor", approval=False, reason="Safety violation detected"))
    mock_revise = AsyncMock(return_value=aip)
    mock_record_lesson = MagicMock()

    with patch.object(evo_service, "audit_aip", mock_audit), \
         patch.object(evo_service, "revise_aip", mock_revise), \
         patch.object(evo_service, "_record_aip_lesson", mock_record_lesson):

        # Cycle 1: max_rounds=2
        res1 = await evo_service.run_aip_evolution_loop(
            aip_id=aip.aip_id,
            max_rounds=2,
            llm_client=MagicMock(),
        )
        assert res1["success"] is False
        assert aip.failure_count == 1
        assert aip.status == "stalled"
        assert res1["status"] == "stalled"
        # Not abandoned yet, no lesson recorded
        mock_record_lesson.assert_not_called()

        # Cycle 2: max_rounds=2
        res2 = await evo_service.run_aip_evolution_loop(
            aip_id=aip.aip_id,
            max_rounds=2,
            llm_client=MagicMock(),
        )
        assert res2["success"] is False
        assert aip.failure_count == 2
        assert aip.status == "abandoned"
        assert res2["status"] == "abandoned"
        # Max failure reached: lesson recorded
        mock_record_lesson.assert_called_once()
        assert "abandoned after 2 failed cycles" in mock_record_lesson.call_args[1]["trigger_error"]


def test_abandon_aip_method(evo_service):
    """Verify explicit abandon_aip method."""
    aip = AIPProposal(
        aip_id="AIP-MANUAL-1",
        initiator_id="node_5a40",
        title="Manual Abandon Test",
        description="Desc",
        status="stalled",
        failure_count=1,
    )
    evo_service.aips[aip.aip_id] = aip

    with patch.object(evo_service, "_record_aip_lesson") as mock_record:
        success = evo_service.abandon_aip(aip.aip_id, reason="Technical dead-end")
        assert success is True
        assert aip.status == "abandoned"
        assert aip.failure_count >= 2
        mock_record.assert_called_once()


@pytest.mark.asyncio
async def test_evolution_watcher_unblocks_proactive_exploration_with_stalled_aip():
    """
    Verify that when only stalled AIPs exist, EvolutionWatcher is NOT blocked
    and proactively triggers auto_explore_and_propose() for a new track.
    """
    from app.services.agent_service import agent_service

    # Create a mock evolution service with only a stalled AIP
    mock_stalled_aip = AIPProposal(
        aip_id="AIP-STALLED-1",
        initiator_id="node_5a40",
        title="Stalled Proposal",
        description="Stalled from previous cycle",
        status="stalled",
        failure_count=1,
    )
    mock_new_aip = AIPProposal(
        aip_id="AIP-NEW-FRESH",
        initiator_id="node_5a40",
        title="Fresh New Proposal",
        description="Discovered on new track",
        status="draft",
        failure_count=0,
    )

    mock_evo = MagicMock()
    mock_evo.is_in_cooldown.return_value = (False, "")
    mock_evo.aips = {mock_stalled_aip.aip_id: mock_stalled_aip}
    mock_evo.auto_explore_and_propose = AsyncMock(return_value=mock_new_aip)
    mock_evo.run_aip_evolution_loop = AsyncMock(return_value={"success": True, "rounds_used": 1})
    mock_evo.record_approval_success = MagicMock()

    with patch("app.services.evolution_service.evolution_service", mock_evo), \
         patch.object(agent_service, "llm", MagicMock()):

        await agent_service.run_evolution_watcher()

        # Proactive exploration MUST have been called even though a stalled proposal existed!
        mock_evo.auto_explore_and_propose.assert_called_once()

        # The loop MUST have targeted the fresh new proposal
        mock_evo.run_aip_evolution_loop.assert_called_once()
        assert mock_evo.run_aip_evolution_loop.call_args[1]["aip_id"] == "AIP-NEW-FRESH"
