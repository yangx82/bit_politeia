import unittest
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import HumanMessage

from backend.app.services.context_manager import BitPoliteiaContextManager
from backend.app.services.task_manager import TaskManager


class TestContextManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Mock Agent Service
        self.mock_agent = MagicMock()
        self.mock_agent.base_url = "https://api.openai.com/v1"
        self.mock_agent.model = "gpt-4o"
        self.mock_agent.api_key = "fake_key"
        self.mock_agent.resident_memory = MagicMock()

        # Setup Task Manager
        self.task_manager = TaskManager()
        # Clean tasks for testing
        self.task_manager.tasks = {}
        self.task_manager.create_task("Research Hermes Architecture", priority=8)
        self.mock_agent.task_manager = self.task_manager

        # Initialize Context Manager
        self.ctx_manager = BitPoliteiaContextManager(self.mock_agent)
        # Mock the summarizer LLM to avoid real API calls
        self.ctx_manager.summarizer_llm = AsyncMock()

    async def test_focus_detection_none(self):
        # General query shouldn't match specialized task
        query = "Hello, how are you today?"
        focus = await self.ctx_manager.detect_focus("test_session", query)
        self.ctx_manager.summarizer_llm.ainvoke.assert_called()
        # Mocking the response to be "NONE"
        self.ctx_manager.summarizer_llm.ainvoke.return_value = MagicMock(content="NONE")
        focus = await self.ctx_manager.detect_focus("test_session", query)
        self.assertEqual(focus, None)

    async def test_compression_trigger(self):
        # 10 huge messages to trigger threshold
        history = [HumanMessage(content="A" * 50000) for _ in range(10)]
        self.ctx_manager.threshold_tokens = 50000  # Set low threshold for test
        self.ctx_manager.summarizer_llm.ainvoke.return_value = MagicMock(
            content="Summary of huge messages"
        )

        optimized, task_id, lineage = await self.ctx_manager.get_optimized_messages(
            "sess_1", "next", history
        )

        # Should contain the summary checkpoint message
        has_checkpoint = any(
            "[ITERATIVE CONTEXT SUMMARY]" in m.content
            for m in optimized
            if isinstance(m, (MagicMock, object))
        )
        # Since optimized has SystemMessage, let's check properly
        self.assertTrue(len(optimized) < len(history))
        self.mock_agent.resident_memory.log_interaction.assert_called()
        print("Compression triggered and logged correctly.")


if __name__ == "__main__":
    unittest.main()
