import datetime
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class Group:
    def __init__(self, group_id: str, level: int, parent_id: str | None = None, name: str = None):
        self.group_id = group_id
        self.name = name or group_id
        self.level = level
        self.parent_id = parent_id
        self.child_ids: list[str] = []
        self.members: set[str] = set()  # Set of Node IDs
        self.core_node_ids: list[str] = []  # Set of Core Node IDs (Governance)
        self.max_subgroups = 3  # Default max subgroups

    def add_member(self, node_id: str):
        self.members.add(node_id)

    def update_core_nodes(self, node_ids: list[str]):
        """Update the list of core nodes (leaders) for this group."""
        self.core_node_ids = list(
            dict.fromkeys(node_ids)
        )  # Ensure uniqueness while preserving order
        logger.info(
            f"Group {self.group_id}: Core nodes updated to {len(self.core_node_ids)} nodes."
        )

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
            "members": list(self.members),
            "core_node_ids": self.core_node_ids,
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
        self.endpoint: str | None = None  # Address of the node's API (e.g. http://192.168.1.5:8001)

        # Nodes belong to at least 1 group, max 2 directly connected
        self.group_ids: set[str] = set()

        self.inbox: list[dict] = []
        self.message_handler: Callable[[dict[str, Any]], Any] | None = None
        self.last_seen: datetime.datetime | None = None
        self.recent_inbox_ids: set[str] = set()  # Runtime deduplication for in-flight messages

    @property
    def is_online(self) -> bool:
        """Determines if the node is online based on last_seen (within 5 minutes)."""
        if not self.last_seen:
            return False
        import datetime

        now = datetime.datetime.now(datetime.UTC)

        # Ensure last_seen is offset-aware for comparison
        target_time = self.last_seen
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=datetime.UTC)

        delta = now - target_time
        return delta.total_seconds() < 300  # 5 minutes

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "public_key": self.public_key,
            "name": self.name,
            "level": self.level,
            "endpoint": self.endpoint,
            "group_ids": list(self.group_ids),
            "is_online": self.is_online,
        }

    def set_message_handler(self, handler: Callable[[dict[str, Any]], Any]):
        """Set a handler to intercept messages. Return True to stop default processing."""
        self.message_handler = handler

    def can_join_group(self, target_group: Group) -> bool:
        """
        Check if node can join the target group based on constraints.
        Rule: Max 2 groups, must be directly connected (parent/child).
        """
        if target_group.group_id in self.group_ids:
            return True  # Already in

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
            target_group.parent_id == current_group.group_id
            or current_group.parent_id == target_group.group_id
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

    async def send_message(
        self,
        target_id: str,
        content: dict[str, Any],
        msg_type: str = "DIRECT",
        message_id: str | None = None,
        timestamp: datetime.datetime | None = None,
    ):
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
            content=content,
            message_id=message_id,
            timestamp=timestamp,
        )

    async def receive_message(self, message: Any):
        """
        Receive a message (SignedMessage object or dict) with signature verification.
        """
        # 1. Parsing & Basic Validation
        if hasattr(message, "to_dict"):
            msg_dict = message.to_dict()
        else:
            msg_dict = message

        m_id = msg_data = msg_dict  # Contextual rename for clarity in this snippet
        m_id = msg_data.get("message_id")
        sender_id = msg_data.get("sender_id")

        # 2. SECURITY: Mandatory Signature Verification for signed payloads
        # We verify if signature is present and it's a standard P2P message
        if msg_data.get("signature") and sender_id:
            try:
                from .message_protocol import SignedMessage

                # Re-parse to SignedMessage to use protocol verification
                msg_obj = (
                    message if hasattr(message, "signature") else SignedMessage.from_dict(msg_data)
                )

                # Verify signature
                # Note: This assumes sender_id IS the public key or that verify_message handles resolution.
                # In this protocol, sender_id is currently the public key PEM.
                if not self.network_manager.message_protocol.verify_message(msg_obj, sender_id):
                    logger.warning(
                        f"[Security] Received message {m_id} from {sender_id[:8]} with INVALID signature. Dropping."
                    )
                    return
            except Exception as ve:
                logger.error(f"[Security] Failed to verify message {m_id}: {ve}")
                return

        # 3. Deduplication (Write-level)
        if m_id:
            if m_id in self.recent_inbox_ids:
                logger.debug(f"Duplicate P2P message {m_id} ignored at receive stage.")
                return
            self.recent_inbox_ids.add(m_id)

            # Keep set size reasonable
            if len(self.recent_inbox_ids) > 1000:
                # Simple cleanup: Clear and restart window
                if len(self.recent_inbox_ids) > 2000:
                    self.recent_inbox_ids.clear()

        logger.info(
            f"[{msg_data.get('sender_id', 'unknown')}] <<< RECEIVED via {msg_data.get('message_type', 'P2P')}: {str(msg_data.get('content'))[:100]}..."
        )

        # 4. Allow external handler to intercept (e.g., for WebRTC Signaling)
        if self.message_handler:
            try:
                # Assuming handler is async
                import inspect

                if inspect.iscoroutinefunction(self.message_handler):
                    if await self.message_handler(msg_data):
                        return  # Handled externally, skip inbox
                else:
                    if self.message_handler(msg_data):
                        return
            except Exception as e:
                logger.error(f"Error in message handler: {e}")

        self.inbox.append(msg_data)

        # Persist to disk inbox for resumption
        try:
            import json
            from pathlib import Path

            # Resolve backend/data/p2p safely
            current_file = Path(__file__).resolve()
            backend_dir = current_file.parent.parent.parent
            data_dir = backend_dir / "data"
            p2p_dir = data_dir / "p2p"

            p2p_dir.mkdir(parents=True, exist_ok=True)

            def json_serial(obj):
                """JSON serializer for objects not serializable by default json code"""
                if hasattr(obj, "isoformat"):
                    return obj.isoformat()
                raise TypeError(f"Type {type(obj)} not serializable")

            inbox_path = p2p_dir / f"inbox_{self.node_id}.jsonl"
            with open(inbox_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(msg_data, default=json_serial) + "\n")
        except Exception as e:
            logger.error(f"Failed to persist inbox message: {e}")

    def get_structure_info(self):
        """
        Access network structure info.
        """
        return self.network_manager.get_network_structure()
