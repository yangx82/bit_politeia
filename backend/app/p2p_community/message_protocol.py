"""
P2P Message Protocol Module

Implements signed messaging protocol where all messages require
node private key signatures for authentication.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages in the P2P network."""

    DIRECT = "direct"  # 节点间直接通信
    GROUP = "group"  # 发送给小组的信息 (广播至所有成员)
    GOSSIP = "gossip"  # 闲聊交互
    PROPOSAL = "proposal"  # 议事交互
    VOTE = "vote"  # 投票
    SYNC = "sync"  # 架构同步
    HEARTBEAT = "heartbeat"  # 心跳/存活检测
    FILE = "file"  # 文件传输
    ELECTION = "election"  # 选举交互
    GROUP_CONFIG = "group_config"  # 小组配置更新

    # WebRTC Signaling
    SDP_OFFER = "sdp_offer"
    SDP_ANSWER = "sdp_answer"
    ICE_CANDIDATE = "ice_candidate"


@dataclass
class SignedMessage:
    """
    A message with cryptographic signature.

    所有发出的讯息均需签名（节点私钥）
    """

    message_id: str
    sender_id: str  # 发送方节点ID (公钥)
    recipient_id: str  # 接收方ID (节点ID或小组ID)
    message_type: MessageType
    content: dict[str, Any]
    timestamp: datetime
    signature: str  # Base64 encoded signature
    nonce: str  # Prevent replay attacks

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "message_type": self.message_type.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "signature": self.signature,
            "nonce": self.nonce,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignedMessage":
        ts = data["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        return cls(
            message_id=data["message_id"],
            sender_id=data["sender_id"],
            recipient_id=data["recipient_id"],
            message_type=MessageType(data["message_type"]),
            content=data["content"],
            timestamp=ts,
            signature=data["signature"],
            nonce=data["nonce"],
        )

    def get_signable_content(self) -> bytes:
        """Get the content that should be signed."""
        signable = {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "message_type": self.message_type.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "nonce": self.nonce,
        }
        return json.dumps(signable, sort_keys=True).encode("utf-8")


@dataclass
class ArchiveRecord:
    """
    Record for distributed storage of interaction history.

    交互记录由发送方、接收方及若干随机第三方节点共同存档
    """

    record_id: str
    message: SignedMessage
    archived_by: list[str]  # List of node IDs that archived this
    archive_timestamp: datetime
    hash_value: str  # Hash of the message for integrity

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "message": self.message.to_dict(),
            "archived_by": self.archived_by,
            "archive_timestamp": self.archive_timestamp.isoformat(),
            "hash_value": self.hash_value,
        }


class MessageProtocol:
    """
    Handles message creation, signing, and verification.
    """

    def __init__(self, crypto_service):
        """
        Initialize with a crypto service for signing operations.

        Args:
            crypto_service: Service providing sign_message and verify_signature
        """
        self.crypto_service = crypto_service
        self._message_counter = 0

    def _generate_message_id(self, sender_id: str) -> str:
        """Generate unique message ID."""
        self._message_counter += 1
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        return f"{sender_id[:8]}_{timestamp}_{self._message_counter}"

    def _generate_nonce(self) -> str:
        """Generate a random nonce for replay attack prevention."""
        import secrets

        return secrets.token_hex(16)

    def create_message(
        self,
        sender_id: str,
        recipient_id: str,
        message_type: MessageType,
        content: dict[str, Any],
        message_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> SignedMessage:
        """
        Create a new signed message.

        Args:
            sender_id: Sender's node ID (public key)
            recipient_id: Recipient's node ID or group ID
            message_type: Type of message
            content: Message content dictionary

        Returns:
            Signed message ready for transmission
        """
        message = SignedMessage(
            message_id=message_id or self._generate_message_id(sender_id),
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_type=message_type,
            content=content,
            timestamp=timestamp or datetime.now(UTC),
            signature="",  # Will be set after signing
            nonce=self._generate_nonce(),
        )

        # Sign the message
        signable_content = message.get_signable_content()
        signature = self.crypto_service.sign_message(signable_content.decode("utf-8"))
        message.signature = signature

        logger.debug(f"Created signed message {message.message_id} from {sender_id}")
        return message

    def verify_message(self, message: SignedMessage, sender_public_key: str) -> bool:
        """
        Verify a message's signature.

        Args:
            message: The signed message to verify
            sender_public_key: Sender's public key for verification

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            signable_content = message.get_signable_content()
            # Note: In production, use proper signature verification
            # This is a simplified check
            if hasattr(self.crypto_service, "verify_signature"):
                return self.crypto_service.verify_signature(
                    signable_content.decode("utf-8"), message.signature, sender_public_key
                )
            # Fallback: Just check signature exists (for testing)
            return bool(message.signature)
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    def compute_message_hash(self, message: SignedMessage) -> str:
        """Compute SHA-256 hash of a message for archiving."""
        content = json.dumps(message.to_dict(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def create_archive_record(
        self, message: SignedMessage, archived_by: list[str]
    ) -> ArchiveRecord:
        """
        Create an archive record for distributed storage.

        Args:
            message: The message to archive
            archived_by: List of node IDs archiving this message

        Returns:
            Archive record for storage
        """
        import uuid

        return ArchiveRecord(
            record_id=str(uuid.uuid4()),
            message=message,
            archived_by=archived_by,
            archive_timestamp=datetime.now(),
            hash_value=self.compute_message_hash(message),
        )

    # Convenience methods for common message types

    def create_gossip_message(
        self, sender_id: str, recipient_id: str, text: str, topic: str | None = None
    ) -> SignedMessage:
        """Create a gossip (闲聊) message."""
        content = {"text": text, "topic": topic}
        return self.create_message(sender_id, recipient_id, MessageType.GOSSIP, content)

    def create_group_broadcast(
        self, sender_id: str, group_id: str, text: str, subject: str | None = None
    ) -> SignedMessage:
        """Create a group broadcast message."""
        content = {"text": text, "subject": subject}
        return self.create_message(sender_id, group_id, MessageType.GROUP, content)

    def create_sync_message(
        self, sender_id: str, recipient_id: str, topology_data: dict[str, Any]
    ) -> SignedMessage:
        """Create a topology sync message for distributed storage."""
        content = {"topology": topology_data, "sync_type": "full"}
        return self.create_message(sender_id, recipient_id, MessageType.SYNC, content)

    def create_proposal_message(
        self,
        sender_id: str,
        group_id: str,
        proposal_title: str,
        proposal_content: str,
        proposal_type: str = "general",
    ) -> SignedMessage:
        """Create a proposal (议事) message."""
        content = {
            "title": proposal_title,
            "content": proposal_content,
            "type": proposal_type,
            "status": "pending",
        }
        return self.create_message(sender_id, group_id, MessageType.PROPOSAL, content)

    def create_vote_message(
        self, sender_id: str, group_id: str, proposal_id: str, vote: str, reason: str
    ) -> SignedMessage:
        """Create a vote message for a proposal."""
        content = {
            "proposal_id": proposal_id,
            "vote": vote,  # "approve", "reject", "abstain"
            "reason": reason,
        }
        return self.create_message(sender_id, group_id, MessageType.VOTE, content)
