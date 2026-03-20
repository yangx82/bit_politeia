"""Async message queue for decoupled channel-agent communication."""

import asyncio
import logging
from typing import Callable, Awaitable, Dict, List, Optional, Set, Any

from .events import InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

class MessageBus:
    """
    Async message bus that decouples chat channels from the agent core.
    
    Channels push messages to the inbound queue, and the agent processes
    them and pushes responses to the outbound queue.
    """
    
    def __init__(self, maxsize: int = 1000):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue(maxsize=maxsize)
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue(maxsize=maxsize)
        self._outbound_subscribers: Dict[str, List[Callable[[OutboundMessage], Awaitable[None]]]] = {}
        self._running = False
        self._dispatch_task: Optional[asyncio.Task[None]] = None
        self._pending_callbacks: Set[asyncio.Task[Any]] = set()
    
    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent."""
        await self.inbound.put(msg)
        logger.debug(f"Published inbound message from {msg.channel}:{msg.sender_id}")
    
    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()
    
    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        await self.outbound.put(msg)
        logger.debug(f"Published outbound message to {msg.channel}:{msg.session_id}")
    
    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()
    
    def subscribe_outbound(
        self, 
        channel: str, 
        callback: Callable[[OutboundMessage], Awaitable[None]]
    ) -> None:
        """Subscribe to outbound messages for a specific channel."""
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)
        logger.info(f"Subscribed callback to channel '{channel}'")
    
    async def start(self) -> None:
        """Start the bus dispatcher."""
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        logger.info("Message Bus dispatcher started")

    async def _dispatch_loop(self) -> None:
        """
        Dispatch outbound messages to subscribed channels.
        Run this as a background task.
        """
        logger.info("Message Bus dispatcher loop running")
        while self._running:
            try:
                # Wait for next outbound message
                msg = await self.outbound.get()
                
                subscribers = self._outbound_subscribers.get(msg.channel, [])
                if not subscribers:
                    logger.warning(f"No subscribers for channel '{msg.channel}', message dropped.")
                
                for callback in subscribers:
                    try:
                        # Call subscribers concurrently to prevent blocking other channels
                        # Ensure callback is awaited if it's a coroutine function
                        coro = callback(msg)
                        task = asyncio.create_task(coro) # type: ignore
                        self._pending_callbacks.add(task)
                        task.add_done_callback(self._pending_callbacks.discard)
                    except Exception as e:
                        logger.error(f"Error launching dispatch task for {msg.channel}: {e}")
                
                self.outbound.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in bus dispatch loop: {e}")
                await asyncio.sleep(1) # Prevent tight loop on error
    
    async def stop(self) -> None:
        """Stop the dispatcher loop and wait for pending tasks."""
        self._running = False
        if self._dispatch_task is not None:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
            self._dispatch_task = None
        
        # Wait for pending callbacks with a timeout
        if self._pending_callbacks:
            logger.info(f"Waiting for {len(self._pending_callbacks)} pending callbacks to finish...")
            await asyncio.wait(self._pending_callbacks, timeout=5.0)
            
        logger.info("Message Bus stopped")
    
    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()
    
    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()

    async def subscribe_async_generator(self, channel: str):
        """
        Yields outbound messages for a channel as an async generator.
        Useful for WebSocket streaming.
        """
        queue = asyncio.Queue()
        
        async def callback(msg: OutboundMessage):
            await queue.put(msg)
            
        self.subscribe_outbound(channel, callback)
        
        try:
            while True:
                msg = await queue.get()
                yield msg
        finally:
            # Cleanup subscription when generator is closed
            if channel in self._outbound_subscribers:
                if callback in self._outbound_subscribers[channel]:
                    self._outbound_subscribers[channel].remove(callback)
                    logger.info(f"Unsubscribed async generator from channel '{channel}'")

# Global singleton (optional, but convenient services)
message_bus = MessageBus()
