from typing import Dict, Optional
from fastapi import WebSocket
import logging
import json

logger = logging.getLogger(__name__)

class RelayManager:
    """
    Manages WebSocket connections for P2P message relaying.
    Allows nodes behind NAT to communicate via the Bootstrap Server.
    """
    def __init__(self):
        # Map node_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, node_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[node_id] = websocket
        logger.info(f"Relay: Node {node_id} connected via WebSocket")

    def disconnect(self, node_id: str):
        if node_id in self.active_connections:
            del self.active_connections[node_id]
            logger.info(f"Relay: Node {node_id} disconnected")

    async def route_message(self, sender_id: str, recipient_id: str, payload: dict) -> bool:
        """
        Route a message to the recipient node's WebSocket.
        Payload is the full SignedMessage dict.
        """
        if recipient_id not in self.active_connections:
            logger.warning(f"Relay: Recipient {recipient_id} not connected via WebSocket")
            return False
            
        try:
            recipient_ws = self.active_connections[recipient_id]
            # Keeping it simple: Send exactly what was received.
            await recipient_ws.send_text(json.dumps(payload))
            return True
        except Exception as e:
            logger.error(f"Relay: Failed to send to {recipient_id}: {e}")
            self.disconnect(recipient_id) # Assume broken link
            return False

    async def broadcast_to_group(self, sender_id: str, group_id: str, payload: dict) -> bool:
        """
        Broadcast a message to all members of a group who are connected via WebSocket.
        """
        from .bootstrap_service import bootstrap_service
        
        # Get members from global topology
        members = bootstrap_service._group_members.get(group_id, set())
        connected_nodes = list(self.active_connections.keys())
        logger.info(f"Relay: broadcast_to_group called. group_id={group_id}, sender={sender_id}")
        logger.info(f"Relay: Known group members for {group_id}: {members}")
        logger.info(f"Relay: All connected WebSocket nodes: {connected_nodes}")
        logger.info(f"Relay: All known groups: {list(bootstrap_service._group_members.keys())}")
        
        if not members:
            logger.warning(f"Relay: Attempted broadcast to unknown or empty group {group_id}. "
                         f"Known groups: {list(bootstrap_service._group_members.keys())}")
            return False
            
        logger.info(f"Relay: Group Broadcast from {sender_id} to Group {group_id} ({len(members)} members)")
        
        success_count = 0
        for member_id in members:
            if member_id == sender_id:
                logger.info(f"Relay: Skipping sender {member_id}")
                continue
                
            if member_id in self.active_connections:
                try:
                    await self.active_connections[member_id].send_text(json.dumps(payload))
                    success_count += 1
                    logger.info(f"Relay: Successfully sent to member {member_id}")
                except Exception as e:
                    logger.error(f"Relay: Failed to broadcast to {member_id}: {e}")
                    self.disconnect(member_id)
            else:
                logger.warning(f"Relay: Member {member_id} is NOT connected via WebSocket")
        
        logger.info(f"Relay: Broadcast complete. Delivered to {success_count}/{len(members)-1} members (excluding sender)")
        return success_count > 0

relay_manager = RelayManager()
