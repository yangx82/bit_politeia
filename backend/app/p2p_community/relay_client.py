import logging
import asyncio
import json
import ssl
from typing import Optional, Callable, Dict
import websockets

logger = logging.getLogger(__name__)

class RelayClient:
    """
    Client for persistent WebSocket connection to the Relay Server (Bootstrap).
    Handles sending messages via relay and receiving messages from relay.
    """
    def __init__(self, server_url: str, node_id: str, message_handler: Callable, verify_ssl: bool = True):
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
        self.verify_ssl = verify_ssl
        self.websocket = None
        self.running = False
        self._send_queue = asyncio.Queue()

    async def start(self):
        """Start the relay client (connect and listen)."""
        self.running = True
        asyncio.create_task(self._connect_loop())
        asyncio.create_task(self._sender_loop())
        asyncio.create_task(self._ping_loop())

    async def stop(self):
        self.running = False
        # Wake up sender loop if waiting on empty queue
        await self._send_queue.put(None)
        if self.websocket:
            await self.websocket.close()

    async def send(self, message: Dict) -> bool:
        """Queue a message to be sent via relay. Returns True if queued, False if disconnected."""
        if not self.websocket or not self.running:
            return False
        await self._send_queue.put(message)
        return True

    async def _connect_loop(self):
        """Persistent connection loop with exponential backoff."""
        backoff = 1
        while self.running:
            try:
                ssl_context = None
                if self.ws_url.startswith("wss://") and not self.verify_ssl:
                    ssl_context = ssl.create_default_context()
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    logger.warning("RelayClient: SSL verification disabled.")

                logger.info(f"RelayClient: Connecting to {self.ws_url}...")
                
                # websockets.connect handles ssl context via 'ssl' param
                # 403 Fix: Add Origin header to satisfy strict CORS or Firewall rules
                # Websockets 14.0+: extra_headers removed, use origin param directly or additional_headers
                # Added keep-alive settings (ping_interval=None to disable automatic ping, we do application level)
                # Actually proper WS ping/pong is better, but app-level ensures full stack works
                async with websockets.connect(
                    self.ws_url, 
                    ssl=ssl_context,
                    origin="http://localhost",
                    ping_interval=20,
                    ping_timeout=20
                ) as ws:
                    self.websocket = ws
                    logger.info(f"RelayClient: Connected! (Node ID: {self.node_id})")
                    backoff = 1 # Reset backoff
                    
                    # Listen loop
                    while self.running:
                        try:
                            message_text = await ws.recv()
                            message = json.loads(message_text)
                            
                            if message.get("type") == "PONG":
                                continue
                                
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

    async def _ping_loop(self):
        """Periodic PING to keep connection alive through NAT."""
        while self.running:
            try:
                if self.websocket:
                    await self.websocket.send(json.dumps({"type": "PING"}))
            except Exception as e:
                logger.debug(f"Ping failed: {e}")
            
            await asyncio.sleep(25) # Send ping every 25 seconds

    async def _sender_loop(self):
        """Loop to send queued messages."""
        while self.running:
            message = await self._send_queue.get()
            if message is None:
                self._send_queue.task_done()
                break
                
            if self.websocket:
                try:
                    await self.websocket.send(json.dumps(message))
                except Exception as e:
                    logger.error(f"RelayClient: Failed to send message: {e}")
                    # Optionally re-queue? For now, drop to avoid blocking
            else:
                logger.warning("RelayClient: Dropping message (Not connected)")
            self._send_queue.task_done()
