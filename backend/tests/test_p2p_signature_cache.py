# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime, timezone
try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc
import pytest

from app.services.crypto_service import CryptoService
from app.p2p_community.message_protocol import MessageProtocol, MessageType, SignedMessage
from app.p2p_community.models import Group, Node
from app.p2p_community.network_manager import NetworkManager


@pytest.mark.asyncio
async def test_disconnect_peer_preserves_node_identity_and_groups(tmp_path):
    """Verify that disconnecting a peer marks its transport offline but preserves its public key and group membership."""
    crypto = CryptoService(str(tmp_path / "local"))
    protocol = MessageProtocol(crypto)
    nm = NetworkManager(protocol)
    
    local_id = "local_node_12345678" * 4
    peer_id = "peer_node_87654321" * 4
    
    nm.local_node_id = local_id
    local_node = Node(local_id, nm, crypto.get_public_key_string(), name="LocalNode")
    nm.nodes[local_id] = local_node
    
    peer_crypto = CryptoService(str(tmp_path / "peer"))
    peer_pk = peer_crypto.get_public_key_string()
    peer_node = Node(peer_id, nm, peer_pk, name="RemotePeer")
    peer_node.endpoint = "http://192.168.1.100:8000"
    peer_node.last_seen = datetime.now(timezone.utc)
    nm.nodes[peer_id] = peer_node
    
    group = Group(group_id="group_test_123", name="TestGroup", level=1)
    group.members = {local_id, peer_id}
    nm.groups["group_test_123"] = group
    
    assert peer_node.is_online is True
    assert peer_node.endpoint == "http://192.168.1.100:8000"
    assert peer_id in nm.nodes
    assert peer_id in group.members
    
    # Execute disconnect_peer
    result = await nm.disconnect_peer(peer_id)
    assert result is True
    
    # 1. Transport is cleared and peer is marked offline
    assert peer_node.endpoint is None
    assert peer_node.is_online is False
    
    # 2. Node identity and public key are strictly preserved in self.nodes
    assert peer_id in nm.nodes
    assert nm.nodes[peer_id].public_key == peer_pk
    
    # 3. Group membership is preserved
    assert peer_id in group.members


def test_get_node_exact_and_prefix_match(tmp_path):
    """Verify that get_node resolves both full 64-char IDs and 8-char short IDs."""
    crypto = CryptoService(str(tmp_path / "crypto"))
    protocol = MessageProtocol(crypto)
    nm = NetworkManager(protocol)
    
    full_id = "5faa88719f9d2a3e" + "0" * 48
    short_id = full_id[:8]
    
    node = Node(full_id, nm, crypto.get_public_key_string(), name="Aristocles")
    nm.nodes[full_id] = node
    
    # Exact match
    assert nm.get_node(full_id) is node
    
    # Prefix match (8 chars)
    assert nm.get_node(short_id) is node
    
    # Prefix match (16 chars)
    assert nm.get_node(full_id[:16]) is node
    
    # Unknown
    assert nm.get_node("nonexistent_id") is None
    assert nm.get_node("") is None
    assert nm.get_node(None) is None


@pytest.mark.asyncio
async def test_receive_message_with_short_sender_id_verifies_signature(tmp_path):
    """Verify that messages sent with an 8-char short sender_id verify against full node public key."""
    local_crypto = CryptoService(str(tmp_path / "local"))
    peer_crypto = CryptoService(str(tmp_path / "peer"))
    
    protocol = MessageProtocol(local_crypto)
    nm = NetworkManager(protocol)
    
    local_id = local_crypto.get_node_id()
    peer_full_id = peer_crypto.get_node_id()
    peer_short_id = peer_full_id[:8]
    
    nm.local_node_id = local_id
    local_node = Node(local_id, nm, local_crypto.get_public_key_string(), name="Local")
    nm.nodes[local_id] = local_node
    
    peer_node = Node(peer_full_id, nm, peer_crypto.get_public_key_string(), name="Peer")
    nm.nodes[peer_full_id] = peer_node
    
    # Peer creates a signed message
    peer_protocol = MessageProtocol(peer_crypto)
    signed_msg = peer_protocol.create_message(
        sender_id=peer_short_id,  # short ID used as sender_id on wire
        recipient_id=local_id,
        message_type=MessageType.DIRECT,
        content={"text": "Hello from short id sender"},
    )
    
    # Local node receives the message
    await local_node.receive_message(signed_msg)
    
    # Verify received and signature verified is True
    assert len(local_node.inbox) == 1
    received = local_node.inbox[0]
    assert received["signature_verified"] is True


@pytest.mark.asyncio
async def test_receive_message_missing_key_does_not_fail_rsa_verification(tmp_path):
    """Verify that an unknown node's message is ingested with basic integrity check without raw RSA errors."""
    local_crypto = CryptoService(str(tmp_path / "local"))
    peer_crypto = CryptoService(str(tmp_path / "peer"))
    
    protocol = MessageProtocol(local_crypto)
    nm = NetworkManager(protocol)
    
    local_id = local_crypto.get_node_id()
    nm.local_node_id = local_id
    local_node = Node(local_id, nm, local_crypto.get_public_key_string(), name="Local")
    nm.nodes[local_id] = local_node
    
    # Peer is NOT added to nm.nodes
    peer_id = peer_crypto.get_node_id()
    peer_protocol = MessageProtocol(peer_crypto)
    signed_msg = peer_protocol.create_message(
        sender_id=peer_id,
        recipient_id=local_id,
        message_type=MessageType.DIRECT,
        content={"text": "Hello from unknown node"},
    )
    
    await local_node.receive_message(signed_msg)
    
    assert len(local_node.inbox) == 1
    received = local_node.inbox[0]
    assert received["signature_verified"] is False


@pytest.mark.asyncio
async def test_tampered_signature_with_known_key_fails(tmp_path):
    """Verify that tampering with message payload causes signature verification to fail and governance messages to be dropped."""
    local_crypto = CryptoService(str(tmp_path / "local"))
    peer_crypto = CryptoService(str(tmp_path / "peer"))
    
    protocol = MessageProtocol(local_crypto)
    nm = NetworkManager(protocol)
    
    local_id = local_crypto.get_node_id()
    peer_full_id = peer_crypto.get_node_id()
    
    nm.local_node_id = local_id
    local_node = Node(local_id, nm, local_crypto.get_public_key_string(), name="Local")
    nm.nodes[local_id] = local_node
    
    peer_node = Node(peer_full_id, nm, peer_crypto.get_public_key_string(), name="Peer")
    nm.nodes[peer_full_id] = peer_node
    
    # 1. Tampered governance message (PROPOSAL) -> should be dropped
    peer_protocol = MessageProtocol(peer_crypto)
    gov_msg = peer_protocol.create_message(
        sender_id=peer_full_id,
        recipient_id=local_id,
        message_type=MessageType.PROPOSAL,
        content={"title": "Legitimate Proposal"},
    )
    # Tamper with content after signing
    gov_msg.content = {"title": "Tampered Malicious Proposal"}
    
    await local_node.receive_message(gov_msg)
    assert len(local_node.inbox) == 0  # Dropped completely
    
    # 2. Tampered normal message (DIRECT) -> ingested but marked signature_verified = False
    direct_msg = peer_protocol.create_message(
        sender_id=peer_full_id,
        recipient_id=local_id,
        message_type=MessageType.DIRECT,
        content={"text": "Original text"},
    )
    direct_msg.content = {"text": "Tampered text"}
    
    await local_node.receive_message(direct_msg)
    assert len(local_node.inbox) == 1
    assert local_node.inbox[0]["signature_verified"] is False


