import unittest
import os
import sqlite3
import sys
from datetime import datetime

# Adjust path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.services.bootstrap_storage import BootstrapStorage
from app.p2p_community.bootstrap_client import GroupInfo, PeerAddress, NodeRegistration

class TestBootstrapStorage(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_bootstrap.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.storage = BootstrapStorage(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                pass # Windows file lock sometimes

    def test_group_persistence(self):
        group = GroupInfo(
            group_id="g1",
            level=1,
            member_count=5,
            max_capacity=10,
            has_space=True,
            name="Test Group",
            core_node_ids=["n1", "n2"],
            node_rankings=["n1", "n2", "n3", "n4", "n5"]
        )
        self.storage.upsert_group(group)
        
        # Reload
        groups = self.storage.load_groups()
        self.assertIn("g1", groups)
        loaded = groups["g1"]
        self.assertEqual(loaded.name, "Test Group")
        self.assertEqual(loaded.core_node_ids, ["n1", "n2"])
        self.assertEqual(loaded.node_rankings, ["n1", "n2", "n3", "n4", "n5"])

    def test_node_persistence(self):
        node = PeerAddress(
            node_id="n1",
            public_key="pk1",
            ip_address="127.0.0.1",
            port=8000,
            name="Alice",
            last_seen=datetime.now()
        )
        self.storage.upsert_node(node)
        
        nodes = self.storage.load_nodes()
        self.assertIn("n1", nodes)
        self.assertEqual(nodes["n1"].name, "Alice")

    def test_membership(self):
        # Setup foreign keys first
        self.storage.upsert_group(GroupInfo("g1", 1, 0, 10))
        self.storage.upsert_node(PeerAddress("n1", "pk", "ip", 80))
        
        self.storage.add_group_member("g1", "n1")
        
        members = self.storage.load_group_members()
        self.assertIn("g1", members)
        self.assertIn("n1", members["g1"])
        
        self.storage.remove_group_member("g1", "n1")
        members = self.storage.load_group_members()
        # Either key gone or empty set depending on impl
        if "g1" in members:
            self.assertNotIn("n1", members["g1"])

    def test_pending_joins(self):
        reg = NodeRegistration("n2", "pk2", "ip", 90, "g1", "Bob")
        self.storage.add_pending_join("g1", reg)
        
        pending = self.storage.load_pending_joins()
        self.assertIn("g1", pending)
        self.assertEqual(pending["g1"][0].node_id, "n2")
        self.assertEqual(pending["g1"][0].name, "Bob")
        
        self.storage.remove_pending_join("g1", "n2")
        pending = self.storage.load_pending_joins()
        if "g1" in pending:
            self.assertEqual(len(pending["g1"]), 0)

if __name__ == '__main__':
    unittest.main()
