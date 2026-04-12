import asyncio
import os
import sys

# Add backend to path explicitly
backend_path = os.path.join(os.getcwd(), "backend")
if backend_path not in sys.path:
    sys.path.append(backend_path)

# Mocking env vars for safe init
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

try:
    from app.services.agent_service import agent_service
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)


async def dump_history():
    print("AgentService Instance Loaded.")
    history = await agent_service.get_history()

    # Filter for resident chat messages
    resident_msgs = [m for m in history if m.session_id == "resident"]

    print(f"\n[Resident Messages Dump] (Count: {len(resident_msgs)})")
    # Show last 5
    for msg in resident_msgs[-5:]:
        data = msg.model_dump() if hasattr(msg, "model_dump") else msg.dict()
        print(
            f"Content: {data.get('content')[:30]}... | Sender: '{data.get('sender')}' | Type: {type(data.get('sender'))}"
        )


if __name__ == "__main__":
    asyncio.run(dump_history())
