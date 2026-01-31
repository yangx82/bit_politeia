
import asyncio
import logging
from app.services.resident_link import ResidentMemory, ResidentReporter
from app.services.knowledge_base import knowledge_base

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
