import asyncio
import logging
from typing import Dict, List, Optional, Any

from .models import Node, Group
from .bootstrap_client import bootstrap_client, PeerAddress
from .message_protocol import MessageProtocol, MessageType, SignedMessage

logger = logging.getLogger(__name__)

class NetworkManager:
    def __init__(self, message_protocol: MessageProtocol):
        self.groups: Dict[str, Group] = {}
        self.nodes: Dict[str, Node] = {}
        self.message_protocol = message_protocol
        self.bootstrap = bootstrap_client # Use the simulator instance

    async def initialize(self):
        """
        Initialize network state from bootstrap server and distributed storage.
        """
        # Sync initial topology from bootstrap
        topo = await self.bootstrap.get_network_topology()
        self._sync_topology(topo)
        logger.info("NetworkManager initialized and topology synced")

    def _sync_topology(self, topology_data: Dict):
        """
        Sync local group view with topology data.
        """
        if "groups" in topology_data:
            for gid, gdata in topology_data["groups"].items():
                if gid not in self.groups:
                    group = Group(
                        group_id=gdata["group_id"],
                        level=gdata["level"],
                        parent_id=gdata["parent_id"]
                    )
                    # Manually setting children if available in dict, 
                    # dependent on Group.to_dict format in bootstrap
                    # For simulation, just ensuring existence
                    self.groups[gid] = group
                    
        # Update hierarchy links
        for gid, group in self.groups.items():
            if group.parent_id and group.parent_id in self.groups:
                parent = self.groups[group.parent_id]
                if gid not in parent.child_ids:
                    parent.add_child(gid)

        # 2. Sync Nodes
        if "nodes" in topology_data:
            for nid, ndata in topology_data["nodes"].items():
                if nid not in self.nodes:
                    # Create skeleton node for topology reference
                    node = Node(
                        node_id=nid,
                        network_manager=self,
                        public_key=ndata.get("public_key", "")
                    )
                    self.nodes[nid] = node
                else:
                    # Update public key if needed
                    self.nodes[nid].public_key = ndata.get("public_key", self.nodes[nid].public_key)

    def get_group(self, group_id: str) -> Optional[Group]:
        return self.groups.get(group_id)

    async def register_node(self, node: Node):
        """
        Register a node into the network.
        1. Register with Bootstrap Server
        2. Find appropriate group
        3. Join group
        """
        self.nodes[node.node_id] = node
        
        # 1. Register with Bootstrap
        reg_info = {
            "node_id": node.node_id,
            "public_key": node.public_key,
            "ip_address": "127.0.0.1", # Mock IP
            "port": 8000
        }
        # Note: bootstrap client expects dataclass, but we are simulating here.
        # Let's import the dataclass to be correct if we were calling strict type method
        from .bootstrap_client import NodeRegistration
        reg = NodeRegistration(**reg_info)
        await self.bootstrap.register_node(reg)

        # 2. Find group if not in any
        if not node.group_ids:
            # Try to join a level 1 group
            joinable_groups = await self.bootstrap.get_joinable_groups(preferred_level=1)
            if joinable_groups:
                target_group_info = joinable_groups[0]
                # Ensure we have this group locally
                if target_group_info.group_id not in self.groups:
                    # Sync this specific group
                    self.groups[target_group_info.group_id] = Group(
                        target_group_info.group_id, 
                        target_group_info.level, 
                        target_group_info.parent_id
                    )
                
                await node.join_group(target_group_info.group_id)
            else:
                logger.warning(f"No joinable groups found for node {node.node_id}")

    async def _sync_network_state(self):
        """Sync network state from bootstrap server."""
        # Use bootstrap client
        try:
            # 1. Get Topology / Groups
            # Default to joining level 1
            joinable_groups = await bootstrap_client.get_joinable_groups(preferred_level=1)
            if not joinable_groups:
                logger.warning("No joinable groups found via bootstrap.")
                return

            # Pick a group (random or first)
            target_group = joinable_groups[0]
            self.current_group_id = target_group.group_id
            
            # 2. Get Peers in that group
            # We need to enhance Client to get peers if API supports it, or use Topology
            # The bootstrap server core logic has get_topology_info, let's use that if needed
            # For now, let's just register ourselves which is the critical part
            
            # 3. Register Self
            if self.local_node_id:
                # We need public key and IP (mocked or discovered)
                pub_key = self.nodes[self.local_node_id].public_key if self.local_node_id in self.nodes else "mock_key"
                
                success = await bootstrap_client.register_node(NodeRegistration(
                    node_id=self.local_node_id,
                    public_key=pub_key, 
                    ip_address="127.0.0.1", # TODO: Real IP
                    port=8000,
                    group_id=self.current_group_id
                ))
                
                if success:
                    logger.info(f"Registered to group {self.current_group_id}")
                else:
                    logger.error("Failed to register with bootstrap server")

        except Exception as e:
            logger.error(f"Bootstrap sync failed: {e}")

    async def register_node_to_group(self, node_id: str, group_id: str) -> bool:
        """
        Handle a node joining a group.
        """
        if group_id not in self.groups:
            logger.error(f"Group {group_id} not found")
            return False
            
        group = self.groups[group_id]
        if node_id not in self.nodes:
            logger.error(f"Node {node_id} unknown")
            return False
            
        node = self.nodes[node_id]
        
        # Verify constraints
        if not node.can_join_group(group):
            logger.warning(f"Node {node_id} cannot join group {group_id} due to constraints")
            return False

        # Add to local group model
        group.add_member(node_id)
        
        # Update bootstrap server (simulated consistency)
        # Re-register with updated group info or specific update call
        # For simulation, register_node handles basic "current group" tracking if we passed it,
        # but here we just ensure local consistency.
        # In real P2P, we would broadcast a "MemberJoined" message.
        
        logger.info(f"Node {node_id} successfully joined group {group_id}")
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

    async def route_message(self, message: SignedMessage):
        """
        Route a signed message to its destination.
        """
        # Verify signature first
        # We need sender's public key. In simulation, we might have it in self.nodes
        sender_node = self.nodes.get(message.sender_id)
        if sender_node:
            sender_pk = sender_node.public_key
        else:
            # If sender unknown locally, try to look up public key from bootstrap
            sender_pk = await self.bootstrap.get_node_public_key(message.sender_id)
            if not sender_pk:
                logger.warning(f"Could not resolve public key for sender {message.sender_id}, dropping message")
                return

        valid = self.message_protocol.verify_message(message, sender_pk)
        if not valid:
            logger.error(f"Invalid signature for message {message.message_id}")
            return

        logger.info(f"[Network] Routing {message.message_type.value} from {message.sender_id} to {message.recipient_id}")

        if message.message_type == MessageType.DIRECT:
            if message.recipient_id in self.nodes:
                await self.nodes[message.recipient_id].receive_message(message)
            else:
                logger.warning(f"Target Node {message.recipient_id} not found locally.")

        elif message.message_type == MessageType.GROUP:
            # Broadcast to group
            if message.recipient_id in self.groups:
                group = self.groups[message.recipient_id]
                tasks = []
                for member_id in group.members:
                    if member_id != message.sender_id:
                        if member_id in self.nodes:
                            tasks.append(self.nodes[member_id].receive_message(message))
                if tasks:
                    await asyncio.gather(*tasks)
            else:
                logger.warning(f"Target Group {message.recipient_id} not found.")

    def get_network_structure(self):
        """Returns a dict representation of the hierarchy."""
        return {
            "total_nodes": len(self.nodes),
            "total_groups": len(self.groups),
            "groups": {g_id: g.to_dict() for g_id, g in self.groups.items()},
            "nodes": {n_id: {"public_key": n.public_key[:16] + "..."} for n_id, n in self.nodes.items()}
        }
