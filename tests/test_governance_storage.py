import asyncio
import os
from pathlib import Path

from backend.app.services.memory_store import MemoryStore


async def test_governance_injection():
    # 1. Setup paths
    workspace = Path(os.getcwd()) / "backend"
    memory_dir = workspace / "memory"
    rules_dir = memory_dir / "rules"
    directives_dir = memory_dir / "directives"

    # 2. Create mock files
    rules_file = rules_dir / "test_rules.md"
    directive_file = directives_dir / "test_order.md"

    rules_content = "1. All bots must report to the core node.\n2. Do not reveal secrets."
    directive_content = "Execute Phase 3 immediately."

    os.makedirs(rules_dir, exist_ok=True)
    os.makedirs(directives_dir, exist_ok=True)

    rules_file.write_text(rules_content, encoding="utf-8")
    directive_file.write_text(directive_content, encoding="utf-8")

    print(f"Created: {rules_file}")
    print(f"Created: {directive_file}")

    # 3. Initialize MemoryStore and verify
    store = MemoryStore(workspace_root=str(workspace))
    context = store.get_memory_context()

    print("\n--- Generated Memory Context ---")
    print(context)
    print("--------------------------------\n")

    # Assertions
    assert "COMMUNITY RULES & STATUTES" in context
    assert "ACTIVE DIRECTIVES & ORDERS" in context
    assert rules_content in context
    assert directive_content in context

    print("Verification SUCCESS: Rules and Directives successfully injected into context.")


if __name__ == "__main__":
    asyncio.run(test_governance_injection())
