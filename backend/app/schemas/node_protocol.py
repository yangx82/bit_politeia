from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    HANDSHAKE = "handshake"
    HANDSHAKE_ACK = "handshake_ack"
    CAPABILITY_ADVERTISEMENT = "capability_advertisement"
    TOOL_INVOCATION = "tool_invocation"
    TOOL_RESULT = "tool_result"
    EVENT = "event"
    PING = "ping"
    PONG = "pong"
    TASK_HANDOFF = "task_handoff"
    TASK_RESULT = "task_result"


class BaseNodeMessage(BaseModel):
    type: MessageType
    id: str = Field(description="Unique message ID")
    timestamp: float = Field(description="Unix timestamp")


class Handshake(BaseNodeMessage):
    type: MessageType = MessageType.HANDSHAKE
    node_id: str
    public_key: str | None = None
    agent_version: str = "1.0.0"


class CapabilityAdvertisement(BaseNodeMessage):
    type: MessageType = MessageType.CAPABILITY_ADVERTISEMENT
    node_id: str
    tools: list[dict[str, Any]] = Field(
        description="List of tool definitions (JSON Schema equivalent)"
    )


class ToolInvocation(BaseNodeMessage):
    type: MessageType = MessageType.TOOL_INVOCATION
    tool_name: str
    arguments: dict[str, Any]
    call_id: str


class ToolResult(BaseNodeMessage):
    type: MessageType = MessageType.TOOL_RESULT
    call_id: str
    result: Any
    error: str | None = None


class GatewayEvent(BaseNodeMessage):
    type: MessageType = MessageType.EVENT
    event_type: str  # e.g. "agent_thought", "agent_reply"
    payload: dict[str, Any]


class TaskHandoff(BaseNodeMessage):
    type: MessageType = MessageType.TASK_HANDOFF
    task: str = Field(description="High-level goal for the peer agent")
    context: str | None = Field(None, description="Detailed background or constraints")
    inputs: dict[str, Any] = Field(
        default_factory=dict, description="Structured parameters for the task"
    )
    requester_id: str


class TaskResult(BaseNodeMessage):
    type: MessageType = MessageType.TASK_RESULT
    task_id: str = Field(description="Original message ID of the handoff")
    output: Any
    error: str | None = None
