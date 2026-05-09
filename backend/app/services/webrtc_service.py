import asyncio
import json
import logging
import os
from collections.abc import Callable
from typing import Any

from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.contrib.signaling import object_from_string

logger = logging.getLogger(__name__)

# Feature: Conditional Debug File Logging
ENABLE_DEBUG_LOG = os.getenv("ENABLE_DEBUG_LOGGING", "true").lower() == "true"
if ENABLE_DEBUG_LOG:
    log_dir = "backend/data/logs"
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(
        os.path.join(log_dir, "webrtc_prod.log"), mode="a", encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)
else:
    # If file logging is disabled, ensure we still have a basic level set for console (handled by main.py usually)
    logger.setLevel(logging.INFO)


class WebRTCManager:
    """
    Manages WebRTC Peer Connections and Data Channels.
    """

    def __init__(
        self,
        signaling_callback: Callable[[str, str, dict[str, Any]], Any],
        message_callback: Callable[[str, str], Any],
    ):
        self.pcs: dict[str, RTCPeerConnection] = {}  # peer_id -> RTCPeerConnection
        self.data_channels: dict[str, Any] = {}  # peer_id -> RTCDataChannel
        self.signaling_callback = (
            signaling_callback  # Function to send signaling messages via HTTP/Relay
        )
        self.message_callback = (
            message_callback  # Function to handle received data channel messages
        )
        self.negotiating: set[str] = set()  # peer_ids currently in handshake
        self.last_init_times: dict[str, float] = {}  # peer_id -> timestamp of last initiation
        self.pending_candidates: dict[
            str, list[dict[str, Any]]
        ] = {}  # peer_id -> list of buffered candidates
        self.heartbeat_tasks: dict[str, asyncio.Task] = {}  # peer_id -> heartbeat task
        self.loop = None

    def set_loop(self, loop):
        self.loop = loop

    async def get_or_create_pc(self, peer_id: str) -> RTCPeerConnection:
        # Use case-insensitive lookup
        peer_id_lower = peer_id.lower() if hasattr(peer_id, "lower") else str(peer_id).lower()
        if peer_id_lower in self.pcs:
            pc = self.pcs[peer_id_lower]
            if pc.signalingState != "closed":
                return pc
            logger.info(
                f"[{peer_id}] Existing PeerConnection is CLOSED. Cleaning up and recreating."
            )
            del self.pcs[peer_id_lower]
            if peer_id_lower in self.data_channels:
                del self.data_channels[peer_id_lower]

        # Configure STUN/TURN servers for NAT traversal
        ice_servers = []

        # 1. Default Robust STUN list for global coverage
        default_stuns = [
            "stun:stun.l.google.com:19302",
            "stun:stun1.l.google.com:19302",
            "stun:stun2.l.google.com:19302",
            "stun:stun3.l.google.com:19302",
            "stun:stun4.l.google.com:19302",
            "stun:stun.cloudflare.com:3478",
            "stun:stun.matrix.org:3478",
            "stun:stun.qq.com:3478",
            "stun:stun.miwifi.com:3478",
            "stun:stun.tuku.cn:3478",
        ]

        # 2. Add from ENV if provided (comma-separated list of STUN/TURN URLs)
        env_ice = os.getenv("ICE_SERVERS")
        if env_ice:
            server_urls = [s.strip() for s in env_ice.split(",")]
            logger.info(f"[{peer_id}] Using custom ICE Servers from environment.")
        else:
            server_urls = default_stuns

        # 3. Handle Credentials (primarily for TURN)
        turn_user = os.getenv("TURN_USER")
        turn_pass = os.getenv("TURN_PASS")

        for url in server_urls:
            if url.startswith("turn:"):
                ice_servers.append(
                    RTCIceServer(urls=[url], username=turn_user, credential=turn_pass)
                )
            else:
                ice_servers.append(RTCIceServer(urls=[url]))

        config = RTCConfiguration(iceServers=ice_servers)

        pc = RTCPeerConnection(configuration=config)
        self.pcs[peer_id.lower()] = pc

        @pc.on("datachannel")
        def on_datachannel(channel):
            logger.info(
                f"[{peer_id}] !!! DATA CHANNEL RECEIVED: {channel.label} (readyState: {channel.readyState}) !!!"
            )
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
                logger.info(
                    f"[{peer_id}] ICE gathering finished. Signaling state: {pc.signalingState}"
                )

        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                logger.info(
                    f"[{peer_id}] Found ICE Candidate: {candidate.host}:{candidate.port} ({candidate.type})"
                )
                # Send candidate to remote peer via signaling
                await self.signaling_callback(
                    peer_id,
                    "ice_candidate",
                    {
                        "sdpMid": candidate.sdpMid,
                        "sdpMLineIndex": candidate.sdpMLineIndex,
                        "candidate": f"candidate:{candidate.foundation} {candidate.component} {candidate.protocol} {candidate.priority} {candidate.host} {candidate.port} typ {candidate.type} "
                        + (
                            f"raddr {candidate.relatedAddress} rport {candidate.relatedPort}"
                            if candidate.relatedAddress
                            else ""
                        ),
                    },
                )
            else:
                logger.info(f"[{peer_id}] No more ICE candidates.")

        # Apply buffered candidates if any
        if peer_id_lower in self.pending_candidates:
            candidates = self.pending_candidates.pop(peer_id_lower)
            logger.info(f"[{peer_id}] Flushing {len(candidates)} buffered ICE candidates.")
            for cand_data in candidates:
                asyncio.create_task(self.handle_candidate(peer_id, cand_data))

        return pc

    async def handle_candidate(self, peer_id: str, candidate_data: Any):
        """Handle incoming ICE Candidate from remote peer."""
        peer_id_lower = peer_id.lower()
        if peer_id_lower not in self.pcs:
            logger.info(f"[{peer_id}] PC not ready. Buffering ICE candidate.")
            if peer_id_lower not in self.pending_candidates:
                self.pending_candidates[peer_id_lower] = []
            self.pending_candidates[peer_id_lower].append(candidate_data)
            return

        pc = self.pcs[peer_id_lower]
        try:
            # Parse candidate data
            # candidate_data usually looks like {"candidate": "...", "sdpMid": "...", "sdpMLineIndex": ...}
            from aiortc.sdp import candidate_from_sdp

            cand_str = candidate_data.get("candidate")
            if cand_str.startswith("candidate:"):
                cand_str = cand_str[10:]

            candidate = candidate_from_sdp(cand_str)
            candidate.sdpMid = candidate_data.get("sdpMid")
            candidate.sdpMLineIndex = candidate_data.get("sdpMLineIndex")

            await pc.addIceCandidate(candidate)
            logger.info(
                f"[{peer_id}] Added remote ICE candidate: {candidate.host}:{candidate.port}"
            )
        except Exception as e:
            logger.error(f"[{peer_id}] Failed to add ICE candidate: {e}")

    def setup_data_channel(self, peer_id: str, channel):
        logger.info(
            f"[{peer_id}] Setting up data channel '{channel.label}' (State: {channel.readyState})"
        )
        self.data_channels[peer_id.lower()] = channel

        @channel.on("open")
        def on_open():
            peer_id_lower = peer_id.lower()
            logger.info(f"[{peer_id}] !!! DATA CHANNEL '{channel.label}' IS OPEN !!!")
            print(f"\n[!!!] WebRTC DATA CHANNEL OPEN WITH {peer_id} [!!!]\n", flush=True)
            # Start heartbeat
            if peer_id_lower not in self.heartbeat_tasks:
                self.heartbeat_tasks[peer_id_lower] = asyncio.create_task(
                    self._heartbeat_loop(peer_id, channel)
                )

        @channel.on("message")
        def on_message(message):
            # Check for heartbeat ping/pong
            try:
                msg_data = json.loads(message)
                if isinstance(msg_data, dict):
                    if msg_data.get("type") == "ping":
                        channel.send(json.dumps({"type": "pong"}))
                        return
                    if msg_data.get("type") == "pong":
                        # Heartbeat received
                        return
            except:
                pass

            logger.info(f"[{peer_id}] >>> RECEIVED VIA WEBRTC: {message[:100]}...")
            # Handle received data
            if self.message_callback:
                if self.loop:
                    asyncio.run_coroutine_threadsafe(
                        self.message_callback(peer_id, message), self.loop
                    )
                else:
                    # Fallback
                    try:
                        import asyncio as _asyncio

                        loop = _asyncio.get_running_loop()
                        _asyncio.run_coroutine_threadsafe(
                            self.message_callback(peer_id, message), loop
                        )
                    except:
                        logger.error(f"[{peer_id}] WebRTC Message Error: No event loop available.")

        if channel.readyState == "open":
            on_open()
        else:
            channel.on("open", on_open)

    async def initiate_connection(self, peer_id: str):
        """Start a WebRTC connection with a peer."""
        import time

        peer_id_lower = peer_id.lower()
        pc = await self.get_or_create_pc(peer_id_lower)

        # Rate Limit Gap: 10 seconds between active initiation attempts
        now = time.time()
        last_init = self.last_init_times.get(peer_id_lower, 0)
        if now - last_init < 10.0:
            logger.debug(
                f"[{peer_id}] Connection initiation rate-limited (last attempt {now - last_init:.1f}s ago)"
            )
            return

        # Guard: Don't initiate if already connecting or connected
        if pc.signalingState != "stable":
            logger.info(
                f"[{peer_id}] Connection initiation skipped: signalingState is {pc.signalingState}"
            )
            return
        if pc.connectionState in ["connecting", "connected"]:
            logger.info(
                f"[{peer_id}] Connection initiation skipped: connectionState is {pc.connectionState}"
            )
            return

        # Synchronization Guard: Prevent multiple concurrent initiations
        if peer_id_lower in self.negotiating:
            logger.info(f"[{peer_id}] Connection initiation skipped: already negotiating.")
            return

        self.last_init_times[peer_id_lower] = now
        self.negotiating.add(peer_id_lower)
        logger.info(f"[{peer_id}] Initiating WebRTC connection...")

        try:
            # Create Data Channel
            channel = pc.createDataChannel("chat")
            self.setup_data_channel(peer_id, channel)

            # Create Offer with Timeout
            async with asyncio.timeout(30.0):
                offer = await pc.createOffer()
                await pc.setLocalDescription(offer)

            # Send Offer via Signaling (Simple dict, avoids double stringify)
            await self.signaling_callback(
                peer_id,
                "sdp_offer",
                {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
            )
        except TimeoutError:
            logger.error(f"[{peer_id}] Connection initiation TIMEOUT (30s).")
            self.negotiating.discard(peer_id_lower)
        except Exception as e:
            logger.error(f"[{peer_id}] Failed to initiate connection: {e}")
            self.negotiating.discard(peer_id_lower)

    async def handle_offer(self, peer_id: str, sdp_data: Any):
        """Handle incoming SDP Offer."""
        peer_id_lower = peer_id.lower()
        pc = await self.get_or_create_pc(peer_id)
        logger.info(
            f"[{peer_id}] Received SDP Offer. Current state: signaling={pc.signalingState}, connection={pc.connectionState}"
        )

        if pc.signalingState != "stable":
            logger.warning(
                f"[{peer_id}] Received Offer while in state {pc.signalingState}. Glare possible."
            )

        try:
            # Permissive Parser: Handle nested JSON stringified SDP (Legacy compat)
            if (
                isinstance(sdp_data, dict)
                and isinstance(sdp_data.get("sdp"), str)
                and sdp_data["sdp"].startswith('{"sdp"')
            ):
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
                from .p2p_service import p2p_service

                local_id = p2p_service.local_node.node_id if p2p_service.local_node else "z"
                if local_id < peer_id:
                    logger.info(
                        f"[{peer_id}] Glare detected. I am POLITE. Resetting connection for their offer."
                    )
                    # aiortc does not support rollback in setLocalDescription.
                    # We must close the current PC and recreate a fresh one to go back to 'stable'.
                    await pc.close()
                    peer_id_lower = peer_id.lower()
                    if peer_id_lower in self.pcs:
                        del self.pcs[peer_id_lower]
                    if peer_id_lower in self.data_channels:
                        del self.data_channels[peer_id_lower]
                    pc = await self.get_or_create_pc(peer_id)
                else:
                    logger.info(f"[{peer_id}] Glare detected. I am IMPOLITE. Ignoring their offer.")
                    return

            logger.info(f"[{peer_id}] Setting remote offer SDP...")
            async with asyncio.timeout(30.0):
                await pc.setRemoteDescription(offer)
                logger.info(
                    f"[{peer_id}] Remote offer set successfully. State: {pc.signalingState}"
                )

                # Create Answer
                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)

            # Send Answer via Signaling
            await self.signaling_callback(
                peer_id,
                "sdp_answer",
                {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
            )
        except TimeoutError:
            logger.error(f"[{peer_id}] SDP Offer handling TIMEOUT (30s).")
            self.negotiating.discard(peer_id_lower)
        except Exception as e:
            logger.error(f"[{peer_id}] Failed to handle offer: {e}")
            self.negotiating.discard(peer_id_lower)

    async def handle_answer(self, peer_id: str, sdp_data: Any):
        """Handle incoming SDP Answer."""
        peer_id_lower = peer_id.lower()
        if peer_id_lower not in self.pcs:
            logger.warning(f"[{peer_id}] Received answer from unknown peer")
            return

        pc = self.pcs[peer_id_lower]
        logger.info(
            f"[{peer_id}] Received SDP Answer. State: signaling={pc.signalingState}, connection={pc.connectionState}"
        )

        if pc.signalingState == "stable":
            logger.debug(f"[{peer_id}] Already stable. Ignoring redundant answer.")
            self.negotiating.discard(peer_id)
            return

        try:
            # Permissive Parser: Handle nested JSON stringified SDP
            if (
                isinstance(sdp_data, dict)
                and isinstance(sdp_data.get("sdp"), str)
                and sdp_data["sdp"].startswith('{"sdp"')
            ):
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

            logger.info(f"[{peer_id}] Setting remote answer SDP...")
            await pc.setRemoteDescription(answer)
            logger.info(f"[{peer_id}] Remote answer set successfully. State: {pc.signalingState}")
            logger.info(f"[{peer_id}] Remote description set (Answer). State is now stable.")
            self.negotiating.discard(peer_id)
        except Exception as e:
            logger.error(f"[{peer_id}] Failed to handle answer: {e}")
            self.negotiating.discard(peer_id)

    async def send_message(self, peer_id: str, message: str) -> bool:
        """Send message via Data Channel if available."""
        peer_id_lower = peer_id.lower()
        if (
            peer_id_lower in self.data_channels
            and self.data_channels[peer_id_lower].readyState == "open"
        ):
            try:
                self.data_channels[peer_id_lower].send(message)
                return True
            except Exception as e:
                logger.error(f"Failed to send via DataChannel: {e}")
                return False
        return False

    async def _heartbeat_loop(self, peer_id: str, channel):
        """Background loop to send pings and keep connection alive."""
        peer_id_lower = peer_id.lower()
        logger.info(f"[{peer_id}] Starting WebRTC Heartbeat loop.")
        try:
            while channel.readyState == "open":
                await asyncio.sleep(30)
                if channel.readyState == "open":
                    try:
                        channel.send(json.dumps({"type": "ping"}))
                    except Exception as e:
                        logger.warning(f"[{peer_id}] Heartbeat PING failed: {e}")
                        break
        except asyncio.CancelledError:
            pass
        finally:
            logger.info(f"[{peer_id}] WebRTC Heartbeat loop stopped.")
            if peer_id_lower in self.heartbeat_tasks:
                del self.heartbeat_tasks[peer_id_lower]
