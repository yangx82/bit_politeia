
import asyncio
import sys
import os
import json
from datetime import datetime
import uuid

# Add backend to path explicitly
backend_path = os.path.join(os.getcwd(), 'backend')
if backend_path not in sys.path:
    sys.path.append(backend_path)

# Mocking env vars for safe init
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

try:
    from app.services.agent_service import agent_service
    from app.models.schemas import Message
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

async def test_history():
    print("AgentService Instance Loaded.")
    
    # 1. Check if history is populated (assuming backend reused same persistence or we mock it)
    history = await agent_service.get_history()
    print(f"Current History Length: {len(history)}")
    
    # 2. Add a test message if empty
    if not history:
        print("Adding mock message...")
        mock_msg = Message(
            id=str(uuid.uuid4()),
            content="Debug Message",
            sender="peer_debug",
            timestamp=datetime.now(),
            session_id="peer_debug"
        )
        agent_service.history.append(mock_msg)
        history = [mock_msg]

    # 3. Simulate Pydantic JSON dump
    print("\n[JSON Serialization Test]")
    try:
        # Pydantic v2 use model_dump, v1 use dict()
        json_data = [m.model_dump() if hasattr(m, 'model_dump') else m.dict() for m in history]
        print(json.dumps(json_data[:2], default=str, indent=2))
        
        # 4. Check session_id specifically
        first_msg = json_data[0]
        if 'session_id' in first_msg:
            print(f"\nSUCCESS: session_id found: {first_msg['session_id']}")
        else:
            print("\nFAILURE: session_id MISSING in JSON output!")
            
    except Exception as e:
        print(f"Serialization Error: {e}")

if __name__ == "__main__":
    # We need to run this in a way that respects the async nature
    asyncio.run(test_history())
