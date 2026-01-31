import logging
import uuid
import json
import os
from typing import Dict, List, Optional, Set
from datetime import datetime

# Import models from p2p_community (adjust path as needed)
from ..p2p_community.bootstrap_client import GroupInfo, PeerAddress, NodeRegistration
from .community_config import community_config, RULES_FILE_PATH

logger = logging.getLogger(__name__)

class BootstrapService:
    """
    Core logic for the Bootstrap Server.
    Manages the network topology, node registry, and community rules.
    Used by both the FastAPI server (Cloud/LAN) and potentially local simulations.
    """
    def __init__(self):
        self._groups: Dict[str, GroupInfo] = {}
        self._peers: Dict[str, PeerAddress] = {}  # node_id -> PeerAddress
        self._group_members: Dict[str, Set[str]] = {}  # group_id -> set of node_ids
        self._last_update = datetime.now()
        
        # Load Config
        self.group_capacity = community_config.get_group_capacity()
        self.max_subgroups = 3 # Hardcoded or config
        
        # Initialize Topology
        self._initialize_root_group()

    def _initialize_root_group(self):
        """Initialize with a single Level 1 group. Higher levels will grow naturally."""
        first_group_id = str(uuid.uuid4())
        self._groups[first_group_id] = GroupInfo(
            group_id=first_group_id,
            level=1,
            member_count=0,
            max_capacity=self.group_capacity,
            parent_id=None
        )
        self._group_members[first_group_id] = set()
        logger.info(f"Bootstrap: Initialized with single Level 1 group: {first_group_id}")

    def get_topology_info(self) -> Dict:
        """
        Returns full network topology: groups, nodes, and hierarchy.
        """
        return {
            "groups": {gid: g.to_dict() for gid, g in self._groups.items()},
            "nodes": {nid: p.to_dict() for nid, p in self._peers.items()},
            "hierarchy": {
                gid: list(members) for gid, members in self._group_members.items()
            },
            "stats": {
                "total_nodes": len(self._peers),
                "total_groups": len(self._groups),
                "last_update": self._last_update.isoformat()
            }
        }

    def get_community_rules(self) -> Dict:
        """
        Reads and returns the content of usage/community rules.
        """
        try:
            if os.path.exists(RULES_FILE_PATH):
                with open(RULES_FILE_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {"error": "Rules file not found"}
        except Exception as e:
            logger.error(f"Error reading rules: {e}")
            return {"error": str(e)}

    def get_joinable_groups(self, preferred_level: int = 1) -> List[GroupInfo]:
        """Find groups with space at the preferred level."""
        joinable = []
        for group in self._groups.values():
            if group.level == preferred_level and group.has_space:
                joinable.append(group)
        
        # Auto-scaling: In bottom-up, new groups are usually created via Splitting.
        # But if we need a specific level and none exists, we might need a parent logic.
        # For new nodes, Level 1 is always the entry point.
        return joinable

    def _create_child_group(self, parent_id: str) -> Optional[GroupInfo]:
        if parent_id not in self._groups: return None
        parent = self._groups[parent_id]
        
        child_count = sum(1 for g in self._groups.values() if g.parent_id == parent_id)
        if child_count >= self.max_subgroups:
            return None # Parent full
            
        new_id = str(uuid.uuid4())
        new_group = GroupInfo(
            group_id=new_id,
            level=parent.level - 1,
            member_count=0,
            max_capacity=self.group_capacity,
            parent_id=parent_id
        )
        self._groups[new_id] = new_group
        self._group_members[new_id] = set()
        self._last_update = datetime.now()
        return new_group

    def register_node(self, registration: NodeRegistration) -> bool:
        # Update/Create Peer
        self._peers[registration.node_id] = PeerAddress(
            node_id=registration.node_id,
            public_key=registration.public_key,
            ip_address=registration.ip_address,
            port=registration.port
        )
        
        # Determine Group
        target_group_id = registration.group_id
        
        # If no group specified/found, auto-assign (Always Level 1 for new nodes)
        if not target_group_id or target_group_id not in self._groups:
             joinable = self.get_joinable_groups(preferred_level=1)
             if joinable:
                  target_group_id = joinable[0].group_id
             else:
                  # Fallback: if somehow no L1 groups exist (shouldn't happen with split logic)
                  # or if all L1 are full but haven't split?
                  l1_groups = [g for g in self._groups.values() if g.level == 1 and g.has_space]
                  if l1_groups:
                       target_group_id = l1_groups[0].group_id
        
        if target_group_id:
            group = self._groups[target_group_id]
            self._group_members[target_group_id].add(registration.node_id)
            group.member_count = len(self._group_members[target_group_id])
            
            # Update space flag
            group.has_space = group.member_count < self.group_capacity
            
            # Check for Split Trigger
            split_threshold = community_config.rules.get("organization", {}).get("split_threshold", 26)
            if group.member_count >= split_threshold:
                logger.info(f"Bootstrap: Group {target_group_id} reached capacity {group.member_count}. Triggering split.")
                self._split_group(target_group_id)
                
            self._last_update = datetime.now()
            logger.info(f"Bootstrap: Node {registration.node_id} joined L{group.level} group {target_group_id}")
            return True
            
        return False

    def _split_group(self, group_id: str):
        """
        Split a group into two halves. 
        Then, ensure each half has a representative in a Level+1 group.
        """
        if group_id not in self._groups: return
        
        old_group = self._groups[group_id]
        members = list(self._group_members[group_id])
        
        mid = len(members) // 2
        remaining_members = members[:mid]
        moving_members = members[mid:]
        
        # 1. Create New Sibling Group
        new_id = str(uuid.uuid4())
        new_group = GroupInfo(
            group_id=new_id,
            level=old_group.level,
            member_count=len(moving_members),
            max_capacity=self.group_capacity,
            parent_id=old_group.parent_id,
            has_space=True
        )
        
        # 2. Update Old Group
        self._group_members[group_id] = set(remaining_members)
        old_group.member_count = len(remaining_members)
        old_group.has_space = True
        
        # 3. Register New Group
        self._groups[new_id] = new_group
        self._group_members[new_id] = set(moving_members)
        
        logger.info(f"Bootstrap: L{old_group.level} Split: {group_id} -> {group_id} & {new_id}")

        # 4. Handle Representatives (Bottom-Up)
        rep_old = remaining_members[0]
        rep_new = moving_members[0]

        # Ensure parent exists or create one
        parent_id = old_group.parent_id
        if not parent_id:
            parent_id = str(uuid.uuid4())
            parent_group = GroupInfo(
                group_id=parent_id,
                level=old_group.level + 1,
                member_count=0,
                max_capacity=self.group_capacity,
                parent_id=None
            )
            self._groups[parent_id] = parent_group
            self._group_members[parent_id] = set()
            
            old_group.parent_id = parent_id
            new_group.parent_id = parent_id
            logger.info(f"Bootstrap: Created new Parent L{parent_group.level} Group: {parent_id}")

        self._register_representative_to_parent(rep_old, parent_id)
        self._register_representative_to_parent(rep_new, parent_id)

    def _register_representative_to_parent(self, node_id: str, parent_id: str):
        """Helper to safely add a rep to parent, triggering recursive splits if needed."""
        if node_id not in self._group_members[parent_id]:
            self._group_members[parent_id].add(node_id)
            parent = self._groups[parent_id]
            parent.member_count = len(self._group_members[parent_id])
            parent.has_space = parent.member_count < self.group_capacity
            
            logger.info(f"Bootstrap: Node {node_id} elected as rep to L{parent.level} Group {parent_id}")
            
            # Recursive Split check
            split_threshold = community_config.rules.get("organization", {}).get("split_threshold", 26)
            if parent.member_count >= split_threshold:
                self._split_group(parent_id)

# Singleton instance
bootstrap_service = BootstrapService()
