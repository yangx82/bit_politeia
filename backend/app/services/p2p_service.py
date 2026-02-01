import logging
import asyncio
from typing import Dict, Any, Optional, List

from .crypto_service import crypto_service
from ..p2p_community.network_manager import NetworkManager
from ..p2p_community.message_protocol import MessageProtocol, MessageType
from ..p2p_community.models import Node

logger = logging.getLogger(__name__)

class P2PService:
    """
    Service layer for P2P network operations.
    Wraps the NetworkManager and provides high-level API for other services.
    """
    
    def __init__(self):
        self.message_protocol = MessageProtocol(crypto_service)
        self.network_manager = NetworkManager(self.message_protocol)
        self.local_node: Optional[Node] = None
        self._initialized = False

    async def initialize(self, node_id: str, node_url: str = None):
        """
        Initialize the P2P service and local node.
        """
        if self._initialized:
            return

        # Initialize network manager (sync topology)
        await self.network_manager.initialize()
        
        # Create and register local node
        public_key = crypto_service.get_public_key_string()
        
        # User Request: Node ID should be a UUID.
        # We generate a deterministic UUID based on the public key so identity persists.
        import uuid
        node_id_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, public_key))
        
        # Override node_id with the UUID if not explicitly provided
        if not node_id or len(node_id) > 64: # If it's the pubkey string, use UUID
             node_id = node_id_uuid

        self.local_node = Node(
            node_id=node_id, 
            network_manager=self.network_manager,
            public_key=public_key
        )
        if node_url:
            self.local_node.endpoint = node_url
        
        await self.network_manager.register_node(self.local_node)
        self._initialized = True
        logger.info(f"P2PService initialized for Node {node_id} at {node_url}")

    async def send_message(self, target_id: str, content: Dict[str, Any], msg_type: str = MessageType.DIRECT.value):
        """
        Send a message to a target (Node or Group).
        """
        if not self.local_node:
            raise RuntimeError("P2PService not initialized")
            
        await self.local_node.send_message(target_id, content, msg_type)

    async def broadcast_to_group(self, group_id: str, text: str, subject: str = None):
        """
        Helper to broadcast to a specific group.
        """
        if not self.local_node:
            raise RuntimeError("P2PService not initialized")
            
        # We need to construct content directly here or use protocol helper?
        # NetworkManager.send_signed_message handles the wrapping if we pass raw content + type,
        # but protocol helper create_group_broadcast is nice to use.
        # Let's stick to generic send_message for now which calls network_manager.send_signed_message
        # which uses protocol.create_message.
        
        content = {
            "text": text,
            "subject": subject
        }
        await self.local_node.send_message(group_id, content, MessageType.GROUP.value)

    def get_network_status(self) -> Dict[str, Any]:
        return self.network_manager.get_network_structure()

    def get_my_groups(self) -> List[str]:
        if self.local_node:
            return list(self.local_node.group_ids)
        return []

p2p_service = P2PService()
