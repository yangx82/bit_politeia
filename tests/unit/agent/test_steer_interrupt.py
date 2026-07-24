"""
Unit tests for Bit Politeia /steer in-flight steering and interrupt mechanism:
1. PipelineContext steering fields and flags.
2. ExecuteStage steering check & interceptor logic.
3. AgentService.steer_session API helper behavior (cancel & steer).
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
from unittest.mock import AsyncMock, MagicMock
from app.agent.pipeline import PipelineContext, ExecuteStage, PlanStage
from app.models.session import Session
from app.bus.events import InboundMessage


class TestSteerInterruptMechanism(unittest.TestCase):

    def setUp(self):
        self.session = Session(session_id="test_resident_session", user_id="resident", channel="resident")
        self.input_msg = InboundMessage(channel="resident", sender_id="resident", content="Run a long task", session_id="test_resident_session")
        self.context = PipelineContext(session=self.session, input_message=self.input_msg)
        self.context.steer_instructions = []
        self.context.steering_flag = False
        self.context.stop_execution = False
        self.context.metadata["messages"] = []

    def test_pipeline_context_steer_initialization(self):
        """Test that PipelineContext initializes steering attributes properly."""
        self.assertEqual(self.context.steer_instructions, [])
        self.assertFalse(self.context.steering_flag)
        self.assertFalse(self.context.stop_execution)

    def test_execute_stage_user_cancel_interrupt(self):
        """Test ExecuteStage stops execution when stop_execution flag is set by user cancel."""
        stage = ExecuteStage()
        agent_mock = MagicMock()
        agent_mock.message_bus = AsyncMock()

        self.context.tool_calls = [
            {"name": "execute_shell_command", "args": {"command": "sleep 10"}, "id": "call_1"},
            {"name": "execute_shell_command", "args": {"command": "echo done"}, "id": "call_2"}
        ]
        self.context.stop_execution = True

        async def run_stage():
            await stage.run(self.context, agent_mock)

        asyncio.run(run_stage())
        self.assertEqual(self.context.tool_results, [])  # No tools executed

    def test_execute_stage_in_flight_steering(self):
        """Test ExecuteStage intercepts steer instruction, discards pending calls and injects steer message."""
        stage = ExecuteStage()
        agent_mock = MagicMock()
        agent_mock.message_bus = AsyncMock()
        agent_mock.tools_map = {"execute_shell_command": AsyncMock(return_value="Output step 1")}

        self.context.tool_calls = [
            {"name": "execute_shell_command", "args": {"command": "echo step1"}, "id": "call_1"},
            {"name": "execute_shell_command", "args": {"command": "echo step2"}, "id": "call_2"}
        ]

        # Inject steer instruction mid-flight
        self.context.steer_instructions = ["Wait, change strategy to python!"]
        self.context.steering_flag = True

        # Mock PlanStage so it doesn't try to invoke real LLM
        with unittest.mock.patch("app.agent.pipeline.PlanStage.run", new_callable=AsyncMock) as mock_plan_run:
            async def run_stage():
                await stage.run(self.context, agent_mock)

            asyncio.run(run_stage())

            # 1. Verify PlanStage was re-triggered
            mock_plan_run.assert_called_once()

            # 2. Verify remaining tool_calls were cleared
            self.assertEqual(self.context.tool_calls, [])

            # 3. Verify HumanMessage containing steering directive was injected into messages
            messages = self.context.metadata["messages"]
            self.assertEqual(len(messages), 1)
            self.assertIn("Wait, change strategy to python!", messages[0].content)

    def test_agent_service_steer_session(self):
        """Test AgentService.steer_session matches active pipeline context."""
        from app.services.agent_service import agent_service

        # Register active context
        agent_service.active_pipelines["test_resident_session"] = self.context

        async def run_steer():
            # Test steer action
            res1 = await agent_service.steer_session("test_resident_session", "steer", "Stop long calculation")
            self.assertTrue(res1["success"])
            self.assertEqual(res1["status"], "steered")
            self.assertIn("Stop long calculation", self.context.steer_instructions)

            # Test cancel action
            res2 = await agent_service.steer_session("test_resident_session", "cancel")
            self.assertTrue(res2["success"])
            self.assertEqual(res2["status"], "cancelled")
            self.assertTrue(self.context.stop_execution)

        asyncio.run(run_steer())
        # Clean up
        agent_service.active_pipelines.pop("test_resident_session", None)


if __name__ == "__main__":
    unittest.main()
