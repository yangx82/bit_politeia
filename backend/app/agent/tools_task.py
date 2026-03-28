from typing import List, Optional
from langchain_core.tools import tool
@tool
def create_long_term_task(goal: str, priority: int = 5, subtasks: Optional[List[str]] = None) -> str:
    """
    Create a new long-term task that persists across sessions.
    Use this for complex goals that require multiple steps, research, or waiting for feedback.
    
    Args:
        goal: The high-level objective/task description.
        priority: Priority from 1 (low) to 10 (high). Default is 5.
        subtasks: Optional list of granular steps to achieve the goal.
    """
    from ..services.agent_service import agent_service
    if not agent_service.task_manager:
        return "Task management system not initialized."
    
    task = agent_service.task_manager.create_task(goal, priority, subtasks)
    return f"Long-term task created. ID: {task.id}. Status: {task.status.value}."

@tool
def update_task_status(task_id: str, status: str, result: Optional[str] = None) -> str:
    """
    Update the status of a long-term task or subtask.
    
    CRITICAL STATUS DEFINITIONS - YOU MUST OBEY THESE:
    - "pending": Not started yet.
    - "active": Currently being worked on.
    - "blocked": You are unable to proceed because you are waiting on an external dependency (e.g., waiting for a peer to reply, waiting for a resident to upload a file). DO NOT mark as completed if you are just waiting!
    - "failed": The goal is permanently impossible to achieve (e.g., repeated fatal errors or dead ends).
    - "completed": The goal has been 100% SUCCESSFULLY ACHIEVED. DO NOT use "completed" if you merely "tried" but did not succeed. If you tried but the goal wasn't achieved, use "failed" or "blocked".

    Args:
        task_id: The UUID of the task.
        status: One of [pending, active, blocked, completed, failed].
        result: Brief summary of what was achieved or why it failed.
    """
    from ..services.agent_service import agent_service
    if not agent_service.task_manager:
        return "Task management system not initialized."
    
    if task_id not in agent_service.task_manager.tasks:
        return f"Task ID {task_id} not found."
    
    # Check if it's a subtask ID
    for task in agent_service.task_manager.tasks.values():
        if task.id == task_id:
            task.update_status(status)
            if status == "completed":
                agent_service.task_manager.complete_task(task_id, lessons=result)
            elif status == "failed":
                agent_service.task_manager.fail_task(task_id, reason=result or "No reason provided")
            else:
                agent_service.task_manager.save_tasks()
            return f"Task {task_id} status updated to {status}."
        
        for st in task.subtasks:
            if st.id == task_id:
                st.status = status
                st.result = result
                agent_service.task_manager.save_tasks()
                return f"Subtask {task_id} status updated to {status}."
                
    return f"Task or Subtask ID {task_id} not found."

@tool
def set_task_checkpoint(task_id: str, checkpoint: str) -> str:
    """
    Record current progress and next planned steps for a long-term task.
    Call this frequently to ensure the task can be resumed accurately after an interruption.
    
    Args:
        task_id: The UUID of the task.
        checkpoint: Summary of progress made and what to do next.
    """
    from ..services.agent_service import agent_service
    if not agent_service.task_manager:
        return "Task management system not initialized."
    
    if task_id not in agent_service.task_manager.tasks:
        return f"Task ID {task_id} not found."
    
    agent_service.task_manager.update_task_checkpoint(task_id, checkpoint)
    return f"Checkpoint updated for task {task_id}."

TASK_TOOLS = [create_long_term_task, update_task_status, set_task_checkpoint]
