import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

# Add project root and backend to sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
backend_dir = os.path.join(root_dir, "backend")
sys.path.append(root_dir)
sys.path.append(backend_dir)

from backend.app.agent.pipeline import PipelineContext, RetrospectiveStage
from backend.app.services.task_manager import TaskManager, TaskStatus


class TestLongTermTasks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create a fresh TaskManager with a temporary file
        self.test_file = "test_tasks.json"
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        self.task_manager = TaskManager(storage_path=self.test_file)

    async def asyncTearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_task_creation_and_persistence(self):
        task = self.task_manager.create_task(
            "Write a research paper", priority=8, subtasks=["Outline", "Draft"]
        )
        self.assertEqual(task.goal, "Write a research paper")
        self.assertEqual(len(task.subtasks), 2)

        # Reload and verify
        new_manager = TaskManager(storage_path=self.test_file)
        self.assertIn(task.id, new_manager.tasks)
        self.assertEqual(new_manager.tasks[task.id].goal, "Write a research paper")

    def test_status_updates(self):
        task = self.task_manager.create_task("Test Status")
        task.update_status("active")
        self.assertEqual(task.status, TaskStatus.ACTIVE)

        self.task_manager.complete_task(task.id, lessons="Success!")
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.lessons_learned, "Success!")

    async def test_retrospective_stage(self):
        # Mock agent
        agent = MagicMock()
        agent.task_manager = self.task_manager
        agent.llm = AsyncMock()
        agent.llm.ainvoke.return_value = MagicMock(content="Key lessons: Planning is important.")
        agent.resident_memory = MagicMock()

        # Create a task that was recently completed
        task = self.task_manager.create_task("Retro Task")
        self.task_manager.complete_task(task.id)

        # Run RetrospectiveStage
        stage = RetrospectiveStage()

        from backend.app.bus.events import InboundMessage
        from backend.app.models.session import Session

        test_session = Session(session_id="test_user", channel="resident", entity_id="test_user")
        test_msg = InboundMessage(
            sender_id="test_user", session_id="test_user", content="hello", channel="resident"
        )

        context = PipelineContext(
            session=test_session,
            input_message=test_msg,
            final_answer="The task was successful because of planning.",
        )

        await stage.run(context, agent)

        self.assertEqual(task.lessons_learned, "Key lessons: Planning is important.")
        agent.llm.ainvoke.assert_called()

    async def test_task_context_injection(self):
        self.task_manager.create_task("Ongoing Project")
        context = self.task_manager.get_task_context()
        self.assertIn("# ACTIVE LONG-TERM TASKS", context)
        self.assertIn("Ongoing Project", context)
        self.assertIn("(Status: active)", context)

    def test_context_injection_after_reload(self):
        # Create task and save it
        self.task_manager.create_task("Reload Test Task")

        # Load in a fresh manager
        new_manager = TaskManager(storage_path=self.test_file)
        context = new_manager.get_task_context()

        self.assertIn("Reload Test Task", context)
        self.assertIn("(Status: active)", context)  # Should not crash!


if __name__ == "__main__":
    unittest.main()
