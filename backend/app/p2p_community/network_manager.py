import asyncio
import logging
import httpx
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
from datetime import datetime

from .models import Node, Group
from .bootstrap_client import bootstrap_client, PeerAddress, NodeRegistration
from .message_protocol import MessageProtocol, MessageType, SignedMessage

logger = logging.getLogger(__name__)

class NetworkManager:
    def _log_throttled(self, level: str, message: str, interval: int = 10):
        """Log a message only if it hasn't been logged in the last 'interval' seconds."""
        import time
        now = time.time()
        last_time = self._last_logs.get(message, 0)
        if now - last_time > interval:
            self._last_logs[message] = now
            getattr(logger, level)(message)

    def __init__(self, message_protocol: MessageProtocol):
        self.groups: Dict[str, Group] = {}
        self.nodes: Dict[str, Node] = {}
        self.local_node_id: Optional[str] = None
        self.message_protocol = message_protocol
        self.bootstrap = bootstrap_client
        self.http_client = httpx.AsyncClient(timeout=3.0, trust_env=False)
        self._last_logs: Dict[str, float] = {} # For deduplication: message -> last_time

    async def initialize(self):
        """Initialize network state from bootstrap server."""
        # 1. Try UPnP Port Mapping
        from .nat_traversal import nat_manager
        
        # Determine the port we want to open (default 8000)
        internal_port = 8000
        
        # Discover and map via UPnP
        if nat_manager.discover_gateway():
            if nat_manager.add_port_mapping(internal_port, internal_port, "TCP", "BitPoliteia P2P"):
                public_ip = nat_manager.get_external_ip()
                if public_ip:
                    logger.info(f"[Network] UPnP NAT Traversal Successful. Public Endpoint: http://{public_ip}:{internal_port}")
        
        # 2. Try STUN Discovery (Parallel Fallback)
        # STUN is often more reliable than UPnP and helps even if UPnP works (verifies mapping)
        # We run this in a thread to avoid blocking the async loop
        try:
            stun_loop = asyncio.get_event_loop()
            await stun_loop.run_in_executor(None, nat_manager.get_stun_endpoint, internal_port)
        except Exception as e:
            logger.debug(f"[Network] STUN background discovery error: {e}")
        
        await self.sync_topology()
        logger.info("NetworkManager initialized and topology synced")

    async def sync_topology(self):
        """Fetch and sync full network topology from bootstrap."""
        try:
            topo = await self.bootstrap.get_network_topology(my_node_id=self.local_node_id)
            if topo:
                self._sync_topology(topo)
                logger.debug("Network topology synchronized")
        except Exception as e:
            logger.error(f"Failed to sync topology: {e}")

    def _sync_topology(self, topology_data: Dict):
        """Sync local view with topology data including endpoints and members."""
        logger.info("[Network] Syncing topology with bootstrap data...")
        
        # 1. Sync Groups
        server_group_ids = set()
        if "groups" in topology_data:
            for gid, gdata in topology_data["groups"].items():
                server_group_ids.add(gid)
                if gid not in self.groups:
                    self.groups[gid] = Group(
                        group_id=gdata["group_id"],
                        level=gdata["level"],
                        parent_id=gdata["parent_id"],
                        name=gdata.get("name")
                    )
                else:
                    # Update name if changed
                    if gdata.get("name"):
                        self.groups[gid].name = gdata["name"]
        
        # REMOVE Stale Groups
        stale_groups = [gid for gid in self.groups if gid not in server_group_ids]
        for gid in stale_groups:
            logger.warning(f"[Network] Removing stale group {gid} (not in bootstrap)")
            
            # If local node is in this group, leave it
            if self.local_node_id and self.local_node_id in self.nodes:
                local_node = self.nodes[self.local_node_id]
                if gid in local_node.group_ids:
                    local_node.group_ids.remove(gid)
                    logger.info(f"[Network] Local node removed from stale group {gid}")
            
            del self.groups[gid]

        # Sync members from hierarchy
        if "hierarchy" in topology_data:
            for gid, members in topology_data["hierarchy"].items():
                if gid in self.groups:
                    self.groups[gid].members = set(members)
                    
        # Update hierarchy links
        for gid, group in self.groups.items():
            if group.parent_id and group.parent_id in self.groups:
                parent = self.groups[group.parent_id]
                if gid not in parent.child_ids:
                    parent.add_child(gid)

        # 2. Sync Nodes
        server_node_ids = set()
        if "nodes" in topology_data:
            for nid, ndata in topology_data["nodes"].items():
                server_node_ids.add(nid)
                if nid not in self.nodes:
                    node = Node(
                        node_id=nid,
                        network_manager=self,
                        public_key=ndata.get("public_key", ""),
                        name=ndata.get("name", "Agent")
                    )
                    self.nodes[nid] = node
                
                # Update endpoint and metadata
                self.nodes[nid].public_key = ndata.get("public_key", self.nodes[nid].public_key)
                if ndata.get("name"):
                    self.nodes[nid].name = ndata.get("name")
                
                ip = ndata.get("ip_address")
                port = ndata.get("port")
                if ip and port:
                    self.nodes[nid].endpoint = f"http://{ip}:{port}"
                
                # Update last_seen
                ls_str = ndata.get("last_seen")
                if ls_str:
                    try:
                        from datetime import datetime
                        self.nodes[nid].last_seen = datetime.fromisoformat(ls_str)
                    except (ValueError, TypeError):
                        pass

        # 3. Remove stale nodes (offline/deleted on bootstrap server)
        stale_nodes = [nid for nid in self.nodes if nid not in server_node_ids and nid != self.local_node_id]
        for nid in stale_nodes:
            logger.info(f"[Network] Removing stale node {nid} from local topology cache")
            del self.nodes[nid]

    def get_group(self, group_id: str) -> Optional[Group]:
        return self.groups.get(group_id)

    async def register_node(self, node: Node):
        """Register the local node and join an entry group."""
        self.nodes[node.node_id] = node
        self.local_node_id = node.node_id
        
        # Parse own endpoint for bootstrap registration
        host, port = "127.0.0.1", 8000
        
        # Use discovered public endpoint from NAT traversal (UPnP or STUN)
        from .nat_traversal import nat_manager
        if nat_manager.public_ip:
            host = nat_manager.public_ip
            if nat_manager.public_port:
                port = nat_manager.public_port
            
            # If node.endpoint was localhost, update it to the public one
            if node.endpoint:
                try:
                    parsed = urlparse(node.endpoint)
                    if parsed.hostname in ("127.0.0.1", "localhost", "0.0.0.0"):
                        node.endpoint = f"http://{host}:{port}"
                except Exception: pass
            else:
                node.endpoint = f"http://{host}:{port}"
                
            logger.info(f"[Network] Using discovered public endpoint for registration: {host}:{port}")
        
        # Override with specifically provided node.endpoint if set and not localhost
        if node.endpoint:
            try:
                parsed = urlparse(node.endpoint)
                if parsed.hostname not in ("127.0.0.1", "localhost", "0.0.0.0"):
                    host = parsed.hostname or host
                    port = parsed.port or port
            except Exception: pass
        
        reg = NodeRegistration(
            node_id=node.node_id,
            public_key=node.public_key,
            ip_address=host,
            port=port,
            name=node.name
        )
        await self.bootstrap.register_node(reg)
        logger.info(f"Registered local node {node.node_id} at {host}:{port}")

        # --- Start Relay Client ---
        from .relay_client import RelayClient
        
        # Stop existing client if any
        if hasattr(self, 'relay_client') and self.relay_client:
            logger.info("Stopping existing RelayClient...")
            await self.relay_client.stop()

        self.relay_client = RelayClient(
            server_url=self.bootstrap.server_url,
            node_id=node.node_id,
            message_handler=self.handle_relayed_message,
            verify_ssl=self.bootstrap.verify
        )
        await self.relay_client.start()
        logger.info(f"RelayClient started (SSL Verify: {self.bootstrap.verify})")
        # ---------------------------

        # Auto-join first level group if none assigned
        if not node.group_ids:
            joinable = await self.bootstrap.get_joinable_groups(preferred_level=1)
            if joinable:
                await node.join_group(joinable[0].group_id)
            else:
                logger.warning(f"No joinable groups found for node {node.node_id}")

    async def handle_relayed_message(self, message_data: Dict):
        """Handle messages received via RelayClient."""
        try:
            # Check for system messages first
            msg_type = message_data.get("type", message_data.get("message_type"))
            if msg_type == "SYSTEM_ERROR":
                self._log_throttled("warning", f"[Network] Relay System Error: {message_data.get('content')} (Target: {message_data.get('recipient_id')}, Message: {message_data.get('message_id')})")
                # Propagate to local node for handling (async status update)
                if self.local_node_id in self.nodes:
                     await self.nodes[self.local_node_id].receive_message(message_data)
                return

            # Basic Validation before parsing
            if "timestamp" not in message_data:
                logger.warning(f"[Network] Received relayed message missing 'timestamp'. Content: {str(message_data)[:200]}")
                # If it has recipient_id and content, maybe it's a malformed SignedMessage?
                # We expect all standard P2P messages to be SignedMessages.
                return

            # Parse dict back to SignedMessage
            message = SignedMessage.from_dict(message_data)
            logger.info(f"[Network] Received RELAYED message {message.message_id} from {message.sender_id}")
            
            # Route locally
            await self.route_message(message, from_relay=True)
        except Exception as e:
            import traceback
            logger.error(f"Failed to handle relayed message: {e}\n{traceback.format_exc()}")
            logger.debug(f"Malformed message data: {message_data}")

    async def register_node_to_group(self, node_id: str, group_id: str) -> bool:
        """Join a group and notify bootstrap if it's the local node."""
        if group_id not in self.groups:
            await self.sync_topology()
            if group_id not in self.groups:
                return False
            
        group = self.groups[group_id]
        if node_id not in self.nodes: return False
        node = self.nodes[node_id]
        
        if not node.can_join_group(group): return False

        if node_id == self.local_node_id:
            # Sync with bootstrap server to update cloud topology
            host, port = "127.0.0.1", 8000
            if node.endpoint:
                try:
                    parsed = urlparse(node.endpoint)
                    host = parsed.hostname or host
                    port = parsed.port or port
                except Exception: pass
            
            reg = NodeRegistration(
                node_id=node_id,
                public_key=node.public_key,
                ip_address=host,
                port=port,
                group_id=group_id,
                name=node.name
            )
            await self.bootstrap.register_node(reg)

        group.add_member(node_id)
        logger.info(f"Node {node_id} joined group {group_id}")
        return True


    async def send_signed_message(
        self,
        sender_id: str,
        target_id: str,
        msg_type: str,
        content: Dict[str, Any],
        message_id: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ):
        """
        Create, sign, and route a message.
        """
        # Convert string msg_type to Enum (handle case-insensitivity)
        try:
            m_type = MessageType(msg_type.lower()) if isinstance(msg_type, str) else msg_type
        except ValueError:
            logger.warning(f"Invalid message type {msg_type}, defaulting to DIRECT")
            m_type = MessageType.DIRECT

        signed_msg = self.message_protocol.create_message(
            sender_id=sender_id,
            recipient_id=target_id,
            message_type=m_type,
            content=content,
            message_id=message_id,
            timestamp=timestamp
        )
        
        return await self.route_message(signed_msg)

    async def _send_http_message(self, endpoint: str, message: SignedMessage) -> bool:
        """Send a signed message to a remote node's API. Returns success boolean."""
        try:
            url = f"{endpoint.rstrip('/')}/api/v1/p2p/message"
            # Use the existing http_client for efficiency
            resp = await self.http_client.post(url, json=message.to_dict())
            if resp.status_code == 200:
                return True
            else:
                logger.warning(f"Transport error to {endpoint}: HTTP {resp.status_code}")
                return False
        except Exception as e:
            self._log_throttled("warning", f"Failed to reach peer {endpoint}: {e}")
            return False

    async def _send_via_relay(self, target_id: str, message: SignedMessage):
        """Fallback: Send message via Bootstrap Relay."""
        return await self._send_via_relay_dict(target_id, message.to_dict())

    async def _send_via_relay_dict(self, target_id: str, msg_dict: Dict):
        """Send raw msg_dict via Bootstrap Relay (supports targeted broadcast)."""
        if hasattr(self, 'relay_client') and self.relay_client.websocket:
            self._log_throttled("info", f"Fallback: Sending message to {target_id} via RELAY")
            return await self.relay_client.send(msg_dict)
        return False

    async def route_message(self, message: SignedMessage, from_relay: bool = False, gossip_forward: bool = True) -> bool:
        """Route message to local node or remote peer via HTTP, fallback to Relay.
        
        Args:
            message: The signed message to route
            from_relay: Whether this message came from relay (prevents loops)
            gossip_forward: Whether to forward to other group members (Gossip protocol)
        """
        self._log_throttled("info", f"[Network] Routing {message.message_type.value} message to {message.recipient_id} (From Relay: {from_relay}, Gossip: {gossip_forward})")

        # Helper to route to single node with fallback
        async def send_to_node(node_id: str, msg: SignedMessage) -> bool:
            if node_id == self.local_node_id:
                if self.local_node_id in self.nodes:
                    await self.nodes[self.local_node_id].receive_message(msg)
                return True

            if node_id in self.nodes:
                target = self.nodes[node_id]
                success = False
                if target.endpoint:
                    success = await self._send_http_message(target.endpoint, msg)
                
                if not success:
                    # BLOCK RE-RELAY: If it came from relay, don't send back to relay
                    if from_relay:
                        self._log_throttled("warning", f"[Network] Dropping message to {node_id} to prevent Relay Loop.")
                        return False
                    
                    # Fallback to Relay
                    return await self._send_via_relay(node_id, msg)
                return True
            else:
                 # Try Relay even if unknown (maybe new node)
                 if from_relay:
                     self._log_throttled("warning", f"[Network] Unknown recipient {node_id} for relayed message. Dropping to prevent loop.")
                     return False
                 return await self._send_via_relay(node_id, msg)

        # Handle routing: Detect if recipient is a group to trigger broadcast logic
        is_group_id = message.recipient_id in self.groups
        
        # FIX: Also broadcast PROPOSAL and VOTE messages to group members
        is_group_broadcast_type = message.message_type in (
            MessageType.GROUP, MessageType.PROPOSAL, MessageType.VOTE
        )
        
        if is_group_broadcast_type or is_group_id:
            group_id = message.recipient_id
            
            # 1. Local Delivery: Deliver to self if we are a member
            local_delivered = False
            if self.local_node_id in self.nodes:
                if group_id in self.nodes[self.local_node_id].group_ids:
                    if message.sender_id != self.local_node_id:
                        await self.nodes[self.local_node_id].receive_message(message)
                        local_delivered = True
            
            # 2. GOSSIP PROTOCOL: Forward to other group members
            # This ensures messages propagate even if not all members are in local topology
            if gossip_forward and not from_relay:
                asyncio.create_task(self._gossip_broadcast(message, group_id, exclude_sender=True))
            
            # 3. Direct delivery to known members (legacy behavior, kept for compatibility)
            if group_id in self.groups:
                members = list(self.groups[group_id].members)
                
                # Filter out ourselves and the original sender
                targets = [m_id for m_id in members if m_id != self.local_node_id and m_id != message.sender_id]
                
                if not targets:
                    return True
                
                logger.info(f"[Network] Broadcast for {message.message_type.value}: Initiating parallel direct delivery to {len(targets)} members.")
                
                # Parallel Task: Attempt direct HTTP for each member
                async def attempt_direct(m_id: str):
                    if m_id in self.nodes:
                        target_node = self.nodes[m_id]
                        if target_node.endpoint:
                            success = await self._send_http_message(target_node.endpoint, message)
                            return m_id if not success else None
                    return m_id # No endpoint or unknown node = Failure for direct

                direct_tasks = [attempt_direct(m_id) for m_id in targets]
                failed_ids = await asyncio.gather(*direct_tasks)
                
                # Filter out Nones (successes)
                failed_ids = [fid for fid in failed_ids if fid is not None]
                
                if not failed_ids:
                    logger.info(f"[Network] Broadcast for {message.message_type.value}: All {len(targets)} members reached via direct HTTP.")
                    return True
                
                # 4. Partial Relay Fallback: Only send to relay for nodes that failed direct delivery
                if from_relay:
                    # Prevent relay loops
                    return True
                
                logger.info(f"[Network] Broadcast for {message.message_type.value}: {len(failed_ids)} members unreachable directly. Requesting Partial Relay Broadcast.")
                msg_dict = message.to_dict()
                msg_dict["target_node_ids"] = failed_ids # Signal to relay to only send to these
                
                return await self._send_via_relay_dict(group_id, msg_dict)
            else:
                if not from_relay:
                    logger.info(f"[Network] Group {group_id} not found locally. Pushing to Relay for full broadcast.")
                    return await self._send_via_relay(group_id, message)
                return True
        
        # Default: Direct route to single node
        return await send_to_node(message.recipient_id, message)

    async def _gossip_broadcast(self, message: SignedMessage, group_id: str, exclude_sender: bool = True):
        """
        Gossip Protocol: Forward message to all known group members.
        This ensures eventual consistency even when topology is incomplete.
        """
        # Prevent duplicate gossip for same message
        gossip_key = f"gossip:{message.message_id}:{self.local_node_id}"
        if hasattr(self, '_gossip_cache') and gossip_key in self._gossip_cache:
            logger.debug(f"[Gossip] Already forwarded message {message.message_id}, skipping.")
            return
        
        # Initialize gossip cache if not exists
        if not hasattr(self, '_gossip_cache'):
            self._gossip_cache = set()
        
        self._gossip_cache.add(gossip_key)
        
        # Clean old cache entries if too large (simple LRU)
        if len(self._gossip_cache) > 10000:
            self._gossip_cache = set(list(self._gossip_cache)[-5000:])
        
        if group_id not in self.groups:
            logger.debug(f"[Gossip] Group {group_id} not in local topology, cannot forward.")
            return
        
        members = self.groups[group_id].members
        targets = []
        
        for member_id in members:
            # Skip self
            if member_id == self.local_node_id:
                continue
            # Skip original sender if requested
            if exclude_sender and member_id == message.sender_id:
                continue
            targets.append(member_id)
        
        if not targets:
            logger.debug(f"[Gossip] No targets to forward message {message.message_id}")
            return
        
        logger.info(f"[Gossip] Forwarding {message.message_type.value} message {message.message_id[:8]}... to {len(targets)} group members")
        
        # Forward to each target
        success_count = 0
        for target_id in targets:
            try:
                success = await self._forward_to_peer(message, target_id)
                if success:
                    success_count += 1
            except Exception as e:
                logger.debug(f"[Gossip] Failed to forward to {target_id[:8]}...: {e}")
        
        logger.info(f"[Gossip] Forwarded to {success_count}/{len(targets)} peers for message {message.message_id[:8]}...")

    async def _forward_to_peer(self, message: SignedMessage, peer_id: str) -> bool:
        """Forward a message to a specific peer via HTTP or Relay."""
        # If peer is known and has endpoint, try HTTP
        if peer_id in self.nodes:
            peer = self.nodes[peer_id]
            if peer.endpoint:
                success = await self._send_http_message(peer.endpoint, message)
                if success:
                    return True
        
        # Fallback to relay
        return await self._send_via_relay(peer_id, message)

    def get_network_structure(self):
        """Returns a dict representation of the hierarchy."""
        return {
            "total_nodes": len(self.nodes),
            "total_groups": len(self.groups),
            "groups": {g_id: g.to_dict() for g_id, g in self.groups.items()},
            "nodes": {n_id: {"name": n.name, "public_key": n.public_key[:16] + "...", "is_online": n.is_online} for n_id, n in self.nodes.items()},
            "relay_connected": getattr(self, 'relay_client', None) and self.relay_client.websocket is not None
        }

    async def request_state_sync(self, group_id: str):
        """
        Request state synchronization from group members.
        Used for periodic consistency checks and catching missed messages.
        """
        if not self.local_node_id or group_id not in self.groups:
            return
        
        logger.info(f"[StateSync] Requesting state sync for group {group_id}")
        
        # Create sync request message
        sync_content = {
            "sync_type": "state_request",
            "requester_id": self.local_node_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        sync_msg = self.message_protocol.create_message(
            sender_id=self.local_node_id,
            recipient_id=group_id,
            message_type=MessageType.SYNC,
            content=sync_content
        )
        
        # Broadcast sync request to all group members
        await self.route_message(sync_msg, gossip_forward=True)

    async def handle_state_sync_request(self, message: SignedMessage):
        """Handle incoming state sync request by sharing known proposals/elections."""
        content = message.content
        if content.get("sync_type") != "state_request":
            return
        
        requester_id = content.get("requester_id")
        if not requester_id or requester_id == self.local_node_id:
            return
        
        logger.info(f"[StateSync] Received sync request from {requester_id[:8]}...")
        
        # Import governance manager to get local state
        from ..services.agent_service import agent_service
        if not agent_service or not agent_service.governance_manager:
            return
        
        # Share active proposals and elections
        gm = agent_service.governance_manager
        group_id = message.recipient_id
        
        # Get proposals for this group
        for proposal in gm.proposals.values():
            if proposal.group_id == group_id:
                # Re-broadcast this proposal
                proposal_data = {
                    "proposal": proposal.to_dict(),
                    "election": gm.active_elections.get(proposal.proposal_id, {}).to_dict() if proposal.proposal_id in gm.active_elections else None
                }
                await self.broadcast_governance_event(group_id, "proposal", proposal_data)
                logger.info(f"[StateSync] Re-shared proposal {proposal.proposal_id[:8]}... to {requester_id[:8]}...")
                await asyncio.sleep(0.1)  # Rate limit to avoid flooding
