import sys
import site

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

import logging

try:
    from langchain_core.tools import BaseTool
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items(): setattr(self, k, v)
    def Field(description=""): return None
    class BaseTool: pass

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


class DefineDeliverablesInput(BaseModel):
    task_id: str = Field(description="The UUID of the task to define deliverables for.")
    deliverables: str = Field(
        description="JSON string of deliverables list. Each deliverable: {\"type\": \"file|message|vote|payment|analysis|research|code|config\", \"description\": \"what to deliver\", \"target\": \"optional target path/id\"}"
    )


class DefineDeliverablesTool(BaseTool):
    name: str = "define_deliverables"
    description: str = """Define expected deliverables for a long-term task. 
    MUST be called when starting a new task to establish what concrete artifacts are expected.
    Deliverable types:
    - file: A physical file (code, document, data)
    - message: A sent message (must have recipient_id and status=SUCCESS)
    - vote: A cast ballot (must have election_id)
    - payment: A completed transfer (must have payee_id, amount)
    - analysis: A report with data (content_length > 100)
    - research: Research output (content_length > 500)
    - code: Code changes (must have file_path and syntax_valid=true)
    - config: Configuration changes (must have parameter_path)
    
    Example: [{"type": "file", "description": "Research report PDF", "target": "data/reports/analysis.pdf"}, {"type": "message", "description": "Notify team", "target": "group_abc"}]
    """
    args_schema: type[BaseModel] = DefineDeliverablesInput

    def _run(self, task_id: str, deliverables: str) -> str:
        import json
        from ..services.agent_service import agent_service
        
        try:
            deliverables_list = json.loads(deliverables)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON format for deliverables: {e}"
        
        if not agent_service.task_manager:
            return "Error: TaskManager not initialized"
        
        success = agent_service.task_manager.define_deliverables(task_id, deliverables_list)
        if success:
            return f"SUCCESS: Defined {len(deliverables_list)} deliverable(s) for task {task_id[:8]}. The agent must now produce evidence for each deliverable before marking the task as completed."
        else:
            return f"Error: Failed to define deliverables for task {task_id[:8]}. Task not found."

    async def _arun(self, task_id: str, deliverables: str) -> str:
        return self._run(task_id, deliverables)


class RecordTaskEvidenceInput(BaseModel):
    task_id: str = Field(description="The UUID of the task.")
    deliverable_id: str = Field(description="The ID of the deliverable (from define_deliverables response). Use 'auto' to match first pending deliverable.")
    evidence: str = Field(
        description="JSON string of evidence. Must contain fields required by deliverable type. Examples: {\"status\": \"SUCCESS\", \"recipient_id\": \"xxx\"} for message; {\"file_path\": \"xxx\", \"file_size\": 1234} for file."
    )


class RecordTaskEvidenceTool(BaseTool):
    name: str = "record_task_evidence"
    description: str = """Record evidence for a deliverable and verify completion.
    MUST be called after producing each deliverable to log the evidence.
    The system will automatically verify the evidence against rules for the deliverable type.
    
    Required evidence fields by type:
    - message: {"recipient_id": str, "status": "SUCCESS"}
    - file: {"file_path": str, "file_size": int}
    - vote: {"election_id": str, "status": "recorded"}
    - payment: {"payee_id": str, "amount": float, "status": "SUCCESS"}
    - analysis: {"content_length": int}
    - research: {"content_length": int}
    - code: {"file_path": str, "syntax_valid": bool}
    - config: {"parameter_path": str, "new_value": str, "status": "SUCCESS"}
    """
    args_schema: type[BaseModel] = RecordTaskEvidenceInput

    def _run(self, task_id: str, deliverable_id: str, evidence: str) -> str:
        import json
        from ..services.agent_service import agent_service
        
        try:
            evidence_dict = json.loads(evidence)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON format for evidence: {e}"
        
        if not agent_service.task_manager:
            return "Error: TaskManager not initialized"
        
        # Handle 'auto' deliverable_id
        actual_deliverable_id = None if deliverable_id == "auto" else deliverable_id
        
        result = agent_service.task_manager.record_evidence(task_id, actual_deliverable_id, evidence_dict)
        
        if result.get("verified"):
            return f"SUCCESS: Evidence verified for deliverable. {result.get('description', '')}"
        else:
            return f"VERIFICATION FAILED: {result.get('reason', 'Unknown reason')}. Please ensure the evidence matches the required format for this deliverable type."

    async def _arun(self, task_id: str, deliverable_id: str, evidence: str) -> str:
        return self._run(task_id, deliverable_id, evidence)


class CheckTaskCompletionInput(BaseModel):
    task_id: str = Field(description="The UUID of the task to check.")


class CheckTaskCompletionTool(BaseTool):
    name: str = "can_complete_task"
    description: str = """Check if a task can be marked as completed.
    MUST be called before setting task status to 'completed'.
    Returns whether all deliverables have been verified.
    If deliverables are still pending or failed, the task cannot be marked as completed.
    """
    args_schema: type[BaseModel] = CheckTaskCompletionInput

    def _run(self, task_id: str) -> str:
        from ..services.agent_service import agent_service
        
        if not agent_service.task_manager:
            return "Error: TaskManager not initialized"
        
        result = agent_service.task_manager.can_complete_task(task_id)
        
        if result.get("can_complete"):
            return f"YES: Task can be marked as completed. {result.get('reason', '')}"
        else:
            pending = result.get("pending_deliverables", [])
            failed = result.get("failed_deliverables", [])
            msg = f"NO: Task cannot be marked as completed. {result.get('reason', '')}"
            if pending:
                msg += f"\nPending deliverables: {', '.join(pending)}"
            if failed:
                msg += f"\nFailed deliverables: {', '.join(failed)}"
            return msg

    async def _arun(self, task_id: str) -> str:
        return self._run(task_id)


class GetTaskCompletionInput(BaseModel):
    task_id: str = Field(description="The UUID of the task.")


class GetTaskCompletionTool(BaseTool):
    name: str = "get_task_completion"
    description: str = """Get detailed completion status for a task.
    Returns completion percentage, list of deliverables with their status, and evidence count.
    """
    args_schema: type[BaseModel] = GetTaskCompletionInput

    def _run(self, task_id: str) -> str:
        import json
        from ..services.agent_service import agent_service
        
        if not agent_service.task_manager:
            return "Error: TaskManager not initialized"
        
        result = agent_service.task_manager.get_task_completion(task_id)
        
        if "error" in result:
            return f"Error: {result['error']}"
        
        return json.dumps(result, indent=2, ensure_ascii=False)

    async def _arun(self, task_id: str) -> str:
        return self._run(task_id)


set_current_task_tool = SetCurrentTaskTool()
define_deliverables_tool = DefineDeliverablesTool()
record_task_evidence_tool = RecordTaskEvidenceTool()
can_complete_task_tool = CheckTaskCompletionTool()
get_task_completion_tool = GetTaskCompletionTool()
