import pytest
import os
import json
import asyncio
from unittest.mock import MagicMock
from app.services.resident_link import ResidentMemory, ResidentReporter, PRIVATE_MEMORY_FILE

@pytest.fixture
def resident_memory():
    # Use a temporary file for testing
    test_file = "test_resident_memory.json"
    memory = ResidentMemory(test_file)
    yield memory
    # Cleanup
    if os.path.exists(test_file):
        os.remove(test_file)

@pytest.fixture
def mock_agent_service():
    agent = MagicMock()
    # Mock governance
    agent.governance_manager = MagicMock()
    agent.governance_manager.active_elections = {1: "election1", 2: "election2"}
    agent.ledger = MagicMock()
    
    async def mock_balance():
        return 123.45
        
    agent.get_balance = MagicMock(side_effect=mock_balance)
    return agent

def test_private_logging(resident_memory):
    content = "Hello Agent"
    resident_memory.log_interaction("user", content)
    
    with open(resident_memory.file_path, "r") as f:
        data = json.load(f)
    
    assert len(data) == 1
    assert data[0]["sender"] == "user"
    assert data[0]["content"] == content
    assert data[0]["type"] == "chat"

def test_history_retrieval(resident_memory):
    for i in range(10):
        resident_memory.log_interaction("user", f"msg {i}")
        
    history = resident_memory.get_recent_history(limit=5)
    assert len(history) == 5
    assert history[-1]["content"] == "msg 9"

@pytest.mark.asyncio
async def test_reporter_generation(mock_agent_service):
    reporter = ResidentReporter(mock_agent_service)
    
    brief = await reporter.generate_daily_brief(["AI"])
    
    assert "Daily Community Brief" in brief
    assert "Active Elections: 2" in brief
    assert "123.45" in brief # Balance
    assert "found new paper on 'AI'" in brief
