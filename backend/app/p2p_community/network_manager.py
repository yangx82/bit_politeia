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
        # Try UPnP Port Mapping
        from .nat_traversal import nat_manager
        if nat_manager.discover_gateway():
            # Try to map default port 8000
            external_port = 8000
            # If we have a local node endpoint configured, try to use that port
            if self.local_node_id and self.local_node_id in self.nodes:
                 # Logic to parse port from endpoint... simplified for now
                 pass

            if nat_manager.add_port_mapping(8000, external_port, "TCP", "BitPoliteia P2P"):
                public_ip = nat_manager.get_external_ip()
                if public_ip:
                    logger.info(f"NAT Traversal Successful. Public Endpoint: http://{public_ip}:{external_port}")
                    # We should update our local node's endpoint to this public one
                    # But we need to be careful not to break local testing.
                    # For now, just log it. In a real scenario, we'd update self.nodes[self.local_node_id].endpoint
        
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
        if node.endpoint:
            try:
                parsed = urlparse(node.endpoint)
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

    async def route_message(self, message: SignedMessage, from_relay: bool = False) -> bool:
        """Route message to local node or remote peer via HTTP, fallback to Relay."""
        self._log_throttled("info", f"[Network] Routing {message.message_type.value} message to {message.recipient_id} (From Relay: {from_relay})")

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
            if self.local_node_id in self.nodes:
                if group_id in self.nodes[self.local_node_id].group_ids:
                    if message.sender_id != self.local_node_id:
                        await self.nodes[self.local_node_id].receive_message(message)
            
            # 2. Peer Delivery strategy: Parallel Direct HTTP + Partial Relay Fallback
            if group_id in self.groups:
                members = list(self.groups[group_id].members)
                
                # Filter out ourselves
                targets = [m_id for m_id in members if m_id != self.local_node_id]
                
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
                
                # 3. Partial Relay Fallback: Only send to relay for nodes that failed direct delivery
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

    def get_network_structure(self):
        """Returns a dict representation of the hierarchy."""
        return {
            "total_nodes": len(self.nodes),
            "total_groups": len(self.groups),
            "groups": {g_id: g.to_dict() for g_id, g in self.groups.items()},
            "nodes": {n_id: {"name": n.name, "public_key": n.public_key[:16] + "...", "is_online": n.is_online} for n_id, n in self.nodes.items()},
            "relay_connected": getattr(self, 'relay_client', None) and self.relay_client.websocket is not None
        }
