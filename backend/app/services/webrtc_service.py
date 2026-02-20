import logging
import json
import asyncio
from typing import Dict, Any, Optional, Callable
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, RTCConfiguration, RTCIceServer
from aiortc.contrib.signaling import object_to_string, object_from_string

logger = logging.getLogger(__name__)

class WebRTCManager:
    """
    Manages WebRTC Peer Connections and Data Channels.
    """
    def __init__(self, signaling_callback: Callable[[str, str, Dict[str, Any]], Any], message_callback: Callable[[str, str], Any]):
        self.pcs: Dict[str, RTCPeerConnection] = {} # peer_id -> RTCPeerConnection
        self.data_channels: Dict[str, Any] = {} # peer_id -> RTCDataChannel
        self.signaling_callback = signaling_callback # Function to send signaling messages via HTTP/Relay
        self.message_callback = message_callback # Function to handle received data channel messages
        self.message_callback = message_callback # Function to handle received data channel messages
        self.loop = None

    def set_loop(self, loop):
        self.loop = loop

    async def get_or_create_pc(self, peer_id: str) -> RTCPeerConnection:
        if peer_id in self.pcs:
            return self.pcs[peer_id]
        
        # Configure STUN server for NAT traversal
        # This helps resolve the public IP and avoids binding errors on some local interfaces
        config = RTCConfiguration(iceServers=[
            RTCIceServer(urls=["stun:stun.l.google.com:19302"])
        ])
        
        pc = RTCPeerConnection(configuration=config)
        self.pcs[peer_id] = pc
        
        @pc.on("datachannel")
        def on_datachannel(channel):
            logger.info(f"[{peer_id}] Data channel received: {channel.label}")
            self.setup_data_channel(peer_id, channel)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"[{peer_id}] Connection state is {pc.connectionState}")
            if pc.connectionState == "failed":
                await pc.close()
                if peer_id in self.pcs:
                    del self.pcs[peer_id]
                if peer_id in self.data_channels:
                    del self.data_channels[peer_id]

        @pc.on("icegatheringstatechange")
        async def on_icegatheringstatechange():
            logger.info(f"[{peer_id}] ICE gathering state is {pc.iceGatheringState}")

        return pc

    def setup_data_channel(self, peer_id: str, channel):
        self.data_channels[peer_id] = channel
        
        @channel.on("message")
        def on_message(message):
            logger.info(f"[{peer_id}] Received via DataChannel: {message[:50]}...")
            # Handle received data
            if self.message_callback:
                if self.loop:
                    asyncio.run_coroutine_threadsafe(self.message_callback(peer_id, message), self.loop)
                else:
                    # Fallback: Try to get running loop (might fail if in thread)
                    try:
                        loop = asyncio.get_running_loop()
                        asyncio.run_coroutine_threadsafe(self.message_callback(peer_id, message), loop)
                    except RuntimeError:
                         logger.error(f"[{peer_id}] WebRTC Message Error: No event loop available to schedule callback.")

        @channel.on("open")
        def on_open():
            logger.info(f"[{peer_id}] Data channel {channel.label} is OPEN")
            print(f"[DEBUG-RTC] Data Channel OPEN with {peer_id}")

    async def initiate_connection(self, peer_id: str):
        """Start a WebRTC connection with a peer."""
        logger.info(f"Initiating WebRTC connection to {peer_id}")
        pc = await self.get_or_create_pc(peer_id)
        
        # Create Data Channel
        channel = pc.createDataChannel("chat")
        self.setup_data_channel(peer_id, channel)
        
        # Create Offer
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        # Send Offer via Signaling
        await self.signaling_callback(peer_id, "sdp_offer", {
            "sdp": object_to_string(pc.localDescription)
        })

    async def handle_offer(self, peer_id: str, sdp_str: str):
        """Handle incoming SDP Offer."""
        logger.info(f"Received SDP Offer from {peer_id}")
        pc = await self.get_or_create_pc(peer_id)
        
        offer = object_from_string(sdp_str)
        await pc.setRemoteDescription(offer)
        
        # Create Answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        # Send Answer via Signaling
        await self.signaling_callback(peer_id, "sdp_answer", {
            "sdp": object_to_string(pc.localDescription)
        })

    async def handle_answer(self, peer_id: str, sdp_str: str):
        """Handle incoming SDP Answer."""
        logger.info(f"Received SDP Answer from {peer_id}")
        if peer_id not in self.pcs:
            logger.warning(f"Received answer from unknown peer {peer_id}")
            return
            
        pc = self.pcs[peer_id]
        answer = object_from_string(sdp_str)
        await pc.setRemoteDescription(answer)

    async def send_message(self, peer_id: str, message: str) -> bool:
        """Send message via Data Channel if available."""
        if peer_id in self.data_channels and self.data_channels[peer_id].readyState == "open":
            try:
                self.data_channels[peer_id].send(message)
                return True
            except Exception as e:
                logger.error(f"Failed to send via DataChannel: {e}")
                return False
        return False
