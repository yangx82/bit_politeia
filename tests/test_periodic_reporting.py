import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Setup environment
os.environ["OPENAI_API_KEY"] = "sk-mock"

from backend.app.services.consolidation import ConsolidationService
from backend.app.services.resident_memory_service import ResidentMemory, ResidentReporter
from backend.app.services.memory_store import memory_store

async def test_periodic_reporting_flow():
    print("Starting Periodic Reporting Flow Verification...")
    
    # 1. Setup Mock Agent Service
    agent_mock = MagicMock()
    agent_mock.agent_language = "中文"
    agent_mock.llm = AsyncMock()
    
    # Mock LLM Response for Consolidation
    consolidation_json = {
        "public_facts": ["The resident likes spicy food.", "The project is called Bit Politeia."],
        "private_secrets": {},
        "social_updates": [{"peer_id": "peer_1", "trust_diff": 2.0, "rel_type": "friend", "name": "Alice"}]
    }
    
    # Mock LLM Response for Reporting
    report_text = "Daily Summary: I've learned about your spicy food preference and strengthened trust with Alice."
    
    # Mock chain of responses
    mock_responses = [
        MagicMock(content=json.dumps(consolidation_json)), # First call for consolidation
        MagicMock(content=report_text)                  # Second call for reporting
    ]
    agent_mock.llm.ainvoke.side_effect = mock_responses
    
    # 2. Setup Memory with some logs
    workspace = Path(os.getcwd()) / "backend"
    mem = ResidentMemory(workspace_root=str(workspace))
    agent_mock.resident_memory = mem
    
    # Log some dummy interactions
    mem.log_interaction("user", "Hello agent, I love spicy food.", "chat")
    mem.log_interaction("agent", "Noted, I will remember that.", "chat")
    
    # 3. Setup Reporter
    agent_mock.message_bus = AsyncMock()
    reporter = ResidentReporter(agent_mock)
    agent_mock.reporter = reporter
    
    # 4. Run Consolidation
    service = ConsolidationService(agent_mock)
    await service.run_daily_consolidation()
    
    # 5. Verify results
    print("\n--- Verifying Calls ---")
    
    # Verify LLM was called twice (once for consolidation, once for report)
    assert agent_mock.llm.ainvoke.call_count == 2
    print("✓ LLM invoked twice (Consolidation + Reporting)")
    
    # Verify message bus was used to send the report
    assert agent_mock.message_bus.publish_outbound.called
    sent_msg = agent_mock.message_bus.publish_outbound.call_args[0][0]
    print(f"✓ Report sent via message bus: {sent_msg.content[:50]}...")
    assert report_text in sent_msg.content
    
    # Verify semantic memory was updated
    assert "The resident likes spicy food." in mem._semantic_profile["facts"]
    print("✓ Semantic memory updated correctly.")
    
    print("\nPeriodic Reporting Flow Verification: SUCCESS")

if __name__ == "__main__":
    asyncio.run(test_periodic_reporting_flow())
