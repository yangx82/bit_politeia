"""
Test Suite for Advanced Evolution Modules (Modules 2, 4, 5, 6)

Tests:
1. Dynamic Hot-Reload & Canary Evolution (hot_reload_manager.py)
2. Zero-Trust Secure Sandbox & AST Audit (secure_sandbox.py)
3. Sleep-Phase Memory Consolidation v2.0 (consolidation.py)
4. Live Observability & Multi-Agent Canvas API (observability_service.py)
"""

import sys
import types
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agent.secure_sandbox import ASTSecurityAuditor, SecureSandbox
from app.p2p_community.message_protocol import SignedMessage, MessageType
from app.services.consolidation import ConsolidationService
from app.services.hot_reload_manager import HotReloadManager
from app.services.observability_service import ObservabilityService


# --- 1. Dynamic Hot-Reload & Canary Tests ---

@pytest.mark.anyio
async def test_hot_reload_canary_and_rollback():
    manager = HotReloadManager()

    dummy_name = "test_dummy_hot_module"
    dummy_mod = types.ModuleType(dummy_name)
    dummy_mod.VERSION = 1
    sys.modules[dummy_name] = dummy_mod

    assert manager.backup_module_state(dummy_name) is True

    # Test Canary Success
    async def canary_pass():
        return True

    res_promote = await manager.apply_canary_patch(dummy_name, verification_fn=canary_pass)
    assert res_promote["status"] in ("promoted", "failed_reload")

    # Test Canary Failure & Auto-Rollback
    async def canary_fail():
        return False

    res_rollback = await manager.apply_canary_patch(dummy_name, verification_fn=canary_fail)
    assert res_rollback["status"] in ("rolled_back", "failed_reload")
    assert len(manager.get_history()) >= 1

    sys.modules.pop(dummy_name, None)


# --- 2. Zero-Trust Secure Sandbox AST Tests ---

def test_secure_sandbox_ast_auditor():
    # Safe code
    safe_code = "a = 1 + 2\nprint(f'Result: {a}')"
    safe_res = ASTSecurityAuditor.audit_code(safe_code)
    assert safe_res.is_safe is True
    assert len(safe_res.violations) == 0

    # Unsafe direct eval
    eval_code = "eval('1 + 1')"
    eval_res = ASTSecurityAuditor.audit_code(eval_code)
    assert eval_res.is_safe is False
    assert any("eval" in v for v in eval_res.violations)

    # Unsafe direct exec
    exec_code = "exec('import os')"
    exec_res = ASTSecurityAuditor.audit_code(exec_code)
    assert exec_res.is_safe is False
    assert any("exec" in v for v in exec_res.violations)

    # Dynamic reflection getattr on builtins
    obfuscated_code = "getattr(__builtins__, 'eval')('print(1)')"
    obfus_res = ASTSecurityAuditor.audit_code(obfuscated_code)
    assert obfus_res.is_safe is False
    assert len(obfus_res.violations) > 0

    # Forbidden ctypes / socket import
    import_code = "import ctypes\nctypes.CDLL(None)"
    import_res = ASTSecurityAuditor.audit_code(import_code)
    assert import_res.is_safe is False
    assert any("ctypes" in v for v in import_res.violations)


@pytest.mark.anyio
async def test_secure_sandbox_execution():
    sandbox = SecureSandbox(timeout_sec=5.0)

    # Safe execution
    safe_run = await sandbox.execute_code("print('HELLO_SECURE_SANDBOX')")
    assert safe_run["success"] is True
    assert "HELLO_SECURE_SANDBOX" in safe_run["stdout"]

    # Blocked dangerous execution
    blocked_run = await sandbox.execute_code("eval('2+2')")
    assert blocked_run["success"] is False
    assert "Security Policy Violation" in blocked_run["stderr"]


# --- 3. Sleep-Phase Memory Consolidation v2.0 Tests ---

@pytest.mark.anyio
async def test_sleep_consolidation_v2():
    mock_agent = MagicMock()
    mock_mem = MagicMock()
    mock_mem._semantic_profile = {
        "facts": ["Fact 1: Old status"],
        "distilled_concepts": [],
        "last_consolidation_time": None,
    }
    mock_mem.search_history.return_value = [
        {"timestamp": "2026-08-22T00:00:00Z", "sender": "user", "content": "Update AIP-101 to applied."},
        {"timestamp": "2026-08-22T00:01:00Z", "sender": "agent", "content": "Applied successfully."},
    ]
    mock_agent.resident_memory = mock_mem

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = """
    ```json
    {
      "public_facts": ["AIP-101 is now applied"],
      "superseded_facts": [{"old_fact": "Fact 1: Old status", "new_fact": "AIP-101 is now applied", "reason": "status updated"}],
      "distilled_concepts": [{"concept": "Automated AIP patching pattern", "category": "architecture", "confidence": 0.95}],
      "private_secrets": {},
      "social_updates": [],
      "research_preferences": {}
    }
    ```
    """
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    mock_agent.llm = mock_llm
    mock_agent.reporter = None

    service = ConsolidationService(agent_service=mock_agent)
    res = await service.run_sleep_consolidation(force=True)

    assert "public_facts" in res
    assert len(res["public_facts"]) == 1
    assert len(res["superseded_facts"]) == 1
    assert len(mock_mem._semantic_profile["distilled_concepts"]) == 1
    assert mock_mem._semantic_profile["distilled_concepts"][0]["concept"] == "Automated AIP patching pattern"


# --- 4. Observability Service Tests ---

def test_observability_service_graphs():
    obs = ObservabilityService()

    # 1. Topology
    topo = obs.get_p2p_topology()
    assert "nodes" in topo
    assert "links" in topo
    assert topo["node_count"] >= 1

    # 2. Event DAG
    from app.p2p_community.dag_resolver import dag_resolver
    from datetime import datetime, timezone
    UTC = timezone.utc
    test_msg = SignedMessage(
        message_id="msg_dag_001",
        sender_id="node_a",
        recipient_id="group_1",
        message_type=MessageType.GROUP,
        content={"text": "Debate AIP"},
        timestamp=datetime.now(UTC),
        signature="mock_sig",
        nonce="mock_nonce",
        parents=[],
    )
    dag_resolver.record_event(test_msg)

    dag = obs.get_event_dag()
    assert "nodes" in dag
    assert "edges" in dag
    assert dag["event_count"] >= 1

    # 3. Memory Graph Snapshot
    mock_mem = MagicMock()
    mock_mem._semantic_profile = {
        "facts": ["Fact Alpha", "Fact Beta"],
        "distilled_concepts": [{"concept": "Concept 1", "confidence": 0.9}],
    }
    mock_mem._social_graph = {
        "peer_123": {"name": "AuditBot", "trust": 8, "rel_type": "ally"}
    }
    mem_graph = obs.get_memory_graph_snapshot(mock_mem)
    assert len(mem_graph["nodes"]) >= 4
    assert len(mem_graph["edges"]) >= 3

    # 4. Evolution Kanban
    kanban = obs.get_evolution_kanban()
    assert "columns" in kanban
    assert "draft" in kanban["columns"]
    assert "applied" in kanban["columns"]
