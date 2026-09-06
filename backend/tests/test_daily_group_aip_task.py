import asyncio
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

UTC = timezone.utc

from app.bus.events import InboundMessage
from app.p2p_community.governance import AIPProposal
from app.p2p_community.models import Group
from app.services.agent_service import agent_service
from app.services.evolution_service import EvolutionService


@pytest.fixture
def temp_evolution_dir():
    """Provides a fresh temporary directory for EvolutionService data."""
    temp_dir = tempfile.mkdtemp(prefix="test_evo_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def evolution_service_inst(temp_evolution_dir):
    """Instantiates a dedicated EvolutionService using temporary storage."""
    return EvolutionService(data_dir=temp_evolution_dir)


def test_get_node_group_rank_hour_calculation():
    """Verify group ranking calculation and target hour determination (rank % 24)."""
    with patch.object(agent_service, "_get_local_node_id", return_value="node_beta"), \
         patch("app.services.agent_service.p2p_service") as mock_p2p:

        mock_p2p._initialized = True
        mock_p2p.get_my_groups.return_value = ["group_omega"]

        mock_group = Group(group_id="group_omega", level=1)
        mock_group.members = {"node_alpha", "node_beta", "node_gamma"}
        mock_group.core_node_ids = ["node_alpha"]

        mock_p2p.network_manager.get_group.return_value = mock_group

        mock_rep = MagicMock()
        mock_rep.get_group_rankings.return_value = [
            ("node_alpha", 95.0),
            ("node_beta", 80.0),
            ("node_gamma", 60.0),
        ]
        mock_rep.get_overall_score.side_effect = lambda nid: {"node_alpha": 95.0, "node_beta": 80.0, "node_gamma": 60.0}.get(nid, 50.0)

        with patch.object(agent_service, "reputation_manager", mock_rep):
            hour, rank, gid, core_nodes = agent_service.get_node_group_rank_hour()

            # node_beta is rank 2 -> hour 2 (2 % 24)
            assert rank == 2
            assert hour == 2
            assert gid == "group_omega"
            assert "node_alpha" in core_nodes
            assert "node_beta" not in core_nodes


def test_get_node_group_rank_hour_env_override():
    """Verify DAILY_AIP_TASK_HOUR overrides target hour if configured."""
    with patch.dict(os.environ, {"DAILY_AIP_TASK_HOUR": "14"}), \
         patch.object(agent_service, "_get_local_node_id", return_value="node_x"), \
         patch("app.services.agent_service.p2p_service") as mock_p2p:

        mock_p2p._initialized = True
        mock_p2p.get_my_groups.return_value = ["grp_1"]
        mock_group = Group(group_id="grp_1", level=1)
        mock_group.members = {"node_x"}
        mock_p2p.network_manager.get_group.return_value = mock_group

        hour, rank, gid, _ = agent_service.get_node_group_rank_hour()
        assert hour == 14
        assert rank == 1


def test_check_recent_aip_submission(evolution_service_inst):
    """Verify detection of submitted proposals within last 24h."""
    now = datetime.now(UTC)
    local_id = "node_local_123"

    # 1. Submitted AIP within 24h (2 hours ago)
    recent_submitted = AIPProposal(
        aip_id="AIP-LOCAL-001",
        initiator_id=local_id,
        title="Adaptive Memory Compactor",
        description="Compacts historical memory.",
        status="verified_and_proposed",
        timestamp=now - timedelta(hours=2),
    )
    evolution_service_inst.aips[recent_submitted.aip_id] = recent_submitted

    found, aip = evolution_service_inst.check_recent_aip_submission(hours=24, initiator_id=local_id)
    assert found is True
    assert aip.aip_id == "AIP-LOCAL-001"

    # 2. Older submitted AIP (26 hours ago) -> should not match cutoff
    evolution_service_inst.aips.clear()
    old_submitted = AIPProposal(
        aip_id="AIP-LOCAL-002",
        initiator_id=local_id,
        title="Old Proposal",
        description="Older submission.",
        status="proposed",
        timestamp=now - timedelta(hours=26),
    )
    evolution_service_inst.aips[old_submitted.aip_id] = old_submitted
    found, aip = evolution_service_inst.check_recent_aip_submission(hours=24, initiator_id=local_id)
    assert found is False
    assert aip is None

    # 3. Draft created within 24h (not submitted) -> should return False
    evolution_service_inst.aips.clear()
    recent_draft = AIPProposal(
        aip_id="AIP-LOCAL-003",
        initiator_id=local_id,
        title="Unsubmitted Draft",
        description="Just a draft.",
        status="draft",
        timestamp=now - timedelta(hours=1),
    )
    evolution_service_inst.aips[recent_draft.aip_id] = recent_draft
    found, aip = evolution_service_inst.check_recent_aip_submission(hours=24, initiator_id=local_id)
    assert found is False


def test_calculate_draft_importance_score(evolution_service_inst):
    """Verify multi-dimensional draft importance scoring formula."""
    local_id = "node_local_123"

    simple_draft = AIPProposal(
        aip_id="AIP-LOCAL-A",
        initiator_id=local_id,
        title="Simple Helper",
        description="Helper utility.",
        target_files=["backend/app/utils/helpers.py"],
        proposed_diff="def add(a, b):\n    return a + b\n",
        research_sources=[],
        status="draft",
    )

    critical_draft = AIPProposal(
        aip_id="AIP-LOCAL-B",
        initiator_id=local_id,
        title="P2P Gossip Router Enhancement",
        description="Deep optimization for gossip protocol.",
        target_files=["backend/app/services/agent_service.py", "backend/app/services/p2p_service.py"],
        proposed_diff=(
            "import threading\n\n"
            "class OptimizedRouter:\n"
            "    def __init__(self):\n"
            "        self._lock = threading.Lock()\n"
            "    def route(self, msg):\n"
            "        assert msg is not None\n"
            "        return True\n"
            "def test_router():\n"
            "    r = OptimizedRouter()\n"
            "    assert r.route(1) is True\n"
        ),
        research_sources=["https://arxiv.org/abs/2304.03442", "https://doi.org/10.1145/example"],
        status="revised_draft",
    )

    score_simple = evolution_service_inst.calculate_draft_importance_score(simple_draft)
    score_critical = evolution_service_inst.calculate_draft_importance_score(critical_draft)

    # Critical draft has more LOC, touches critical core files, has citations, and unit test assertions
    assert score_critical > score_simple
    assert score_critical >= 60.0


def test_get_most_important_draft(evolution_service_inst):
    """Verify selection of the highest scoring draft among candidates."""
    now = datetime.now(UTC)
    local_id = "node_local_123"

    draft_1 = AIPProposal(
        aip_id="AIP-LOCAL-D1",
        initiator_id=local_id,
        title="Minor Draft",
        description="Minor tweak.",
        target_files=["backend/app/utils/dummy.py"],
        proposed_diff="x = 1\n",
        status="draft",
        timestamp=now - timedelta(hours=3),
    )

    draft_2 = AIPProposal(
        aip_id="AIP-LOCAL-D2",
        initiator_id=local_id,
        title="Major Adaptive Compaction",
        description="High impact compaction engine.",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff="def compact():\n    assert True\n" * 10,
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="revised_draft",
        timestamp=now - timedelta(hours=1),
    )

    evolution_service_inst.aips[draft_1.aip_id] = draft_1
    evolution_service_inst.aips[draft_2.aip_id] = draft_2

    top = evolution_service_inst.get_most_important_draft(hours=24, initiator_id=local_id)
    assert top is not None
    assert top.aip_id == "AIP-LOCAL-D2"


def test_generate_and_save_archive_md(evolution_service_inst, temp_evolution_dir):
    """Verify markdown archive generation and file persistence."""
    aip = AIPProposal(
        aip_id="AIP-5A40-XYZ99",
        initiator_id="node_leader_99",
        title="Decentralized State Compression",
        description="Applies differential state compression across p2p gossip channels.",
        target_files=["backend/app/services/p2p_service.py"],
        proposed_diff="def compress_state(data):\n    assert data\n    return data\n",
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="draft",
    )

    md = evolution_service_inst.generate_group_discussion_archive_md(
        aip=aip,
        group_id="grp_consensus_1",
        sender_rank=3,
        discussion_summary="小组审阅通过，同意存档。",
    )

    assert "# AIP 提案小组研讨与存档纪要" in md
    assert "AIP-5A40-XYZ99" in md
    assert "第 3 名" in md
    assert "grp_consensus_1" in md
    assert "小组审阅通过，同意存档。" in md

    file_path = evolution_service_inst.save_archive_document(aip.aip_id, md, date_str="20260906")
    assert os.path.exists(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        read_content = f.read()
    assert "Decentralized State Compression" in read_content


@pytest.mark.asyncio
async def test_run_daily_group_aip_audit_skips_when_already_submitted():
    """Verify that daily audit skips if an AIP was already submitted in the last 24h."""
    now = datetime.now(UTC)
    mock_submitted = AIPProposal(
        aip_id="AIP-SUB-001",
        initiator_id="node_me",
        title="Already Done",
        description="Already submitted.",
        status="verified_and_proposed",
        timestamp=now - timedelta(hours=5),
    )

    with patch.object(agent_service, "get_node_group_rank_hour", return_value=(2, 2, "grp_main", ["core_1"])), \
         patch.object(agent_service, "_get_local_node_id", return_value="node_me"), \
         patch("app.services.evolution_service.evolution_service.check_recent_aip_submission", return_value=(True, mock_submitted)), \
         patch("app.services.agent_service.p2p_service.broadcast_to_group", new_callable=AsyncMock) as mock_broadcast:

        res = await agent_service.run_daily_group_aip_audit()
        assert res["status"] == "skipped"
        assert res["reason"] == "already_submitted_24h"
        assert res["aip_id"] == "AIP-SUB-001"
        assert mock_broadcast.await_count == 0


@pytest.mark.asyncio
async def test_run_daily_group_aip_audit_broadcasts_and_archives_draft():
    """Verify that daily audit broadcasts the most important draft and sends archive to core node."""
    mock_draft = AIPProposal(
        aip_id="AIP-DRAFT-999",
        initiator_id="node_me",
        title="Crucial Adaptive Cache",
        description="Important cache improvement.",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff="class AdaptiveCache:\n    pass\n",
        status="draft",
    )

    with patch.object(agent_service, "get_node_group_rank_hour", return_value=(3, 3, "grp_alpha", ["core_peer_1"])), \
         patch.object(agent_service, "_get_local_node_id", return_value="node_me"), \
         patch("app.services.evolution_service.evolution_service.check_recent_aip_submission", return_value=(False, None)), \
         patch("app.services.evolution_service.evolution_service.get_most_important_draft", return_value=mock_draft), \
         patch("app.services.agent_service.p2p_service.broadcast_to_group", new_callable=AsyncMock) as mock_broadcast, \
         patch("app.services.agent_service.p2p_service.send_message", new_callable=AsyncMock) as mock_send, \
         patch.object(agent_service.message_bus, "publish_outbound", new_callable=AsyncMock) as mock_pub:

        res = await agent_service.run_daily_group_aip_audit()

        assert res["status"] == "completed"
        assert res["aip_id"] == "AIP-DRAFT-999"
        assert res["rank"] == 3

        # Group broadcast called
        assert mock_broadcast.await_count == 1
        bc_args = mock_broadcast.await_args
        target_grp = bc_args.kwargs.get("group_id") or (bc_args.args[0] if bc_args.args else None)
        assert target_grp == "grp_alpha"
        target_text = bc_args.kwargs.get("text") or (bc_args.args[1] if len(bc_args.args) > 1 else None)
        assert "Crucial Adaptive Cache" in target_text

        # P2P direct send to core node called
        assert mock_send.await_count == 1
        send_call = mock_send.await_args
        target_rec = send_call.kwargs.get("recipient_id") or (send_call.args[0] if send_call.args else None)
        assert target_rec == "core_peer_1"
        payload = send_call.kwargs.get("content") or (send_call.args[1] if len(send_call.args) > 1 else None)
        assert payload["type"] == "aip_archive"
        assert payload["aip_id"] == "AIP-DRAFT-999"
        assert "content" in payload


@pytest.mark.asyncio
async def test_core_node_receives_and_saves_aip_archive(temp_evolution_dir):
    """Verify that when a core node receives an aip_archive message, it persists it to archives/ without calling LLM."""
    import json

    archive_dir = os.path.join(agent_service.data_dir, "archives")
    test_filename = "AIP_AIP-TEST-123_Group_Discussion_Archive_20260906.md"
    test_filepath = os.path.join(archive_dir, test_filename)

    if os.path.exists(test_filepath):
        os.remove(test_filepath)

    archive_dict = {
        "type": "aip_archive",
        "aip_id": "AIP-TEST-123",
        "filename": test_filename,
        "content": "# Test Archive Content for Core Node",
        "sender_rank": 3,
        "group_id": "grp_alpha",
    }
    msg = InboundMessage(
        channel="p2p",
        sender_id="peer_rank_3",
        session_id="peer_rank_3",
        content=json.dumps(archive_dict),
        metadata={"package_type": "aip_archive", "message_id": "msg_arc_1"},
    )

    with patch.object(agent_service, "_run_ralph_wiggum_loop", new_callable=AsyncMock) as mock_llm:
        await agent_service.process_bus_message(msg)

        # File must be written
        assert os.path.exists(test_filepath)
        with open(test_filepath, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == "# Test Archive Content for Core Node"

        # LLM must not be called
        assert mock_llm.await_count == 0

    # Cleanup
    if os.path.exists(test_filepath):
        os.remove(test_filepath)
