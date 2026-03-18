import asyncio
import os
import shutil
import json
from pathlib import Path
from datetime import datetime, timedelta
from backend.app.services.resident_link import ResidentMemory
from backend.app.services.memory_store import memory_store
from backend.app.services.consolidation import ConsolidationService

class MockAgent:
    def __init__(self, mem):
        self.resident_memory = mem
        self.llm = None # Will mock or skip LLM call

async def test_consolidation_range():
    temp_dir = Path("tmp_consolidation_test")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()
    
    try:
        # Isolate
        memory_store.memory_dir = temp_dir
        os.environ["AGENT_MEMORY_DIR"] = str(temp_dir)
        
        mem = ResidentMemory()
        agent = MockAgent(mem)
        service = ConsolidationService(agent)
        
        # 1. Setup a "last run" time of 2 hours ago
        last_run = datetime.now() - timedelta(hours=2)
        mem._semantic_profile["last_consolidation_time"] = last_run.isoformat()
        mem.save_semantic_profile()
        
        # 2. Log something OLD (3 hours ago) - Should be IGNORED
        old_time = (datetime.now() - timedelta(hours=3)).isoformat()
        mem.log_interaction("user", "This is old news", msg_type="chat")
        # Manually backdate the entry in the file because log_interaction uses now()
        chat_file = temp_dir / "chat.jsonl"
        lines = chat_file.read_text().splitlines()
        last_line = json.loads(lines[-1])
        last_line["timestamp"] = old_time
        lines[-1] = json.dumps(last_line)
        chat_file.write_text("\n".join(lines) + "\n")
        
        # 3. Log something NEW (1 hour ago) - Should be INCLUDED
        mem.log_interaction("user", "This is important current info", msg_type="chat")
        # Manually backdate to 1 hour ago
        new_time = (datetime.now() - timedelta(hours=1)).isoformat()
        lines = chat_file.read_text().splitlines()
        last_line = json.loads(lines[-1])
        last_line["timestamp"] = new_time
        lines[-1] = json.dumps(last_line)
        chat_file.write_text("\n".join(lines) + "\n")
        
        # 4. Verify search_history range
        logs = mem.search_history(date_from=last_run.isoformat())
        print(f"Found {len(logs)} logs since last run.")
        assert len(logs) == 1
        assert logs[0]["content"] == "This is important current info"
        
        # 5. Test manual notes range
        date_str = datetime.now().strftime("%Y-%m-%d")
        memory_store.append_today("Manual note from today")
        notes = memory_store.get_memories_since(last_run)
        assert "Manual note from today" in notes
        
        print("\nSUCCESS: Memory range filtering verified!")
        
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    asyncio.run(test_consolidation_range())
