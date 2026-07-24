"""
Unit tests for Bit Politeia Prefix-Caching Prompt Optimization:
1. Static and Semi-Static Prompt byte-level prefix parity across requests.
2. MemoryStore snapshotting and dirty-flag cache invalidation.
3. SkillManager deterministic sorted index snapshotting.
"""

import sys
import site
import os

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "backend"))

import unittest
import time
from app.agent.context import ContextBuilder
from app.services.memory_store import MemoryStore
from app.services.skill_manager import SkillManager


class TestPrefixCachingOptimization(unittest.TestCase):

    def setUp(self):
        self.context_builder = ContextBuilder()

    def test_system_prompt_static_head_parity(self):
        """Test that static_head and semi_static_mid remain 100% byte-level identical across time steps."""
        head1, mid1, tail1 = self.context_builder.build_system_prompt(name="PoliteiaAgent", channel="resident")
        time.sleep(0.01)  # Ensure system clock advances
        head2, mid2, tail2 = self.context_builder.build_system_prompt(name="PoliteiaAgent", channel="resident")

        # Static Head & Semi-Static Mid MUST be 100% identical for Prefix Caching
        self.assertEqual(head1, head2)
        self.assertEqual(mid1, mid2)

        # Dynamic Tail SHOULD reflect time changes
        self.assertIn("Current System Time", tail1)
        self.assertIn("Current System Time", tail2)

    def test_memory_store_snapshot_caching(self):
        """Test MemoryStore uses in-memory snapshot cache and invalidates on update."""
        mem_store = MemoryStore()
        mem_store.write_long_term("Initial Core Memory")

        # 1. First fetch compiles snapshot
        ctx1 = mem_store.get_memory_context()
        self.assertIn("Initial Core Memory", ctx1)
        self.assertFalse(mem_store._dirty_flag)

        # 2. Second fetch returns exact cached instance
        ctx2 = mem_store.get_memory_context()
        self.assertIs(ctx1, ctx2)

        # 3. Writing new content invalidates cache
        mem_store.write_long_term("Updated Core Memory")
        self.assertTrue(mem_store._dirty_flag)

        ctx3 = mem_store.get_memory_context()
        self.assertIn("Updated Core Memory", ctx3)
        self.assertIsNot(ctx1, ctx3)

    def test_skill_manager_sorted_index_parity(self):
        """Test SkillManager produces deterministic sorted index for prefix caching."""
        sm = SkillManager()
        sm.get_skill_index()

        # Check that dirty_flag is set to False after first read
        self.assertFalse(sm._dirty_flag)

        index1 = sm.get_skill_index()
        index2 = sm.get_skill_index()
        self.assertIs(index1, index2)


if __name__ == "__main__":
    unittest.main()
