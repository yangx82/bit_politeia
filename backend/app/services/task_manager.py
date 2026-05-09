import json
import logging
import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class SubTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    subtasks: list[SubTask] = Field(default_factory=list)
    checkpoint: str | None = None  # Last reasoning summary + next planned action
    lessons_learned: str | None = None  # Filled during Retrospective
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    priority: int = 5  # 1-10
    metadata: dict[str, Any] = Field(default_factory=dict)

    def update_status(self, new_status: TaskStatus):
        self.status = new_status
        self.updated_at = datetime.now(UTC)


class TaskManager:
    def __init__(self, storage_path: str = None):
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            # Default to backend/data/tasks.json
            self.storage_path = (
                Path(__file__).resolve().parent.parent.parent / "data" / "tasks.json"
            )

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.tasks: dict[str, Task] = {}
        self.load_tasks()

    def load_tasks(self):
        """Load tasks from disk."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, encoding="utf-8") as f:
                    data = json.load(f)
                    for t_id, t_data in data.items():
                        self.tasks[t_id] = Task(**t_data)
                logger.info(f"Loaded {len(self.tasks)} tasks from {self.storage_path}")
            except Exception as e:
                logger.error(f"Failed to load tasks: {e}")

    def save_tasks(self):
        """Persist tasks to disk and generate a human-readable summary."""
        try:
            data = {t_id: t.model_dump(mode="json") for t_id, t in self.tasks.items()}
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # Generate human-readable summary
            summary_path = self.storage_path.parent / "tasks_summary.md"
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write("# Long-term Task Summary\n\n")
                active = self.get_active_tasks()
                if not active:
                    f.write("No active long-term tasks.\n")
                else:
                    for t in active:
                        f.write(f"## {t.goal}\n")
                        f.write(f"- **Status**: `{t.status}`\n")
                        f.write(f"- **Priority**: {t.priority}\n")
                        f.write(f"- **Created**: {t.created_at.strftime('%Y-%m-%d %H:%M')}\n")
                        if t.checkpoint:
                            f.write(f"- **Checkpoint**: {t.checkpoint}\n")
                        if t.subtasks:
                            f.write("- **Subtasks**:\n")
                            for st in t.subtasks:
                                check = "[x]" if st.status == TaskStatus.COMPLETED else "[ ]"
                                f.write(f"  - {check} {st.description}\n")
                        f.write("\n")

                # Recently completed
                completed = [t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED][
                    -5:
                ]
                if completed:
                    f.write("---\n## Recently Completed\n\n")
                    for t in completed:
                        f.write(f"- ✅ {t.goal} (Lessons: {t.lessons_learned or 'None'})\n")

        except Exception as e:
            logger.error(f"Failed to save tasks: {e}")

    def create_task(self, goal: str, priority: int = 5, subtasks: list[str] = None) -> Task:
        """Create a new long-term task."""
        task = Task(goal=goal, priority=priority)
        if subtasks:
            for st_desc in subtasks:
                task.subtasks.append(SubTask(description=st_desc))

        self.tasks[task.id] = task
        self.save_tasks()
        return task

    def get_active_tasks(self) -> list[Task]:
        """Return tasks that are not completed or failed."""
        return [
            t
            for t in self.tasks.values()
            if t.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED]
        ]

    def update_task_checkpoint(self, task_id: str, checkpoint: str):
        if task_id in self.tasks:
            self.tasks[task_id].checkpoint = checkpoint
            self.tasks[task_id].updated_at = datetime.now(UTC)
            self.save_tasks()

    def complete_task(self, task_id: str, lessons: str = None):
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.update_status(TaskStatus.COMPLETED)
            task.lessons_learned = lessons
            self.save_tasks()

    def fail_task(self, task_id: str, reason: str):
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.update_status(TaskStatus.FAILED)
            task.metadata["failure_reason"] = reason
            self.save_tasks()

    def get_task_context(self) -> str:
        """Format active tasks for the agent's prompt."""
        active = self.get_active_tasks()
        if not active:
            return ""

        lines = ["# ACTIVE LONG-TERM TASKS"]
        for t in active:
            lines.append(f"## Task: {t.goal} (Status: {t.status})")
            lines.append(f"- ID: {t.id}")
            if t.checkpoint:
                lines.append(f"- Last Checkpoint: {t.checkpoint}")
            if t.subtasks:
                lines.append("- Subtasks:")
                for st in t.subtasks:
                    check = "[x]" if st.status == TaskStatus.COMPLETED else "[ ]"
                    lines.append(f"  {check} {st.description}")
        return "\n".join(lines)


# Global task manager instance for singleton pattern access
task_manager = TaskManager()
