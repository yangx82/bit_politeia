"""
P2P Message Protocol Module

Implements signed messaging protocol where all messages require
node private key signatures for authentication.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
UTC = timezone.utc
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

    # IM Enhancements: Receipts, SyncKey Delta, Event DAG
    RECEIPT = "receipt"  # 状态回执 (Sent, Delivered, Thinking, Replied)
    SYNC_PULL = "sync_pull"  # 增量同步拉取 (SyncKey request)
    SYNC_RESP = "sync_resp"  # 增量同步回复 (SyncKey payload)

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
    seq_id: int = 0  # 单调递增序列号 (SyncKey)
    parents: list[str] = None  # Event DAG 因果父事件ID列表
    receipt_status: str | None = None  # 回执状态: delivered, thinking, replied
    raw_timestamp_str: str | None = None  # 保留原始时间戳字符串用于兼容验签

    def __post_init__(self):
        if self.parents is None:
            self.parents = []

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
            "seq_id": self.seq_id,
            "parents": self.parents,
            "receipt_status": self.receipt_status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignedMessage":
        raw_ts = data.get("timestamp")
        ts = raw_ts
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
            seq_id=data.get("seq_id", 0),
            parents=data.get("parents", []),
            receipt_status=data.get("receipt_status"),
            raw_timestamp_str=raw_ts if isinstance(raw_ts, str) else None,
        )

    def get_signable_content(
        self, seq_id_override: int | None = None, ts_str_override: str | None = None
    ) -> bytes:
        """
        Get the content that should be signed.
        Uses deterministic JSON serialization (canonical-like).
        """
        if ts_str_override is not None:
            ts_str = ts_str_override
        else:
            ts_str = self.timestamp.isoformat(timespec="microseconds")

        effective_seq_id = self.seq_id if seq_id_override is None else seq_id_override

        signable = {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "message_type": self.message_type.value,
            "content": self.content,
            # Use timespec='microseconds' to ensure consistent decimal places
            "timestamp": ts_str,
            "nonce": self.nonce,
            "seq_id": effective_seq_id,
            "parents": self.parents,
            "receipt_status": self.receipt_status,
        }
        # sort_keys and separators eliminate non-deterministic whitespace
        return json.dumps(signable, sort_keys=True, separators=(",", ":")).encode("utf-8")


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
        seq_id: int = 0,
        parents: list[str] | None = None,
        receipt_status: str | None = None,
    ) -> SignedMessage:
        """
        Create a new signed message.

        Args:
            sender_id: Sender's node ID (public key)
            recipient_id: Recipient's node ID or group ID
            message_type: Type of message
            content: Message content dictionary
            seq_id: Monotonic sequence ID (assigned before signing)
            parents: Causal parent message IDs
            receipt_status: Optional lifecycle receipt state

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
            seq_id=seq_id,
            parents=parents or [],
            receipt_status=receipt_status,
        )

        # Sign the message with its final seq_id and signable payload
        signable_content = message.get_signable_content()
        signature = self.crypto_service.sign_message(signable_content.decode("utf-8"))
        message.signature = signature

        logger.debug(f"Created signed message {message.message_id} from {sender_id} with seq_id={seq_id}")
        return message

    def verify_message(self, message: SignedMessage, sender_public_key: str) -> bool:
        """
        Verify a message's signature with backward-compatible candidate fallbacks.

        Args:
            message: The signed message to verify
            sender_public_key: Sender's public key for verification

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            if hasattr(self.crypto_service, "verify_signature"):
                candidates = []
                # 1. Standard candidate: current message fields with standard microseconds isoformat
                candidates.append(message.get_signable_content())

                # 2. Legacy fallback: if seq_id != 0, try seq_id = 0 (unpatched peer that mutated seq_id after signing)
                if message.seq_id != 0:
                    candidates.append(message.get_signable_content(seq_id_override=0))

                # 3. Timestamp variants (e.g. ISO with Z vs +00:00 or original wire string)
                if message.raw_timestamp_str:
                    raw_ts = message.raw_timestamp_str
                    candidates.append(message.get_signable_content(ts_str_override=raw_ts))
                    if message.seq_id != 0:
                        candidates.append(message.get_signable_content(seq_id_override=0, ts_str_override=raw_ts))
                    if raw_ts.endswith("Z"):
                        alt_ts = raw_ts[:-1] + "+00:00"
                        candidates.append(message.get_signable_content(ts_str_override=alt_ts))
                        if message.seq_id != 0:
                            candidates.append(message.get_signable_content(seq_id_override=0, ts_str_override=alt_ts))
                    elif "+00:00" in raw_ts:
                        alt_ts = raw_ts.replace("+00:00", "Z")
                        candidates.append(message.get_signable_content(ts_str_override=alt_ts))
                        if message.seq_id != 0:
                            candidates.append(message.get_signable_content(seq_id_override=0, ts_str_override=alt_ts))

                seen = set()
                for cand in candidates:
                    if cand in seen:
                        continue
                    seen.add(cand)
                    try:
                        if self.crypto_service.verify_signature(
                            cand.decode("utf-8"), message.signature, sender_public_key
                        ):
                            return True
                    except Exception as ve:
                        logger.debug(f"Candidate verify failed: {ve}")
                        continue

                logger.warning(
                    f"Signature verification failed for message {message.message_id} from {message.sender_id[:8]}"
                )
                return False

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
