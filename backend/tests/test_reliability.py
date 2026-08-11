import asyncio
import logging
import os
import sys
from unittest.mock import AsyncMock, patch

# Add current directory to path
sys.path.append(os.getcwd())

# Mock modules before import
from unittest.mock import MagicMock


def setup_mocks():
    mock_aiortc = MagicMock()
    mock_aiortc.__path__ = []
    sys.modules["aiortc"] = mock_aiortc
    sys.modules["aiortc.contrib"] = MagicMock()
    sys.modules["aiortc.contrib.signaling"] = MagicMock()

    sys.modules["v8py"] = MagicMock()

    mock_apscheduler = MagicMock()
    sys.modules["apscheduler"] = mock_apscheduler
    sys.modules["apscheduler.schedulers"] = MagicMock()
    sys.modules["apscheduler.schedulers.asyncio"] = MagicMock()
    sys.modules["apscheduler.jobstores"] = MagicMock()
    sys.modules["apscheduler.jobstores.sqlalchemy"] = MagicMock()
    sys.modules["apscheduler.executors"] = MagicMock()
    sys.modules["apscheduler.executors.pool"] = MagicMock()

    sys.modules["langchain_openai"] = MagicMock()
    sys.modules["langchain_core"] = MagicMock()
    sys.modules["langchain_core.prompts"] = MagicMock()
    sys.modules["langchain_core.messages"] = MagicMock()

    # Mock ResidentMemory and Ledger to avoid DB/File issues
    sys.modules["app.services.resident_link"] = MagicMock()
    sys.modules["app.p2p_community.economy"] = MagicMock()
    sys.modules["app.p2p_community.reputation"] = MagicMock()
    sys.modules["app.p2p_community.blockchain"] = MagicMock()
    sys.modules["app.services.memory_store"] = MagicMock()
    sys.modules["app.services.knowledge_base"] = MagicMock()
    sys.modules["app.services.consolidation"] = MagicMock()
    sys.modules["app.services.task_manager"] = MagicMock()


setup_mocks()

from app.services.agent_service import AgentService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_reliability_success():
    logger.info("Testing reliability success path...")

    with patch("app.services.agent_service.p2p_service") as mock_p2p:
        mock_p2p._initialized = True
        mock_p2p.get_network_status.return_value = {"nodes": {}}
        # Mock WebRTC fail, HTTP success
        mock_p2p.webrtc_manager.send_message = AsyncMock(return_value=False)
        mock_p2p.send_message = AsyncMock(return_value=True)

        agent = AgentService()
        agent.message_bus = AsyncMock()

        target_id = "test_peer"
        content = "Hello reliable world"

        # We need to bypass compliance check or mock it
        agent._check_compliance = AsyncMock(return_value=(True, ""))

        result = await agent.send_p2p_message(target_id, content)

        logger.info(f"Result: {result}")

        # Verify status in history
        last_msg = agent.history[-1]
        logger.info(f"Last message status in history: {last_msg.status}")

        if last_msg.status == "sent":
            logger.info("SUCCESS: Message status updated to 'sent'")
        else:
            logger.error(f"FAILURE: Expected 'sent', got '{last_msg.status}'")

        # Verify gateway broadcast for status_update
        calls = agent.message_bus.publish_outbound.call_args_list
        status_updates = [c[0][0] for c in calls if c[0][0].type == "status_update"]

        if status_updates and status_updates[0].metadata["status"] == "sent":
            logger.info("SUCCESS: Broadcasted status_update='sent' to gateway")
        else:
            logger.error("FAILURE: Missing or incorrect status_update broadcast")


async def test_reliability_failure():
    logger.info("\nTesting reliability failure path...")

    with patch("app.services.agent_service.p2p_service") as mock_p2p:
        mock_p2p._initialized = True
        mock_p2p.get_network_status.return_value = {"nodes": {}}
        # Mock both fail
        mock_p2p.webrtc_manager.send_message = AsyncMock(return_value=False)
        mock_p2p.send_message = AsyncMock(return_value=False)

        agent = AgentService()
        agent.message_bus = AsyncMock()
        agent._check_compliance = AsyncMock(return_value=(True, ""))

        target_id = "test_peer_fail"
        content = "Goodbye reliable world"

        result = await agent.send_p2p_message(target_id, content)

        logger.info(f"Result: {result}")

        # Verify status in history
        last_msg = agent.history[-1]
        logger.info(f"Last message status in history: {last_msg.status}")

        if last_msg.status == "failed":
            logger.info("SUCCESS: Message status updated to 'failed'")
        else:
            logger.error(f"FAILURE: Expected 'failed', got '{last_msg.status}'")

        # Verify gateway broadcast
        calls = agent.message_bus.publish_outbound.call_args_list
        status_updates = [c[0][0] for c in calls if c[0][0].type == "status_update"]

        if status_updates and status_updates[0].metadata["status"] == "failed":
            logger.info("SUCCESS: Broadcasted status_update='failed' to gateway")
        else:
            logger.error("FAILURE: Missing or incorrect status_update broadcast")


async def main():
    await test_reliability_success()
    await test_reliability_failure()


if __name__ == "__main__":
    asyncio.run(main())
