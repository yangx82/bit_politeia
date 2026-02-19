from typing import List, Optional, Set, Dict, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

class Group:
    def __init__(self, group_id: str, level: int, parent_id: Optional[str] = None, name: str = None):
        self.group_id = group_id
        self.name = name or group_id
        self.level = level
        self.parent_id = parent_id
        self.child_ids: List[str] = []
        self.members: Set[str] = set()  # Set of Node IDs
        self.max_subgroups = 3 # Default max subgroups

    def add_member(self, node_id: str):
        self.members.add(node_id)

    def remove_member(self, node_id: str):
        if node_id in self.members:
            self.members.remove(node_id)

    def add_child(self, group_id: str) -> bool:
        """Add a child group if under capacity."""
        if len(self.child_ids) < self.max_subgroups:
            self.child_ids.append(group_id)
            return True
        return False

    def remove_child(self, group_id: str):
        if group_id in self.child_ids:
            self.child_ids.remove(group_id)

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "level": self.level,
            "parent_id": self.parent_id,
            "child_ids": self.child_ids,
            "members": list(self.members)
        }

    def __repr__(self):
        return f"Group(id={self.group_id}, level={self.level}, members={len(self.members)})"


class Node:
    def __init__(self, node_id: str, network_manager, public_key: str, name: str = "Agent"):
        self.node_id = node_id  # This is the Node ID (Public Key usually)
        self.public_key = public_key
        self.name = name
        self.network_manager = network_manager
        self.level: int = 1  # Default level for new nodes
        self.endpoint: Optional[str] = None # Address of the node's API (e.g. http://192.168.1.5:8001)
        
        # Nodes belong to at least 1 group, max 2 directly connected
        self.group_ids: Set[str] = set()
        
        self.inbox: List[dict] = []

    def can_join_group(self, target_group: Group) -> bool:
        """
        Check if node can join the target group based on constraints.
        Rule: Max 2 groups, must be directly connected (parent/child).
        """
        if target_group.group_id in self.group_ids:
            return True # Already in
            
        if len(self.group_ids) >= 2:
            return False
            
        if len(self.group_ids) == 0:
            return True
            
        # If already in 1 group, second must be adjacent
        current_group_id = list(self.group_ids)[0]
        current_group = self.network_manager.get_group(current_group_id)
        
        if not current_group:
            # Should not happen if state is consistent
            return True
            
        is_adjacent = (
            target_group.parent_id == current_group.group_id or
            current_group.parent_id == target_group.group_id
        )
        return is_adjacent

    async def join_group(self, group_id: str) -> bool:
        """
        Attempt to join a group.
        """
        success = await self.network_manager.register_node_to_group(self.node_id, group_id)
        if success:
            self.group_ids.add(group_id)
        return success

    async def send_message(self, target_id: str, content: Dict[str, Any], msg_type: str = 'DIRECT'):
        """
        Send a signed message via the network manager.
        """
        # Note: In the new architecture, we delegate message creation/signing 
        # to the protocol handler in network manager or a service.
        # This method is kept for backward compatibility but using new protocol.
        
        return await self.network_manager.send_signed_message(
            sender_id=self.node_id,
            target_id=target_id,
            msg_type=msg_type,
            content=content
        )

    async def receive_message(self, message: Any):
        """
        Receive a message (SignedMessage object or dict).
        """
        # If it's a SignedMessage object, convert to something loggable or store it
        if hasattr(message, 'to_dict'):
            msg_data = message.to_dict()
        else:
            msg_data = message
            
        logger.info(f"[Node {self.node_id}] Received {msg_data.get('message_type', 'unknown')} from {msg_data.get('sender_id', 'unknown')}")
        self.inbox.append(msg_data)
        
        # Persist to disk inbox for resumption
        try:
            import json
            import os
            os.makedirs("data/p2p", exist_ok=True)
            inbox_path = f"data/p2p/inbox_{self.node_id}.jsonl"
            with open(inbox_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(msg_data) + "\n")
        except Exception as e:
            logger.error(f"Failed to persist inbox message: {e}")

    def get_structure_info(self):
        """
        Access network structure info.
        """
        return self.network_manager.get_network_structure()
