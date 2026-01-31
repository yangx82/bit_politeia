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
    last_seen: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "public_key": self.public_key,
            "ip_address": self.ip_address,
            "port": self.port,
            "last_seen": self.last_seen.isoformat()
        }

@dataclass
class GroupInfo:
    group_id: str
    level: int
    member_count: int
    max_capacity: int
    parent_id: Optional[str] = None
    has_space: bool = False

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "level": self.level,
            "member_count": self.member_count,
            "max_capacity": self.max_capacity,
            "parent_id": self.parent_id,
            "has_space": self.has_space
        }

@dataclass
class NodeRegistration:
    node_id: str
    public_key: str
    ip_address: str
    port: int
    group_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "public_key": self.public_key,
            "ip_address": self.ip_address,
            "port": self.port,
            "group_id": self.group_id
        }

class BootstrapClient:
    """
    Client for interacting with the P2P Bootstrap Server (Cloud or Local LAN).
    """
    def __init__(self, server_url: str = "http://localhost:8000"):
        self.server_url = server_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=5.0)

    async def get_joinable_groups(self, preferred_level: int = 1) -> List[GroupInfo]:
        """Fetch topology and filter for joinable groups."""
        try:
            resp = await self.client.get(f"{self.server_url}/topology")
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
                    has_space=g_dict.get("has_space", True)
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

    async def get_network_topology(self) -> Dict:
        """Fetch full network topology dictionary from server."""
        try:
            resp = await self.client.get(f"{self.server_url}/topology")
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
