"""
Scoped Subagent & Activation Manager Module (DeepSeek Harness dsh-subagent Pattern)

Implements continuable subagent activations with scoped tool isolation (toolFilter)
and hierarchical lineage tracking.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
UTC = timezone.utc
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ActivationState(Enum):
    RUNNING = "running"
    WAITING = "waiting"
    SETTLED = "settled"


@dataclass
class ToolFilter:
    """Defines tool scoping and permissions for a child agent."""
    allowed_tools: list[str] | None = None  # Explicit whitelist (None means all allowed)
    forbidden_tools: list[str] = field(default_factory=list)  # Explicit blacklist
    read_only: bool = False  # If True, automatically forbids write/exec tools

    def is_tool_allowed(self, tool_name: str) -> bool:
        if self.read_only:
            modifying_tools = {
                "write_to_file",
                "replace_file_content",
                "run_command",
                "git_commit",
                "execute_sandbox_code",
            }
            if tool_name in modifying_tools:
                return False

        if self.forbidden_tools and tool_name in self.forbidden_tools:
            return False

        if self.allowed_tools is not None and tool_name not in self.allowed_tools:
            return False

        return True


@dataclass
class SubagentActivation:
    activation_id: str
    parent_session_id: str
    child_session_id: str
    role_description: str
    persona: str | None = None
    tool_filter: ToolFilter = field(default_factory=ToolFilter)
    state: ActivationState = ActivationState.RUNNING
    inbox: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ScopedSubagentManager:
    """
    Manages child subagent activations with scoped permissions and FIFO queueing.
    """

    def __init__(self):
        self._activations: dict[str, SubagentActivation] = {}

    def create_activation(
        self,
        parent_session_id: str,
        role_description: str,
        persona: str | None = None,
        tool_filter: ToolFilter | None = None,
    ) -> SubagentActivation:
        """Creates and registers a new subagent activation."""
        act_id = f"sub_{uuid.uuid4().hex[:8]}"
        child_session = f"session_child_{act_id}"
        
        activation = SubagentActivation(
            activation_id=act_id,
            parent_session_id=parent_session_id,
            child_session_id=child_session,
            role_description=role_description,
            persona=persona,
            tool_filter=tool_filter or ToolFilter(),
            state=ActivationState.RUNNING,
        )
        self._activations[act_id] = activation
        logger.info(
            f"[ScopedSubagent] Created activation {act_id} for '{role_description}' "
            f"(read_only={activation.tool_filter.read_only})"
        )
        return activation

    def filter_tools_for_activation(self, activation_id: str, all_tools: list[Any]) -> list[Any]:
        """Filters tool list according to the activation's scoped tool filter."""
        act = self._activations.get(activation_id)
        if not act:
            return all_tools

        filtered = []
        for tool in all_tools:
            tool_name = getattr(tool, "name", str(tool))
            if act.tool_filter.is_tool_allowed(tool_name):
                filtered.append(tool)
            else:
                logger.debug(f"[ScopedSubagent] Tool '{tool_name}' hidden for activation {activation_id}")

        return filtered

    def enqueue_message(self, activation_id: str, message: dict[str, Any]) -> bool:
        """Enqueues a message into the subagent's FIFO queue."""
        act = self._activations.get(activation_id)
        if not act or act.state == ActivationState.SETTLED:
            return False

        act.inbox.append(message)
        act.state = ActivationState.RUNNING
        return True

    def settle_activation(self, activation_id: str):
        """Marks an activation as settled/completed."""
        act = self._activations.get(activation_id)
        if act:
            act.state = ActivationState.SETTLED
            logger.info(f"[ScopedSubagent] Activation {activation_id} settled.")

    def get_activation(self, activation_id: str) -> SubagentActivation | None:
        return self._activations.get(activation_id)


# Singleton instance
scoped_subagent_manager = ScopedSubagentManager()
