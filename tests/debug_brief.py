import asyncio
import logging
import os
import sys

# Add backend to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
backend_dir = os.path.join(project_root, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.services.resident_memory_service import ResidentMemory, ResidentReporter

# Setup logging
logging.basicConfig(level=logging.INFO)


class MockAgent:
    def __init__(self):
        self.resident_memory = ResidentMemory()
        self.llm = None  # Use None to bypass LLM logic or test fallback
        self.governance_manager = None
        self.ledger = None


async def test():
    print("Initializing Mock Agent...")
    agent = MockAgent()
    reporter = ResidentReporter(agent)

    interests = ["Blockchain", "Cognition"]
    print(f"Testing with interests: {interests}")

    result = await reporter.collect_research_updates(interests)
    print("\n=== RESULT ===\n")
    print(result)


if __name__ == "__main__":
    asyncio.run(test())
