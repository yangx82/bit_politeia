
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from typing import Dict, Any
import logging
import asyncio
import json

from ..bus.queue import message_bus
from ..bus.events import InboundMessage, OutboundMessage
from ..services.agent_service import agent_service
from ..schemas.node_protocol import (
    BaseNodeMessage, MessageType, Handshake, GatewayEvent
)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws/gateway")
async def websocket_gateway(
    websocket: WebSocket,
    token: str = Query(None)
):
    """
    Neural Gateway WebSocket Endpoint.
    Connects external nodes/interfaces to the Agent's MessageBus.
    """
    try:
        logger.info(f"Gateway: Connection attempt from {websocket.client}")
        
        # 1. Authentication
        # Allow if no config set yet, or if token matches
        current_key = None
        try:
            if hasattr(agent_service, 'api_key'):
                current_key = agent_service.api_key
        except Exception as e:
            logger.warning(f"Gateway: Failed to access agent config: {e}")
        
        if current_key and token != current_key:
            logger.warning(f"Gateway connection denied: Invalid token {token}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.accept()
        logger.info("Gateway: New WebSocket connection accepted.")

    except Exception as e:
        logger.error(f"Gateway handshake failed: {e}", exc_info=True)
        # Verify if websocket is already closed?
        return

    # 3. Bi-directional Loops
    # Task A: Forward OutboundBus -> WebSocket
    sender_task = asyncio.create_task(stream_outbound_to_socket(websocket))
    
    try:
        # Task B: Forward WebSocket -> InboundBus
        while True:
            data = await websocket.receive_text()
            try:
                # Parse as generic JSON first
                payload = json.loads(data)
                
                # Basic validation
                if "type" not in payload:
                    logger.warning("Gateway: Received message without type")
                    continue
                    
                msg_type = payload["type"]
                
                # Route based on type
                if msg_type == MessageType.HANDSHAKE:
                    logger.info(f"Gateway: handshake from {payload.get('node_id')}")
                    # TODO: Register node capabilities
                    
                elif msg_type == MessageType.EVENT:
                    # Convert to InboundMessage for the Agent
                    # We assume the external node acts as a "channel"
                    inbound = InboundMessage(
                        channel="gateway",
                        sender_id=payload.get("id", "anonymous_node"),
                        chat_id="global",  # Simplified for now
                        content=str(payload.get("payload", "")),
                        metadata=payload
                    )
                    await message_bus.publish_inbound(inbound)
                    
                elif msg_type == MessageType.PING:
                    await websocket.send_json({"type": MessageType.PONG, "timestamp": 0})
                    
                else:
                    logger.debug(f"Gateway: Received unhandled message type {msg_type}")

            except json.JSONDecodeError:
                logger.warning("Gateway: Received invalid JSON")
                
    except WebSocketDisconnect:
        logger.info("Gateway: WebSocket disconnected")
    except Exception as e:
        logger.error(f"Gateway Error: {e}")
    finally:
        sender_task.cancel()
        try:
            await sender_task
        except asyncio.CancelledError:
            pass


async def stream_outbound_to_socket(websocket: WebSocket):
    """Subscribe to MessageBus and push events to WebSocket."""
    # We define a unique channel ID for this socket or just subscribe to all "gateway" messages?
    # For "Neural Gateway" pattern, the UI often wants to see EVERYTHING the agent says.
    # So we subscribe to specific channels or a wildcard.
    # For now, let's stream all messages intended for 'gateway' channel OR debug events.
    # OR, we might want to stream *everything* if this is a "Control Plane".
    
    # Since existing queue implementation is channel-based:
    # We will subscribe this specific socket to a 'gateway' channel.
    # If the Agent wants to speak to the UI/Node, it sends to 'gateway'.
    
    # Limitation: This doesn't tap into 'telegram' messages unless we change the Bus to fan-out all messages.
    # For now, we only stream messages explicitly sent to 'gateway' or 'debug'.
    
    # Using the new Async Generator!
    channel_name = "resident"
    
    async for msg in message_bus.subscribe_async_generator(channel_name):
        try:
                # Convert OutboundMessage to NodeProtocol Event
                # Map internal msg.type directly to event_type
                # msg.type defaults to 'message', but can be 'thought', 'tool_call', etc.
                
                event = GatewayEvent(
                    id="srv_" + str(msg.chat_id), # Ensure string
                    timestamp=0, # TODO: use msg timestamp if available
                    event_type=f"agent_{msg.type}", # e.g. agent_message, agent_thought
                    payload={
                        "content": msg.content,
                        "media": msg.media,
                        "metadata": msg.metadata
                    }
                )
                # Send as JSON
                await websocket.send_text(event.model_dump_json())
            
        except Exception as e:
            logger.error(f"Gateway Sender Error: {e}")
            break
