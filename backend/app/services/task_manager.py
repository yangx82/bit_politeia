import json
import logging
import uuid
from datetime import datetime, timezone
UTC = timezone.utc
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# 延迟导入 DeliverableStore 以避免循环依赖
_deliverable_store = None

def get_deliverable_store():
    global _deliverable_store
    if _deliverable_store is None:
        try:
            from app.services.deliverable_store import DeliverableStore
            _deliverable_store = DeliverableStore()
        except ImportError:
            logger.warning("DeliverableStore not available, archiving disabled")
            return None
    return _deliverable_store

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items(): setattr(self, k, v)
        def model_dump(self, mode="json"):
            return self.__dict__
    def Field(default_factory=None, **kwargs):
        return default_factory() if default_factory else None

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFYING = "verifying"  # 正在验证成果
    PARTIAL = "partial"  # 部分交付物完成


class DeliverableType(str, Enum):
    """交付物类型"""
    FILE = "file"  # 文件（代码、文档、数据）
    MESSAGE = "message"  # 已发送的消息
    VOTE = "vote"  # 已投出的选票
    PAYMENT = "payment"  # 已完成的转账
    ANALYSIS = "analysis"  # 分析报告（含数据支撑）
    RESEARCH = "research"  # 研究成果（论文/提案）
    CODE = "code"  # 代码修改/修复
    CONFIG = "config"  # 配置变更


class Deliverable(BaseModel):
    """任务交付物定义"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: DeliverableType
    description: str  # 交付物描述
    target: str | None = None  # 文件路径/消息接收者/投票ID等
    status: str = "pending"  # pending/verified/failed
    evidence: dict[str, Any] | None = None  # 完成证据
    verified_at: datetime | None = None


class VerificationRules:
    """任务完成验证规则"""
    
    RULES = {
        DeliverableType.MESSAGE: {
            "required_evidence": ["recipient_id", "status"],
            "check": lambda e: e.get("status") == "SUCCESS" or e.get("status") == "sent",
            "description": "消息必须成功发送并返回确认"
        },
        DeliverableType.FILE: {
            "required_evidence": ["file_path", "file_size"],
            "check": lambda e: e.get("file_size", 0) > 0,
            "description": "文件必须存在且非空"
        },
        DeliverableType.VOTE: {
            "required_evidence": ["election_id"],
            "check": lambda e: e.get("status") in ["recorded", "SUCCESS", "cast"],
            "description": "投票必须被记录"
        },
        DeliverableType.PAYMENT: {
            "required_evidence": ["payee_id", "amount"],
            "check": lambda e: e.get("status") == "SUCCESS" and e.get("amount", 0) > 0,
            "description": "转账必须成功且金额大于0"
        },
        DeliverableType.ANALYSIS: {
            "required_evidence": ["content_length"],
            "check": lambda e: e.get("content_length", 0) > 100,
            "description": "分析报告必须有实质内容"
        },
        DeliverableType.RESEARCH: {
            "required_evidence": ["content_length"],
            "check": lambda e: e.get("content_length", 0) > 500,
            "description": "研究成果必须有实质内容"
        },
        DeliverableType.CODE: {
            "required_evidence": ["file_path"],
            "check": lambda e: e.get("syntax_valid", True) == True,
            "description": "代码必须语法正确"
        },
        DeliverableType.CONFIG: {
            "required_evidence": ["parameter_path", "new_value"],
            "check": lambda e: e.get("status") == "SUCCESS",
            "description": "配置必须成功更新"
        }
    }
    
    @classmethod
    def verify(cls, deliverable_type: DeliverableType, evidence: dict) -> dict:
        """验证交付物是否完成"""
        rules = cls.RULES.get(deliverable_type)
        if not rules:
            return {"verified": False, "reason": f"No verification rules for {deliverable_type}"}
        
        # 检查必要证据字段
        missing = [f for f in rules["required_evidence"] if f not in evidence]
        if missing:
            return {"verified": False, "reason": f"Missing evidence: {missing}"}
        
        # 执行验证逻辑
        try:
            if rules["check"](evidence):
                return {"verified": True, "description": rules["description"]}
            else:
                return {"verified": False, "reason": "Verification check failed"}
        except Exception as e:
            return {"verified": False, "reason": f"Verification error: {e}"}


class SubTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
    deliverables: list[Deliverable] = Field(default_factory=list)  # 子任务交付物
    evidence_log: list[dict[str, Any]] = Field(default_factory=list)  # 证据日志


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
    
    # === 新增：成果交付追踪 ===
    deliverables: list[Deliverable] = Field(default_factory=list)  # 预期交付物列表
    evidence_log: list[dict[str, Any]] = Field(default_factory=list)  # 证据日志
    completion_percentage: float = 0.0  # 完成百分比 (0-100)

    def update_status(self, new_status: TaskStatus):
        self.status = new_status
        self.updated_at = datetime.now(UTC)
    
    def add_deliverable(self, deliverable: Deliverable):
        """添加预期交付物"""
        self.deliverables.append(deliverable)
        self.updated_at = datetime.now(UTC)
    
    def add_evidence(self, evidence: dict[str, Any]):
        """记录证据"""
        self.evidence_log.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "evidence": evidence
        })
        self.updated_at = datetime.now(UTC)
    
    def calculate_completion(self) -> float:
        """计算完成百分比"""
        if not self.deliverables:
            # 如果没有定义交付物，根据状态估算
            status_map = {
                TaskStatus.PENDING: 0.0,
                TaskStatus.ACTIVE: 50.0,
                TaskStatus.RUNNING: 50.0,
                TaskStatus.BLOCKED: 30.0,
                TaskStatus.VERIFYING: 90.0,
                TaskStatus.PARTIAL: 60.0,
                TaskStatus.COMPLETED: 100.0,
                TaskStatus.FAILED: 0.0,
            }
            return status_map.get(self.status, 0.0)
        
        verified = sum(1 for d in self.deliverables if d.status == "verified")
        total = len(self.deliverables)
        self.completion_percentage = (verified / total * 100) if total > 0 else 0.0
        return self.completion_percentage


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
                        # 兼容旧数据：如果没有 deliverables 字段，初始化为空列表
                        if "deliverables" not in t_data:
                            t_data["deliverables"] = []
                        if "evidence_log" not in t_data:
                            t_data["evidence_log"] = []
                        if "completion_percentage" not in t_data:
                            t_data["completion_percentage"] = 0.0
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
                        f.write(f"- **Completion**: {t.completion_percentage:.0f}%\n")
                        f.write(f"- **Created**: {t.created_at.strftime('%Y-%m-%d %H:%M')}\n")
                        if t.checkpoint:
                            f.write(f"- **Checkpoint**: {t.checkpoint}\n")
                        if t.deliverables:
                            f.write("- **Deliverables**:\n")
                            for d in t.deliverables:
                                icon = "✅" if d.status == "verified" else "⏳" if d.status == "pending" else "❌"
                                f.write(f"  - {icon} [{d.type.value}] {d.description}\n")
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

    def get_all_tasks(self) -> list[Task]:
        """Return all tasks regardless of status."""
        return list(self.tasks.values())

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
            lines.append(f"- Completion: {t.completion_percentage:.0f}%")
            if t.checkpoint:
                lines.append(f"- Last Checkpoint: {t.checkpoint}")
            if t.deliverables:
                lines.append("- Expected Deliverables:")
                for d in t.deliverables:
                    icon = "✅" if d.status == "verified" else "⏳" if d.status == "pending" else "❌"
                    lines.append(f"  {icon} [{d.type.value}] {d.description}")
            if t.subtasks:
                lines.append("- Subtasks:")
                for st in t.subtasks:
                    check = "[x]" if st.status == TaskStatus.COMPLETED else "[ ]"
                    lines.append(f"  {check} {st.description}")
        return "\n".join(lines)
    
    # === 新增：成果交付验证方法 ===
    
    def define_deliverables(self, task_id: str, deliverables: list[dict]) -> bool:
        """为任务定义预期交付物"""
        if task_id not in self.tasks:
            logger.warning(f"Task {task_id} not found")
            return False
        
        task = self.tasks[task_id]
        for d in deliverables:
            deliverable = Deliverable(
                type=d.get("type", DeliverableType.ANALYSIS),
                description=d.get("description", ""),
                target=d.get("target")
            )
            task.add_deliverable(deliverable)
        
        self.save_tasks()
        logger.info(f"Defined {len(deliverables)} deliverables for task {task_id[:8]}")
        return True
    
    def record_evidence(self, task_id: str, deliverable_id: str, evidence: dict) -> dict:
        """记录交付物证据并验证，同时自动归档到统一存储"""
        if task_id not in self.tasks:
            return {"success": False, "reason": "Task not found"}
        
        task = self.tasks[task_id]
        
        # 查找对应的交付物
        deliverable = None
        for d in task.deliverables:
            if d.id == deliverable_id:
                deliverable = d
                break
        
        if not deliverable:
            # 如果没有指定 deliverable_id，尝试找到第一个 pending 的交付物
            for d in task.deliverables:
                if d.status == "pending":
                    deliverable = d
                    break
        
        # 验证证据
        verification_result = VerificationRules.verify(deliverable.type if deliverable else DeliverableType.ANALYSIS, evidence)
        
        # 记录证据到任务级别
        task.add_evidence({
            "deliverable_id": deliverable_id,
            "deliverable_type": deliverable.type.value if deliverable else "analysis",
            "evidence": evidence,
            "verification": verification_result
        })
        
        # 更新交付物状态
        if deliverable:
            if verification_result.get("verified"):
                deliverable.status = "verified"
                deliverable.evidence = evidence
                deliverable.verified_at = datetime.now(UTC)
                
                # === P2 改进：自动归档到统一存储 ===
                self._archive_deliverable(task_id, deliverable, evidence)
            else:
                deliverable.status = "failed"
                deliverable.evidence = {"error": verification_result.get("reason")}
        
        # 重新计算完成百分比
        task.calculate_completion()
        
        # 检查是否所有交付物都已完成
        if task.deliverables:
            all_verified = all(d.status == "verified" for d in task.deliverables)
            any_failed = any(d.status == "failed" for d in task.deliverables)
            
            if all_verified:
                task.update_status(TaskStatus.COMPLETED)
            elif any_failed:
                task.update_status(TaskStatus.PARTIAL)
        
        self.save_tasks()
        return verification_result
    
    def _archive_deliverable(self, task_id: str, deliverable: Deliverable, evidence: dict):
        """自动归档交付物到统一存储"""
        store = get_deliverable_store()
        if not store:
            return
        
        try:
            # 根据交付物类型准备内容和元数据
            content = json.dumps({
                "task_id": task_id,
                "deliverable_id": deliverable.id,
                "type": deliverable.type.value,
                "description": deliverable.description,
                "evidence": evidence,
                "verified_at": deliverable.verified_at.isoformat() if deliverable.verified_at else None
            }, ensure_ascii=False, indent=2)
            
            metadata = {
                "task_goal": self.tasks[task_id].goal if task_id in self.tasks else "",
                "deliverable_description": deliverable.description
            }
            
            # 对于文件类型，尝试复制实际文件
            if deliverable.type == DeliverableType.FILE and deliverable.target:
                try:
                    result = store.store_file_copy(task_id, deliverable.target, metadata)
                    logger.info(f"Archived file deliverable: {result['id']}")
                    return
                except Exception as e:
                    logger.warning(f"Failed to copy file, storing metadata only: {e}")
            
            # 存储内容
            result = store.store_deliverable(
                task_id=task_id,
                deliverable_type=deliverable.type.value,
                content=content,
                metadata=metadata
            )
            logger.info(f"Archived deliverable: {result['id']}")
            
        except Exception as e:
            logger.error(f"Failed to archive deliverable: {e}")
    
    def get_task_completion(self, task_id: str) -> dict:
        """获取任务完成情况"""
        if task_id not in self.tasks:
            return {"error": "Task not found"}
        
        task = self.tasks[task_id]
        return {
            "task_id": task_id,
            "status": task.status.value,
            "completion_percentage": task.completion_percentage,
            "deliverables": [
                {
                    "id": d.id,
                    "type": d.type.value,
                    "description": d.description,
                    "status": d.status,
                    "evidence": d.evidence
                }
                for d in task.deliverables
            ],
            "evidence_count": len(task.evidence_log)
        }
    
    def can_complete_task(self, task_id: str) -> dict:
        """检查任务是否可以标记为完成"""
        if task_id not in self.tasks:
            return {"can_complete": False, "reason": "Task not found"}
        
        task = self.tasks[task_id]
        
        # 如果没有定义交付物，允许完成（向后兼容）
        if not task.deliverables:
            return {"can_complete": True, "reason": "No deliverables defined (legacy mode)"}
        
        # 检查所有交付物是否已验证
        pending = [d for d in task.deliverables if d.status == "pending"]
        verified = [d for d in task.deliverables if d.status == "verified"]
        failed = [d for d in task.deliverables if d.status == "failed"]
        
        if pending:
            return {
                "can_complete": False,
                "reason": f"{len(pending)} deliverable(s) still pending verification",
                "pending_deliverables": [d.description for d in pending]
            }
        
        if failed:
            return {
                "can_complete": False,
                "reason": f"{len(failed)} deliverable(s) failed verification",
                "failed_deliverables": [d.description for d in failed]
            }
        
        return {
            "can_complete": True,
            "reason": f"All {len(verified)} deliverable(s) verified",
            "verified_count": len(verified)
        }


# Global task manager instance for singleton pattern access
task_manager = TaskManager()
