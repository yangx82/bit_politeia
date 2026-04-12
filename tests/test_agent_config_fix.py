import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.services.agent_service import AgentService


class TestAgentConfigFix(unittest.IsolatedAsyncioTestCase):
    async def test_configure_agent_reinit(self):
        """Test configure_agent when P2P service is ALREADY initialized (the bug case)."""
        service = AgentService()

        # Mock dependencies
        service.message_bus = AsyncMock()
        service.listen_to_bus = AsyncMock()

        with (
            patch("app.services.agent_service.p2p_service") as mock_p2p,
            patch("app.services.agent_service.crypto_service") as mock_crypto,
            patch("app.services.agent_service.ChatOpenAI") as MockChat,
        ):
            # Setup: P2P Service IS initialized
            mock_node = MagicMock()
            mock_node.node_id = "existing_node_123"
            mock_p2p.local_node = mock_node
            mock_p2p.update_node_info = AsyncMock()

            # Act
            await service.configure_agent("http://new-url", "new-key")

            # Assert
            mock_p2p.update_node_info.assert_called_once()
            mock_p2p.initialize.assert_not_called()

            # Verify node_id was correctly resolved for component init
            self.assertEqual(service.governance_manager.node_id, "existing_node_123")
            self.assertEqual(service.reputation_manager.node_id, "existing_node_123")

    async def test_configure_agent_first_run(self):
        """Test configure_agent when P2P service is NOT initialized (the normal case)."""
        service = AgentService()

        # Mock dependencies
        service.message_bus = AsyncMock()
        service.listen_to_bus = AsyncMock()

        with (
            patch("app.services.agent_service.p2p_service") as mock_p2p,
            patch("app.services.agent_service.crypto_service") as mock_crypto,
            patch("app.services.agent_service.ChatOpenAI") as MockChat,
        ):
            # Setup: P2P Service is NOT initialized
            mock_p2p.local_node = None
            mock_p2p.initialize = AsyncMock()
            mock_crypto.get_node_id.return_value = "new_node_456"

            # Act
            await service.configure_agent("http://new-url", "new-key")

            # Assert
            mock_p2p.update_node_info.assert_not_called()
            mock_p2p.initialize.assert_called_once()

            # Verify node_id was correctly resolved
            self.assertEqual(service.governance_manager.node_id, "new_node_456")


if __name__ == "__main__":
    unittest.main()
