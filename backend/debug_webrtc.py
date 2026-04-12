import asyncio
import logging
from typing import Any

from app.services.webrtc_service import WebRTCManager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("webrtc_debug")


class MockNode:
    def __init__(self, node_id):
        self.node_id = node_id


class MockP2PService:
    def __init__(self, node_id):
        self.local_node = MockNode(node_id)
        self._initialized = True


class SignalingBridge:
    def __init__(self):
        self.managers: dict[str, WebRTCManager] = {}

    def register(self, node_id: str, manager: WebRTCManager):
        self.managers[node_id] = manager

    async def send_signaling(self, sender_id: str, msg_type: str, content: dict[str, Any]):
        target_id = "node_b" if sender_id == "node_a" else "node_a"
        recipient = self.managers.get(target_id)
        if not recipient:
            return

        logger.info(f"SIGNALING: {sender_id} -> {target_id} [{msg_type}]")

        async def dispatch():
            import app.services.p2p_service

            app.services.p2p_service.p2p_service = MockP2PService(target_id)
            if msg_type == "sdp_offer":
                await recipient.handle_offer(sender_id, content)
            elif msg_type == "sdp_answer":
                await recipient.handle_answer(sender_id, content)
            elif msg_type == "ice_candidate":
                await recipient.handle_candidate(sender_id, content)

        asyncio.create_task(dispatch())


async def run_test():
    bridge = SignalingBridge()

    def msg_callback(peer_id, msg):
        logger.info(f"RECEIVED MESSAGE from {peer_id}: {msg}")

    # Initialize Node A
    async def sig_a(target, mtype, content):
        await bridge.send_signaling("node_a", mtype, content)

    manager_a = WebRTCManager(sig_a, msg_callback)
    manager_a.set_loop(asyncio.get_running_loop())
    bridge.register("node_a", manager_a)

    # Initialize Node B
    async def sig_b(target, mtype, content):
        await bridge.send_signaling("node_b", mtype, content)

    manager_b = WebRTCManager(sig_b, msg_callback)
    manager_b.set_loop(asyncio.get_running_loop())
    bridge.register("node_b", manager_b)

    logger.info("Nodes initialized. Starting GLARE connection (A and B initiate simultaneously)...")

    # Start connection from both sides simultaneously to trigger glare
    await asyncio.gather(
        manager_a.initiate_connection("node_b"), manager_b.initiate_connection("node_a")
    )

    # Wait for completion or timeout
    for _ in range(30):
        await asyncio.sleep(1)
        # Check if both have data channels open
        a_open = (
            "node_b" in manager_a.data_channels
            and manager_a.data_channels["node_b"].readyState == "open"
        )
        b_open = (
            "node_a" in manager_b.data_channels
            and manager_b.data_channels["node_a"].readyState == "open"
        )

        if a_open and b_open:
            logger.info("!!! TEST SUCCESS: BOTH DATA CHANNELS OPEN !!!")
            # Try sending a message
            chan_a = manager_a.data_channels["node_b"]
            chan_a.send("Hello from A")
            await asyncio.sleep(1)
            break
    else:
        logger.error("TEST FAILED: Timeout waiting for data channels")

    # Final cleanup
    for pc in list(manager_a.pcs.values()) + list(manager_b.pcs.values()):
        await pc.close()


if __name__ == "__main__":
    asyncio.run(run_test())
