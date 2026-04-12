import asyncio
import sys
from pathlib import Path

# Fix path to import app
sys.path.append(str(Path(__file__).resolve().parent.parent))


async def test_archiving():
    print("Testing Block Archiving Logic...")
    from app.services.agent_service import agent_service

    # Manually trigger archiving
    result = await agent_service.run_archiving()
    print(f"Result: {result}")

    # Check blockchain file
    db_path = Path("backend/data/blockchain.json")
    if db_path.exists():
        import json

        with open(db_path) as f:
            data = json.load(f)
            print(f"Current chain length: {len(data.get('chain', []))}")
    else:
        print("Blockchain file not found.")


if __name__ == "__main__":
    asyncio.run(test_archiving())
