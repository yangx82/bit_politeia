import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import os
import sys

# Ensure project root is in path
sys.path.append(os.getcwd())

from backend.app.services.group_service import GroupService

class TestMembershipAdmissionLogic(unittest.IsolatedAsyncioTestCase):
    async def test_apply_and_approve_logic(self):
        print("\n--- Testing Membership Admission Logic ---")
        
        # 1. Setup Mocks
        import backend.app.services.p2p_service as p2p_mod
        with patch.object(p2p_mod, "p2p_service") as mock_p2p:
            mock_network = MagicMock()
            mock_network.broadcast_group_config = AsyncMock(return_value=True)
            mock_p2p.network_manager = mock_network
            mock_p2p.local_node = MagicMock(node_id="applicant_node_1")
            
            # Mock BootstrapClient
            import backend.app.p2p_community.bootstrap_client as bc_mod
            with patch.object(bc_mod.bootstrap_client, "request_join", new_callable=AsyncMock) as mock_request:
                mock_request.return_value = True
                
                service = GroupService()
                
                # Test Application
                print("Testing apply_to_join...")
                res = await service.apply_to_join("group_A", "I want to contribute.")
                self.assertTrue(res)
                mock_request.assert_called_once_with("group_A", "applicant_node_1", "I want to contribute.")
                
            with patch.object(bc_mod.bootstrap_client, "get_pending_joins", new_callable=AsyncMock) as mock_list:
                mock_list.return_value = [{"node_id": "applicant_node_1", "reason": "test"}]
                
                # Test Listing
                print("Testing get_pending_requests...")
                pending = await service.get_pending_requests("group_A")
                self.assertEqual(len(pending), 1)
                self.assertEqual(pending[0]["node_id"], "applicant_node_1")
                
            with patch.object(bc_mod.bootstrap_client, "approve_join", new_callable=AsyncMock) as mock_approve:
                mock_approve.return_value = True
                
                # Switch identity to core node
                mock_p2p.local_node.node_id = "core_node_admin"
                
                # Test Approval
                print("Testing approve_member...")
                res = await service.approve_member("group_A", "applicant_node_1")
                self.assertTrue(res)
                mock_approve.assert_called_once_with("group_A", "applicant_node_1", "core_node_admin")
                
                # Verify Broadcast
                print("Verifying P2P broadcast after approval...")
                mock_network.broadcast_group_config.assert_called_once()

        print("✅ Membership Admission Logic: SUCCESS")

if __name__ == "__main__":
    unittest.main()
