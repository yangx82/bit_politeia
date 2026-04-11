import asyncio
import json
import os
import shutil
from datetime import datetime, timezone
from app.services.agent_service import AgentService
from app.services.knowledge_base import knowledge_base

async def test_universal_search_logic():
    print("--- Starting Universal Search Test ---")
    
    # 1. Setup Data Directory
    test_data_dir = "backend/data/test_logs"
    if os.path.exists(test_data_dir):
        shutil.rmtree(test_data_dir)
    os.makedirs(test_data_dir, exist_ok=True)
    
    # Create fake mission log
    test_file = os.path.join("backend/data", "test_mission.jsonl")
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sender": "system",
        "content": "The P2P network delay was fixed by increasing the timeout to 120 seconds in the relay_manager.py file. "
                   "This solution resolved the connection drops observed in the Singapore cluster.",
        "type": "research_conclusion"
    }
    
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    print(f"Created test log: {test_file}")

    # 2. Initialize Agent Service (Mocking environment)
    os.environ["OPENAI_API_KEY"] = "sk-dummy" # Ensure it doesn't crash on init
    agent = AgentService()
    
    # Force KnowledgeBase initialization for test
    kb = knowledge_base
    kb.sync_all_topics()
    
    # 3. Test Direct Retrieval
    print("\nTesting Hybrid Retrieval...")
    res = kb.retrieve_hybrid("P2P network delay fix relay_manager", limit=1)
    print(f"Retrieved Context: {res}")
    
    if "120 seconds" in res:
        print("✅ SUCCESS: Hybrid Search found the relevant conclusion.")
    else:
        print("❌ FAILURE: Hybrid Search missed the content.")

    # 4. Test Tool Execution (with Summarization)
    print("\nTesting CrossTaskSearchTool (Summarization)...")
    # We need a real auxiliary model for this to work in a real test, 
    # but we can at least check if the tool calls the summarizer.
    from backend.app.agent.tools_search_ext import CrossTaskSearchTool
    tool = CrossTaskSearchTool(agent_service=agent)
    
    # Mocking the summarizer response if no real API key provided
    if os.getenv("AUX_MODEL_KEY") == "placeholder" or not os.getenv("AUX_MODEL_KEY"):
         print("Note: Skipping real LLM summarization check due to missing API keys.")
    else:
         report = await tool._arun(query="What was the fix for P2P delay?")
         print(f"Tool Report:\n{report}")
         if "P2P" in report:
             print("✅ SUCCESS: Tool generated the summary report.")

    # Cleanup
    if os.path.exists(test_file):
        os.remove(test_file)
    print("\n--- Test Finished ---")

if __name__ == "__main__":
    asyncio.run(test_universal_search_logic())
