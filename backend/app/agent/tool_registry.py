"""
Tool Registry & Execution Capability Manager (CodeWhale-inspired)
Provides fine-grained capability tags (ToolCapability), risk levels (ToolRiskLevel),
and approval requirements (ApprovalRequirement) for Agent Tools in Bit-Politeia.
"""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
import logging
import asyncio

logger = logging.getLogger(__name__)


class ToolCapability(str, Enum):
    READ_ONLY = "read_only"
    WRITES_FILES = "writes_files"
    EXECUTES_CODE = "executes_code"
    NETWORK = "network"
    REQUIRES_APPROVAL = "requires_approval"


class ToolRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ApprovalRequirement(str, Enum):
    AUTO = "auto"
    SUGGEST = "suggest"
    REQUIRED = "required"


@dataclass
class ToolMeta:
    name: str
    description: str
    capabilities: Set[ToolCapability] = field(default_factory=set)
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    approval: ApprovalRequirement = ApprovalRequirement.AUTO
    handler: Optional[Callable] = None


class ToolRegistry:
    """
    Registry managing tool functions with capabilities, risk levels, and safety policies.
    """

    def __init__(self):
        self._registry: Dict[str, ToolMeta] = {}
        self._file_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def register(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        capabilities: Optional[List[ToolCapability]] = None,
        risk_level: ToolRiskLevel = ToolRiskLevel.LOW,
        approval: ApprovalRequirement = ApprovalRequirement.AUTO,
    ):
        """Register a tool with capability tags and risk metadata."""
        caps = set(capabilities or [])
        if risk_level == ToolRiskLevel.HIGH:
            caps.add(ToolCapability.REQUIRES_APPROVAL)
            approval = ApprovalRequirement.REQUIRED
        elif risk_level == ToolRiskLevel.MEDIUM and approval == ApprovalRequirement.AUTO:
            approval = ApprovalRequirement.SUGGEST

        meta = ToolMeta(
            name=name,
            description=description,
            capabilities=caps,
            risk_level=risk_level,
            approval=approval,
            handler=handler,
        )
        self._registry[name] = meta
        logger.debug(f"[ToolRegistry] Registered tool '{name}' (Risk: {risk_level.value}, Caps: {[c.value for c in caps]})")

    def get_meta(self, name: str) -> Optional[ToolMeta]:
        return self._registry.get(name)

    def list_tools(self) -> List[ToolMeta]:
        return list(self._registry.values())

    async def get_file_lock(self, file_path: str) -> asyncio.Lock:
        """Get or create per-file execution lock to prevent concurrent write conflicts."""
        async with self._global_lock:
            if file_path not in self._file_locks:
                self._file_locks[file_path] = asyncio.Lock()
            return self._file_locks[file_path]

    async def execute(self, tool_name: str, *args, target_file: Optional[str] = None, **kwargs) -> Any:
        """
        Execute registered tool with capability checks and file write concurrency guards.
        """
        meta = self.get_meta(tool_name)
        if not meta or not meta.handler:
            raise ValueError(f"Tool '{tool_name}' is not registered in ToolRegistry.")

        # Log high risk execution
        if meta.risk_level == ToolRiskLevel.HIGH:
            logger.warning(f"[ToolRegistry] Executing HIGH RISK tool: '{tool_name}' with args={args}, kwargs={kwargs}")

        # Per-file lock for file modification tools
        if target_file and ToolCapability.WRITES_FILES in meta.capabilities:
            lock = await self.get_file_lock(target_file)
            async with lock:
                if asyncio.iscoroutinefunction(meta.handler):
                    return await meta.handler(*args, **kwargs)
                return meta.handler(*args, **kwargs)

        if asyncio.iscoroutinefunction(meta.handler):
            return await meta.handler(*args, **kwargs)
        return meta.handler(*args, **kwargs)


# Global singleton instance
tool_registry = ToolRegistry()
