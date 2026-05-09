"""Event types for the message bus."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    """Message received from a chat channel."""

    channel: str  # telegram, feishu, cli
    sender_id: str  # User identifier
    session_id: str  # Chat/channel/session identifier
    content: str  # Message text
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    media: list[dict[str, Any]] = Field(
        default_factory=list
    )  # Media metadata e.g. {"type": "file", "path": "/path"}
    metadata: dict[str, Any] = Field(default_factory=dict)  # Channel-specific data

    @property
    def session_key(self) -> str:
        """Unique key for session identification."""
        return f"{self.channel}:{self.session_id}"


class OutboundMessage(BaseModel):
    """Message to send to a chat channel."""

    channel: str
    session_id: str
    content: str
    type: str = "message"  # 'message', 'thought', 'tool_call', 'tool_result'
    reply_to: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    media: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
