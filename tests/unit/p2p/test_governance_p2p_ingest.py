"""
Unit tests for P2P governance proposal ingestion and deserialization resilience in Bit Politeia.
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
from datetime import datetime, timezone
from app.p2p_community.governance import GovernanceManager, Proposal


class TestGovernanceP2PIngest(unittest.TestCase):

    def setUp(self):
        self.gov_mgr = GovernanceManager(node_id="test_node")

    def test_proposal_from_dict_robustness(self):
        """Test Proposal.from_dict safely handles missing or alternate key names."""
        raw_proposal = {
            "proposal_id": "prop_999",
            "initiator_id": "node_abc",
            # Missing group_id!
            "title": "Upgrade network protocol",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        prop = Proposal.from_dict(raw_proposal)
        self.assertEqual(prop.proposal_id, "prop_999")
        self.assertEqual(prop.initiator_id, "node_abc")
        self.assertEqual(prop.group_id, "global")  # Safe fallback
        self.assertEqual(prop.content, "Upgrade network protocol")  # Title mapped to content

    def test_receive_p2p_event_proposal_ingestion(self):
        """Test receive_p2p_event successfully ingests wrapped proposal payload."""
        payload = {
            "proposal": {
                "proposal_id": "99040f87-835f-48dd-99f3-6b2f93cafdce",
                "initiator_id": "5a40d9e65ff88c11a22fe5bd35c7b4f8f9efe4792b1026b3538aaed52fb4cdfa",
                "text": "Optimize P2P dispatching"
            }
        }

        success = self.gov_mgr.receive_p2p_event("proposal", payload)
        self.assertTrue(success)
        self.assertIn("99040f87-835f-48dd-99f3-6b2f93cafdce", self.gov_mgr.proposals)
        stored_prop = self.gov_mgr.proposals["99040f87-835f-48dd-99f3-6b2f93cafdce"]
        self.assertEqual(stored_prop.content, "Optimize P2P dispatching")


if __name__ == "__main__":
    unittest.main()
