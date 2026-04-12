"""
Cron/Scheduler tools for Agent.
Allows the agent to schedule reminders or tasks using APScheduler.
"""

import logging
import os
from datetime import datetime, timedelta

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _log_debug(msg):
    try:
        # backend/app/agent/tools_cron.py -> backend/app/agent -> backend/app -> backend -> data
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_path = os.path.join(base_dir, "data", "cron.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()}: {msg}\n")
    except Exception as e:
        print(f"cron log fail: {e}")


async def _handle_reminder(message: str):
    """Callback function for scheduled reminders."""
    from ..services.agent_service import agent_service

    _log_debug(f"Reminder FIRED: {message}")
    logger.info(f"Executing Scheduled Reminder: {message}")
    # We inject this as a user instruction so the agent "receives" the reminder and acts on it.
    await agent_service.process_user_instruction(f"[SCHEDULED REMINDER] {message}", broadcast=True)


@tool
async def schedule_reminder(
    message: str, seconds_delay: int = 0, minutes_delay: int = 0, hours_delay: int = 0
) -> str:
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

        _log_debug(
            f"Request to schedule: '{message}' in {hours_delay}h {minutes_delay}m {seconds_delay}s"
        )

        if not agent_service.scheduler.running:
            return "Error: Scheduler is not running."

        run_date = datetime.now() + timedelta(
            seconds=seconds_delay, minutes=minutes_delay, hours=hours_delay
        )
        _log_debug(f"Calculated run_date: {run_date}")

        # Add job using string reference to avoid pickling issues
        # and ensure the function is importable by the scheduler
        job = agent_service.scheduler.add_job(
            "app.agent.tools_cron:_handle_reminder",
            "date",
            run_date=run_date,
            args=[message],
            name=message[:50],
        )

        _log_debug(f"Job added successfully. ID: {job.id}")
        return f"Reminder scheduled for {run_date.isoformat()} (Job ID: {job.id})"

    except Exception as e:
        import traceback

        error_msg = f"Error scheduling reminder: {e!s}\n{traceback.format_exc()}"
        _log_debug(error_msg)
        # Return the error so the agent knows what happened (and user sees it if agent repeats it)
        return error_msg


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
        return f"Error listing reminders: {e!s}"


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
        return f"Error starting scheduler: {e!s}"


@tool
async def get_scheduler_status() -> str:
    """Get the status of the scheduler."""
    try:
        from ..services.agent_service import agent_service

        running = agent_service.scheduler.running
        jobs = len(agent_service.scheduler.get_jobs())
        return f"Scheduler Running: {running} | Jobs: {jobs}"
    except Exception as e:
        return f"Error getting status: {e!s}"


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
        return f"Error cancelling reminder: {e!s}"
