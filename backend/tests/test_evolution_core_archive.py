import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure workspace backend is loaded before any stale site-packages
backend_dir = str(Path(__file__).resolve().parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.p2p_community.governance import AIPProposal
from app.services.evolution_service import EvolutionService, ENABLE_AUTONOMOUS_GIT_PUSH


@pytest.fixture
def temp_evolution_service(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    svc = EvolutionService(data_dir=str(data_dir))
    return svc


def test_default_autonomous_git_push_disabled():
    # By default, autonomous git push must be disabled under Option 1 safety protocol
    assert ENABLE_AUTONOMOUS_GIT_PUSH is False


def test_generate_passed_aip_archive_md(temp_evolution_service):
    aip = AIPProposal(
        aip_id="AIP-TEST-123",
        initiator_id="node_abc123",
        title="Test Proposal for Core Archiving",
        description="Detailed description for the proposal.",
        target_files=["backend/app/services/test_service.py"],
        proposed_diff="--- a/test\n+++ b/test\n@@ -1 +1 @@\n+added line",
        research_sources=["https://arxiv.org/abs/2401.00000"],
        sandbox_results={"test_exit_code": 0, "test_passed": True},
        quality_report={"ast_check": "passed", "security_risk": "low"},
    )

    md = temp_evolution_service.generate_passed_aip_archive_md(aip)
    assert "AIP-TEST-123" in md
    assert "Test Proposal for Core Archiving" in md
    assert "node_abc123" in md
    assert "backend/app/services/test_service.py" in md
    assert "+added line" in md
    assert "去中心化演化安全规约（方案一）" in md


def test_archive_passed_aip_local(temp_evolution_service, tmp_path):
    aip = AIPProposal(
        aip_id="AIP-LOCAL-001",
        initiator_id="initiator_node",
        title="Local Archive Test",
        description="Testing local archive output.",
        target_files=["backend/app/sample.py"],
        proposed_diff="+ sample diff",
    )

    res = temp_evolution_service.archive_passed_aip_local(aip)
    assert os.path.exists(res["json_path"])
    assert os.path.exists(res["md_path"])

    with open(res["json_path"], "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["aip_id"] == "AIP-LOCAL-001"
    assert data["status"] == "consensus_archived"
    assert data["proposed_diff"] == "+ sample diff"

    with open(res["md_path"], "r", encoding="utf-8") as f:
        md_text = f.read()
    assert "AIP-LOCAL-001" in md_text
    assert "Local Archive Test" in md_text


def test_save_core_node_archive_and_ledger(temp_evolution_service):
    aip_id = "AIP-CORE-888"
    data = {
        "aip_id": aip_id,
        "title": "Core Ledger Aggregation Test",
        "initiator_id": "peer_node_xyz",
        "target_files": ["backend/app/core.py"],
        "proposed_diff": "+ core diff",
    }
    md_content = "# Core Archive MD content"

    res = temp_evolution_service.save_core_node_archive(
        aip_id=aip_id,
        data=data,
        md_content=md_content,
        source_node="peer_node_xyz",
    )

    assert os.path.exists(res["json_path"])
    assert os.path.exists(res["md_path"])
    assert os.path.exists(res["ledger_path"])

    with open(res["ledger_path"], "r", encoding="utf-8") as f:
        ledger = json.load(f)

    assert ledger["total_passed_aips"] == 1
    assert aip_id in ledger["passed_aips"]
    entry = ledger["passed_aips"][aip_id]
    assert entry["title"] == "Core Ledger Aggregation Test"
    assert entry["source_node"] == "peer_node_xyz"
    assert entry["json_file"] == f"passed_aips/{aip_id}.json"

    # Save a second one to verify ledger append
    aip_id_2 = "AIP-CORE-999"
    data_2 = {
        "aip_id": aip_id_2,
        "title": "Second Core Test",
        "initiator_id": "peer_node_2",
        "target_files": ["backend/app/second.py"],
    }
    temp_evolution_service.save_core_node_archive(
        aip_id=aip_id_2,
        data=data_2,
        md_content="# Second MD",
        source_node="peer_node_2",
    )

    with open(res["ledger_path"], "r", encoding="utf-8") as f:
        ledger2 = json.load(f)
    assert ledger2["total_passed_aips"] == 2
    assert aip_id in ledger2["passed_aips"]
    assert aip_id_2 in ledger2["passed_aips"]


@pytest.mark.asyncio
async def test_archive_consensus_aip_flow(temp_evolution_service):
    aip = AIPProposal(
        aip_id="AIP-FLOW-777",
        initiator_id="node_flow",
        title="Flow Test Proposal",
        description="Testing full archive_consensus_aip flow.",
        target_files=["backend/app/flow.py"],
        proposed_diff="+ flow diff",
    )
    temp_evolution_service.aips[aip.aip_id] = aip

    mock_agent_service = MagicMock()
    mock_agent_service.get_node_group_rank_hour.return_value = (10, 1, "group-1", ["core_node_1"])
    mock_agent_service.notify_resident = AsyncMock()

    res = await temp_evolution_service.archive_consensus_aip(
        aip_id=aip.aip_id,
        agent_service=mock_agent_service,
    )

    assert res["success"] is True
    assert res["status"] == "consensus_archived"
    assert aip.status == "consensus_archived"
    assert os.path.exists(res["json_path"])
    assert os.path.exists(res["md_path"])
    assert os.path.exists(res["core_ledger_path"])
    mock_agent_service.notify_resident.assert_awaited_once()


@pytest.mark.asyncio
async def test_submit_pr_routes_to_archive_when_auto_push_disabled(temp_evolution_service):
    aip = AIPProposal(
        aip_id="AIP-SUBMIT-001",
        initiator_id="node_sub",
        title="Submit PR Interception Test",
        description="Testing that submit_pr safely archives instead of pushing to git.",
        target_files=["backend/app/sub.py"],
        proposed_diff="+ sub diff",
    )
    temp_evolution_service.aips[aip.aip_id] = aip

    mock_agent_service = MagicMock()
    mock_agent_service.get_node_group_rank_hour.return_value = (12, 0, "group-test", [])
    mock_agent_service.notify_resident = AsyncMock()

    # Ensure git checkout or push is never called
    with patch("subprocess.run") as mock_run:
        res = await temp_evolution_service.submit_pr(
            aip_id=aip.aip_id,
            agent_service=mock_agent_service,
            force_git_push=False,
        )

        mock_run.assert_not_called()
        assert res["success"] is True
        assert res["status"] == "consensus_archived"
        assert aip.status == "consensus_archived"
