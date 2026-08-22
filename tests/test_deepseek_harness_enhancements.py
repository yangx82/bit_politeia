"""
Test Suite for DeepSeek Harness 5-Layer Architectural Enhancements

Tests:
1. Tool Output Spill Store (dsh-spill)
2. Tool Result Pruner & Compaction (dsh-compaction & toolResultPruner)
3. Waterfall Execution Pipeline (core/agent-loop middleware)
4. Event-Sourced Session Log (dsh-session & deterministic derive_messages)
5. Scoped Subagent & Activation Management (dsh-subagent & toolFilter)
"""

import os
import shutil
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agent.waterfall import WaterfallPipeline
from app.services.context_pruner import ToolResultPruner, CompactionEngine
from app.services.scoped_subagent import ScopedSubagentManager, ToolFilter, ActivationState
from app.services.session_event_log import SessionEventLog, SessionEvent
from app.services.spill_store import SpillStore


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="test_dsh_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


# --- 1. Spill Store Tests ---

def test_spill_store_basic_and_threshold(temp_dir):
    store = SpillStore(storage_dir=temp_dir, max_inline_bytes=200)
    session_id = "test_session_spill_1"

    # Small output should NOT be spilled
    small_text = "Small output"
    res_small = store.process_tool_output(session_id, "test_tool", "c1", small_text)
    assert res_small == small_text

    # Large output (>200 bytes) SHOULD be spilled
    large_text = "A" * 500
    res_large = store.process_tool_output(session_id, "test_tool", "c2", large_text)
    assert "[TOOL OUTPUT EXCEEDED INLINE LIMIT" in res_large
    assert "Full output (500 bytes) spilled" in res_large

    # Direct save and read back
    ref = store.save_text(session_id, "grep", "c3", "Content to persist", "grep_out.txt")
    assert os.path.exists(ref["locator"])
    assert store.read_spill(ref["locator"]) == "Content to persist"


# --- 2. Context Pruning & Compaction Tests ---

def test_tool_result_pruner():
    pruner = ToolResultPruner(budget_per_old_tool=100, keep_recent_steps=1)
    
    # Text pruning
    long_str = "HEAD_CONTENT_" + ("X" * 300) + "_TAIL_CONTENT"
    pruned = pruner.prune_text(long_str, max_chars=80)
    assert "HEAD_CONTENT" in pruned
    assert "TAIL_CONTENT" in pruned
    assert "Tool result pruned" in pruned
    assert len(pruned) < len(long_str)

    # History pruning
    history = [
        {"role": "user", "content": "Query 1"},
        {"role": "tool", "content": "OLD_TOOL_LARGE_" + ("O" * 500), "name": "tool1"},
        {"role": "user", "content": "Query 2"},
        {"role": "tool", "content": "RECENT_TOOL_LARGE_" + ("R" * 500), "name": "tool2"},
    ]
    pruned_history, chars_saved = pruner.prune_message_history(history)
    assert chars_saved > 0
    # Old tool should be pruned
    assert "Tool result pruned" in pruned_history[1]["content"]
    # Recent tool should remain intact
    assert "RECENT_TOOL_LARGE_" in pruned_history[3]["content"]
    assert "Tool result pruned" not in pruned_history[3]["content"]


@pytest.mark.anyio
async def test_compaction_engine_semantic():
    compactor = CompactionEngine(max_context_chars=100, keep_recent_turns=1)
    
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Summary: User asked for files, agent listed them."
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    history = [
        {"role": "user", "content": "Long message 1 " * 10},
        {"role": "assistant", "content": "Long response 1 " * 10},
        {"role": "user", "content": "Long message 2 " * 10},
        {"role": "assistant", "content": "Long response 2 " * 10},
        {"role": "user", "content": "Recent question"},
        {"role": "assistant", "content": "Recent answer"},
    ]

    compacted = await compactor.compact_if_needed(history, llm_client=mock_llm)
    assert len(compacted) < len(history)
    assert compacted[0].get("compacted") is True
    assert "[SYSTEM COMPACTION CHECKPOINT]" in compacted[0]["content"]


# --- 3. Waterfall Pipeline Tests ---

@pytest.mark.anyio
async def test_waterfall_security_guard_and_hooks():
    pipeline = WaterfallPipeline()
    ctx = {"session_id": "test_waterfall_sess"}

    # Security Guard should block dangerous command patterns
    safe_check = await pipeline.run_pre_execute("bash", {"command": "ls -la"}, ctx)
    assert safe_check["allow"] is True

    unsafe_check = await pipeline.run_pre_execute("bash", {"command": "rm -rf /"}, ctx)
    assert unsafe_check["allow"] is False
    assert "forbidden pattern" in unsafe_check["reason"]

    # Pre-step hook
    pipeline.add_pre_step_hook(lambda msgs, context: msgs + [{"role": "system", "content": "injected"}])
    res_msgs = await pipeline.run_pre_step([], ctx)
    assert len(res_msgs) == 1
    assert res_msgs[0]["content"] == "injected"

    # Post-execute hook transformation
    pipeline.add_post_execute_hook(lambda name, args, res, context: f"TRANSFORMED({res})")
    post_res = await pipeline.run_post_execute("test_tool", {}, "raw_val", ctx)
    assert post_res == "TRANSFORMED(raw_val)"


# --- 4. Event-Sourced Session Log Tests ---

def test_session_event_log_replay(temp_dir):
    event_log = SessionEventLog(storage_dir=temp_dir)
    session_id = "sess_event_replay_100"

    event_log.append_event(session_id, "turn/start", {"turn": 1})
    event_log.append_event(session_id, "user/message", {"content": "Find research papers"})
    event_log.append_event(session_id, "tool/call", {"tool_name": "arxiv_search", "args": {"q": "P2P"}, "call_id": "c1"})
    event_log.append_event(session_id, "tool/result", {"tool_name": "arxiv_search", "content": "Found 3 papers", "call_id": "c1"})
    event_log.append_event(session_id, "assistant/message", {"content": "Here are the papers."})
    event_log.append_event(session_id, "turn/end", {"turn": 1})

    events = event_log.get_events(session_id)
    assert len(events) == 6
    assert [e.seq for e in events] == [1, 2, 3, 4, 5, 6]

    # Deterministic replay/projection
    messages = event_log.derive_messages(session_id)
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Find research papers"
    assert messages[1]["role"] == "tool"
    assert messages[1]["content"] == "Found 3 papers"
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "Here are the papers."


# --- 5. Scoped Subagent & ToolFilter Tests ---

def test_scoped_subagent_tool_filter():
    mgr = ScopedSubagentManager()
    
    # Read-only filter
    ro_filter = ToolFilter(read_only=True)
    assert ro_filter.is_tool_allowed("view_file") is True
    assert ro_filter.is_tool_allowed("search_web") is True
    assert ro_filter.is_tool_allowed("write_to_file") is False
    assert ro_filter.is_tool_allowed("run_command") is False

    # Whitelist filter
    whitelist_filter = ToolFilter(allowed_tools=["view_file", "search_web"])
    assert whitelist_filter.is_tool_allowed("view_file") is True
    assert whitelist_filter.is_tool_allowed("other_tool") is False

    # Activation lifecycle
    act = mgr.create_activation(
        parent_session_id="parent_01",
        role_description="Code Auditor",
        tool_filter=ro_filter,
    )
    assert act.state == ActivationState.RUNNING
    assert act.parent_session_id == "parent_01"

    # Enqueue FIFO message
    assert mgr.enqueue_message(act.activation_id, {"task": "Audit AIP-101"}) is True
    assert len(act.inbox) == 1

    # Settle activation
    mgr.settle_activation(act.activation_id)
    assert act.state == ActivationState.SETTLED
    assert mgr.enqueue_message(act.activation_id, {"task": "New task"}) is False
