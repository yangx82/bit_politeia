import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


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
