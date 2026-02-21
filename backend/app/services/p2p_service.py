import logging
import asyncio
import datetime
from typing import Dict, Any, Optional, List

from .crypto_service import crypto_service
from ..p2p_community.network_manager import NetworkManager
from ..p2p_community.message_protocol import MessageProtocol, MessageType
from ..p2p_community.models import Node
from .webrtc_service import WebRTCManager

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
        
        # Initialize WebRTC Manager
        self.webrtc_manager = WebRTCManager(self.send_signaling_message, self.handle_webrtc_message)

    async def initialize(self, node_id: str, node_url: str = None, name: str = "Agent"):
        """
        Initialize the P2P service and local node.
        """
        if self._initialized:
            return

        # Capture async loop for WebRTC callbacks
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            self.webrtc_manager.set_loop(loop)
        except RuntimeError:
            logger.warning("P2P initialize called without running loop?")

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
            public_key=public_key,
            name=name
        )
        if node_url:
            self.local_node.endpoint = node_url
        
        # Pass name to network manager registration if needed?
        # Actually network_manager.register_node just adds to local dict.
        # But we need to ensure when we call bootstrap_client.register_node that we pass the name.
        # NetworkManager.register_node calls bootstrap_client.register_node? 
        # No, NetworkManager.register_node seems to be local.
        # I need to check where the actual bootstrap registration happens.
        # It happens in `await self.network_manager.register_node(self.local_node)` line 54?
        # Let's check NetworkManager code.
        
        await self.network_manager.register_node(self.local_node)
        
        # Register Signaling Handler
        self.local_node.set_message_handler(self.handle_p2p_message)
        
        self._initialized = True
        logger.info(f"P2PService initialized for Node {node_id} at {node_url}")

    async def send_signaling_message(self, target_id: str, msg_type: str, content: Dict[str, Any]):
        """Callback for WebRTCManager to send signaling via Relay/HTTP."""
        await self.send_message(target_id, content, msg_type)

    async def handle_webrtc_message(self, peer_id: str, message: str):
        """Callback: Handle message received via WebRTC Data Channel."""
        # Wrap as generic message structure
        msg_data = {
            "sender_id": peer_id,
            "recipient_id": self.local_node.node_id if self.local_node else "unknown",
            "message_type": MessageType.DIRECT.value, # Default to DIRECT for now
            "content": {"text": message}, # Assuming simple text for now, can be parsed if JSON
            "timestamp": datetime.datetime.now().isoformat()
        }
        # Try parse JSON if message looks like it
        try:
            import json
            import datetime
            content = json.loads(message)
            # Reconstruct full object if possible
            if "type" in content:
                msg_data["content"] = content
        except:
            pass
            
        if self.local_node:
             # We call receive_message directly (bypassing message_handler interceptor to avoid loops? 
             # No, receive_message calls message_handler. 
             # But this IS the handler result. We want to put it in inbox.
             # Wait, receive_message puts in inbox.
             # But if we call receive_message, it might trigger the interceptor again?
             # My interceptor checks for SDP/ICE. This is "DIRECT" type. So it should pass through.
             await self.local_node.receive_message(msg_data)

    async def handle_p2p_message(self, message: Dict[str, Any]) -> bool:
        """
        Intercept P2P messages for WebRTC signaling.
        Returns True if handled, False otherwise.
        """
        msg_type = message.get("message_type")
        sender_id = message.get("sender_id")
        content = message.get("content", {})
        
        if msg_type == MessageType.SDP_OFFER.value:
            await self.webrtc_manager.handle_offer(sender_id, content)
            return True
            
        elif msg_type == MessageType.SDP_ANSWER.value:
            await self.webrtc_manager.handle_answer(sender_id, content)
            return True
            
        elif msg_type == MessageType.ICE_CANDIDATE.value:
            # Handle ICE candidate to support NAT traversal
            await self.webrtc_manager.handle_candidate(sender_id, content)
            return True
            
        return False

    async def send_message(self, target_id: str, content: Dict[str, Any], msg_type: str = MessageType.DIRECT.value):
        """
        Send a message to a target (Node or Group).
        """
        if not self.local_node:
            raise RuntimeError("P2PService not initialized")
            
        return await self.local_node.send_message(target_id, content, msg_type)

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
        return await self.local_node.send_message(group_id, content, MessageType.GROUP.value)

    def get_network_status(self) -> Dict[str, Any]:
        return self.network_manager.get_network_structure()

    async def update_node_info(self, name: str = None):
        """Update local node info and sync with bootstrap."""
        if not self.local_node:
            logger.warning("Cannot update node info: P2PService not initialized")
            return
            
        if name:
            self.local_node.name = name
            
        # Re-register with bootstrap to update metadata
        await self.network_manager.register_node(self.local_node)
        logger.info(f"Updated node info for {self.local_node.node_id}: name='{self.local_node.name}'")

    def get_my_groups(self) -> List[str]:
        if self.local_node:
            return list(self.local_node.group_ids)
        return []

    def get_groups(self) -> List[Dict[str, Any]]:
        """
        Get all known groups with details.
        """
        if not self._initialized:
            return []
            
        groups_data = []
        for gid, group in self.network_manager.groups.items():
            groups_data.append(group.to_dict())
        return groups_data

p2p_service = P2PService()
