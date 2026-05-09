import pytest

from app.services.crypto_service import crypto_service
from backend.app.p2p_community.message_protocol import MessageProtocol, MessageType
from backend.app.p2p_community.models import Group, Node
from backend.app.p2p_community.network_manager import NetworkManager


# Mock Bootstrap
class MockBootstrap:
    def __init__(self):
        self.peers = {}  # node_id -> public_key

    async def get_network_topology(self):
        return {}

    async def register_node(self, registration):
        # Store public key for lookup test
        self.peers[registration.node_id] = registration.public_key
        pass

    async def get_joinable_groups(self, preferred_level=1):
        return []

    async def get_node_public_key(self, node_id: str):
        return self.peers.get(node_id)


@pytest.fixture
def message_protocol():
    return MessageProtocol(crypto_service)


@pytest.fixture
def network_manager(message_protocol):
    nm = NetworkManager(message_protocol)
    nm.bootstrap = MockBootstrap()  # Override with simple mock
    return nm


@pytest.mark.asyncio
async def test_group_hierarchy_constraints(network_manager):
    """
    Test that a node cannot join an invalid configuration of groups.
    Rule: Max 2 groups, must be directly connected.
    """
    # Setup Hierarchy: Root -> G1 -> G1_1
    root = Group("root", 0, None)
    g1 = Group("g1", 1, "root")
    g1_1 = Group("g1_1", 2, "g1")
    g_other = Group("other", 1, "root")  # Sibling to g1

    root.add_child("g1")
    g1.add_child("g1_1")

    network_manager.groups = {"root": root, "g1": g1, "g1_1": g1_1, "other": g_other}

    # Create Node
    pk = crypto_service.get_public_key_string()
    node = Node("node1", network_manager, pk)
    network_manager.nodes["node1"] = node

    # 1. Join first group (G1) - Should succeed
    assert await node.join_group("g1") is True
    assert "g1" in node.group_ids

    # 2. Join child group (G1_1) - Should succeed (Adjacent)
    assert await node.join_group("g1_1") is True
    assert "g1_1" in node.group_ids

    # 3. Join third group (Other) - Should fail (Max 2 groups)
    assert await node.join_group("other") is False
    assert "other" not in node.group_ids

    # Reset
    node.group_ids.clear()
    node.group_ids.add("g1")

    # 4. Join non-adjacent group (Other) while in G1 - Should fail (Not adjacent)
    # G1 (parent=root, children=g1_1). Other (parent=root).
    # They share parent, but are not parent/child of each other.
    assert await node.join_group("other") is False


@pytest.mark.asyncio
async def test_message_signing_flow(network_manager):
    """
    Test message creation, signing, and local routing.
    """
    pk = crypto_service.get_public_key_string()
    node1 = Node("node1", network_manager, pk)
    node2 = Node("node2", network_manager, pk)  # Sharing PK for simplicity in test

    network_manager.nodes["node1"] = node1
    network_manager.nodes["node2"] = node2

    message_content = {"text": "Hello P2P"}

    # Send Direct Message
    await network_manager.send_signed_message(
        sender_id="node1", target_id="node2", msg_type="direct", content=message_content
    )

    # Check Inbox
    assert len(node2.inbox) == 1
    msg = node2.inbox[0]
    assert msg["content"]["text"] == "Hello P2P"
    assert msg["sender_id"] == "node1"
    assert "signature" in msg
    assert msg["signature"] != ""


@pytest.mark.asyncio
async def test_public_key_resolution(network_manager):
    """
    Test that NetworkManager resolves public key via Bootstrap when sender is unknown locally.
    """
    pk_sender = crypto_service.get_public_key_string()
    sender_id = "external_node_uuid"

    # Register sender in Bootstrap (but NOT in network_manager.nodes)
    network_manager.bootstrap.peers[sender_id] = pk_sender

    content = {"text": "Hello from outside"}
    signed_msg = network_manager.message_protocol.create_message(
        sender_id=sender_id,
        recipient_id="local_node",
        message_type=MessageType.DIRECT,
        content=content,
    )

    # Ensure local node exists to receive it
    pk_local = crypto_service.get_public_key_string()
    local_node = Node("local_node", network_manager, pk_local)
    network_manager.nodes["local_node"] = local_node

    # Route message
    await network_manager.route_message(signed_msg)

    # Check if received
    assert len(local_node.inbox) == 1
    assert local_node.inbox[0]["sender_id"] == sender_id
    assert local_node.inbox[0]["content"]["text"] == "Hello from outside"
