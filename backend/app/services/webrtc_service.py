import logging
import json
import asyncio
from typing import Dict, Any, Optional, Callable
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, RTCConfiguration, RTCIceServer
from aiortc.contrib.signaling import object_to_string, object_from_string
from .p2p_service import p2p_service

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
        self.negotiating: set[str] = set() # peer_ids currently in handshake
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
            if pc.iceGatheringState == "complete":
                # On Windows, gathering 'complete' often follows a bind error, 
                # but we should check if we actually found any candidates.
                logger.info(f"[{peer_id}] ICE gathering finished. Signaling state: {pc.signalingState}")

        return pc

    def setup_data_channel(self, peer_id: str, channel):
        self.data_channels[peer_id] = channel
        
        @channel.on("message")
        def on_message(message):
            logger.info(f"[{peer_id}] >>> RECEIVED VIA WEBRTC: {message[:100]}...")
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
            logger.info(f"[{peer_id}] !!! DATA CHANNEL '{channel.label}' IS OPEN !!!")
            print(f"\n[!!!] WebRTC DATA CHANNEL OPEN WITH {peer_id} [!!!]\n", flush=True)

    async def initiate_connection(self, peer_id: str):
        """Start a WebRTC connection with a peer."""
        pc = await self.get_or_create_pc(peer_id)
        
        # Guard: Don't initiate if already connecting or connected
        if pc.signalingState != "stable":
            logger.info(f"[{peer_id}] Connection initiation skipped: signalingState is {pc.signalingState}")
            return
        if pc.connectionState in ["connecting", "connected"]:
            logger.info(f"[{peer_id}] Connection initiation skipped: connectionState is {pc.connectionState}")
            return
            
        # Synchronization Guard: Prevent multiple concurrent initiations
        if peer_id in self.negotiating:
            logger.info(f"[{peer_id}] Connection initiation skipped: already negotiating.")
            return
            
        self.negotiating.add(peer_id)
        logger.info(f"[{peer_id}] Initiating WebRTC connection...")
        
        try:
            # Create Data Channel
            channel = pc.createDataChannel("chat")
            self.setup_data_channel(peer_id, channel)
            
            # Create Offer
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)
            
            # Send Offer via Signaling (Simple dict, avoids double stringify)
            await self.signaling_callback(peer_id, "sdp_offer", {
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type
            })
        except Exception as e:
            logger.error(f"[{peer_id}] Failed to initiate connection: {e}")
            self.negotiating.discard(peer_id)

    async def handle_offer(self, peer_id: str, sdp_data: Any):
        """Handle incoming SDP Offer."""
        pc = await self.get_or_create_pc(peer_id)
        logger.info(f"[{peer_id}] Received SDP Offer. Current state: signaling={pc.signalingState}, connection={pc.connectionState}")
        
        if pc.signalingState != "stable":
            logger.warning(f"[{peer_id}] Received Offer while in state {pc.signalingState}. Glare possible.")
        
        try:
            # Permissive Parser: Handle nested JSON stringified SDP (Legacy compat)
            if isinstance(sdp_data, dict) and isinstance(sdp_data.get("sdp"), str) and sdp_data["sdp"].startswith('{"sdp"'):
                try:
                    nested = json.loads(sdp_data["sdp"])
                    sdp_data = nested
                    logger.info(f"[{peer_id}] Unwrapped nested JSON SDP in Offer.")
                except:
                    pass

            # Normalize SDP input
            if isinstance(sdp_data, str):
                offer = object_from_string(sdp_data)
            elif isinstance(sdp_data, dict):
                offer = RTCSessionDescription(sdp=sdp_data["sdp"], type=sdp_data["type"])
            else:
                raise ValueError("Unsupported SDP data format")

            # Glare Handling (Polite Peer logic)
            # If we both sent offers (signalingState is have-local-offer),
            # the peer with the lexicographically "smaller" ID backs off (polite).
            # The one with the "larger" ID ignores the incoming offer and waits for an answer.
            if pc.signalingState == "have-local-offer":
                local_id = p2p_service.local_node.node_id if p2p_service.local_node else "z"
                if local_id < peer_id:
                    logger.info(f"[{peer_id}] Glare detected. I am POLITE. Rolling back for their offer.")
                    # In aiortc, we don't necessarily have a 'rollback' like in JS,
                    # but we can just set their remote description if we haven't committed to our answer yet.
                    # Or we just accept the remote offer which will overwrite.
                else:
                    logger.info(f"[{peer_id}] Glare detected. I am IMPOLITE. Ignoring their offer.")
                    return

            await pc.setRemoteDescription(offer)
            
            # Create Answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            
            # Send Answer via Signaling
            await self.signaling_callback(peer_id, "sdp_answer", {
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type
            })
        except Exception as e:
            logger.error(f"[{peer_id}] Failed to handle offer: {e}")
            self.negotiating.discard(peer_id)

    async def handle_answer(self, peer_id: str, sdp_data: Any):
        """Handle incoming SDP Answer."""
        if peer_id not in self.pcs:
            logger.warning(f"[{peer_id}] Received answer from unknown peer")
            return
            
        pc = self.pcs[peer_id]
        logger.info(f"[{peer_id}] Received SDP Answer. State: signaling={pc.signalingState}, connection={pc.connectionState}")
        
        if pc.signalingState == "stable":
            logger.info(f"[{peer_id}] Already stable. Ignoring redundant answer.")
            self.negotiating.discard(peer_id)
            return

        try:
            # Permissive Parser: Handle nested JSON stringified SDP
            if isinstance(sdp_data, dict) and isinstance(sdp_data.get("sdp"), str) and sdp_data["sdp"].startswith('{"sdp"'):
                try:
                    nested = json.loads(sdp_data["sdp"])
                    sdp_data = nested
                    logger.info(f"[{peer_id}] Unwrapped nested JSON SDP in Answer.")
                except:
                    pass

            if isinstance(sdp_data, str):
                answer = object_from_string(sdp_data)
            elif isinstance(sdp_data, dict):
                answer = RTCSessionDescription(sdp=sdp_data["sdp"], type=sdp_data["type"])
            else:
                raise ValueError("Unsupported SDP data format")

            await pc.setRemoteDescription(answer)
            logger.info(f"[{peer_id}] Remote description set (Answer). State is now stable.")
            self.negotiating.discard(peer_id)
        except Exception as e:
            logger.error(f"[{peer_id}] Failed to handle answer: {e}")
            self.negotiating.discard(peer_id)

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
