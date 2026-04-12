import logging

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SetCurrentTaskInput(BaseModel):
    task_id: str = Field(description="The UUID of the task to focus on for this session.")
    reason: str = Field(description="Brief reason for switching focus.")


class SetCurrentTaskTool(BaseTool):
    name: str = "set_current_task"
    description: str = "Explicitly set the current focal point of the conversation to a specific long-term task. This helps the context manager retrieve correct lineage records."
    args_schema: type[BaseModel] = SetCurrentTaskInput

    def _run(self, task_id: str, reason: str) -> str:
        # This is a placeholder for async execution. In the real system,
        # the agent_service will handle the result.
        return f"Focus set to Task ID: {task_id}. Reason: {reason}"

    async def _arun(self, task_id: str, reason: str) -> str:
        # Note: session_id is needed to store this in metadata.
        # However, tools usually don't have access to session_id directly in signature
        # unless injected. We will handle the metadata update in agent_service.process_tool_output
        # or by injecting a callback.

        # In bit_politeia, we can access the session via session_manager
        # but we need to know WHICH session.
        # For now, we return a structured instruction that agent_service can interpret.
        return f"FOCUS_SWITCH_TARGET:{task_id}"


set_current_task_tool = SetCurrentTaskTool()
