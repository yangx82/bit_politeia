"""Event types for the message bus."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, List, Dict, Optional


class InboundMessage(BaseModel):
    """Message received from a chat channel."""
    
    channel: str  # telegram, feishu, cli
    sender_id: str  # User identifier
    chat_id: str  # Chat/channel identifier
    content: str  # Message text
    timestamp: datetime = Field(default_factory=datetime.now)
    media: List[Dict[str, Any]] = Field(default_factory=list)  # Media metadata e.g. {"type": "file", "path": "/path"}
    metadata: Dict[str, Any] = Field(default_factory=dict)  # Channel-specific data
    
    @property
    def session_key(self) -> str:
        """Unique key for session identification."""
        return f"{self.channel}:{self.chat_id}"


class OutboundMessage(BaseModel):
    """Message to send to a chat channel."""
    
    channel: str
    chat_id: str
    content: str
    type: str = "message"  # 'message', 'thought', 'tool_call', 'tool_result'
    reply_to: Optional[str] = None
    media: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
