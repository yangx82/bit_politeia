"""
Comprehensive unit tests for distilled AIP features:
1. ToolHealthWatcher & ToolRegistry integration
2. HierarchicalMemoryCompactor pure-Python lexical cosine, clustering & research boost
3. AIP Quality Gate & EvolutionService Non-Goals scope boundaries
"""

import asyncio
import time
import pytest

from app.agent.tool_health_watcher import ToolHealthWatcher, ToolScore
from app.agent.tool_registry import ToolRegistry, ToolCapability, ToolRiskLevel
from app.services.hierarchical_memory_compactor import (
    HierarchicalMemoryCompactor,
    MemoryEntry,
    lexical_cosine_similarity,
    extract_key_topics,
    cluster_by_lexical_similarity,
)
from app.services.aip_quality_gate import ASTConsistencyAuditor


def test_tool_health_watcher_basic_and_pruning():
    watcher = ToolHealthWatcher(failure_threshold=3, min_success_rate=0.3, cooldown_seconds=10.0)
    assert watcher.is_healthy("tool_a") is True

    # 1. Successful execution
    score = watcher.record_execution("tool_a", success=True, latency=0.05)
    assert score.calls == 1
    assert score.successes == 1
    assert score.failures == 0
    assert score.consecutive_failures == 0
    assert score.avg_latency == pytest.approx(0.05)
    assert watcher.is_healthy("tool_a") is True

    # 2. Consecutive failures up to threshold
    watcher.record_execution("tool_a", success=False, latency=0.1)
    assert watcher.is_healthy("tool_a") is True
    watcher.record_execution("tool_a", success=False, latency=0.1)
    assert watcher.is_healthy("tool_a") is True
    score = watcher.record_execution("tool_a", success=False, latency=0.1)
    assert score.consecutive_failures == 3
    assert score.is_pruned is True
    assert watcher.is_healthy("tool_a") is False

    # Filter healthy tools
    class DummyTool:
        def __init__(self, name):
            self.name = name

    t_a = DummyTool("tool_a")
    t_b = DummyTool("tool_b")
    healthy = watcher.filter_healthy_tools([t_a, t_b])
    assert len(healthy) == 1
    assert healthy[0].name == "tool_b"


def test_tool_health_watcher_cooldown_probe_recovery():
    watcher = ToolHealthWatcher(failure_threshold=2, cooldown_seconds=0.15)
    watcher.record_execution("flaky_tool", success=False)
    watcher.record_execution("flaky_tool", success=False)
    assert watcher.is_healthy("flaky_tool") is False

    # Still in cooldown
    time.sleep(0.05)
    assert watcher.is_healthy("flaky_tool") is False

    # Cooldown expires -> first probe permitted
    time.sleep(0.12)
    assert watcher.is_healthy("flaky_tool") is True
    # In-flight probe locks out second probe until outcome recorded
    assert watcher.is_healthy("flaky_tool") is False

    # Successful probe restores tool to healthy
    watcher.record_execution("flaky_tool", success=True, latency=0.02)
    assert watcher.is_healthy("flaky_tool") is True
    score = watcher.get_score("flaky_tool")
    assert score.is_pruned is False
    assert score.consecutive_failures == 0


@pytest.mark.asyncio
async def test_tool_registry_health_integration():
    watcher = ToolHealthWatcher(failure_threshold=2, cooldown_seconds=60.0)
    registry = ToolRegistry(health_watcher=watcher)

    def ok_handler(val: int) -> int:
        return val * 2

    def err_handler():
        raise RuntimeError("boom")

    registry.register("double", ok_handler, description="Doubles value")
    registry.register("fail", err_handler, description="Always fails")

    res = await registry.execute("double", 5)
    assert res == 10
    score_ok = watcher.get_score("double")
    assert score_ok.calls == 1
    assert score_ok.successes == 1

    with pytest.raises(RuntimeError):
        await registry.execute("fail")
    with pytest.raises(RuntimeError):
        await registry.execute("fail")

    score_fail = watcher.get_score("fail")
    assert score_fail.calls == 2
    assert score_fail.is_pruned is True

    healthy_tools = registry.list_healthy_tools()
    healthy_names = [t.name for t in healthy_tools]
    assert "double" in healthy_names
    assert "fail" not in healthy_names


def test_hierarchical_memory_compactor_lexical_similarity():
    sim_identical = lexical_cosine_similarity("consensus protocol voting", "consensus protocol voting")
    assert sim_identical == pytest.approx(1.0)

    sim_related = lexical_cosine_similarity("p2p network node topology", "p2p gossip routing protocol")
    assert sim_related > 0.2

    sim_orthogonal = lexical_cosine_similarity("quantum computing superposition", "vegetable recipe soup cooking")
    assert sim_orthogonal == 0.0


def test_hierarchical_memory_compactor_clustering_and_topics():
    entries = [
        MemoryEntry(content="Discussing p2p network mesh routing topology.", timestamp=10.0, role="agent"),
        MemoryEntry(content="Recipe for vegetable soup broth and baking bread.", timestamp=9.0, role="resident"),
        MemoryEntry(content="Network p2p peer latency optimization algorithms.", timestamp=8.0, role="agent"),
        MemoryEntry(content="Cooking ingredients include onions, carrots, and salt broth.", timestamp=7.0, role="resident"),
    ]

    clusters = cluster_by_lexical_similarity(entries, threshold=0.15)
    assert len(clusters) == 2

    topics = extract_key_topics(entries, top_k=3)
    assert len(topics) <= 3
    assert any(t in ["p2p", "network", "soup", "broth", "cooking"] for t in topics)


def test_hierarchical_memory_compactor_research_boost_and_pruning():
    compactor = HierarchicalMemoryCompactor(hot_window=2, warm_window=4, cold_threshold=6)
    now = time.time()

    generic_entry = MemoryEntry(content="hello nice weather today", timestamp=now - 500, role="agent")
    research_doi_entry = MemoryEntry(
        content="Evaluation benchmark using 10.1145/3318464.3389700 baseline",
        timestamp=now - 500,
        role="agent",
    )
    research_arxiv_entry = MemoryEntry(
        content="Inspired by arXiv:2304.03442 generative agents experiment",
        timestamp=now - 500,
        role="agent",
    )

    score_generic = compactor.score_importance(generic_entry, now)
    score_doi = compactor.score_importance(research_doi_entry, now)
    score_arxiv = compactor.score_importance(research_arxiv_entry, now)

    assert score_doi > score_generic + 0.4
    assert score_arxiv > score_generic + 0.4

    # Pruning survival
    survivors = compactor.prune_by_threshold([generic_entry, research_doi_entry, research_arxiv_entry], min_score=0.6)
    assert research_doi_entry in survivors
    assert research_arxiv_entry in survivors


def test_aip_quality_gate_non_goals_stripping():
    desc_with_non_goals = (
        "[Scope-Corrected | Atomic Enhancement] Implements AdaptiveCacheHint for query caching.\n"
        "- feature: cache hit recording\n"
        "- feature: dynamic TTL calculation\n"
        "### 🚫 Non-Goals & Scope Boundaries\n"
        "- distributed Redis cluster\n"
        "- disk persistence daemon\n"
        "- multi-region replication\n"
    )

    claims = ASTConsistencyAuditor.extract_claims_from_description(desc_with_non_goals)
    # Ensure positive claims are present
    assert any("cache hit" in c.lower() for c in claims)
    assert any("dynamic ttl" in c.lower() for c in claims)
    # Ensure items under Non-Goals are NOT treated as claimed features
    assert not any("distributed redis" in c.lower() for c in claims)
    assert not any("disk persistence" in c.lower() for c in claims)
    assert not any("multi-region" in c.lower() for c in claims)
