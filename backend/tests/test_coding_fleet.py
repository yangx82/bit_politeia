import pytest
import asyncio
import backend.app.agent.tools  # Trigger tool registrations in tool_registry
from backend.app.agent.tool_registry import tool_registry, ToolCapability, ToolRiskLevel, ApprovalRequirement
from backend.app.agent.coding_fleet import coding_fleet, AgentSession

def test_tool_registry_registration():
    meta = tool_registry.get_meta("read_file")
    assert meta is not None
    assert ToolCapability.READ_ONLY in meta.capabilities
    assert meta.risk_level == ToolRiskLevel.LOW

    meta_shell = tool_registry.get_meta("execute_shell_command")
    assert meta_shell is not None
    assert ToolCapability.EXECUTES_CODE in meta_shell.capabilities
    assert meta_shell.risk_level == ToolRiskLevel.HIGH
    assert meta_shell.approval == ApprovalRequirement.REQUIRED

def test_coding_fleet_session_and_locking(tmp_path):
    async def _run():
        session_id = "test_fleet_session_001"
        target_path = str(tmp_path / "test_file.py")
        
        session = coding_fleet.create_session(session_id, "Build test script", target_path)
        assert session.session_id == session_id
        assert session.status == "running"

        coding_fleet.update_checkpoint(session_id, checkpoint="iter_1", created_files=[target_path], status="running")
        updated = coding_fleet.get_session(session_id)
        assert updated.checkpoint == "iter_1"
        assert target_path in updated.created_files

        # Verify per-file lock
        lock1 = await coding_fleet.acquire_file_lock(target_path)
        lock2 = await coding_fleet.acquire_file_lock(target_path)
        assert lock1 is lock2

    asyncio.run(_run())
