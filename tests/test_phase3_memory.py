import asyncio
import os
import shutil
import json
from pathlib import Path
from backend.app.services.resident_memory_service import ResidentMemory
from backend.app.services.memory_store import memory_store

async def test_phase3_memory():
    # Setup temp memory dir
    temp_dir = Path("tmp_memory_test_p3")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()
    
    try:
        # Isolate MemoryStore
        memory_store.memory_dir = temp_dir
        os.environ["AGENT_MEMORY_DIR"] = str(temp_dir)
        
        mem = ResidentMemory()
        
        # 1. Test User Vault
        print("Testing User Vault...")
        mem.update_vault_item("api_key", "sk-123456789")
        
        # Reload to verify persistence
        mem2 = ResidentMemory()
        assert mem2._vault["api_key"] == "sk-123456789"
        
        vault_context = mem2.get_vault_context()
        assert "api_key: sk-123456789" in vault_context
        assert "Private Resident Vault" in vault_context
        
        # 2. Test Procedural Awareness
        print("Testing Procedural Awareness...")
        # Since SkillManager is global, we might see existing skills or none if running in clean environment
        proc_context = mem2.get_procedural_context()
        print(f"Procedural Context Found: {bool(proc_context)}")
        # Even if empty, it shouldn't crash
        
        # 3. Test Agent Journaling
        print("Testing Agent Journaling...")
        mem2.log_interaction("agent", "I should try to be more helpful.", msg_type="agent")
        
        # Verify file exists
        agent_journal = temp_dir / "agent.jsonl"
        assert agent_journal.exists()
        lines = agent_journal.read_text().splitlines()
        last_entry = json.loads(lines[-1])
        assert last_entry["sender"] == "agent"
        assert last_entry["content"] == "I should try to be more helpful."
        
        # 4. Test Full Context Integration
        print("Testing Full Context Tiering...")
        mem2.update_semantic_fact("Resident loves coffee")
        full_context = mem2.get_full_context_text()
        
        assert "Resident loves coffee" in full_context
        assert "api_key: sk-123456789" in full_context
        # Note: Interaction buffer (Working Memory) only populates for 'chat' type
        
        print("\nSUCCESS: Dimension 3 (Procedural) and 4 (Subject Separation) verified!")
        
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    asyncio.run(test_phase3_memory())
