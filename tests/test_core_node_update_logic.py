import os

# Ensure project root is in path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.append(os.getcwd())


class TestCoreNodeUpdateLogic(unittest.IsolatedAsyncioTestCase):
    async def test_group_core_node_update_logic(self):
        print("\n--- Testing Service Layer ---")
        # 1. Setup Mocks
        import backend.app.services.p2p_service as p2p_mod
        from backend.app.p2p_community.models import Group
        from backend.app.services.group_service import GroupService

        with patch.object(p2p_mod, "p2p_service") as mock_p2p:
            mock_network = MagicMock()
            mock_network.broadcast_group_config = AsyncMock(return_value=True)
            mock_p2p.network_manager = mock_network
            mock_p2p.local_node = MagicMock(node_id="node_a")

            # Mock Group
            group_id = "test_group_123"
            test_group = Group(group_id, level=1)
            mock_network.get_group.return_value = test_group

            # Patch BootstrapClient instance correctly
            import backend.app.p2p_community.bootstrap_client as bc_mod

            with patch.object(
                bc_mod.bootstrap_client, "set_core_nodes", new_callable=AsyncMock
            ) as mock_set_core:
                mock_set_core.return_value = True

                # 2. Execute Update via Service
                service = GroupService()
                new_cores = ["node_b", "node_c"]
                print(f"Calling update_core_nodes for {group_id}...")

                success = await service.update_core_nodes(group_id, new_cores)

                # 3. Assertions
                self.assertTrue(success, "Service logic failed or was blocked.")

                # Check Local Model Update
                print("Verifying local model update (Order Check)...")
                self.assertEqual(test_group.core_node_ids, new_cores)
                print(f"Core Nodes: {test_group.core_node_ids}")

                # Check Broadcast call
                print("Verifying P2P broadcast...")
                mock_network.broadcast_group_config.assert_called_once()

        print("✅ Service Layer Update Logic: SUCCESS")

    async def test_governance_ingestion_logic(self):
        print("\n--- Testing Governance Ingestion ---")
        from backend.app.p2p_community.governance import GovernanceManager

        # Use a safe temporary path
        temp_dir = os.environ.get("TEMP", "C:/Temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, "gov_vfinal_test.json")

        gm = GovernanceManager("local_node", storage_path=temp_path)

        mock_group = MagicMock()
        mock_network = MagicMock()
        mock_network.get_group.return_value = mock_group

        # Patch the agent_service inside the governance module specifically
        # because it uses a local import inside receive_p2p_event
        # We also need to patch the singleton globally to be sure
        import backend.app.services.agent_service as as_mod

        with patch.object(as_mod, "agent_service") as mock_agent_service:
            mock_agent_service.p2p_service.network_manager = mock_network

            # Since receive_p2p_event does 'from ..services.agent_service import agent_service'
            # we also patch it in the governance namespace
            with patch(
                "backend.app.p2p_community.governance.agent_service",
                mock_agent_service,
                create=True,
            ):
                # 2. Simulate receiving a GROUP_CONFIG event
                config_content = {"group_id": "group_1", "core_node_ids": ["node_x", "node_y"]}

                print("Simulating P2P group_config event...")
                success = gm.receive_p2p_event("group_config", config_content)

                # 3. Assertions
                self.assertTrue(success)
                mock_group.update_core_nodes.assert_called_once_with(["node_x", "node_y"])

        # Cleanup
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

        print("✅ Governance Ingestion Logic: SUCCESS")


if __name__ == "__main__":
    import logging

    logging.getLogger("backend").setLevel(logging.ERROR)
    unittest.main()
