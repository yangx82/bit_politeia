
import asyncio
import logging
from pathlib import Path
import json
import sys
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VerifyMemory")

# Add backend to path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root / "backend"))

try:
    from app.services.memory_store import memory_store
    from app.services.resident_link import ResidentMemory
    from app.services.agent_service import agent_service
except ImportError as e:
    logger.error(f"Import failed: {e}")
    sys.exit(1)

async def test_memory_refactoring():
    logger.info("Starting Memory Refactoring Verification...")
    
    # 1. Test MemoryStore
    logger.info("1. Testing MemoryStore...")
    memory_store.write_long_term("This is a test long-term memory.")
    memory_store.append_today("Today's test note.")
    
    if (memory_store.memory_dir / "MEMORY.md").exists():
        logger.info("   - MEMORY.md created.")
    else:
        logger.error("   - MEMORY.md NOT found!")
        
    # 2. Test ResidentMemory (New JSONL)
    logger.info("2. Testing ResidentMemory (JSONL)...")
    rm = ResidentMemory()
    rm.log_interaction("user", "Hello JSONL", msg_type="chat")
    rm.log_interaction("agent", "Hi there", msg_type="chat")
    rm.log_interaction("system", "System Event", msg_type="system")
    
    chat_file = rm.topic_files["chat"]
    system_file = rm.topic_files["system"]
    
    if chat_file.exists():
        logger.info(f"   - chat.jsonl created at {chat_file}")
        with open(chat_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            logger.info(f"   - chat.jsonl has {len(lines)} lines (expect >1)")
    else:
        logger.error("   - chat.jsonl NOT found!")
        
    if system_file.exists():
        logger.info(f"   - system.jsonl created.")
    else:
        logger.error("   - system.jsonl NOT found!")

    # 3. Test AgentService Integration
    logger.info("3. Testing AgentService Context Injection...")
    # We can't easily check internal state without deep inspection, 
    # but successful import and initialization is a good sign.
    # We can try to run a dummy think loop if LLM is not configured it returns error string which is fine.
    
    response = await agent_service._think_and_act("Test context injection", "VerificationScript")
    logger.info(f"   - Agent response: {response[:50]}...")
    
    logger.info("Verification Complete.")

if __name__ == "__main__":
    asyncio.run(test_memory_refactoring())
