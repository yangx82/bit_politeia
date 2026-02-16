import logging
import asyncio
import json
from typing import Optional, Callable, Dict
import websockets

logger = logging.getLogger(__name__)

class RelayClient:
    """
    Client for persistent WebSocket connection to the Relay Server (Bootstrap).
    Handles sending messages via relay and receiving messages from relay.
    """
    def __init__(self, server_url: str, node_id: str, message_handler: Callable):
        # Convert http/https to ws/wss
        if server_url.startswith("https://"):
            self.ws_url = server_url.replace("https://", "wss://")
        elif server_url.startswith("http://"):
            self.ws_url = server_url.replace("http://", "ws://")
        else:
            self.ws_url = f"ws://{server_url}"
            
        self.ws_url = f"{self.ws_url.rstrip('/')}/ws/relay/{node_id}"
        self.node_id = node_id
        self.message_handler = message_handler # Callback(message_dict)
        self.websocket = None
        self.running = False
        self._send_queue = asyncio.Queue()

    async def start(self):
        """Start the relay client (connect and listen)."""
        self.running = True
        asyncio.create_task(self._connect_loop())
        asyncio.create_task(self._sender_loop())

    async def stop(self):
        self.running = False
        if self.websocket:
            await self.websocket.close()

    async def send(self, message: Dict):
        """Queue a message to be sent via relay."""
        await self._send_queue.put(message)

    async def _connect_loop(self):
        """Persistent connection loop with exponential backoff."""
        backoff = 1
        while self.running:
            try:
                logger.info(f"RelayClient: Connecting to {self.ws_url}...")
                async with websockets.connect(self.ws_url) as ws:
                    self.websocket = ws
                    logger.info("RelayClient: Connected!")
                    backoff = 1 # Reset backoff
                    
                    # Listen loop
                    while self.running:
                        try:
                            message_text = await ws.recv()
                            message = json.loads(message_text)
                            # Pass to NetworkManager to handle
                            if self.message_handler:
                                asyncio.create_task(self.message_handler(message))
                        except websockets.ConnectionClosed:
                            logger.warning("RelayClient: Connection closed by server.")
                            break
                        except Exception as e:
                            logger.error(f"RelayClient: Error receiving message: {e}")
                            break
            except Exception as e:
                logger.error(f"RelayClient: Connection failed: {e}")
            
            self.websocket = None
            if self.running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60) # Max 60s backoff

    async def _sender_loop(self):
        """Loop to send queued messages."""
        while self.running:
            message = await self._send_queue.get()
            if self.websocket:
                try:
                    await self.websocket.send(json.dumps(message))
                except Exception as e:
                    logger.error(f"RelayClient: Failed to send message: {e}")
                    # Optionally re-queue? For now, drop to avoid blocking
            else:
                logger.warning("RelayClient: Dropping message (Not connected)")
            self._send_queue.task_done()
