import httpx
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class PeerAddress:
    node_id: str
    public_key: str
    ip_address: str
    port: int
    name: Optional[str] = None
    from datetime import timezone
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_online(self) -> bool:
        """Check if the node has been seen in the last 5 minutes."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        target_time = self.last_seen
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)
        diff = (now - target_time).total_seconds()
        return diff < 300 # 5 minutes

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "public_key": self.public_key,
            "ip_address": self.ip_address,
            "port": self.port,
            "name": self.name,
            "last_seen": self.last_seen.isoformat(),
            "is_online": self.is_online
        }

@dataclass
class GroupInfo:
    group_id: str
    level: int
    member_count: int
    max_capacity: int
    parent_id: Optional[str] = None
    name: Optional[str] = None
    has_space: bool = False
    core_node_ids: List[str] = field(default_factory=list)
    node_rankings: List[str] = field(default_factory=list)  # Ordered list of IDs

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "level": self.level,
            "member_count": self.member_count,
            "max_capacity": self.max_capacity,
            "parent_id": self.parent_id,
            "name": self.name,
            "has_space": self.has_space,
            "core_node_ids": self.core_node_ids,
            "node_rankings": self.node_rankings
        }

@dataclass
class NodeRegistration:
    node_id: str
    public_key: str
    ip_address: str
    port: int
    group_id: Optional[str] = None
    name: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "public_key": self.public_key,
            "ip_address": self.ip_address,
            "port": self.port,
            "group_id": self.group_id,
            "name": self.name
        }

class BootstrapClient:
    """
    Client for interacting with the P2P Bootstrap Server (Cloud or Local LAN).
    """
    def __init__(self, server_url: str = "http://localhost:8000", verify: bool = True):
        self.server_url = server_url.rstrip("/")
        # httpx handles verify=False to disable SSL cert checking
        self.verify = verify
        self.client = httpx.AsyncClient(timeout=15.0, verify=verify)  # Increased for LAN stability

    async def set_server_url(self, url: str):
        """Dynamically update the bootstrap server URL."""
        if url:
            self.server_url = url.rstrip("/")
            logger.info(f"BootstrapClient: Server URL updated to {self.server_url}")

    async def set_verify(self, verify: bool):
        """Update SSL verification setting and recreate client."""
        self.verify = verify
        # Close old client if possible, though httpx handles it
        await self.client.aclose()
        self.client = httpx.AsyncClient(timeout=15.0, verify=verify)
        logger.info(f"BootstrapClient: SSL verification set to {verify}")

    async def get_joinable_groups(self, preferred_level: int = 1, my_node_id: Optional[str] = None) -> List[GroupInfo]:
        """Fetch topology and filter for joinable groups."""
        try:
            params = {"node_id": my_node_id} if my_node_id else {}
            resp = await self.client.get(f"{self.server_url}/topology", params=params)
            if resp.status_code != 200:
                logger.error(f"Failed to fetch topology: {resp.status_code}")
                return []
            
            data = resp.json()
            groups_data = data.get("groups", {})
            
            joinable = []
            for gid, g_dict in groups_data.items():
                g_info = GroupInfo(
                    group_id=g_dict["group_id"],
                    level=g_dict["level"],
                    member_count=g_dict["member_count"],
                    max_capacity=g_dict["max_capacity"],
                    parent_id=g_dict.get("parent_id"),
                    has_space=g_dict.get("has_space", True),
                    core_node_ids=g_dict.get("core_node_ids", []),
                    node_rankings=g_dict.get("node_rankings", [])
                )
                
                if g_info.level == preferred_level and g_info.has_space:
                    joinable.append(g_info)
            
            return joinable
        except Exception as e:
            logger.error(f"Bootstrap client error: {e}")
            return []

    async def register_node(self, registration: NodeRegistration) -> bool:
        """Register local node with server."""
        try:
            resp = await self.client.post(f"{self.server_url}/register", json=registration.to_dict())
            return resp.status_code == 200 and resp.json().get("success", False)
        except Exception as e:
            logger.error(f"Bootstrap registration error: {e}")
            return False

    async def get_pending_joins(self, group_id: str) -> List[dict]:
        """Fetch pending join requests for a group."""
        try:
            resp = await self.client.get(f"{self.server_url}/groups/{group_id}/pending")
            if resp.status_code == 200:
                return resp.json().get("pending", [])
            return []
        except Exception as e:
            logger.error(f"Error fetching pending joins: {e}")
            return []

    async def approve_join(self, group_id: str, node_id: str, approver_id: str) -> bool:
        """Approve a pending join request."""
        try:
            payload = {"node_id": node_id, "approver_id": approver_id}
            resp = await self.client.post(f"{self.server_url}/groups/{group_id}/approve", json=payload)
            return resp.status_code == 200 and resp.json().get("success", False)
        except Exception as e:
            logger.error(f"Error approving join: {e}")
            return False

    async def set_group_rankings(self, group_id: str, rankings: List[str], requester_id: str) -> bool:
        """Set the node rankings for a group (must be a core node)."""
        try:
            payload = {"rankings": rankings, "requester_id": requester_id}
            resp = await self.client.post(f"{self.server_url}/groups/{group_id}/rankings", json=payload)
            return resp.status_code == 200 and resp.json().get("success", False)
        except Exception as e:
            logger.error(f"Error setting group rankings: {e}")
            return False

    async def set_core_nodes(self, group_id: str, core_node_ids: List[str], requester_id: str) -> bool:
        """Update core nodes for a group after election (must be a core node)."""
        try:
            payload = {"core_nodes": core_node_ids, "requester_id": requester_id}
            resp = await self.client.post(f"{self.server_url}/groups/{group_id}/core-nodes", json=payload)
            return resp.status_code == 200 and resp.json().get("success", False)
        except Exception as e:
            logger.error(f"Error setting core nodes: {e}")
            return False

    async def get_candidates(self, group_id: str) -> List[str]:
        """Fetch candidate suggestions for a core node election based on reputation."""
        try:
            resp = await self.client.get(f"{self.server_url}/groups/{group_id}/candidates")
            if resp.status_code == 200:
                return resp.json().get("candidates", [])
            return []
        except Exception as e:
            logger.error(f"Error fetching candidates: {e}")
            return []

    async def get_network_topology(self, my_node_id: Optional[str] = None) -> Dict:
        """Fetch full network topology dictionary from server."""
        try:
            params = {"node_id": my_node_id} if my_node_id else {}
            resp = await self.client.get(f"{self.server_url}/topology", params=params)
            if resp.status_code == 200:
                return resp.json()
            return {}
        except Exception as e:
            logger.error(f"Bootstrap topology fetch error: {e}")
            return {}

    async def get_node_public_key(self, node_id: str) -> Optional[str]:
        """Fetch public key for a specific node."""
        try:
            # We can get this from topology
            topo = await self.get_network_topology()
            nodes = topo.get("nodes", {})
            node_info = nodes.get(node_id)
            if node_info:
                return node_info.get("public_key")
            return None
        except Exception as e:
            logger.error(f"Bootstrap public key fetch error: {e}")
            return None

    async def get_community_rules(self) -> Dict:
        """Fetch community rules."""
        try:
            resp = await self.client.get(f"{self.server_url}/rules")
            if resp.status_code == 200:
                return resp.json()
            return {}
        except Exception as e:
            logger.error(f"Bootstrap rules fetch error: {e}")
            return {}

# Global instance
bootstrap_client = BootstrapClient()

# Backward compatibility alias
LocalBootstrapSimulator = BootstrapClient 
