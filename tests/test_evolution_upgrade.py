import asyncio
import os
import shutil
import tempfile
import pytest

from app.services.evolution_service import EvolutionService


@pytest.fixture
def temp_evolution_service():
    temp_dir = tempfile.mkdtemp()
    service = EvolutionService(data_dir=temp_dir)
    yield service
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_deterministic_aip_id(temp_evolution_service):
    """Verify deterministic collision-proof ID generation."""
    service = temp_evolution_service
    id1 = service._generate_deterministic_aip_id(
        initiator_id="node_5faa8871",
        title="Adaptive TTL Cache Hint",
        proposed_diff="def calculate_ttl(hit_rate): return int(300 + hit_rate * 300)",
    )
    assert id1.startswith("AIP-5FAA-")

    # Creating proposal with id1
    service.create_aip(
        initiator_id="node_5faa8871",
        title="Adaptive TTL Cache Hint",
        description="Implements adaptive cache hint.",
        proposed_diff="def calculate_ttl(hit_rate): return int(300 + hit_rate * 300)",
    )

    # Calling with exact same content returns same ID
    id_same = service._generate_deterministic_aip_id(
        initiator_id="node_5faa8871",
        title="Adaptive TTL Cache Hint",
        proposed_diff="def calculate_ttl(hit_rate): return int(300 + hit_rate * 300)",
    )
    assert id_same == id1

    # Calling with different content under same title/node derives collision-free version
    id_diff = service._generate_deterministic_aip_id(
        initiator_id="node_5faa8871",
        title="Adaptive TTL Cache Hint",
        proposed_diff="def calculate_ttl_v2(hit_rate): return int(600 * hit_rate)",
    )
    assert id_diff != id1
    assert id_diff.startswith("AIP-5FAA-")


def test_literature_inspiration(temp_evolution_service):
    """Verify literature inspiration returns verified real papers and avoids hallucinated 2408.00001."""
    service = temp_evolution_service
    lit = service._fetch_real_literature_inspiration()
    assert "title" in lit and len(lit["title"]) > 5
    assert "url" in lit and (lit["url"].startswith("http://") or lit["url"].startswith("https://"))
    assert "2408.00001" not in lit["url"]


def test_pre_flight_consistency_gate(temp_evolution_service):
    """Verify that inflated description triggers Scope-Correction tag."""
    service = temp_evolution_service

    # Case 1: Inflated claims with 2-line code
    is_valid, corrected_desc, msg = service._pre_flight_consistency_audit(
        title="Autonomous Distributed Vector Engine",
        description="Introduces an entire system and complete engine for distributed multi-tier vector streaming.",
        proposed_diff="def calculate_adaptive_ttl(hit_rate: float) -> int:\n    return int(300 + hit_rate * 300)\n",
        target_files=["backend/app/services/agent_service.py"],
    )
    assert is_valid is True
    assert "[Scope-Corrected" in corrected_desc
    assert "intentionally out-of-scope" in corrected_desc

    # Case 2: Empty diff is rejected
    is_valid_empty, _, _ = service._pre_flight_consistency_audit(
        title="Empty Proposal",
        description="Empty",
        proposed_diff="",
        target_files=["backend/app/services/agent_service.py"],
    )
    assert is_valid_empty is False

    # Case 3: Syntax error diff is rejected
    is_valid_syntax, _, _ = service._pre_flight_consistency_audit(
        title="Bad Syntax Proposal",
        description="Broken",
        proposed_diff="def bad_syntax(:\n   return",
        target_files=["backend/app/services/agent_service.py"],
    )
    assert is_valid_syntax is False


def test_5_dimension_audit_aip(temp_evolution_service):
    """Verify 5-dimension audit engine correctly approves honest MVP and rejects inflated/hallucinated AIPs."""
    service = temp_evolution_service

    async def _run_checks():
        # 1. Aarron style (Honest, Scope-Corrected, thread-safe, input bounds) -> MUST PASS
        honest_aip = service.create_aip(
            initiator_id="node_aarron",
            title="TTL Adaptive Cache Hint (Scope-Corrected v2)",
            description="Calculates adaptive TTL based on cache hit rate.\n\n[Scope-Corrected: Atomic helper only]",
            target_files=["backend/app/services/agent_service.py"],
            proposed_diff=(
                "import threading\n\n"
                "def calculate_adaptive_ttl(hit_rate: float) -> int:\n"
                "    hit_rate = max(0.0, min(1.0, float(hit_rate)))\n"
                "    return int(300 + (hit_rate * 300))\n"
            ),
            research_sources=["https://arxiv.org/abs/2310.08560"],
        )
        vote_honest = await service.audit_aip(honest_aip.aip_id)
        assert vote_honest.approval is True
        assert "✅ Audit Approved" in vote_honest.reason

        # 2. Viki style (Inflated claims + 2 lines of code without Scope tag) -> MUST REJECT
        inflated_aip = service.create_aip(
            initiator_id="node_viki",
            title="Autonomous Adaptive Memory & P2P Stream Optimization",
            description="Introduces entire system, complete engine, stream optimization and monitoring.",
            target_files=["backend/app/services/agent_service.py"],
            proposed_diff="def get_ttl(h): return 300",
            research_sources=["https://arxiv.org/abs/2310.08560"],
        )
        # Manually strip scope tag to simulate external inbound P2P proposal from legacy node
        inflated_aip.description = "Introduces entire system, complete engine, stream optimization and monitoring."
        vote_inflated = await service.audit_aip(inflated_aip.aip_id)
        assert vote_inflated.approval is False
        assert "Description Inflation" in vote_inflated.reason

        # 3. Hallucinated Citation (arXiv:2408.00001) -> MUST REJECT
        hallucinated_aip = service.create_aip(
            initiator_id="node_viki2",
            title="Vector Cache",
            description="Cache hint [Scope-Corrected: helper]",
            target_files=["backend/app/services/agent_service.py"],
            proposed_diff="def get_ttl(h): return max(0, min(100, int(h)))",
            research_sources=["https://arxiv.org/abs/2408.00001"],
        )
        vote_hallucinated = await service.audit_aip(hallucinated_aip.aip_id)
        assert vote_hallucinated.approval is False
        assert "Hallucinated/Irrelevant Citation" in vote_hallucinated.reason

    asyncio.run(_run_checks())
