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

    async def route_message(self, sender_id: str, target_id: str, payload: dict) -> bool:
        """
        Route a message to the target node's WebSocket.
        Payload is the full SignedMessage dict.
        """
        if target_id not in self.active_connections:
            logger.warning(f"Relay: Target {target_id} not connected via WebSocket")
            return False
            
        try:
            target_ws = self.active_connections[target_id]
            # Wrap in a structure indicating it's a relayed message
            # Or just send raw signed message?
            # Let's send a wrapper so the client knows source context if needed, 
            # though SignedMessage has sender_id.
            # Keeping it simple: Send exactly what was received.
            await target_ws.send_text(json.dumps(payload))
            return True
        except Exception as e:
            logger.error(f"Relay: Failed to send to {target_id}: {e}")
            self.disconnect(target_id) # Assume broken link
            return False

relay_manager = RelayManager()
