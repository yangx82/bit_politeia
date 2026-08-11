import os
import sys
from pathlib import Path

# Add backend to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(project_root, "backend"))

from app.services.resident_memory_service import ResidentMemory


def test_memory_read():
    print("Testing ResidentMemory read for GIT REPO...")

    # Target D:\git\bit_politeia\backend
    git_backend = Path("D:/git/bit_politeia/backend")

    if not git_backend.exists():
        print(f"Error: {git_backend} does not exist.")
        return

    # Initialize implementation pointing to git backend
    mem = ResidentMemory(workspace_root=str(git_backend))
    print(f"Memory Dir: {mem.memory_dir}")

    history = mem.get_all_history()
    print(f"Total History Items: {len(history)}")

    print("\n--- Last 10 Items ---")
    for item in history[-10:]:
        print(f"[{item.get('timestamp')}] {item.get('sender')}: {item.get('content')[:50]}...")


if __name__ == "__main__":
    test_memory_read()
