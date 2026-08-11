import sys
import site
import os

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

import uuid
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    def Field(default_factory=None, **kwargs):
        return default_factory() if default_factory else None


class Session(BaseModel):
    """
    Global Session object to persist state across interactions and channels.
    """

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_id: str
    channel: str

    # State tracking
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Context & Logic
    history_slice: list[Any] = []  # Recent Relevant messages
    current_task: str | None = None
    active_tools: list[str] = []

    # Metrics
    token_usage_total: int = 0
    message_count: int = 0

    # Dynamic Metadata (Plugins/Skills can store stuff here)
    metadata: dict[str, Any] = {}

    # Task persistence (for multi-step long-running goals)
    pending_goals: list[dict[str, Any]] = []

    class Config:
        arbitrary_types_allowed = True
