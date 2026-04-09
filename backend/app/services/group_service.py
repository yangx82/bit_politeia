import logging
from typing import Optional, List, Dict
from .p2p_service import p2p_service

logger = logging.getLogger(__name__)

class GroupService:
    """
    Manages group-level business logic:
    - Node transfers
    - Hierarchy queries
    - Future: Elections, Promotions
    """
    
    async def get_current_group_info(self) -> List[Dict]:
        """Get info about groups this node belongs to."""
        group_ids = p2p_service.get_my_groups()
        groups = []
        for gid in group_ids:
            group = p2p_service.network_manager.get_group(gid)
            if group:
                groups.append(group.to_dict())
        return groups

    async def get_hierarchy_view(self) -> Dict:
        """Get the full view of the network hierarchy."""
        return p2p_service.get_network_status()

    async def request_transfer(self, target_group_id: str) -> bool:
        """
        Request transfer/join to another group.
        
        Args:
            target_group_id: Group ID to join
            
        Returns:
            Success status
        """
        local_node = p2p_service.local_node
        if not local_node:
            logger.error("Cannot transfer: Node not initialized")
            return False
            
        # Check if target group exists
        target_group = p2p_service.network_manager.get_group(target_group_id)
        if not target_group:
            logger.error(f"Cannot transfer: Target group {target_group_id} not found")
            return False
            
        # Attempt to join
        # Note: If this puts node > 2 groups, it will fail.
        # Logic to 'leave' old group before joining could be added here if 'Transfer' implies strict move.
        # For now, we treat as "Join if possible".
        
        success = await local_node.join_group(target_group_id)
        if success:
            logger.info(f"Node successfully joined group {target_group_id}")
            return True
        else:
            logger.warning(f"Failed to join group {target_group_id} (Constraints or Capacity)")
            return False

    async def leave_group(self, group_id: str) -> bool:
        """Leave a group."""
        local_node = p2p_service.local_node
        if not local_node:
            return False
            
        if group_id in local_node.group_ids:
            local_node.group_ids.remove(group_id)
            group = p2p_service.network_manager.get_group(group_id)
            if group:
                group.remove_member(local_node.node_id)
            logger.info(f"Left group {group_id}")
            return True
        return False

    async def update_core_nodes(self, group_id: str, node_ids: List[str]) -> bool:
        """
        Update group core nodes (leadership).
        1. Sync with Bootstrap Server
        2. Broadcast to P2P network
        """
        from .p2p_service import p2p_service
        from ..p2p_community.bootstrap_client import bootstrap_client
        
        local_node = p2p_service.local_node
        if not local_node:
            return False
            
        logger.info(f"Initiating core node update for group {group_id} to {len(node_ids)} nodes.")
        
        # 1. Sync with Bootstrap (Source of Truth)
        
        success = await bootstrap_client.set_core_nodes(group_id, node_ids, local_node.node_id)
        if not success:
            logger.error("Failed to update core nodes on bootstrap server (Authorization or Network issue).")
            # We skip broadcasting if bootstrap fails to prevent local/cloud divergence
            return False
            
        # 2. Local Update
        group = p2p_service.network_manager.get_group(group_id)
        if group:
            group.update_core_nodes(node_ids)
            
        # 3. P2P Broadcast
        await p2p_service.network_manager.broadcast_group_config(group_id, node_ids)
        
        return True

group_service = GroupService()
