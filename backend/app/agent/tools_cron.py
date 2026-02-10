
"""
Cron/Scheduler tools for Agent.
Allows the agent to schedule reminders or tasks using APScheduler.
"""

import logging
from typing import Optional
from langchain_core.tools import tool
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

async def _handle_reminder(message: str):
    """Callback function for scheduled reminders."""
    from ..services.agent_service import agent_service
    logger.info(f"Executing Scheduled Reminder: {message}")
    # We inject this as a user instruction so the agent "receives" the reminder and acts on it.
    await agent_service.process_user_instruction(f"[SCHEDULED REMINDER] {message}")

@tool
async def schedule_reminder(message: str, seconds_delay: int = 0, minutes_delay: int = 0, hours_delay: int = 0) -> str:
    """
    Schedule a reminder for yourself in the future.
    The agent will receive this message as a user instruction when the time comes.
    
    Args:
        message: The content of the reminder (e.g., "Check election status").
        seconds_delay: Seconds to wait.
        minutes_delay: Minutes to wait.
        hours_delay: Hours to wait.
    """
    try:
        from ..services.agent_service import agent_service
        
        if not agent_service.scheduler.running:
            return "Error: Scheduler is not running."
            
        run_date = datetime.now() + timedelta(seconds=seconds_delay, minutes=minutes_delay, hours=hours_delay)
        
        # Add job
        job = agent_service.scheduler.add_job(
            _handle_reminder, 
            'date', 
            run_date=run_date, 
            args=[message],
            name=message[:50]
        )
        
        return f"Reminder scheduled for {run_date.isoformat()} (Job ID: {job.id})"
        
    except Exception as e:
        return f"Error scheduling reminder: {str(e)}"

@tool
async def list_reminders() -> str:
    """List all pending scheduled reminders."""
    try:
        from ..services.agent_service import agent_service
        jobs = agent_service.scheduler.get_jobs()
        
        if not jobs:
            return "No pending reminders."
            
        output = ["--- Pending Reminders ---"]
        for job in jobs:
            next_run = job.next_run_time.isoformat() if job.next_run_time else "Unknown"
            output.append(f"ID: {job.id} | Time: {next_run} | Task: {job.name}")
            
        return "\n".join(output)
    except Exception as e:
        return f"Error listing reminders: {str(e)}"

@tool
async def start_scheduler() -> str:
    """Start the internal scheduler if it is not running."""
    try:
        from ..services.agent_service import agent_service
        if not agent_service.scheduler.running:
            agent_service.scheduler.start()
            return "Scheduler started successfully."
        return "Scheduler is already running."
    except Exception as e:
        return f"Error starting scheduler: {str(e)}"

@tool
async def get_scheduler_status() -> str:
    """Get the status of the scheduler."""
    try:
        from ..services.agent_service import agent_service
        running = agent_service.scheduler.running
        jobs = len(agent_service.scheduler.get_jobs())
        return f"Scheduler Running: {running} | Jobs: {jobs}"
    except Exception as e:
        return f"Error getting status: {str(e)}"

@tool
async def cancel_reminder(job_id: str) -> str:
    """
    Cancel a scheduled reminder by Job ID.
    Args:
        job_id: The ID of the job to remove.
    """
    try:
        from ..services.agent_service import agent_service
        agent_service.scheduler.remove_job(job_id)
        return f"Successfully cancelled reminder {job_id}"
    except Exception as e:
        return f"Error cancelling reminder: {str(e)}"
