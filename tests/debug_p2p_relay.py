import asyncio
import logging
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.p2p_community.message_protocol import MessageProtocol, MessageType
from backend.app.p2p_community.models import Node
from backend.app.p2p_community.network_manager import NetworkManager
from backend.app.services.crypto_service import CryptoService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("DebugP2P")


async def test_relay_loopback():
    logger.info("--- Starting P2P Relay Loopback Test ---")

    # 1. Setup Services
    crypto = CryptoService()
    if not os.path.exists("backend/keys/private_key.pem"):
        crypto.generate_keys()

    protocol = MessageProtocol(crypto)
    network = NetworkManager(protocol)

    # 2. Initialize Identity
    node_id = crypto.get_node_id()
    network.local_node_id = node_id
    # Create local node object
    network.nodes[node_id] = Node(node_id, network, crypto.get_public_key_string())

    logger.info(f"Local Node ID: {node_id}")

    # 3. Setup Relay Client manually (skip full bootstrap to avoid port binding)
    from backend.app.p2p_community.bootstrap_client import bootstrap_client
    from backend.app.p2p_community.relay_client import RelayClient

    # Explicitly verify we can connect to default bootstrap
    logger.info(f"Connecting to Relay Server at {bootstrap_client.server_url}...")

    network.relay_client = RelayClient(
        server_url=bootstrap_client.server_url,
        node_id=node_id,
        message_handler=network.handle_relayed_message,
        verify_ssl=False,
    )

    await network.relay_client.start()

    # Wait for connection
    connected = False
    for _ in range(5):
        if network.relay_client.websocket:
            connected = True
            break
        await asyncio.sleep(1)

    if not connected:
        logger.error("❌ Relay Client FAILED to connect via WebSocket.")
        return
    else:
        logger.info("✅ Relay Client Connected via WebSocket.")

    # 4. Send Message to Self via Relay
    target_id = node_id
    content = {"text": "Loopback Test Message", "timestamp": str(datetime.now())}

    msg = protocol.create_message(node_id, target_id, MessageType.DIRECT, content)

    logger.info(f"Sending message {msg.message_id} to SELF via RELAY...")

    try:
        await network.relay_client.send(msg.to_dict())
        logger.info("Message sent to Relay Server.")
    except Exception as e:
        logger.error(f"Failed to send: {e}")
        return

    # 5. Wait for Recv
    logger.info("Waiting 10s for message to return...")

    start_time = datetime.now()
    found = False

    while (datetime.now() - start_time).seconds < 10:
        node = network.nodes.get(node_id)
        if node and node.inbox:
            # Check inbox
            for m in node.inbox:
                if m.get("message_id") == msg.message_id:
                    logger.info("✅ SUCCESS: Loopback message received!")
                    logger.info(f"Content: {m.get('content')}")
                    found = True
                    break
        if found:
            break
        await asyncio.sleep(0.5)
        print(".", end="", flush=True)

    # Stop client
    await network.relay_client.stop()

    if not found:
        logger.error("\n❌ TIMEOUT: Loopback message NOT received.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_relay_loopback())
