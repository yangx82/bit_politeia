import sys
import site
import os

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items(): setattr(self, k, v)
    def Field(default_factory=None, **kwargs):
        return default_factory() if default_factory else None


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
