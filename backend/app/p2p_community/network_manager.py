import asyncio
import logging
import httpx
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

from .models import Node, Group
from .bootstrap_client import bootstrap_client, PeerAddress, NodeRegistration
from .message_protocol import MessageProtocol, MessageType, SignedMessage

logger = logging.getLogger(__name__)

class NetworkManager:
    def __init__(self, message_protocol: MessageProtocol):
        self.groups: Dict[str, Group] = {}
        self.nodes: Dict[str, Node] = {}
        self.message_protocol = message_protocol
        self.bootstrap = bootstrap_client
        self.local_node_id = None
        self.http_client = httpx.AsyncClient(timeout=10.0)

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
            topo = await self.bootstrap.get_network_topology()
            if topo:
                self._sync_topology(topo)
                logger.debug("Network topology synchronized")
        except Exception as e:
            logger.error(f"Failed to sync topology: {e}")

    def _sync_topology(self, topology_data: Dict):
        """Sync local view with topology data including endpoints and members."""
        # 1. Sync Groups
        if "groups" in topology_data:
            for gid, gdata in topology_data["groups"].items():
                if gid not in self.groups:
                    self.groups[gid] = Group(
                        group_id=gdata["group_id"],
                        level=gdata["level"],
                        parent_id=gdata["parent_id"]
                    )
        
        # Sync members from hierarchy (Critical for P2P discovery)
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

        # 2. Sync Nodes (Endpoints are critical for routing)
        if "nodes" in topology_data:
            for nid, ndata in topology_data["nodes"].items():
                if nid not in self.nodes:
                    node = Node(
                        node_id=nid,
                        network_manager=self,
                        public_key=ndata.get("public_key", "")
                    )
                    self.nodes[nid] = node
                
                # Update endpoint and public key if provided
                self.nodes[nid].public_key = ndata.get("public_key", self.nodes[nid].public_key)
                ip = ndata.get("ip_address")
                port = ndata.get("port")
                if ip and port:
                    self.nodes[nid].endpoint = f"http://{ip}:{port}"

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
            port=port
        )
        await self.bootstrap.register_node(reg)
        logger.info(f"Registered local node {node.node_id} at {host}:{port}")

        # --- Start Relay Client ---
        # --- Start Relay Client ---
        from .relay_client import RelayClient
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

    async def handle_relayed_message(self, message_dict: Dict):
        """Callback for messages received via WebSocket relay."""
        try:
            # message_dict is the raw SignedMessage dict
            # We need to parse it back to SignedMessage object if possible or pass as is
            # The receive_message expects SignedMessage object
            # Let's reconstruct it
            msg = SignedMessage(
                message_id=message_dict.get("message_id"),
                sender_id=message_dict.get("sender_id"),
                recipient_id=message_dict.get("recipient_id"),
                message_type=MessageType(message_dict.get("message_type")),
                content=message_dict.get("content"),
                timestamp=message_dict.get("timestamp"),
                signature=message_dict.get("signature"),
                nonce=message_dict.get("nonce")
            )
            
            logger.info(f"Received RELAYED message from {msg.sender_id}")
            if self.local_node_id in self.nodes:
                await self.nodes[self.local_node_id].receive_message(msg)
                
        except Exception as e:
            logger.error(f"Failed to handle relayed message: {e}")

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
                group_id=group_id
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
        content: Dict[str, Any]
    ):
        """
        Create, sign, and route a message.
        """
        # Convert string msg_type to Enum
        try:
            m_type = MessageType(msg_type)
        except ValueError:
            logger.warning(f"Invalid message type {msg_type}, defaulting to DIRECT")
            m_type = MessageType.DIRECT

        signed_msg = self.message_protocol.create_message(
            sender_id=sender_id,
            recipient_id=target_id,
            message_type=m_type,
            content=content
        )
        
        await self.route_message(signed_msg)

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
            logger.warning(f"Failed to reach peer {endpoint}: {e}")
            return False

    async def _send_via_relay(self, target_id: str, message: SignedMessage):
        """Fallback: Send message via Bootstrap Relay."""
        if hasattr(self, 'relay_client') and self.relay_client.websocket:
            logger.info(f"Fallback: Sending message to {target_id} via RELAY")
            await self.relay_client.send(message.to_dict())
            return True
        return False

    async def route_message(self, message: SignedMessage):
        """Route message to local node or remote peer via HTTP, fallback to Relay."""
        logger.info(f"[Network] Routing {message.message_type.value} message to {message.recipient_id}")

        # Helper to route to single node with fallback
        async def send_to_node(node_id: str, msg: SignedMessage):
            if node_id == self.local_node_id:
                if self.local_node_id in self.nodes:
                    await self.nodes[self.local_node_id].receive_message(msg)
                return

            if node_id in self.nodes:
                target = self.nodes[node_id]
                success = False
                if target.endpoint:
                    success = await self._send_http_message(target.endpoint, msg)
                
                if not success:
                    # Fallback to Relay
                    await self._send_via_relay(node_id, msg)
            else:
                 # Try Relay even if unknown (maybe new node)
                 await self._send_via_relay(node_id, msg)


        if message.message_type == MessageType.DIRECT:
            await send_to_node(message.recipient_id, message)

        elif message.message_type == MessageType.GROUP:
            if message.recipient_id in self.groups:
                members = self.groups[message.recipient_id].members
                tasks = []
                for mid in members:
                    if mid == self.local_node_id:
                        if message.sender_id != self.local_node_id:
                            # Deliver group messages sent by others to our inbox
                            tasks.append(self.nodes[mid].receive_message(message))
                    else:
                        tasks.append(send_to_node(mid, message))
                if tasks:
                    await asyncio.gather(*tasks)
            else:
                logger.warning(f"Target group {message.recipient_id} not found")

    def get_network_structure(self):
        """Returns a dict representation of the hierarchy."""
        return {
            "total_nodes": len(self.nodes),
            "total_groups": len(self.groups),
            "groups": {g_id: g.to_dict() for g_id, g in self.groups.items()},
            "nodes": {n_id: {"public_key": n.public_key[:16] + "..."} for n_id, n in self.nodes.items()},
            "relay_connected": getattr(self, 'relay_client', None) and self.relay_client.websocket is not None
        }
