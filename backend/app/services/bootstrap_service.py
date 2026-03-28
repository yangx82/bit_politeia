import logging
import uuid
import json
import os
from typing import Dict, List, Optional, Set
from datetime import datetime

# Import models from p2p_community (adjust path as needed)
from ..p2p_community.bootstrap_client import GroupInfo, PeerAddress, NodeRegistration
from ..p2p_community.reputation import ReputationManager
from .community_config import community_config, RULES_FILE_PATH
from .bootstrap_storage import BootstrapStorage

logger = logging.getLogger(__name__)

class BootstrapService:
    """
    Core logic for the Bootstrap Server.
    Manages the network topology, node registry, and community rules.
    Used by both the FastAPI server (Cloud/LAN) and potentially local simulations.
    """
    def __init__(self):
        self.storage = None
        self._groups = {}
        self._peers = {}
        self._group_members = {}
        self._pending_joins = {}
        self._tunnel_allocations = {}
        
        self._reputation = ReputationManager("bootstrap")
        self._last_update = datetime.now()
        
        # Load Config
        self.group_capacity = community_config.get_group_capacity()
        self.max_subgroups = 3 # Hardcoded or config
        
        self._initialized = False

    def initialize(self):
        """Must be called after the event loop starts (e.g., inside FastAPI lifespan)."""
        if self._initialized: return
        
        self.storage = BootstrapStorage()
        
        # Load from Storage
        self._groups = self.storage.load_groups()
        self._peers = self.storage.load_nodes()
        self._group_members = self.storage.load_group_members()
        self._pending_joins = self.storage.load_pending_joins()
        self._tunnel_allocations = self.storage.load_tunnel_allocations()
        
        # Initialize Topology if empty
        if not self._groups:
            self._initialize_root_group()
            
        self._initialized = True
        logger.info("BootstrapService initialized successfully.")

    def _generate_group_name(self, level: int) -> str:
        """Generate a sequential human-readable name for a group (e.g., L1-G1)."""
        count = sum(1 for g in self._groups.values() if g.level == level)
        return f"L{level}-G{count + 1}"

    def _initialize_root_group(self):
        """Initialize with a single Level 1 group. Higher levels will grow naturally."""
        first_group_id = str(uuid.uuid4())
        new_group = GroupInfo(
            group_id=first_group_id,
            level=1,
            member_count=0,
            max_capacity=self.group_capacity,
            parent_id=None,
            core_node_ids=[],
            has_space=True,
            name=self._generate_group_name(1)
        )
        self._groups[first_group_id] = new_group
        self._group_members[first_group_id] = set()
        self._pending_joins[first_group_id] = []
        
        # Persist
        self.storage.upsert_group(new_group)
        
        logger.info(f"Bootstrap: Initialized with single Level 1 group: {first_group_id} ({self._groups[first_group_id].name})")

    def is_valid_group(self, group_id: str) -> bool:
        """Check if group_id exists in the topology."""
        return group_id in self._groups

    def get_topology_info(self, node_id: Optional[str] = None) -> Dict:
        """
        Returns full network topology: groups, nodes, and hierarchy.
        If node_id is provided, updates its last_seen timestamp (Heartbeat).
        """
        if node_id and node_id in self._peers:
            from datetime import timezone
            peer = self._peers[node_id]
            peer.last_seen = datetime.now(timezone.utc)
            # Persist the heartbeat to storage
            self.storage.upsert_node(peer)
            logger.debug(f"Bootstrap: Heartbeat received via topology sync from {node_id}")

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
    
    # ... (get_community_rules, get_joinable_groups, get_pending_joins unchanged) ...

    def _create_child_group(self, parent_id: str) -> Optional[GroupInfo]:
        if parent_id not in self._groups: return None
        parent = self._groups[parent_id]
        
        child_count = sum(1 for g in self._groups.values() if g.parent_id == parent_id)
        if child_count >= self.max_subgroups:
            return None # Parent full
            
        new_id = str(uuid.uuid4())
        new_level = parent.level - 1 # Logic error in original code? Groups grow UP or DOWN? 
        # Typically Root is L1, sub is L0? Or Root is L1 and Parents are L2?
        # Re-reading: "group.level = preferred_level". Usually L1 is base.
        # But _create_child_group implies going DOWN? 
        # Wait, the code says "parent.level - 1". So children have LOWER level.
        # But usually L1 is the lowest user group.
        # Let's assume standard hierarchy: L1 (Users) -> L2 (Reps) -> L3 (System).
        # In that case, creating a CHILD group usually implies a subgroup? 
        # Actually, in this system, groups split horizontally, and representatives form HIGHER level groups.
        # So _create_child_group might be a misnomer or for specific logic.
        # Let's stick to the existing logic but add naming.
        
        new_level = parent.level - 1
        new_group = GroupInfo(
            new_id,
            new_level,
            0,
            self.group_capacity,
            parent_id,
            has_space=True,
            core_node_ids=[],
            name=self._generate_group_name(new_level)
        )
        self._groups[new_id] = new_group
        self._group_members[new_id] = set()
        self._pending_joins[new_id] = []
        self._last_update = datetime.now()
        
        # Persist
        self.storage.upsert_group(new_group)
        
        return new_group

    def register_node(self, registration: NodeRegistration) -> bool:
        # 1. Update/Create Peer representation (metadata only)
        self._peers[registration.node_id] = PeerAddress(
            node_id=registration.node_id,
            public_key=registration.public_key,
            ip_address=registration.ip_address,
            port=registration.port,
            name=registration.name
        )
        self.storage.upsert_node(self._peers[registration.node_id])
        
        # Determine Group
        target_group_id = registration.group_id
        
        # If no group specified/found, auto-assign (Always Level 1 for new nodes)
        if not target_group_id or target_group_id not in self._groups:
             joinable = self.get_joinable_groups(preferred_level=1)
             if joinable:
                  target_group_id = joinable[0].group_id
             else:
                  # Fallback
                  l1_groups = [g for g in self._groups.values() if g.level == 1 and g.has_space]
                  if l1_groups:
                       target_group_id = l1_groups[0].group_id
        
        if not target_group_id:
            return False

        group = self._groups[target_group_id]
        
        # Apply Rules
        # Rule 1 & 2: Group empty or < 3 members -> Direct join
        if group.member_count < 3:
            return self._perform_actual_join(target_group_id, registration)
        
        # Rule 3: Member count >= 3 -> Approval required
        # Check if already pending
        if target_group_id not in self._pending_joins:
            self._pending_joins[target_group_id] = []
            
        is_already_pending = any(r.node_id == registration.node_id for r in self._pending_joins[target_group_id])
        if not is_already_pending:
            self._pending_joins[target_group_id].append(registration)
            self.storage.add_pending_join(target_group_id, registration)
            logger.info(f"Bootstrap: Node {registration.node_id} request to join Group {target_group_id} is PENDING approval.")
        
        # Return True because node is registered in _peers (visible in topology)
        # even though group membership is pending
        return True

    def unregister_node(self, node_id: str) -> bool:
        """
        Manually remove a node from the bootstrap server's state.
        Returns True if the node existed and was removed.
        """
        node_id = node_id.strip()
        # Case-insensitive match check
        target_nid = None
        for nid in self._peers.keys():
            if nid.lower() == node_id.lower():
                target_nid = nid
                break
                
        if not target_nid:
            available = list(self._peers.keys())[:5]
            logger.warning(f"Service: Attempted to unregister unknown node {node_id}. Available IDs (prefix): {available}")
            return False
            
        # 1. Remove from in-memory maps
        # Use the matched target_nid
        self._peers.pop(target_nid, None)
        
        # Remove from all group memberships and update group stats
        for group_id, members in self._group_members.items():
            if target_nid in members:
                members.remove(target_nid)
                if group_id in self._groups:
                    group = self._groups[group_id]
                    group.member_count = len(members)
                    group.has_space = group.member_count < self.group_capacity
                    
                    # Remove from core nodes
                    if node_id in group.core_node_ids:
                        group.core_node_ids.remove(node_id)
                    
                    # Remove from rankings
                    if node_id in group.node_rankings:
                        group.node_rankings.remove(node_id)
                    
                    # Persist group update (since count/cores/rankings changed)
                    self.storage.upsert_group(group)

        # 2. Remove from pending joins
        for group_id, pending in self._pending_joins.items():
            original_len = len(pending)
            self._pending_joins[group_id] = [r for r in pending if r.node_id != node_id]
            if len(self._pending_joins[group_id]) < original_len:
                # remove_pending_join already called inside storage.delete_node, 
                # but good to be explicit if iterating specifically here.
                pass

        # 3. Remove from peers registry
        self._peers.pop(node_id, None)

        # 4. Storage cleanup (Removes from nodes, group_members, rankings, cores, pending)
        self.storage.delete_node(node_id)
        
        # 5. Release tunnel allocation if any
        if node_id in self._tunnel_allocations:
            self._tunnel_allocations.pop(node_id)
            self.storage.delete_tunnel_allocation(node_id)
            logger.info(f"Bootstrap: Released tunnel port for node {node_id}")

        # 6. Global update
        self._last_update = datetime.now()
        logger.info(f"Bootstrap: Node {node_id} has been manually unregistered and removed from topology.")
        return True

    # --- Tunnel Management ---

    def allocate_tunnel_port(self, node_id: str) -> Optional[int]:
        """Allocate a unique port for a node's frp tunnel (Range: 60000-61000)."""
        # 1. Existing check
        if node_id in self._tunnel_allocations:
            return self._tunnel_allocations[node_id]
        
        # 2. Find available port
        used_ports = set(self._tunnel_allocations.values())
        port_start = 60000
        port_end = 61000
        for port in range(port_start, port_end + 1):
            if port not in used_ports:
                # Assign and Persist
                self._tunnel_allocations[node_id] = port
                self.storage.upsert_tunnel_allocation(node_id, port)
                logger.info(f"Bootstrap: Allocated tunnel port {port} to node {node_id}")
                return port
        
        logger.error(f"Bootstrap: Tunnel port pool exhausted ({port_start}-{port_end})!")
        return None

    def get_election_candidates(self, group_id: str) -> List[str]:
        """
        Identify candidates for the next core node election.
        Rules:
        1. Exclude existing formal core nodes.
        2. Pick top 2 nodes by reputation overall score.
        """
        if group_id not in self._groups:
            return []
            
        group = self._groups[group_id]
        members = self._group_members.get(group_id, set())
        
        # Filter out existing core nodes
        potentials = [mid for mid in members if mid not in group.core_node_ids]
        
        if not potentials:
            return []
            
        # Rank by reputation
        rankings = self._reputation.get_group_rankings(potentials)
        
        # Take top 2
        candidates = [nid for nid, score in rankings[:2]]
        
        # Log auto-nomination
        logger.info(f"Bootstrap: Auto-nominated candidates for Group {group_id}: {candidates}")
        return candidates

    def approve_node_join(self, group_id: str, node_id: str, approver_id: str) -> bool:
        """Approve a pending join request."""
        if group_id not in self._groups: return False
        group = self._groups[group_id]
        
        # Permission Check: Approver must be a core node if group >= 3
        if group.member_count >= 3 and approver_id not in group.core_node_ids:
            logger.warning(f"Approver {approver_id} is not a core node of group {group_id}")
            return False
            
        # Find registration in pending
        pending = self._pending_joins.get(group_id, [])
        registration = next((r for r in pending if r.node_id == node_id), None)
        
        if registration:
            # Perform join
            success = self._perform_actual_join(group_id, registration)
            if success:
                # Remove from pending
                self._pending_joins[group_id] = [r for r in pending if r.node_id != node_id]
                self.storage.remove_pending_join(group_id, node_id)
                logger.info(f"Bootstrap: Node {node_id} join to Group {group_id} APPROVED by {approver_id}")
                return True
        return False

    def set_group_rankings(self, group_id: str, rankings: List[str], requester_id: str) -> bool:
        """Set the ranking order for nodes in a group."""
        if group_id not in self._groups: return False
        group = self._groups[group_id]
        
        # Only existing core nodes can set rankings
        if requester_id not in group.core_node_ids:
            logger.warning(f"Unauthorized ranking update: {requester_id} is not a core node.")
            return False
            
        # Validate that all ranked nodes are actually in the group
        members = self._group_members.get(group_id, set())
        if not all(nid in members for nid in rankings):
            logger.warning(f"Invalid rankings: some nodes are not members of group {group_id}")
            return False
            
        group.node_rankings = rankings
        self.storage.upsert_group(group)
        logger.info(f"Bootstrap: Rankings updated for Group {group_id} by {requester_id}")
        return True

    def update_group_core_nodes(self, group_id: str, core_node_ids: List[str], requester_id: str) -> bool:
        """Update core nodes (e.g. after election)."""
        if group_id not in self._groups: return False
        group = self._groups[group_id]
        
        if requester_id not in group.core_node_ids:
            logger.warning(f"Unauthorized core node update: {requester_id} is not a core node.")
            return False
            
        group.core_node_ids = core_node_ids
        self.storage.upsert_group(group)
        logger.info(f"Bootstrap: Core nodes updated for Group {group_id}: {core_node_ids}")
        return True

    def _perform_actual_join(self, target_group_id: str, registration: NodeRegistration) -> bool:
        group = self._groups[target_group_id]
        self._group_members[target_group_id].add(registration.node_id)
        group.member_count = len(self._group_members[target_group_id])
        
        # REVISED RULE 1: First 2 nodes are proxy core nodes
        if group.member_count <= 2:
            if registration.node_id not in group.core_node_ids:
                group.core_node_ids.append(registration.node_id)
                logger.info(f"Bootstrap: Node {registration.node_id} designated as Proxy Core Node for Group {target_group_id}")
        
        # REVISED RULE 2: Election Triggers
        if group.member_count == 3:
            logger.info(f"ELECTION TRIGGER: Group {target_group_id} reached 3 members. Triggering election for 1st formal core node.")
        elif group.member_count == 11:
            logger.info(f"ELECTION TRIGGER: Group {target_group_id} reached 11 members. Triggering election for 2nd formal core node.")
        elif group.member_count == 19:
            logger.info(f"ELECTION TRIGGER: Group {target_group_id} reached 19 members. Triggering election for 3rd formal core node.")
        
        # Initial ranking is just join order if not set
        if registration.node_id not in group.node_rankings:
            group.node_rankings.append(registration.node_id)
        
        # Update space flag
        group.has_space = group.member_count < self.group_capacity
        
        # Check for Split Trigger
        split_threshold = community_config.rules.get("organization", {}).get("split_threshold", 26)
        if group.member_count >= split_threshold:
            logger.info(f"Bootstrap: Group {target_group_id} reached capacity {group.member_count}. Triggering split.")
            self._split_group(target_group_id)
            
        # Persist Membership and Group State (Core Nodes, Rankings, Count)
        self.storage.add_group_member(target_group_id, registration.node_id)
        self.storage.upsert_group(group)
            
        self._last_update = datetime.now()
        logger.info(f"Bootstrap: Node {registration.node_id} joined L{group.level} group {target_group_id}")
        return True

    def _split_group(self, group_id: str):
        """
        Split a group into two halves using odd/even ranking distribution.
        """
        if group_id not in self._groups: return
        
        old_group = self._groups[group_id]
        
        # REVISED RULE 4: Split by odd/even ranking
        if old_group.node_rankings:
            rankings = old_group.node_rankings
            remaining_members = [rankings[i] for i in range(len(rankings)) if i % 2 == 0]
            moving_members = [rankings[i] for i in range(len(rankings)) if i % 2 != 0]
        else:
            # Fallback to old mid-point logic if rankings missing
            members = list(self._group_members[group_id])
            mid = len(members) // 2
            remaining_members = members[:mid]
            moving_members = members[mid:]
        
        # 1. Create New Sibling Group
        new_id = str(uuid.uuid4())
        new_group = GroupInfo(
            new_id,
            old_group.level,
            len(moving_members),
            self.group_capacity,
            old_group.parent_id,
            has_space=True,
            core_node_ids=[],
            node_rankings=moving_members, # Carry over rankings to new group
            name=self._generate_group_name(old_group.level)
        )
        
        # 2. Update Old Group
        self._group_members[group_id] = set(remaining_members)
        old_group.member_count = len(remaining_members)
        old_group.has_space = True
        old_group.node_rankings = remaining_members # Update rankings
        
        # Filter core nodes for both groups
        old_cores = [cid for cid in old_group.core_node_ids if cid in remaining_members]
        new_cores = [cid for cid in old_group.core_node_ids if cid in moving_members]
        old_group.core_node_ids = old_cores
        new_group.core_node_ids = new_cores
        
        # 3. Register New Group
        self._groups[new_id] = new_group
        self._group_members[new_id] = set(moving_members)
        self._pending_joins[new_id] = []
        
        # Persist New Group
        self.storage.upsert_group(new_group)
        self.storage.upsert_group(old_group)
        
        # Persist Member Moves
        for mid in moving_members:
            self.storage.remove_group_member(group_id, mid)
            self.storage.add_group_member(new_id, mid)

        logger.info(f"Bootstrap: L{old_group.level} Split (Alternating): {old_group.name} ({group_id}) -> {old_group.name} & {new_group.name} ({new_id})")

        # 4. Handle Representatives (Bottom-Up)
        rep_old = remaining_members[0]
        rep_new = moving_members[0]

        # Ensure parent exists or create one
        parent_id = old_group.parent_id
        if not parent_id:
            parent_id = str(uuid.uuid4())
            parent_level = old_group.level + 1
            parent_group = GroupInfo(
                group_id=parent_id,
                level=parent_level,
                member_count=0,
                max_capacity=self.group_capacity,
                parent_id=None,
                name=self._generate_group_name(parent_level)
            )
            self._groups[parent_id] = parent_group
            self._group_members[parent_id] = set()
            self.storage.upsert_group(parent_group)
            
            old_group.parent_id = parent_id
            new_group.parent_id = parent_id
            logger.info(f"Bootstrap: Created new Parent L{parent_group.level} Group: {parent_id} ({parent_group.name})")

        self._register_representative_to_parent(rep_old, parent_id)
        self._register_representative_to_parent(rep_new, parent_id)

    def _register_representative_to_parent(self, node_id: str, parent_id: str):
        """Helper to safely add a rep to parent, triggering recursive splits if needed."""
        if node_id not in self._group_members[parent_id]:
            self._group_members[parent_id].add(node_id)
            parent = self._groups[parent_id]
            parent.member_count = len(self._group_members[parent_id])
            parent.has_space = parent.member_count < self.group_capacity
            
            self.storage.add_group_member(parent_id, node_id)
            self.storage.upsert_group(parent)
            
            logger.info(f"Bootstrap: Node {node_id} elected as rep to L{parent.level} Group {parent_id}")
            
            # Recursive Split check
            split_threshold = community_config.rules.get("organization", {}).get("split_threshold", 26)
            if parent.member_count >= split_threshold:
                self._split_group(parent_id)

# Singleton instance
bootstrap_service = BootstrapService()
