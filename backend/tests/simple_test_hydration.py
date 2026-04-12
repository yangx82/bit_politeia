import json
import os
from pathlib import Path


def test_logic():
    print("Testing Atomic Hydration Logic...")
    node_id = "test_node"
    data_dir = Path("backend/data")
    p2p_dir = data_dir / "p2p"
    p2p_dir.mkdir(parents=True, exist_ok=True)

    inbox_path = p2p_dir / f"inbox_{node_id}.jsonl"
    proc_path = p2p_dir / f"inbox_{node_id}.jsonl.processing"

    # Clean up
    if inbox_path.exists():
        os.remove(inbox_path)
    if proc_path.exists():
        os.remove(proc_path)

    # 1. Create inbox
    test_msg = {"message_id": "m1", "content": "test"}
    with open(inbox_path, "w") as f:
        f.write(json.dumps(test_msg) + "\n")

    print(f"Inbox created: {inbox_path.name}")

    # 2. Simulate Hydration Logic
    if inbox_path.exists():
        if proc_path.exists():
            with open(proc_path, "a") as pf, open(inbox_path) as ifile:
                pf.write(ifile.read())
            os.remove(inbox_path)
        else:
            os.rename(inbox_path, proc_path)

    print(
        f"After Rename - Inbox exists: {inbox_path.exists()}, Processing exists: {proc_path.exists()}"
    )

    # 3. Read and Cleanup
    if proc_path.exists():
        messages = []
        with open(proc_path) as f:
            for line in f:
                messages.append(json.loads(line))

        print(f"Loaded {len(messages)} messages.")
        os.remove(proc_path)
        print(f"Processing file deleted: {not proc_path.exists()}")

    if len(messages) == 1 and not inbox_path.exists() and not proc_path.exists():
        print("\nSUCCESS: Core logic verified.")
    else:
        print("\nFAILURE.")


if __name__ == "__main__":
    test_logic()
