"""
Unit tests for Pipeline Checkpoint Manager & Self-Modification Auto-Resume in Bit Politeia.
"""

import sys
import site
import os

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "backend"))

import unittest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from app.agent.checkpoint_manager import PipelineCheckpointManager


class TestAutoResumeCheckpoint(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.checkpoint_mgr = PipelineCheckpointManager(data_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_load_clear_checkpoint(self):
        """Test basic lifecycle of execution checkpointing."""
        # 1. Initially empty
        self.assertIsNone(self.checkpoint_mgr.load_checkpoint())

        # 2. Save checkpoint
        self.checkpoint_mgr.save_checkpoint(
            session_id="test_session_123",
            channel="resident",
            sender_id="resident",
            input_message_content="Fix bug in pipeline.py",
            thoughts=["I need to modify pipeline.py to fix the error."],
            tool_results=[{"tool": "replace_file_content", "result": "Success"}],
            pending_tool_calls=[{"name": "check_python_syntax", "args": {}}],
            task_id="task_001",
        )

        # 3. Load checkpoint
        cp = self.checkpoint_mgr.load_checkpoint()
        self.assertIsNotNone(cp)
        self.assertEqual(cp["session_id"], "test_session_123")
        self.assertEqual(cp["input_message_content"], "Fix bug in pipeline.py")
        self.assertEqual(len(cp["thoughts"]), 1)
        self.assertEqual(len(cp["tool_results"]), 1)
        self.assertEqual(cp["status"], "IN_PROGRESS")

        # 4. Clear checkpoint
        self.checkpoint_mgr.clear_checkpoint()
        self.assertIsNone(self.checkpoint_mgr.load_checkpoint())

    def test_agent_service_auto_resume(self):
        """Test agent_service auto-resume triggering when checkpoint exists."""
        async def run_test():
            from app.services.agent_service import AgentService
            svc = AgentService()
            svc.llm = MagicMock()
            svc.context_manager = MagicMock()

            # Mock checkpoint manager to return fake checkpoint
            fake_cp = {
                "session_id": "res_session",
                "channel": "resident",
                "sender_id": "resident",
                "input_message_content": "Modify backend code",
                "thoughts": ["Thought 1: modifying file"],
                "tool_results": [{"tool": "write_file", "result": "done"}],
                "status": "IN_PROGRESS"
            }

            from app.agent import checkpoint_manager as cp_mod
            original_mgr = cp_mod.checkpoint_manager

            mock_mgr = MagicMock()
            mock_mgr.load_checkpoint.return_value = fake_cp
            cp_mod.checkpoint_manager = mock_mgr

            svc.process_bus_message = AsyncMock()

            try:
                await svc.check_and_resume_interrupted_tasks()
                # Verify process_bus_message was invoked with auto-resume notice
                svc.process_bus_message.assert_called_once()
                call_args = svc.process_bus_message.call_args[0][0]
                self.assertIn("[SYSTEM AUTO-RESUME NOTICE]", call_args.content)
                self.assertTrue(call_args.metadata.get("is_auto_resume"))
            finally:
                cp_mod.checkpoint_manager = original_mgr

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
