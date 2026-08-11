import asyncio
import logging
import os
import sys
from unittest.mock import AsyncMock, MagicMock

# Ensure we can import from backend
sys.path.append(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
)

from app.services.agent_service import AgentService
from app.services.consolidation import ConsolidationService
from app.services.knowledge_base import knowledge_base
from app.services.memory_store import memory_store

# Configure logging
logging.basicConfig(level=logging.INFO)


# Mock Agent Service with a Fake LLM
class MockAgent(AgentService):
    def __init__(self):
        self.llm = MagicMock()
        self.llm.ainvoke = AsyncMock()
        # Mock response properly for LangChain 0.1+
        mock_resp = MagicMock()
        mock_resp.content = '["User likes classical music", "User is studying Python"]'
        self.llm.ainvoke.return_value = mock_resp


async def test_consolidation():
    print("Setting up test environment...")

    # 1. Setup Mock Data in MemoryStore
    test_note = """
    Agent: Hello!
    User: I really enjoy listening to Mozart and Bach while I code.
    Agent: That sounds relaxing. What are you coding?
    User: I'm learning Python right now. It's great.
    """
    memory_store.append_today(test_note)
    print("Added mock conversation to Today's Memory.")

    # 2. Initialize Service with Mock Agent
    try:
        mock_agent = MockAgent()
        service = ConsolidationService(mock_agent)

        # 3. Run Consolidation
        print("Running consolidation...")
        await service.run_daily_consolidation()

        # 4. Verify Ingestion
        print("Verifying Core Memory...")

        results = knowledge_base.retrieve_hybrid("What music does the user like?", limit=1)
        print(f"Retrieval Result:\n{results}")

        if "classical music" in results:
            print("[PASS] Insight retrieval successful.")
        else:
            print("[FAIL] Insight not found.")

    except Exception as e:
        print(f"Test Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_consolidation())
