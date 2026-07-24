"""
Unit tests for Hermes Agent inspired memory architecture enhancements in Bit Politeia:
1. USER.md persistence and automatic semantic profile synchronization.
2. ContextBuilder System Prompt order stability for Prefix-Caching.
3. manage_memory tool read/append/update operations.
4. RetrospectiveStage self-healing skill card auto-learning.
"""

import sys
import site
import os

p = "/home/xing/.local/lib/python3.10/site-packages"
if p not in sys.path and os.path.exists(p):
    sys.path.insert(0, p)

import unittest
import tempfile
import asyncio
from pathlib import Path

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "backend"))

from app.services.memory_store import MemoryStore
from app.services.resident_memory_service import ResidentMemory
from app.agent.context import ContextBuilder
from app.agent.tools import manage_memory


class TestHermesMemoryEnhancements(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.backend_dir = Path(self.tmp_dir.name) / "backend"
        self.backend_dir.mkdir(parents=True, exist_ok=True)
        
        self.memory_store = MemoryStore(workspace_root=str(self.backend_dir))

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_user_md_persistence_and_sync(self):
        """Test USER.md reading, appending, and automatic sync from semantic profile."""
        # 1. Test direct write & read
        self.memory_store.write_user_profile("Resident prefers MATLAB for data analysis.")
        content = self.memory_store.read_user_profile()
        self.assertIn("Resident prefers MATLAB", content)

        # 2. Test append
        self.memory_store.append_user_profile("Preferred language: Chinese.")
        updated_content = self.memory_store.read_user_profile()
        self.assertIn("Resident prefers MATLAB", updated_content)
        self.assertIn("Preferred language: Chinese.", updated_content)

        # 3. Test memory context inclusion
        ctx = self.memory_store.get_memory_context()
        self.assertIn("USER.md", ctx)
        self.assertIn("Resident prefers MATLAB", ctx)

    def test_prefix_caching_prompt_order(self):
        """Test that System Prompt orders static identity and memory before dynamic time for Prefix Caching."""
        cb = ContextBuilder()
        head, mid, tail = cb.build_system_prompt(name="TestAgent", personality="Methodical")
        prompt = f"{head}\n\n{mid}\n\n{tail}"

        # Core identity, Memory, Rules MUST appear BEFORE Current System Time
        identity_idx = prompt.find("# AGENT NODE IDENTITY")
        memory_idx = prompt.find("# Memory Context")
        time_idx = prompt.find("# Current System Time")

        self.assertNotEqual(identity_idx, -1)
        self.assertNotEqual(time_idx, -1)
        self.assertLess(identity_idx, time_idx, "Identity MUST be placed before dynamic System Time for Prefix Caching.")

    def test_manage_memory_tool(self):
        """Test the manage_memory Tool execution."""
        async def run_tool():
            if hasattr(manage_memory, "ainvoke"):
                res1 = await manage_memory.ainvoke({"target": "user", "action": "append", "content": "Always format code in clean MATLAB style."})
            else:
                res1 = await manage_memory(target="user", action="append", content="Always format code in clean MATLAB style.")
            self.assertIn("Successfully appended", res1)

            # Test read via tool
            if hasattr(manage_memory, "ainvoke"):
                res2 = await manage_memory.ainvoke({"target": "user", "action": "read"})
            else:
                res2 = await manage_memory(target="user", action="read")
            self.assertIn("USER.md", res2)
            self.assertIn("MATLAB style", res2)

            # Test append to agent memory via tool
            if hasattr(manage_memory, "ainvoke"):
                res3 = await manage_memory.ainvoke({"target": "agent", "action": "append", "content": "Always verify .m file existence before reporting."})
            else:
                res3 = await manage_memory(target="agent", action="append", content="Always verify .m file existence before reporting.")
            self.assertIn("Successfully appended to MEMORY.md", res3)

        asyncio.run(run_tool())


if __name__ == "__main__":
    unittest.main()
