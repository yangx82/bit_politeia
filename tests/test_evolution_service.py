import os
import pytest
import asyncio
from app.services.evolution_service import EvolutionService
from app.p2p_community.governance import AIPProposal


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_evolution_service_create_aip(tmp_path):
    data_dir = str(tmp_path / "data")
    service = EvolutionService(data_dir=data_dir)

    aip = service.create_aip(
        initiator_id="test_node_1",
        title="Test Adaptive Memory Index",
        description="Proposal to optimize vector memory indexing in Bit Politeia.",
        target_files=["backend/app/agent/memory.py"],
        research_sources=["https://arxiv.org/abs/2401.00001"],
    )

    assert aip.aip_id.startswith("AIP-")
    assert aip.title == "Test Adaptive Memory Index"
    assert aip.status == "draft"
    assert aip.target_files == ["backend/app/agent/memory.py"]
    assert aip.aip_id in service.aips


@pytest.mark.anyio
async def test_evolution_service_audit_aip(tmp_path):
    data_dir = str(tmp_path / "data")
    service = EvolutionService(data_dir=data_dir)

    # Safe proposal
    safe_aip = service.create_aip(
        initiator_id="node_1",
        title="Safe Refactor",
        description="Clean up docstrings",
        proposed_diff="def foo(): pass",
    )
    vote = await service.audit_aip(safe_aip.aip_id)
    assert vote.approval is True

    # Dangerous proposal containing dangerous eval pattern
    dangerous_aip = service.create_aip(
        initiator_id="malicious_node",
        title="Dangerous Injection",
        description="Inject arbitrary execution",
        proposed_diff="eval(user_input)",
    )
    dangerous_vote = await service.audit_aip(dangerous_aip.aip_id)
    assert dangerous_vote.approval is False
    assert "Contains dangerous code pattern" in dangerous_vote.reason


@pytest.mark.anyio
async def test_evolution_service_sandbox_verification(tmp_path):
    data_dir = str(tmp_path / "data")
    service = EvolutionService(data_dir=data_dir)

    aip = service.create_aip(
        initiator_id="node_1",
        title="Sandbox Verification Test",
        description="Testing sandbox runner",
    )

    results = await service.verify_in_sandbox(aip.aip_id)
    assert "success" in results
    assert aip.status in ["sandbox_passed", "failed"]
