"""Event types for the message bus."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Dict, Optional


@dataclass
class InboundMessage:
    """Message received from a chat channel."""
    
    channel: str  # telegram, feishu, cli
    sender_id: str  # User identifier
    chat_id: str  # Chat/channel identifier
    content: str  # Message text
    timestamp: datetime = field(default_factory=datetime.now)
    media: List[str] = field(default_factory=list)  # Media URLs
    metadata: Dict[str, Any] = field(default_factory=dict)  # Channel-specific data
    
    @property
    def session_key(self) -> str:
        """Unique key for session identification."""
        return f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """Message to send to a chat channel."""
    
    channel: str
    chat_id: str
    content: str
    reply_to: Optional[str] = None
    media: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
