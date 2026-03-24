from typing import Dict, Optional
from fastapi import WebSocket
import logging
import json
import asyncio

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
        Broadcast a message to members of a group who are connected via WebSocket.
        Supports 'Partial Broadcast' if target_node_ids is present in payload.
        """
        from .bootstrap_service import bootstrap_service
        
        # 1. Resolve members
        all_members = bootstrap_service._group_members.get(group_id, set())
        
        # 2. Support Partial Broadcast if requested by sender
        target_ids = payload.get("target_node_ids")
        if target_ids:
            if isinstance(target_ids, list):
                members = set(target_ids).intersection(all_members)
                logger.info(f"Relay: Partial Broadcast requested for {len(members)} specific members.")
            else:
                members = all_members
        else:
            members = all_members

        if not members:
            logger.warning(f"Relay: No valid members to broadcast to for group {group_id}")
            return False
            
        logger.info(f"Relay: Parallel Group Broadcast from {sender_id} to {group_id} ({len(members)} target members)")
        
        async def send_to_member(member_id: str):
            if member_id == sender_id:
                return 0
                
            if member_id in self.active_connections:
                try:
                    # Parallel write to WebSocket
                    await self.active_connections[member_id].send_text(json.dumps(payload))
                    return 1
                except Exception as e:
                    logger.error(f"Relay: Failed to broadcast to {member_id}: {e}")
                    self.disconnect(member_id)
                    return 0
            else:
                logger.debug(f"Relay: Member {member_id} is NOT connected via WebSocket")
                return 0

        # 3. CONCURRENT EXECUTION
        tasks = [send_to_member(m_id) for m_id in members]
        results = await asyncio.gather(*tasks)
        
        success_count = sum(results)
        logger.info(f"Relay: Parallel Broadcast complete. Delivered to {success_count} members.")
        return success_count > 0

relay_manager = RelayManager()
