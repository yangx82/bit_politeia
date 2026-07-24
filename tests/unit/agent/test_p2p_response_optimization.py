"""
Unit tests for P2P message response optimization in Bit Politeia:
1. P2P System Prompt contains RESPONSE MANDATE for queries.
2. NotifyStage fallback automatically invokes send_p2p_message when tool call was omitted.
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
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.agent.context import ContextBuilder
from app.agent.pipeline import NotifyStage, PipelineContext
from app.bus.events import InboundMessage
from app.models.session import Session


class TestP2PResponseOptimization(unittest.TestCase):

    def test_p2p_context_response_mandate(self):
        """Test ContextBuilder includes RESPONSE MANDATE for p2p channel."""
        cb = ContextBuilder()
        head, mid, tail = cb.build_system_prompt(name="P2PAgent", channel="p2p")

        self.assertIn("RESPONSE MANDATE", head)
        self.assertIn("ONLY output `[NO_RESPONSE_NEEDED]`", head)

    def test_notify_stage_p2p_fallback_delivery(self):
        """Test NotifyStage auto-routes final answer via send_p2p_message if tool call was omitted."""
        async def run_test():
            stage = NotifyStage()
            session = Session(session_id="peer_node_123", channel="p2p")
            msg = InboundMessage(
                channel="p2p",
                sender_id="peer_node_123",
                session_id="peer_node_123",
                content="Can you perform Tavily search?"
            )
            context = PipelineContext(session=session, input_message=msg)
            context.final_answer = "Yes, Tavily search is fully configured and supported."

            agent = MagicMock()
            agent.message_bus.publish_outbound = AsyncMock()
            agent.send_p2p_message = AsyncMock()

            await stage.run(context, agent)

            # Check that send_p2p_message fallback was triggered
            agent.send_p2p_message.assert_called_once_with(
                recipient_id="peer_node_123",
                content="Yes, Tavily search is fully configured and supported.",
                msg_type="direct"
            )

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
