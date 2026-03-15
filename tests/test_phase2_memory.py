import asyncio
import os
import shutil
import json
from pathlib import Path
from backend.app.services.resident_link import ResidentMemory

async def test_social_memory():
    # Setup temp memory dir
    temp_dir = Path("tmp_memory_test")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()
    
    try:
        # 0. Isolate MemoryStore before importing ResidentMemory
        from backend.app.services.memory_store import memory_store
        memory_store.memory_dir = temp_dir
        
        from backend.app.services.resident_link import ResidentMemory
        
        # Initialize Memory
        mem = ResidentMemory()
        
        # 1. Test Working Memory
        print("Testing Working Memory...")
        mem.log_interaction("user", "Hello agent!", chat_id="session_1")
        mem.log_interaction("agent", "Hello user!", chat_id="session_1")
        working = mem.get_working_context()
        print(f"Working context length: {len(working)}")
        assert len(working) == 2
        assert working[0]["content"] == "Hello agent!"
        
        # 2. Test Social Graph
        print("Testing Social Graph...")
        peer_id = "peer_123"
        mem.update_social_edge(peer_id, trust_diff=10.0, rel_type="ally", name="Friendly Node")
        
        # Reload to verify persistence
        print("Reloading memory to verify persistence...")
        mem2 = ResidentMemory()
        assert peer_id in mem2._social_graph
        print(f"Trust score: {mem2._social_graph[peer_id]['trust_score']}")
        assert mem2._social_graph[peer_id]["trust_score"] == 60.0
        assert mem2._social_graph[peer_id]["relationship_type"] == "ally"
        
        # 3. Test Hierarchical Context
        print("Testing Hierarchical Context...")
        mem2.update_semantic_fact("User is a developer")
        # Log to mem2 since working memory is not persistent across instances
        mem2.log_interaction("user", "Testing hierarchy!", chat_id="session_2")
        context = mem2.get_full_context_text(peer_id=peer_id)
        print(f"Full Context:\n{context}")
        
        assert "User is a developer" in context
        assert "Social Context for Friendly Node" in context
        assert "Relationship: ally" in context
        assert "Testing hierarchy!" in context
        
        print("\nSUCCESS: All memory layers (Working, Semantic, Social) verified!")
        
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    asyncio.run(test_social_memory())
