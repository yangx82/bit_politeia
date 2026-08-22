import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
UTC = timezone.utc
from typing import Any

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ImportError:
    class AsyncIOScheduler:
        def __init__(self, **kwargs): pass
        def start(self): pass
        def shutdown(self): pass
        def add_job(self, *args, **kwargs): pass

from ..bus.events import InboundMessage, OutboundMessage
from ..bus.queue import message_bus
from ..models.schemas import AgentStatus, Message, P2PMessage
from .crypto_service import crypto_service
from .p2p_service import p2p_service

# Placeholder for LangChain
# from langchain.llms import OpenAI

logger = logging.getLogger(__name__)
p2p_logger = logging.getLogger("p2p_network")
try:
    import langchain
    langchain.debug = True
except ImportError:
    langchain = None

import json

try:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
    from langchain_openai import ChatOpenAI
except ImportError:
    class BaseMessage:
        def __init__(self, content: str = "", **kwargs):
            self.content = content
            for k, v in kwargs.items(): setattr(self, k, v)
    class AIMessage(BaseMessage): pass
    class HumanMessage(BaseMessage): pass
    class SystemMessage(BaseMessage): pass
    class ToolMessage(BaseMessage): pass
    class ChatOpenAI: pass

from ..agent.context import ContextBuilder
from ..agent.prompts import AGENT_SYSTEM_PROMPT, CODING_SUBAGENT_PROMPT, SELF_HEALING_SUBAGENT_PROMPT
from ..agent.tools import AGENT_TOOLS, CODING_TOOLS, REPAIR_TOOLS
from ..agent.tools_meta import create_tool_tool
from ..agent.tools_search_ext import create_search_tools
from ..agent.tools_task_ext import (
    set_current_task_tool,
    define_deliverables_tool,
    record_task_evidence_tool,
    can_complete_task_tool,
    get_task_completion_tool,
)
from ..tools.tools_deliverable_store import (
    list_archived_deliverables,
    verify_deliverable_integrity,
    get_deliverable_store_stats,
    read_archived_deliverable,
    get_task_deliverables_summary,
)
from ..p2p_community.blockchain import ArchiveManager
from ..p2p_community.economy import Ledger
from ..p2p_community.governance import ElectionType, GovernanceManager, Vote
from ..p2p_community.reputation import ReputationManager
from .consolidation import ConsolidationService
from .context_manager import BitPoliteiaContextManager
from .knowledge_base import knowledge_base
from .resident_memory_service import ResidentMemory, ResidentReporter
from .session_service import session_manager
from .identity_service import identity_manager
from .skill_manager import skill_manager
from .task_manager import TaskManager, TaskStatus

# DeepSeek Harness Architecture Enhancements
from ..agent.waterfall import waterfall_pipeline
from .spill_store import spill_store
from .context_pruner import tool_result_pruner, compaction_engine
from .session_event_log import session_event_log
from .scoped_subagent import scoped_subagent_manager, ToolFilter


class AgentService:
    def __init__(self):
        self.history: list[Message] = []
        self.processed_message_ids: set[str] = set()  # For de-duplication
        self.notified_governance_ids: set[str] = set()  # Track proposals shared with agent
        self.notified_error_signatures: set[str] = (
            set()
        )  # Track error signatures for self-reflection
        self.notified_watchdog_ids: set[str] = set()  # Track watchdog-triggered message IDs
        self._is_processing_inbox = False  # Concurrency Guard
        self.status = AgentStatus(is_online=True, reputation=10, balance=0.0)
        self.message_bus = message_bus
        self.resident_bridges: dict[str, str] = {}  # Bridge Name -> Chat/OpenID
        self.active_pipelines: dict[str, Any] = {}  # session_id -> PipelineContext for /steer

        # Resolve absolute path to backend/data
        from pathlib import Path

        current_file = Path(__file__).resolve()
        self.backend_dir = current_file.parent.parent.parent
        self.data_dir = self.backend_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Scheduler (Memory-only to avoid DB trigger persistence conflicts with hardcoded boot jobs)
        try:
            job_defaults = {
                "coalesce": True,  # Merge multiple missed runs into one
                "max_instances": 3,
                "misfire_grace_time": 60,  # Generous grace time to prevent skipping on boot load
            }
            self.scheduler = AsyncIOScheduler(job_defaults=job_defaults)
            logger.info("Scheduler initialized with Memory persistence.")
        except Exception as e:
            logger.error(f"Failed to init scheduler: {e}")
            self.scheduler = AsyncIOScheduler()

        # Scheduler will be started in start_scheduler() called by main.py lifespan
        self.base_url = None
        self.api_key = None
        self.llm = None

        # .env 文件路径（项目根目录）- 方案A: 统一使用 .env
        self.env_file = self.backend_dir.parent / ".env"

        # P2P Reply Delay Default

        from ..utils.env_utils import load_dotenv_safe

        load_dotenv_safe()
        self.p2p_reply_delay = 60

        # Initialization logic (Moved to __init__)
        self.tools_map = {getattr(t, "name", getattr(t, "__name__", str(t))): t for t in AGENT_TOOLS}
        self.governance_manager = None
        self.reputation_manager = None
        self.archive_manager = None
        ledger_path = str(self.data_dir / "ledger.json")
        self.ledger = Ledger(storage_path=ledger_path)
        # Register transaction event callback for broadcasting
        self.ledger.set_event_callback(self._on_transaction_completed)
        self.resident_memory = ResidentMemory()
        self.reporter = None
        self.research_field = "AI Governance"
        self.enable_welcome = True
        self.task_manager = TaskManager()
        self.context_builder = ContextBuilder(task_manager=self.task_manager)
        self.consolidation_service = ConsolidationService(self)

        # Identity Defaults
        self.name = os.getenv("AGENT_NAME", "Agent")
        self.personality = "Professional and helpful"
        self.agent_language = "中文"
        self.model = os.getenv("AGENT_MODEL", None)
        self.base_url = os.getenv("AGENT_BASE_URL", None)
        self.api_key = os.getenv("AGENT_API_KEY", None)
        self.llm = None
        self.context_manager = None
        self.knowledge_base = knowledge_base

        # Hydrate History and System State from Disk
        self._hydrate_history()
        self._hydrate_system_state()
        self.verbose_llm = False

    def start_scheduler(self):
        """Start the scheduler and add background jobs."""
        try:
            # Add jobs only once
            if not getattr(self, "_jobs_added", False):
                self.scheduler.add_job(
                    "app.services.agent_service:trigger_scheduled_task_proxy",
                    "cron",
                    hour=0,
                    minute=0,
                    misfire_grace_time=3600,
                    id="periodic_brief_job",
                    replace_existing=True,
                )
                self.scheduler.add_job(
                    "app.services.agent_service:run_literature_watcher_proxy",
                    "cron",
                    hour=0,
                    minute=30,
                    misfire_grace_time=3600,
                    id="periodic_literature_watcher_job",
                    replace_existing=True,
                )
                if os.getenv("AGENT_AUTO_EVOLUTION_ENABLED", "false").lower() == "true":
                    interval_hours = int(os.getenv("AGENT_AUTO_EVOLUTION_INTERVAL_HOURS", "24"))
                    first_run = datetime.now(UTC) + timedelta(seconds=60)
                    self.scheduler.add_job(
                        "app.services.agent_service:run_evolution_watcher_proxy",
                        "interval",
                        hours=interval_hours,
                        next_run_time=first_run,
                        misfire_grace_time=3600,
                        id="periodic_evolution_watcher_job",
                        replace_existing=True,
                    )
                self.scheduler.add_job(
                    "app.services.agent_service:process_network_inbox_proxy",
                    "interval",
                    seconds=30,
                    misfire_grace_time=15,
                    id="network_inbox_job",
                    replace_existing=True,
                )
                self.scheduler.add_job(
                    "app.services.agent_service:sync_network_proxy",
                    "interval",
                    minutes=2,
                    id="sync_network_job",
                    replace_existing=True,
                )
                self.scheduler.add_job(
                    "app.services.agent_service:nightly_maintenance_pipeline_proxy",
                    "cron",
                    hour=2,
                    minute=0,
                    id="nightly_maintenance_pipeline_job",
                    replace_existing=True,
                )
                self.scheduler.add_job(
                    "app.services.agent_service:check_tasks_monitor_proxy",
                    "interval",
                    minutes=5,
                    next_run_time=datetime.now(UTC),
                    id="task_monitor_job",
                    replace_existing=True,
                )
                self.scheduler.add_job(
                    "app.services.agent_service:check_governance_proposals_proxy",
                    "interval",
                    minutes=10,
                    next_run_time=datetime.now(UTC),
                    id="governance_monitor_job",
                    replace_existing=True,
                )
                self.scheduler.add_job(
                    "app.services.agent_service:retry_failed_messages_proxy",
                    "interval",
                    minutes=10,
                    next_run_time=datetime.now(UTC),
                    id="retry_messages_job",
                    replace_existing=True,
                )
                self.scheduler.add_job(
                    "app.services.agent_service:system_health_monitor_proxy",
                    "interval",
                    minutes=15,
                    id="system_health_monitor_job",
                    replace_existing=True,
                )
                self.scheduler.add_job(
                    "app.services.agent_service:check_unhandled_messages_proxy",
                    "interval",
                    minutes=5,
                    id="unhandled_msg_watchdog",
                    replace_existing=True,
                )
                # Gossip State Sync: Periodic state synchronization for eventual consistency
                self.scheduler.add_job(
                    "app.services.agent_service:gossip_state_sync_proxy",
                    "interval",
                    minutes=3,
                    id="gossip_state_sync_job",
                    replace_existing=True,
                )
                # P2P Throttle Flush: Send buffered messages after cooldown
                self.scheduler.add_job(
                    "app.services.agent_service:flush_throttled_messages_proxy",
                    "interval",
                    minutes=1,
                    id="p2p_throttle_flush_job",
                    replace_existing=True,
                )
                # Self-Healing: only register supervisor job if env var is set
                if os.environ.get("ENABLE_SELF_HEALING", "false").lower() in ("true", "1", "yes"):
                    self.scheduler.add_job(
                        "app.services.agent_service:code_supervisor_proxy",
                        "interval",
                        seconds=10,
                        id="code_supervisor_job",
                        replace_existing=True,
                    )
                    logger.info(
                        "Self-Healing: Code supervisor job registered (ENABLE_SELF_HEALING=true)."
                    )
                self._jobs_added = True

                # --- STARTUP BACKFILL CHECK ---
                if self.archive_manager:
                    try:
                        last_block = self.archive_manager.chain.latest_block
                        last_ts = datetime.fromtimestamp(last_block.timestamp, tz=UTC)
                        now = datetime.now(UTC)

                        # We should have a block for each day 2:10 AM.
                        # Calculate the most recent scheduled archiving time (2:10 AM)
                        scheduled_time = now.replace(hour=2, minute=10, second=0, microsecond=0)
                        if now < scheduled_time:
                            # If it's earlier than 2:10 AM today, the target is yesterday's 2:10 AM
                            scheduled_time -= timedelta(days=1)

                        if last_ts < scheduled_time:
                            logger.info(
                                f"Startup: Missed archive detected (Last: {last_ts.isoformat()}, Target: {scheduled_time.isoformat()}). Backfilling..."
                            )
                            # Trigger immediate archiving in background
                            asyncio.create_task(self.run_archiving())
                    except Exception as be:
                        logger.error(f"Startup backfill check failed: {be}")

                logger.info("Scheduler background jobs registered successfully.")

            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("Scheduler started successfully.")
            else:
                logger.info("Scheduler already running, jobs ensured.")

            # --- STARTUP AUTO-RESUME CHECK ---
            asyncio.create_task(self.check_and_resume_interrupted_tasks())
        except Exception as e:
            logger.error(f"Failed to start scheduler/jobs: {e}")

    async def check_and_resume_interrupted_tasks(self):
        """
        Check for interrupted tasks caused by self-code modification or backend reloads.
        Restores working memory (thoughts, previous tool calls) and resumes execution.
        """
        try:
            from app.agent.checkpoint_manager import checkpoint_manager

            checkpoint = checkpoint_manager.load_checkpoint()
            if not checkpoint:
                logger.info("[Auto-Resume] No interrupted task checkpoint found.")
                return

            session_id = checkpoint.get("session_id", "resident")
            channel = checkpoint.get("channel", "resident")
            sender_id = checkpoint.get("sender_id", "resident")
            orig_input = checkpoint.get("input_message_content", "")
            thoughts = checkpoint.get("thoughts", [])
            tool_results = checkpoint.get("tool_results", [])

            logger.info(
                f"[Auto-Resume] Interrupted task checkpoint detected! Session: {session_id}, "
                f"Thoughts: {len(thoughts)}, Tool Results: {len(tool_results)}"
            )

            # Build continuation prompt
            thoughts_str = "\n".join([f"- {t[:150]}..." if len(t) > 150 else f"- {t}" for t in thoughts[-3:]]) if thoughts else "无"
            executed_tools = ", ".join([r.get("tool", "tool") for r in tool_results]) or "无"

            resume_prompt = (
                f"[SYSTEM AUTO-RESUME NOTICE]: 检测到系统因代码修改/热重载进行了重新启动。"
                f"已成功自动恢复工作记忆与执行断点！\n"
                f"你中断前正在推进的需求: \"{orig_input}\"\n"
                f"中断前的最新思考记录:\n{thoughts_str}\n"
                f"中断前已执行完毕的工具: {executed_tools}\n"
                f"请先检查修改后的代码文件状态，验证代码语法/文件逻辑，然后接着从中断的地方继续完成后续的任务。"
            )

            # Clear checkpoint to prevent repeated resumption
            checkpoint_manager.clear_checkpoint()

            from app.bus.events import InboundMessage
            resume_msg = InboundMessage(
                channel=channel,
                sender_id=sender_id,
                session_id=session_id,
                content=resume_prompt,
                metadata={"is_auto_resume": True, "original_request": orig_input}
            )

            logger.info(f"[Auto-Resume] Triggering async pipeline resume for session {session_id}...")

            # Wait for Agent LLM and ContextManager to fully initialize (up to 30s)
            for wait_turn in range(60):
                if self.llm and self.context_manager:
                    logger.info(f"[Auto-Resume] Agent fully initialized after {wait_turn * 0.5:.1f}s. Proceeding with resume.")
                    break
                await asyncio.sleep(0.5)

            if not self.llm or not self.context_manager:
                logger.warning("[Auto-Resume] Agent initialization timed out after 30s. Deferring auto-resume.")
                return

            asyncio.create_task(self.process_bus_message(resume_msg))

        except Exception as e:
            logger.error(f"[Auto-Resume] Failed to resume interrupted task: {e}")

    async def _retry_failed_messages(self):
        """10-minute automatic retry for failed/pending P2P messages."""
        logger.info("Starting automatic retry for failed/pending P2P messages...")

        # 1. Find candidates (last 2 hours for safety, but focus on the 10min window)
        # focus on the 10min window
        now = datetime.now(UTC)
        ten_minutes_ago = now - timedelta(minutes=10)
        one_minute_ago = now - timedelta(minutes=1)

        # We only retry messages that failed recently (within the last 10 mins).
        # We use a 1-minute grace period to avoid double-sending messages that are still connecting.
        retry_candidates = []
        for msg in self.history:
            if msg.sender == "agent" and msg.status in ["failed", "pending", None]:
                # Ensure msg.timestamp is aware before comparison
                m_ts = msg.timestamp
                if m_ts and m_ts.tzinfo is None:
                    m_ts = m_ts.replace(tzinfo=UTC)

                if m_ts and ten_minutes_ago <= m_ts <= one_minute_ago:
                    retry_candidates.append(msg)

        if not retry_candidates:
            logger.info("No candidates for P2P retry found.")
            return

        logger.info(f"Found {len(retry_candidates)} messages for P2P retry.")

        for msg in retry_candidates:
            try:
                # session_id in history is normalized, but send_p2p_message handles it
                # We use is_retry=True to skip moderation and history duplication
                # We pass original_msg_id to ensure the P2P network deduplicates if needed
                recipient_id = msg.session_id

                # 1.5 CIRCUIT BREAKER: Only retry if it looks like a P2P ID and is NOT resident/system
                # We also check for an explicit metadata flag that we'll add to real P2P messages
                is_p2p_meta = False
                if hasattr(msg, "metadata") and msg.metadata:
                    is_p2p_meta = msg.metadata.get("is_p2p", False)

                if not is_p2p_meta and (
                    recipient_id in ["resident", "system"] or "[" in recipient_id
                ):
                    continue

                # Double-check: If it's not a known P2P session ID or hex ID, don't retry it over P2P
                if not is_p2p_meta and len(recipient_id) < 16:
                    continue

                logger.info(f"Triggering automatic retry for message {msg.id} to {recipient_id}")
                await self.send_p2p_message(
                    recipient_id=recipient_id,
                    content=msg.content,
                    is_retry=True,
                    original_msg_id=msg.id,
                )
            except Exception as e:
                logger.error(f"Failed to retry message {msg.id}: {e}")

    async def _flush_throttled_messages(self):
        """Scans sessions for pending messages that are past their 5-minute cooldown."""
        logger.info("Scanning for throttled P2P messages to flush...")

        # 1. Iterate through in-memory sessions
        sessions_to_check = list(session_manager.sessions.values())

        # 2. Optionally scan disk if memory is empty (expensive, but thorough)
        # For now, we rely on core active sessions in memory

        now = datetime.now(UTC)
        cooldown_seconds = int(os.getenv("AGENT_P2P_COOLDOWN_SECONDS", getattr(self, "p2p_cooldown_seconds", 300)))

        flushed_count = 0
        for session in sessions_to_check:
            pending_reply = session.metadata.get("pending_reply")
            if not pending_reply:
                continue

            last_reply_iso = session.metadata.get("last_p2p_reply_at")
            if not last_reply_iso:
                # Shouldn't happen if pending_reply is set, but safety first
                continue

            try:
                last_reply_at = datetime.fromisoformat(last_reply_iso)
                if last_reply_at.tzinfo is None:
                    last_reply_at = last_reply_at.replace(tzinfo=UTC)

                elapsed = (now - last_reply_at).total_seconds()
                if elapsed >= cooldown_seconds:
                    logger.info(
                        f"Flushing throttled message for session {session.entity_id} (Cooldown expired: {int(elapsed)}s)"
                    )

                    # Call send_p2p_message with bypass_throttle=True
                    # This will also clear the metadata and update the last_reply_at
                    await self.send_p2p_message(
                        recipient_id=session.entity_id, content=pending_reply, bypass_throttle=True
                    )
                    flushed_count += 1
            except Exception as e:
                logger.error(f"Error flushing session {session.entity_id}: {e}")

        if flushed_count > 0:
            logger.info(f"Successfully flushed {flushed_count} toggled P2P messages.")

    # ... remaining of file ...

    def _get_host_info(self) -> str:
        """Detect current host environment (OS, Shell, CWD) for the agent."""
        import os
        import platform

        system = platform.system()
        release = platform.release()
        machine = platform.machine()
        cwd = os.getcwd()

        shell = "cmd.exe" if system == "Windows" else os.getenv("SHELL", "bash/sh")

        info = "\n### HOST ENVIRONMENT (DYNAMICALLY DETECTED)\n"
        info += f"- **Operating System**: {system} {release} ({machine})\n"
        info += f"- **Primary Shell**: {shell}\n"
        info += f"- **Current Working Directory**: {cwd}\n"

        if system == "Windows":
            info += "- **File System**: Windows-style paths (e.g., C:\\Users\\...)\n"
            info += (
                "- **Constraint**: Use Windows-compatible commands (e.g., `dir` instead of `ls`).\n"
            )
        else:
            info += "- **File System**: POSIX-style paths (e.g., /home/user/...)\n"
            info += (
                "- **Constraint**: Use POSIX-compatible commands (e.g., `ls` instead of `dir`).\n"
            )

        return info

    def _normalize_session_id(self, sid: str, channel: str = None) -> str:
        """Standardize Session/Chat IDs via IdentityManager for cross-channel consistency."""
        if not sid:
            return sid
        
        # 1. Resolve unified ID if channel is provided
        if channel:
            return identity_manager.resolve_unified_id(sid, channel)

        # 2. Legacy fallback for P2P IDs (if no channel provided)
        if sid.startswith("[p2p] "):
            sid = sid[6:]
        if p2p_service._initialized and p2p_service.network_manager:
            for node_id, node in p2p_service.network_manager.nodes.items():
                if node.name == sid:
                    return node_id
        return sid

    def _is_automated_error_notification(self, content: str) -> bool:
        """Detect if a P2P message is an automated system/LLM error notification or refusal.
        
        Such messages should be stored in history for audit/context, but must NOT trigger
        downstream LLM response generation to prevent error-reply feedback loops across nodes.
        """
        if not content:
            return False
            
        text = content.strip().lower()
        
        error_indicators = [
            "[no_response_needed]",
            "[no response needed]",
            "error communicating with llm",
            "triggered ralph wiggum auto-heal",
            "llm 限制提示",
            "llm 服务提示",
            "message refused:",
            "security suppression:",
            "fatal_llm_request_validation_error",
            "fatal_parallel_tool_calls_unsupported",
            "fatal_no_model_loaded",
            "fatal_sglang_fc_parser_error",
            "token_length_exceeded",
            "api_error:",
            "connection error",
        ]
        for pattern in error_indicators:
            if pattern in text:
                return True
        return False

    def _is_pure_acknowledgment_rules(self, content: str) -> bool:
        """Detect if a P2P message is a pure acknowledgment or status confirmation using rules."""
        if not content:
            return False
            
        text = content.strip().lower()
        
        # Check automated error notifications or explicit bypass flags
        if self._is_automated_error_notification(text):
            return True
            
        import re
        
        # Strip common local agent-generated prefixes/metadata if present
        text = text.replace("[agent completed p2p task]:", "")
        
        # 1. First-pass: Strip signatures and timestamps
        text = re.sub(r'—\s*[^\n]+', '', text)
        text = re.sub(r'--\s*[^\n]+', '', text)
        text = re.sub(r'\d{4}-\d{2}-\d{2}(?:\s+|\s*t\s*)\d{2}:\d{2}(?::\d{2})?', '', text)
        
        # 2. Check for question/instruction/request indicators on the cleaned text.
        indicators = [
            "?", "？", "为什么", "how", "why", "what", "who", "where", "which",
            "如何", "怎么", "谁", "什么", "哪", "是否", "吗", "请问", "please",
            "request", "question", "help", "请", "需要", "要求", "错误",
            "bug", "fail", "失败", "except", "warn", "alert", "警报", "更新", "update",
            "check", "检查", "verify", "验证", "test", "测试"
        ]
        for ind in indicators:
            if ind in text:
                return False
                
        # Normalize: strip all non-alphanumeric/non-chinese characters
        clean_text = re.sub(r'[^\w\u4e00-\u9fff]', '', text)
        
        # 3. Strip all known node names
        if p2p_service._initialized and p2p_service.network_manager:
            for node in p2p_service.network_manager.nodes.values():
                if node.name:
                    name_clean = re.sub(r'[^\w\u4e00-\u9fff]', '', node.name.lower())
                    if name_clean:
                        clean_text = clean_text.replace(name_clean, "")
                        
        # Also strip self name if configured
        if hasattr(self, "name") and self.name:
            self_name_clean = re.sub(r'[^\w\u4e00-\u9fff]', '', self.name.lower())
            if self_name_clean:
                clean_text = clean_text.replace(self_name_clean, "")
                
        if not clean_text:
            return True
            
        # 4. Pure acknowledgment phrases
        pure_ack_phrases = {
            "收到", "收悉", "已收到", "已收悉", "好的", "知道了", "已阅", "明白",
            "了解", "同意", "遵命", "ok", "okay", "ack", "acknowledged", "gotit",
            "noted", "received", "copied", "roger", "confirmed", "agreed", "copythat",
            "收到啦", "收到哈", "知道了好的", "同步确认", "已确认"
        }
        if clean_text in pure_ack_phrases:
            return True
            
        # 5. Combination of acknowledgment + status confirmation components
        ack_components = [
            "收到", "收悉", "已收到", "已收悉", "好的", "知道了", "已阅", "明白",
            "了解", "同意", "ok", "okay", "ack", "acknowledged", "gotit", "noted",
            "received", "copied", "roger", "confirmed", "agreed", "copythat",
            "同步", "确认", "同步确认", "已确认", "confirm", "sync", "synced",
            "acknowledgment", "acknowledgement", "acknowledging"
        ]
        status_components = [
            "维持", "保持", "处于", "维持在", "状态", "standby", "active", "normal",
            "运行", "运行中", "已切换", "继续", "保持在", "保持现状", "继续保持",
            "维持现状", "继续维持", "继续处于", "状态不变",
            "议题结束", "议题已结束", "讨论结束", "讨论已结束", "流程结束", "会话结束", "交互结束", "任务结束", "任务已结束", "结束",
            "maintain", "maintaining", "keep", "keeping", "state", "status", "running",
            "topic ended", "discussion ended", "session ended", "interaction ended", "task completed", "task ended", "completed", "finished"
        ]
        
        ack_components = sorted(ack_components, key=len, reverse=True)
        status_components = sorted(status_components, key=len, reverse=True)
        
        has_ack = any(ack in clean_text for ack in ack_components)
        if has_ack:
            temp = clean_text
            for ack in ack_components:
                temp = temp.replace(ack, "")
            for stat in status_components:
                temp = temp.replace(stat, "")
            if len(temp) <= 2:
                return True
                
        return False

    async def is_pure_acknowledgment(self, content: str) -> bool:
        """Detect if a P2P message is a pure acknowledgment or status confirmation.
        
        Calls the auxiliary model to make a classification decision, with graceful fallback to
        rules if model configurations or network resources are unavailable.
        """
        if not content:
            return False
            
        text = content.strip().lower()
        
        # 0. Fast-path check for explicit bypass flags & automated error notifications
        if self._is_automated_error_notification(text):
            return True

        # Try utilizing the auxiliary LLM
        try:
            llm = None
            if self.context_manager and getattr(self.context_manager, "summarizer_llm", None):
                llm = self.context_manager.summarizer_llm
            else:
                aux_url = os.getenv("AUX_MODEL_URL", getattr(self, "base_url", None))
                aux_name = os.getenv("AUX_MODEL_NAME", getattr(self, "model", "gpt-4o"))
                aux_key = os.getenv("AUX_MODEL_KEY", getattr(self, "api_key", None))
                if aux_url and aux_key:
                    llm = ChatOpenAI(
                        base_url=aux_url,
                        api_key=aux_key,
                        model=aux_name,
                        temperature=0.0,
                        max_tokens=10,
                    )
            
            if llm:
                system_prompt = (
                    "You are a P2P message filter assistant. Your task is to analyze the user message "
                    "and determine if it is a pure acknowledgment, standby status confirmation message, "
                    "or automated system/LLM error notification (e.g., '收到', '收悉', 'OK', 'got it', 'agreed', '维持 standby 状态', "
                    "'同步确认。议题结束，维持 Standby。', 'Error communicating with LLM', 'Message Refused', etc.) "
                    "which requires NO further response from the receiver.\n\n"
                    "Follow these rules:\n"
                    "1. If the message only serves as an acknowledgment, agreement, sign-off, standby confirmation, or automated system error notification, "
                    "respond with exactly 'YES'.\n"
                    "2. If the message contains actual user questions, instructions, or requires a response/action "
                    "from the receiver, respond with exactly 'NO'.\n"
                    "Respond ONLY with 'YES' or 'NO' (no punctuation, no explanation)."
                )
                response = await llm.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=content)
                ])
                res_text = response.content.strip().upper()
                if "YES" in res_text:
                    return True
                elif "NO" in res_text:
                    return False
        except Exception as e:
            logger.warning(f"Auxiliary model acknowledgment check failed, falling back to rules: {e}")

        # Fallback to rule-based checker
        return self._is_pure_acknowledgment_rules(content)

    async def configure_agent(
        self,
        base_url: str,
        api_key: str,
        model: str = "gpt-4o",
        research_field: str = "AI Governance",
        bootstrap_url: str = None,
        verbose_llm: bool = False,
        bootstrap_verify: bool = True,
        name: str = None,
        personality: str = None,
        p2p_reply_delay: int = 5,
        p2p_cooldown_seconds: int = 300,
        agent_language: str = "中文",
        ralph_wiggum_mode: bool = False,
        llm_timeout: float = 300.0,
    ):
        try:
            self.scheduler.start()
        except Exception:
            pass

        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.research_field = research_field
        self.bootstrap_url = bootstrap_url
        self.verbose_llm = verbose_llm
        self.bootstrap_verify = bootstrap_verify
        if name:
            self.name = name
            self.status.name = name
        if personality:
            self.personality = personality
            self.status.personality = personality
        self.p2p_reply_delay = p2p_reply_delay
        self.p2p_cooldown_seconds = p2p_cooldown_seconds
        self.agent_language = agent_language
        self.ralph_wiggum_mode = ralph_wiggum_mode
        self.llm_timeout = llm_timeout

        # 方案A: 统一保存到 .env
        self._save_config(
            {
                "name": self.name,
                "personality": self.personality,
                "base_url": self.base_url,
                "api_key": self.api_key,
                "model": self.model,
                "research_field": self.research_field,
                "bootstrap_url": self.bootstrap_url,
                "verbose_llm": self.verbose_llm,
                "bootstrap_verify": self.bootstrap_verify,
                "p2p_reply_delay": self.p2p_reply_delay,
                "agent_language": self.agent_language,
                "ralph_wiggum_mode": self.ralph_wiggum_mode,
                "llm_timeout": self.llm_timeout,
            }
        )

        logger.info(f"Agent Configured: Name={self.name}, Model={model}")

        # Apply custom bootstrap settings if provided
        from ..p2p_community.bootstrap_client import bootstrap_client

        if bootstrap_url:
            await bootstrap_client.set_server_url(bootstrap_url)

        # Always apply verify setting (re-initializes client)
        await bootstrap_client.set_verify(bootstrap_verify)

        # Determine P2P Endpoint (Listening Address)
        # 1. Try to get LAN IP
        import socket

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            lan_ip = s.getsockname()[0]
            s.close()
        except Exception:
            lan_ip = "127.0.0.1"

        # Default P2P endpoint is http://<LAN_IP>:8001
        # In a real deployment, this should be configurable via env var AGENT_P2P_ENDPOINT
        import os

        p2p_endpoint = os.getenv("AGENT_P2P_ENDPOINT")
        if not p2p_endpoint:
            p2p_endpoint = f"http://{lan_ip}:8001"

        logger.info(f"Setting P2P Endpoint to: {p2p_endpoint}")

        if p2p_service.local_node:
            await p2p_service.update_node_info(name=self.name)
            node_id = p2p_service.local_node.node_id
        else:
            # Initialize if not already (first run)
            node_id = crypto_service.get_node_id()
            await p2p_service.initialize(node_id, p2p_endpoint, name=self.name)

        # Start Message Bus and Listener
        await self.message_bus.start()
        asyncio.create_task(self.listen_to_bus())

        gov_path = str(self.data_dir / "governance_store.json")
        reputation_path = str(self.data_dir / "reputation.json")
        self.governance_manager = GovernanceManager(node_id, storage_path=gov_path)
        self.reputation_manager = ReputationManager(node_id, storage_path=reputation_path)
        self.archive_manager = ArchiveManager(node_id)
        self.reporter = ResidentReporter(self)

        # Load Knowledge Base
        if self.resident_memory:
            knowledge_base.ingest_history(self.resident_memory.get_recent_history(100))
        if self.archive_manager:
            knowledge_base.ingest_archives(self.archive_manager.chain.get_chain_dict())

        # Use the actual node_id from p2p_service for consistency
        real_node_id = p2p_service.local_node.node_id if p2p_service.local_node else node_id

        # Initialize Ledger Balance (Mocking initial funding)
        if self.ledger.get_balance(real_node_id) == 0:
            self.ledger.credit(real_node_id, 0.0)

        # Initialize LLM with Tools
        try:
            # Clear proxy env vars that use unsupported schemes (e.g. socks://)
            # httpx (used internally by langchain/OpenAI) doesn't support socks without extras
            import os

            for proxy_var in [
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            ]:
                if proxy_var in os.environ and "socks" in os.environ[proxy_var].lower():
                    logger.info(
                        f"Clearing unsupported proxy env var: {proxy_var}={os.environ[proxy_var]}"
                    )
                    del os.environ[proxy_var]

            # Allow configuring max_tokens via env, default to 4000 to prevent premature truncation of analysis/replies
            max_tokens = int(os.getenv("AGENT_MAX_TOKENS", "4000"))
            logger.info(f"Initializing ChatOpenAI with base_url: {base_url}, max_tokens: {max_tokens}")

            raw_llm = ChatOpenAI(
                base_url=base_url,
                api_key=api_key,
                model=model,
                temperature=0.7,  # Default to 1 for generic providers,
                request_timeout=llm_timeout,
                max_tokens=max_tokens,
            )
            # Load custom skills (Run in thread to avoid blocking loop)
            # Load custom skills (Run in thread to avoid blocking loop)
            # 1. Load Autonomous Python Tools
            await asyncio.to_thread(skill_manager.load_skills)
            # 2. Load Claude-Style Skills (e.g. from backend/skills)
            import os

            claude_skills_path = os.path.join(os.getcwd(), "backend", "skills")
            await asyncio.to_thread(skill_manager.load_claude_skills, claude_skills_path)

            skill_tools = skill_manager.get_active_tools()

            # 3. Load Universal Search Tools (Hybrid)
            search_tools = create_search_tools(self)

            # Combine standard tools with skill tools and search tools
            all_tools = (
                AGENT_TOOLS + skill_tools + search_tools + [
                    create_tool_tool,
                    set_current_task_tool,
                    define_deliverables_tool,
                    record_task_evidence_tool,
                    can_complete_task_tool,
                    get_task_completion_tool,
                    # P2: 成果物统一存储工具
                    list_archived_deliverables,
                    verify_deliverable_integrity,
                    get_deliverable_store_stats,
                    read_archived_deliverable,
                    get_task_deliverables_summary,
                ]
            )

            # Update system prompt with skill index (Progressive Disclosure) AND IDENTITY
            skill_index_prompt = skill_manager.get_skill_index()

            # INJECT IDENTITY INTO PROMPT
            identity_section = f"\n\nYOUR IDENTITY CONFIGURATION:\nName: {self.name}\nPersonality Guidelines: {self.personality}\n"

            # INJECT DYNAMIC HOST INFO
            host_info = self._get_host_info()

            base_prompt = AGENT_SYSTEM_PROMPT

            self.current_system_prompt = (
                base_prompt + identity_section + host_info + "\n" + skill_index_prompt
            )

            # Initialize Context Manager before LLM is ready to prevent race conditions during message processing
            from .context_manager import BitPoliteiaContextManager
            self.context_manager = BitPoliteiaContextManager(self)

            # Local models/engines (e.g. SGLang, vLLM, Ollama) usually work better with sequential tool calling.
            # We disable parallel tool calls by default to maximize compatibility, unless using official OpenAI or Aliyun Bailian endpoints.
            url_str = (base_url or "").lower()
            enable_parallel = "api.openai.com" in url_str or "aliyuncs.com" in url_str or "dashscope" in url_str
            def _get_tool_name(t):
                if hasattr(t, "name"):
                    return t.name
                if hasattr(t, "__name__"):
                    try:
                        t.name = t.__name__
                    except Exception:
                        pass
                    return getattr(t, "name", t.__name__)
                return str(t)

            if enable_parallel:
                self.llm = raw_llm.bind_tools(all_tools)
            else:
                try:
                    self.llm = raw_llm.bind_tools(all_tools, parallel_tool_calls=False)
                except Exception as bte:
                    logger.warning(f"Failed to bind tools with parallel_tool_calls=False, falling back to default: {bte}")
                    self.llm = raw_llm.bind_tools(all_tools)
            self.tools_map = {_get_tool_name(t): t for t in all_tools}

            logger.info(f"Agent LLM Initialized. Active Tools: {list(self.tools_map.keys())}")

            # Hydrate system state (inbox, de-dup IDs) after potential initialization
            self._hydrate_system_state()
            # Check if we should send a first-time welcome message
            await self._check_first_run_welcome()

        except Exception as e:
            logger.error(f"Failed to initialize Agent LLM: {e}")

        return self.status

    async def _check_first_run_welcome(self):
        """Check if this is the first run and send a welcome message if so."""
        if not getattr(self, "enable_welcome", True):
            return

        # Check if any chat history exists with the resident via long-term memory
        chat_history = self.resident_memory.get_all_history()
        # Filter for actual chat messages (excluding metadata)
        actual_messages = [m for m in chat_history if m.get("_type") != "metadata"]

        if not actual_messages:
            logger.info(
                "First-run Detection: No resident history found. Sending welcome message..."
            )
            await self._send_welcome_message()

    async def _send_welcome_message(self):
        """Send a built-in professional introduction to the resident."""
        welcome_text = (
            "您好！我是您的 AI 控制塔（Bit-Politeia 智能体）。很高兴能为您服务。\n\n"
            "作为一个去中心化治理系统的核心，我可以协助您：\n"
            "1. 🔍 追踪科研动态与文献评价\n"
            "2. 🗳️ 参与社区提案投票与治理\n"
            "3. 💰 管理您的社区资产与声誉\n\n"
            "您可以随时向我咨询系统运行状态或下达管理指令。让我们开始构建更加智能和公正的社区吧！"
        )

        logger.info("First-run detected for resident session. Sending welcome greeting...")

        # 1. Create and log to history
        welcome_id = str(uuid.uuid4())
        welcome_msg = Message(
            id=welcome_id,
            content=welcome_text,
            sender="agent",
            timestamp=datetime.now(UTC),
            session_id="resident",
            msg_type="chat",
        )
        self.history.append(welcome_msg)
        self._notify_observers()

        # 2. Log to persistent episodic memory (ResidentMemory)
        self.resident_memory.log_interaction(
            sender="agent",
            content=welcome_text,
            msg_type="chat",
            session_id="resident",
            msg_id=welcome_id,
        )

        # 3. Publish to Gateway so it shows up in UI immediately
        await self.message_bus.publish_outbound(
            OutboundMessage(
                channel="gateway",
                session_id="resident",
                content=welcome_text,
                type="chat",
                sender="agent",
                timestamp=welcome_msg.timestamp,
            )
        )

    # ... (process_message, etc.) ...

    def load_config_from_env(self):
        """方案A: 所有配置统一从 .env 读取"""
        from ..utils.env_utils import load_dotenv_safe

        load_dotenv_safe()
        import os

        # 所有配置都从环境变量读取
        base_url = os.getenv("AGENT_BASE_URL")
        api_key = os.getenv("AGENT_API_KEY")
        model = os.getenv("AGENT_MODEL", "gpt-4o")
        bootstrap_url = os.getenv("AGENT_BOOTSTRAP_URL", "https://bootstrap.bitpoliteia.com")
        bootstrap_verify = os.getenv("AGENT_BOOTSTRAP_VERIFY", "true").lower() == "true"
        
        # 身份和行为配置
        name = os.getenv("AGENT_NAME", "Agent")
        personality = os.getenv("AGENT_PERSONALITY", "Professional, helpful, and humorous")
        research_field = os.getenv("AGENT_RESEARCH_FIELD", "AI Governance")
        p2p_reply_delay = int(os.getenv("AGENT_P2P_REPLY_DELAY", "5"))
        p2p_cooldown_seconds = int(os.getenv("AGENT_P2P_COOLDOWN_SECONDS", "300"))
        agent_language = os.getenv("AGENT_LANGUAGE", "中文")
        ralph_wiggum_mode = os.getenv("AGENT_RALPH_WIGGUM_MODE", "false").lower() == "true"
        llm_timeout = max(180.0, float(os.getenv("AGENT_LLM_TIMEOUT", "180.0")))
        verbose_llm = os.getenv("AGENT_VERBOSE_LLM", "true").lower() == "true"
        self.enable_welcome = os.getenv("AGENT_ENABLE_WELCOME", "true").lower() == "true"

        if base_url and api_key:
            return {
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
                "research_field": research_field,
                "bootstrap_url": bootstrap_url,
                "verbose_llm": verbose_llm,
                "bootstrap_verify": bootstrap_verify,
                "name": name,
                "personality": personality,
                "p2p_reply_delay": p2p_reply_delay,
                "p2p_cooldown_seconds": p2p_cooldown_seconds,
                "agent_language": agent_language,
                "ralph_wiggum_mode": ralph_wiggum_mode,
                "llm_timeout": llm_timeout,
            }
        return None

    # Financial Methods
    # Concurrency lock for ledger operations to prevent race conditions
    _ledger_lock = asyncio.Lock()

    async def transfer_funds(
        self,
        payee_id: str,
        amount: float,
        details: str,
        category: str = "TRANSFER",
        context_id: str = None,
        payer_id: str = None,
    ) -> str:
        if not self.ledger:
            return "Ledger not initialized"

        # === PAYEE VALIDATION ===
        if not payee_id or not isinstance(payee_id, str):
            logger.warning(f"Transfer rejected: invalid payee_id '{payee_id}'")
            return "Transfer failed: invalid payee_id. Must be a non-empty string."
        
        payee_stripped = payee_id.strip()
        if not payee_stripped:
            logger.warning("Transfer rejected: empty payee_id after stripping whitespace")
            return "Transfer failed: payee_id cannot be empty."
        
        if payee_stripped.lower() == "system":
            logger.warning(f"Transfer rejected: cannot transfer to 'system' account")
            return "Transfer failed: cannot transfer to 'system' account."
        
        # Validate payee exists in network (for P2P transfers, not system payouts)
        if payer_id != "system" and p2p_service._initialized and p2p_service.network_manager:
            if payee_stripped not in p2p_service.network_manager.nodes:
                logger.warning(f"Transfer rejected: payee '{payee_stripped[:8]}' not found in network topology")
                return f"Transfer failed: payee '{payee_stripped[:8]}' not found in network topology."

        # === REWARD AMOUNT VALIDATION ===
        if amount <= 0:
            logger.warning(f"Transfer rejected: invalid amount {amount} (must be positive)")
            return f"Transfer failed: invalid amount {amount}. Amount must be positive."
        
        if amount > 10000:
            logger.warning(f"Transfer rejected: amount {amount} exceeds maximum limit 10000")
            return f"Transfer failed: amount {amount} exceeds maximum limit 10000."

        if not payer_id:
            payer_id = self.governance_manager.node_id if self.governance_manager else "unknown"

        # === CONCURRENT LEDGER ACCESS PROTECTION ===
        async with self._ledger_lock:
            # === RETRY TRACKING FOR GOVERNANCE PAYOUTS ===
            if self.governance_manager and context_id:
                election = self.governance_manager.finished_elections.get(context_id)
                if election:
                    # Check max retry limit
                    if election.payout_attempts >= election.max_payout_attempts:
                        election.payout_status = "failed"
                        election.payout_error = f"Max retry attempts ({election.max_payout_attempts}) exceeded"
                        self.governance_manager.save_state()
                        logger.error(f"Payout for election {context_id[:8]} failed: max retries exceeded")
                        return f"Transfer failed: maximum retry attempts ({election.max_payout_attempts}) exceeded for this payout."
                    
                    # Increment attempt counter
                    election.payout_attempts += 1
                    election.payout_last_attempt = datetime.now(UTC)
                    logger.info(f"Payout attempt {election.payout_attempts}/{election.max_payout_attempts} for election {context_id[:8]}")

            tx = self.ledger.create_transaction(
                payer_id, payee_stripped, amount, details, category=category, context_id=context_id
            )

            if tx:
                # If this is a reward or governance payout linked to a finalized election, update its status
                if self.governance_manager and context_id:
                    if context_id in self.governance_manager.finished_elections:
                        election = self.governance_manager.finished_elections[context_id]
                        election.payout_status = "paid"
                        election.payout_error = None
                        self.governance_manager.save_state()
                        logger.info(f"Financial: Marked election {context_id} payout as paid.")
                return f"Transfer successful. TX ID: {tx.transaction_id}"
            else:
                if self.governance_manager and context_id:
                    if context_id in self.governance_manager.finished_elections:
                        election = self.governance_manager.finished_elections[context_id]
                        election.payout_status = "failed"
                        election.payout_error = "Transfer failed. Insufficient funds or invalid amount."
                        self.governance_manager.save_state()
                return "Transfer failed. Insufficient funds or invalid amount."

    async def execute_governance_payout(self, election_id: str, requester_id: str) -> str:
        """
        Execute a governance payout. ONLY core nodes can trigger this.
        
        This is the manual payout execution method that replaces the automatic
        payout trigger in check_governance_proposals().
        
        Args:
            election_id: The election ID to process payout for
            requester_id: The node ID requesting the payout (must be core node)
        
        Returns:
            Status message
        """
        if not self.governance_manager:
            return "Error: Governance Manager not initialized"
        
        if not p2p_service.local_node:
            return "Error: P2P node not initialized"
        
        # === CORE NODE PERMISSION CHECK ===
        is_core_node = False
        target_group_id = None
        
        election = self.governance_manager.finished_elections.get(election_id)
        if not election:
            return f"Error: Election {election_id} not found in finished elections."
        
        target_group_id = election.group_id
        
        # Check if requester is a core node of the group
        if target_group_id in p2p_service.local_node.network_manager.groups:
            group = p2p_service.local_node.network_manager.groups[target_group_id]
            if requester_id in group.core_node_ids:
                is_core_node = True
        
        if not is_core_node:
            logger.warning(f"Payout request denied: {requester_id[:8]} is not a core node of group {target_group_id[:8]}")
            return f"Error: Only core nodes can execute governance payouts. Node {requester_id[:8]} is not authorized."
        
        # === VALIDATE ELECTION PAYOUT STATUS ===
        if election.payout_status == "paid":
            return f"Payout already completed for election {election_id[:8]}."
        
        if election.payout_status == "failed" and election.payout_attempts >= election.max_payout_attempts:
            return f"Payout failed after {election.max_payout_attempts} attempts. Manual intervention required."
        
        if election.payout_status not in ["pending", "failed"]:
            return f"Election {election_id[:8]} payout status is '{election.payout_status}', not eligible for payout."
        
        # === VALIDATE REWARD AMOUNT ===
        payout_amount = election.payout_amount
        if payout_amount <= 0:
            election.payout_status = "no_reward"
            self.governance_manager.save_state()
            return f"No reward to distribute for election {election_id[:8]} (amount: {payout_amount})."
        
        # === EXECUTE PAYOUT ===
        tally = election.tally()
        recipient_id = election.initiator_id
        category = "REWARD" if election.election_type == ElectionType.RESEARCH_EVALUATION else "GOVERNANCE"
        details = f"Governance payout for {election.election_type.value} (election {election_id[:8]})"
        
        logger.info(f"Core node {requester_id[:8]} executing payout for election {election_id[:8]}: {payout_amount} stater to {recipient_id[:8]}")
        
        result = await self.transfer_funds(
            payee_id=recipient_id,
            amount=payout_amount,
            details=details,
            category=category,
            context_id=election_id,
            payer_id="system",
        )
        
        return result

    def _load_config(self) -> dict:
        """方案A: 从 .env 加载配置（兼容旧接口）"""
        from ..utils.env_utils import load_dotenv_safe
        load_dotenv_safe()
        import os
        
        # 从环境变量构建配置字典
        return {
            "name": os.getenv("AGENT_NAME", "Agent"),
            "personality": os.getenv("AGENT_PERSONALITY", "Professional, helpful, and humorous"),
            "research_field": os.getenv("AGENT_RESEARCH_FIELD", "AI Governance"),
            "bootstrap_url": os.getenv("AGENT_BOOTSTRAP_URL"),
            "bootstrap_verify": os.getenv("AGENT_BOOTSTRAP_VERIFY", "true").lower() == "true",
            "p2p_reply_delay": int(os.getenv("AGENT_P2P_REPLY_DELAY", "5")),
            "p2p_cooldown_seconds": int(os.getenv("AGENT_P2P_COOLDOWN_SECONDS", "300")),
            "agent_language": os.getenv("AGENT_LANGUAGE", "中文"),
            "ralph_wiggum_mode": os.getenv("AGENT_RALPH_WIGGUM_MODE", "false").lower() == "true",
            "verbose_llm": os.getenv("AGENT_VERBOSE_LLM", "true").lower() == "true",
            "llm_timeout": float(os.getenv("AGENT_LLM_TIMEOUT", "180.0")),
        }

    def _save_config(self, config: dict):
        """方案A: 保存配置到 .env（替代 JSON）"""
        try:
            from dotenv import set_key
            import os
            
            # 确保 .env 文件存在
            env_path = self.env_file
            if not os.path.exists(env_path):
                with open(env_path, "w") as f:
                    f.write("# Bit-Politeia Agent Configuration\n")
            
            # 映射配置键到环境变量
            key_mapping = {
                "name": "AGENT_NAME",
                "personality": "AGENT_PERSONALITY",
                "research_field": "AGENT_RESEARCH_FIELD",
                "bootstrap_url": "AGENT_BOOTSTRAP_URL",
                "bootstrap_verify": "AGENT_BOOTSTRAP_VERIFY",
                "p2p_reply_delay": "AGENT_P2P_REPLY_DELAY",
                "agent_language": "AGENT_LANGUAGE",
                "ralph_wiggum_mode": "AGENT_RALPH_WIGGUM_MODE",
                "verbose_llm": "AGENT_VERBOSE_LLM",
                "llm_timeout": "AGENT_LLM_TIMEOUT",
            }
            
            for config_key, env_key in key_mapping.items():
                if config_key in config:
                    value = config[config_key]
                    # 转换为字符串
                    if isinstance(value, bool):
                        value = "true" if value else "false"
                    else:
                        value = str(value)
                    set_key(str(env_path), env_key, value)
            
            logger.info(f"Configuration saved to {env_path}")
        except Exception as e:
            logger.error(f"Failed to save config to .env: {e}")

    async def _on_transaction_completed(self, event_type: str, transaction_data: dict):
        """Handle transaction completion events.
        
        This method is called by the Ledger when a transaction is successfully recorded.
        It broadcasts the event to the message bus for UI updates and audit logging.
        
        Args:
            event_type: Type of event (e.g., "transaction.completed")
            transaction_data: Transaction details as dict
        """
        try:
            # Broadcast to Gateway for UI updates
            await self.message_bus.publish_outbound(
                OutboundMessage(
                    channel="gateway",
                    session_id="transactions",
                    content=f"Transaction {transaction_data.get('transaction_id', '')[:8]} completed: "
                            f"{transaction_data.get('amount', 0)} stater from "
                            f"{transaction_data.get('payer_id', '')[:8]} to "
                            f"{transaction_data.get('payee_id', '')[:8]}",
                    type="transaction",
                    metadata=transaction_data,
                )
            )
            logger.info(f"Transaction event broadcast: {event_type} - {transaction_data.get('transaction_id', '')[:8]}")
        except Exception as e:
            logger.warning(f"Failed to broadcast transaction event: {e}")

    async def get_balance(self) -> float:
        if self.ledger and p2p_service.local_node:
            node_id = p2p_service.local_node.node_id
            balance = self.ledger.get_balance(node_id)
            logger.info(f"Retrieving Balance for UUID {node_id[:8]}: {balance}")
            return balance

        if self.ledger and self.governance_manager:
            node_id = self.governance_manager.node_id
            balance = self.ledger.get_balance(node_id)
            logger.info(f"Retrieving Balance for PubKey {node_id[:8]}: {balance} (Fallback)")
            return balance

        return 0.0

    async def run_pipeline(self, msg: InboundMessage) -> tuple[str, bool, str]:
        """Execute the 6-stage pipeline for an inbound message."""
        from ..agent.pipeline import (
            ArchiveStage,
            ConsolidateStage,
            ExecuteStage,
            NotifyStage,
            PipelineContext,
            PlanStage,
            RetrospectiveStage,
            SenseStage,
        )
        from ..services.session_service import session_manager

        # 0. Check Initialization State
        if not self.context_manager or not self.llm:
            logger.warning(f"Pipeline triggered while agent is still initializing. msg={msg.content[:50]}")
            return "智能体正在初始化配置中，请稍后再试...", False, "INITIALIZING"

        # 0. Get or Create Session
        session = session_manager.get_session(msg.sender_id, msg.channel)

        # [ICE WARMUP] Start handshake in background during reasoning/delay
        if msg.sender_id and msg.channel == "p2p":
            asyncio.create_task(p2p_service.warmup_webrtc(msg.sender_id))

        # Refactored P2P Delay: Move delay to cognitive layer (Pipeline Start)
        delay_val = getattr(self, "p2p_reply_delay", 60)

        if msg.channel == "p2p" and delay_val > 0:
            # Calculate remaining delay relative to message timestamp
            # This ensures that the total delay is consistent regardless of transit time.
            now = datetime.now(UTC)
            # Ensure msg.timestamp is offset-aware for comparison
            msg_ts = msg.timestamp
            if msg_ts.tzinfo is None:
                msg_ts = msg_ts.replace(tzinfo=UTC)
                
            target_time = msg_ts + timedelta(seconds=delay_val)
            remaining_seconds = (target_time - now).total_seconds()

            if remaining_seconds > 0:
                # 1. Notify Gateway that we are thinking (so UI shows status)
                ui_session_id = self._normalize_session_id(msg.session_id)
                await self.message_bus.publish_outbound(
                    OutboundMessage(
                        channel="gateway",
                        session_id=ui_session_id,
                        content=f"... (Finalizing research... {int(remaining_seconds)}s remaining) ...",
                        type="thought",
                    )
                )
                await asyncio.sleep(remaining_seconds)
        
        context = PipelineContext(session=session, input_message=msg)
        self.active_pipelines[session.session_id] = context

        try:
            stages = [
                SenseStage(),
                PlanStage(),
                ExecuteStage(),
                ConsolidateStage(),
                RetrospectiveStage(),
                NotifyStage(),
                ArchiveStage(),
            ]

            logger.info(
                f"Starting pipeline execution for user {msg.sender_id} (Session: {session.session_id})"
            )

            # 1. Preliminary Stage: Sense
            await stages[0].run(context, self)

            # 2. Main Loop: Plan & Execute (ReAct)
            max_iterations = 50
            iteration = 0
            while not context.stop_execution and iteration < max_iterations:
                iteration += 1

                # --- Micro-compact context before planning to prevent context explosion ---
                if "messages" in context.metadata and self.context_manager:
                    self.context_manager.apply_micro_compaction(context.metadata["messages"])

                await stages[1].run(context, self)  # Plan
                if not context.stop_execution:
                    await stages[2].run(context, self)  # Execute

            # 3. Wrapping Up: Consolidate, Retrospective, Notify, Archive
            await stages[3].run(context, self)  # Consolidate
            session_manager.save_session(context.session)  # Save intermediate
            await stages[4].run(context, self)  # Retrospective
            await stages[5].run(context, self)  # Notify
            await stages[6].run(context, self)  # Archive
            session_manager.save_session(context.session)  # Final save
        finally:
            self.active_pipelines.pop(session.session_id, None)

        if iteration >= max_iterations:
            logger.warning(
                f"Pipeline hit max iterations ({max_iterations}) for session {context.session.session_id}"
            )
            return (
                (
                    context.final_answer
                    or f"ReAct Loop Timeout: The agent reached its maximum reasoning limit ({max_iterations} steps) without concluding a final answer. Please break down your request."
                ),
                True,
                "MAX_ITERATIONS",
            )

        final_ans = context.final_answer
        if not final_ans and context.thoughts:
            final_ans = f"【执行总结】\n{context.thoughts[-1]}"

        return (
            (final_ans or "智能体已接收指令并完成分析，未产生额外的文本回复。"),
            context.continuation_req,
            context.continuation_reason,
        )

    async def _run_ralph_wiggum_loop(self, msg: InboundMessage) -> tuple[str, bool, str]:
        current_msg = msg
        max_epochs = 5
        epoch = 0
        final_response = ""
        last_cont_req = False
        last_cont_reason = ""

        while epoch < max_epochs:
            epoch += 1
            response_text, cont_req, cont_reason = await self.run_pipeline(current_msg)
            final_response = response_text
            last_cont_req = cont_req
            last_cont_reason = cont_reason

            if not getattr(self, "ralph_wiggum_mode", False) or not cont_req:
                return response_text, cont_req, cont_reason

            logger.warning(
                f"Ralph Wiggum Mode: Triggering Epoch {epoch + 1}/{max_epochs} for {msg.session_id} due to {cont_reason}"
            )

            # Send status update to Gateway so user sees it's auto-recovering
            await self.message_bus.publish_outbound(
                OutboundMessage(
                    channel="gateway",
                    session_id=msg.sender_id,
                    content=f"[Ralph Wiggum Auto-Heal Activated] Re-initiating loop {epoch + 1}/{max_epochs} due to: {cont_reason}",
                    type="thought",
                )
            )

            # Compress context or inject error message to heal
            if cont_reason == "MAX_ITERATIONS":
                prompt = "System Control: You hit the 50-step execution limit. Summarize your current progress over the last 50 steps, clarify what is missing, and state your next tool call to continue."
                meta = {"epoch": epoch}
            else:
                # Detect token/length errors to trigger force compression
                is_token_error = any(kw in cont_reason.lower() for kw in ["token", "length", "202745", "260096", "context_length_exceeded", "algo.invalidparameter", "token_length_exceeded"])
                meta = {"epoch": epoch, "force_compact": is_token_error}
                prompt = f"System Control: Execution interrupted by API Error: {cont_reason}. Diagnose the issue, drop redundant context if it was a token length error, and adjust your strategy before continuing."

            # Create a synthetic inbound message to re-trigger the loop
            current_msg = InboundMessage(
                channel=msg.channel,
                sender_id="system",
                session_id=msg.session_id,
                content=prompt,
                metadata=meta,
            )

        return final_response, last_cont_req, "MAX_EPOCHS_REACHED"

    async def _think_and_act(self, context: str, source: str) -> str:
        """Core Agent Logic: Perceive -> Think -> Act (ReAct Loop)"""
        if not self.llm:
            return "LLM not configured."

        try:
            # 1. Prepare Messages using ContextBuilder
            # Retrieve RAG Context
            rag_context = knowledge_base.search_web_and_context(context)

            # Retrieve P2P Network Context
            my_id = p2p_service.local_node.node_id if p2p_service.local_node else "unknown"
            my_groups = list(p2p_service.local_node.group_ids) if p2p_service.local_node else []
            network_identity = f"- Node ID: {my_id}\n- My Groups: {my_groups}\n- My Monitoring Research Focus: {self.research_field}"

            # Build initial messages

            # 1.1 Convert recent history (last 10 messages) to LangChain format

            # Determine effective history (exclude current message if it's already in history)
            # We use a while loop to remove ALL immediate repetitions of the current query from the tail of history
            # This solves the issue where the user asks "What did I ask?" multiple times and the agent quotes the previous "What did I ask?".
            effective_history = self.history[:]
            while effective_history and effective_history[-1].content == context:
                effective_history.pop()

            recent_history = effective_history[-10:] if effective_history else []
            lc_history = []
            for msg in recent_history:
                if msg.sender == "agent":
                    # Include status for agent's own messages to perceive delivery state
                    status_prefix = (
                        f"[STATUS: {msg.status.upper()}] "
                        if msg.status and msg.status in ["pending", "failed"]
                        else ""
                    )
                    lc_history.append(AIMessage(content=f"{status_prefix}{msg.content}"))
                else:
                    lc_history.append(HumanMessage(content=f"[{msg.sender}] {msg.content}"))

            messages = self.context_builder.build_messages(
                history=lc_history,
                current_message=context,
                rag_context=rag_context,
                network_identity=network_identity,
                source=source,
                name=self.name,
                personality=self.personality,
                agent_language=self.agent_language,
            )

            # 2. ReAct Loop
            max_iterations = 50
            iteration = 0
            final_content = None

            while iteration < max_iterations:
                iteration += 1

                # Invoke LLM
                response = await self.llm.ainvoke(messages)

                # Extract Reasoning
                thought_content = ""
                if "reasoning_content" in response.additional_kwargs:
                    thought_content = response.additional_kwargs["reasoning_content"]
                elif hasattr(response, "reasoning_content") and response.reasoning_content:
                    thought_content = response.reasoning_content
                elif response.tool_calls and response.content:
                    thought_content = response.content

                if self.verbose_llm:
                    logger.info(
                        f"\n[AGENTS] Iteration {iteration} Response Content:\n{response.content}"
                    )
                    if thought_content:
                        logger.info(f"[AGENTS] Iteration {iteration} Reasoning:\n{thought_content}")
                    logger.info("-" * 50)

                # Emit Thought to Bus
                if thought_content or response.content:
                    display_thought = thought_content or response.content
                    logger.info(f"Agent Thought: {str(display_thought)[:200]}...")
                    thought_msg = OutboundMessage(
                        channel="gateway",
                        session_id="global",
                        content=str(display_thought),
                        type="thought",
                    )
                    await self.message_bus.publish_outbound(thought_msg)

                # Check for Tool Calls
                if response.tool_calls:
                    messages.append(response)  # Add AIMessage with tool_calls

                    # Execute Tools
                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        args = tool_call["args"]
                        tool_call_id = tool_call["id"]

                        # Emit Tool Call Event
                        await self.message_bus.publish_outbound(
                            OutboundMessage(
                                channel="gateway",
                                session_id="global",
                                content=f"Invoking {tool_name} with {args}",
                                type="tool_call",
                                metadata={"tool": tool_name, "args": args},
                            )
                        )

                        if tool_name in self.tools_map:
                            logger.info(f"Agent Invoking Tool: {tool_name} with {args}")
                            tool_func = self.tools_map[tool_name]
                            session_id = getattr(self, "current_session_id", "default_session")

                            # 1. Log tool/call event in SessionEventLog
                            session_event_log.append_event(
                                session_id,
                                "tool/call",
                                {"tool_name": tool_name, "args": args, "call_id": tool_call_id},
                            )

                            # 2. Waterfall pre_execute hook (Security policy & validation)
                            waterfall_ctx = {"session_id": session_id, "call_id": tool_call_id}
                            pre_res = await waterfall_pipeline.run_pre_execute(tool_name, args, waterfall_ctx)

                            if not pre_res.get("allow", True):
                                tool_output = f"Execution Blocked by Security Policy: {pre_res.get('reason', 'Security Policy Rejection')}"
                            else:
                                try:
                                    tool_output = await tool_func.ainvoke(args)
                                except Exception as te:
                                    tool_output = f"Error: {te}"

                            # Self-Improvement Error Detector Hook
                            error_patterns = [
                                "error:",
                                "Error:",
                                "ERROR:",
                                "failed",
                                "FAILED",
                                "command not found",
                                "No such file",
                                "Permission denied",
                                "fatal:",
                                "Exception",
                                "Traceback",
                                "npm ERR!",
                                "ModuleNotFoundError",
                                "SyntaxError",
                                "TypeError",
                                "exit code",
                                "non-zero",
                            ]

                            output_str = str(tool_output)
                            contains_error = any(
                                pattern in output_str for pattern in error_patterns
                            )
                            if contains_error:
                                error_hook = """
<error-detected>
A command error was detected. Consider logging this to .learnings/ERRORS.md if:
- The error was unexpected or non-obvious
- It required investigation to resolve
- It might recur in similar contexts
- The solution could benefit future sessions

Use the self-improvement skill format: [ERR-YYYYMMDD-XXX]
</error-detected>"""
                                output_str += error_hook

                            # 3. Waterfall post_execute hook (SpillStore automatic offload & trimming)
                            output_str = await waterfall_pipeline.run_post_execute(
                                tool_name, args, output_str, waterfall_ctx
                            )

                            # 4. Log tool/result event in SessionEventLog
                            session_event_log.append_event(
                                session_id,
                                "tool/result",
                                {"tool_name": tool_name, "content": output_str[:1000], "call_id": tool_call_id},
                            )

                            messages.append(
                                ToolMessage(
                                    tool_call_id=tool_call_id, content=output_str, name=tool_name
                                )
                            )

                            # Emit Tool Result Event
                            out_msg = OutboundMessage(
                                channel="gateway",
                                session_id="global",
                                content=f"Result: {output_str[:200]}...",
                                type="tool_result",
                                metadata={"tool": tool_name, "result": output_str},
                            )
                            # print(f"[DEBUG-AG] Publishing Tool Result: {tool_name}")
                            await self.message_bus.publish_outbound(out_msg)

                        else:
                            messages.append(
                                ToolMessage(
                                    tool_call_id=tool_call_id,
                                    content=f"Error: Tool {tool_name} not found",
                                    name=tool_name,
                                )
                            )

                    # Continue loop to let LLM process tool outputs
                    continue
                else:
                    # No tool calls, this is the final response
                    final_content = response.content
                    logger.info(
                        f"Agent Final Response (to {source}): {str(final_content)[:200]}..."
                    )
                    break

            # Fallback if loop limitation reached
            if final_content is None:
                final_content = "I reached my thought limit effectively. " + (
                    response.content if response else ""
                )

            return final_content

        except Exception as e:
            logger.error(f"Agent Logic Error: {e}")
            return f"Error processing message: {e}"

    async def listen_to_bus(self):
        """Background task to consume messages from the bus."""
        logger.info("Agent listening to Message Bus...")
        while True:
            try:
                msg: InboundMessage = await self.message_bus.consume_inbound()
                await self.process_bus_message(msg)
            except Exception as e:
                logger.error(f"Error in bus listener: {e}")
                await asyncio.sleep(1)

    async def process_bus_message(self, msg: InboundMessage):
        """Process an inbound message from a channel."""
        # 1. Log to history (Frontend Sync)
        # Standardize ID: P2P messages use Hex ID consistently
        raw_session_id = self._normalize_session_id(msg.session_id, channel=msg.channel)
        formatted_sender = msg.sender_id  # Default

        # Identity Normalization for History
        history_session_id = raw_session_id
        if msg.channel == "p2p":
            # Try to find name for sender formatting
            if p2p_service._initialized:
                node = p2p_service.network_manager.nodes.get(msg.sender_id)
                if node and node.name:
                    formatted_sender = node.name
        elif msg.channel != "resident":
            # Other channels keep prefix for now (Legacy)
            history_session_id = f"[{msg.channel}] {raw_session_id}"
            formatted_sender = f"[{msg.channel}] {msg.sender_id}"
            # Update Resident Bridges registry for proactive notifications
            self.resident_bridges[msg.channel] = raw_session_id
            self._save_system_state()

        # Use original timestamp if available in metadata
        msg_ts = msg.metadata.get("timestamp")
        original_ts = None
        try:
            if isinstance(msg_ts, str):
                msg_ts = datetime.fromisoformat(msg_ts)
                if msg_ts.tzinfo is None:
                    msg_ts = msg_ts.replace(tzinfo=UTC)
                original_ts = msg_ts
            elif not msg_ts:
                msg_ts = datetime.now(UTC)
            else:
                # Ensure existing datetime object is aware
                if hasattr(msg_ts, "tzinfo") and msg_ts.tzinfo is None:
                    msg_ts = msg_ts.replace(tzinfo=UTC)
                original_ts = msg_ts
        except:
            msg_ts = datetime.now(UTC)

        # Calculate and log delivery latency
        if original_ts:
            try:
                # Ensure UTC for comparison
                calc_ts = original_ts
                if calc_ts.tzinfo is None:
                    calc_ts = calc_ts.replace(tzinfo=UTC)
                latency = (datetime.now(UTC) - calc_ts).total_seconds()
                logger.info(
                    f"P2P Latency: Receiving message {msg.metadata.get('message_id')} from {msg.sender_id} via {msg.channel}. Latency: {latency:.3f}s"
                )
            except Exception as le:
                logger.debug(f"Could not calculate latency: {le}")

        user_msg_obj = Message(
            id=msg.metadata.get("message_id") or str(uuid.uuid4()),
            content=msg.content,
            sender=formatted_sender,
            timestamp=msg_ts,
            session_id=history_session_id,
            msg_type="chat",
        )
        self.history.append(user_msg_obj)
        self.resident_memory.log_interaction(
            formatted_sender,
            msg.content,
            msg_type="chat",
            session_id=history_session_id,
            timestamp=msg_ts,
            msg_id=msg.metadata.get("message_id"),
        )

        # 1.5 DUAL BROADCAST: Inform Gateway of inbound P2P message
        if msg.channel == "p2p":
            await self.message_bus.publish_outbound(
                OutboundMessage(
                    channel="gateway",
                    session_id=history_session_id,
                    content=msg.content,
                    sender=formatted_sender,
                    type="chat",
                )
            )

        # 1.7 Loop Prevention: Check for pure acknowledgment/status confirmations
        if msg.channel == "p2p":
            text_content = msg.content
            if isinstance(text_content, dict) and "text" in text_content:
                text_content = text_content["text"]
            elif not isinstance(text_content, str):
                text_content = str(text_content)

            if await self.is_pure_acknowledgment(text_content):
                logger.info(
                    f"Loop prevention (Bus): message from {msg.sender_id} is a pure acknowledgment/status confirmation. Storing in history without triggering LLM pipeline."
                )
                s_id_short = msg.sender_id[:8] if msg.sender_id else "unknown"
                await self.message_bus.publish_outbound(
                    OutboundMessage(
                        channel="gateway",
                        session_id=history_session_id,
                        content=f"Loop prevention: received pure acknowledgment/status confirmation from {s_id_short}. Stored in history without auto-processing.",
                        type="thought",
                    )
                )
                return

        # 2. Pipeline Execution
        # p2p_logger.info(f"DEBUG: process_bus_message calling run_pipeline. Channel={msg.channel}, Sender={msg.sender_id}")
        response_text, cont_req, cont_reason = await self._run_ralph_wiggum_loop(msg)

        # 3. Reply via Bus
        reply_id = str(uuid.uuid4())
        is_internal_report = False

        if response_text and "[NO_RESPONSE_NEEDED]" in str(response_text):
            logger.info(
                f"P2P Logic: Conversation terminated by agent via [NO_RESPONSE_NEEDED] for session_id={raw_session_id}"
            )
            is_internal_report = True
        elif (
            response_text
            and str(response_text).strip()
            and response_text != "No response generated."
        ):
            target_transport_id = msg.metadata.get("original_session_id") or msg.session_id
            out_msg = OutboundMessage(
                channel=msg.channel,
                session_id=target_transport_id,  # Must use RAW platform ID for transport (e.g. oc_xxx for Feishu)
                content=response_text,
                reply_to=msg.metadata.get("message_id"),
                metadata={"message_id": reply_id, "original_session_id": target_transport_id},
                is_final=True,  # Mark as final response for channel filtering
            )
            await self.message_bus.publish_outbound(out_msg)

            # 3.5 DUAL BROADCAST: Push Agent response to Gateway immediately
            if msg.channel == "p2p":
                await self.message_bus.publish_outbound(
                    OutboundMessage(
                        channel="gateway",
                        session_id=history_session_id,
                        content=response_text,
                        type="chat",
                        metadata={"message_id": reply_id},
                    )
                )

        # 4. Log Reply to history
        target_session = "resident" if is_internal_report else history_session_id
        target_status = None if is_internal_report else "sent"

        agent_msg_obj = Message(
            id=reply_id,
            content=response_text,
            sender="agent",
            timestamp=datetime.now(UTC),
            session_id=target_session,
            status=target_status,
        )
        self.history.append(agent_msg_obj)
        self.resident_memory.log_interaction(
            "agent", response_text, msg_type="chat", session_id=target_session, status=target_status
        )

        # Periodic trim: prevent in-memory history from growing unbounded
        self._trim_in_memory_history()

    async def notify_resident(
        self,
        content: str,
        type: str = "agent_message",
        session_id: str = None,
        broadcast: bool = True,
        media: list = None,
    ):
        """
        Notify the resident.
        If broadcast=True, sends to all known bridges (Feishu, etc.).
        If broadcast=False, only sends to local Gateway (Web UI).
        """
        if session_id is None or session_id == "resident":
            session_id = identity_manager.resolve_unified_id("resident", "resident")

        logger.info(f"Notifying resident (broadcast={broadcast}): {content[:50]}...")

        # 1. Log to history (Web UI)
        msg_id = str(uuid.uuid4())
        self.history.append(
            Message(
                id=msg_id,
                content=content,
                sender="agent",
                timestamp=datetime.now(UTC),
                session_id=session_id,
                status="resident_only",  # Prevents P2P retry scheduler from picking this up
            )
        )
        self.resident_memory.log_interaction(
            "agent", content, msg_type="chat", session_id=session_id
        )

        # 2. Broadcast or Targeted Send
        if broadcast:
            bridges_to_notify = self.resident_bridges.copy()
            if "gateway" not in bridges_to_notify:
                bridges_to_notify["gateway"] = "global"
            # Fallback: If feishu is not yet recorded in resident_bridges, check identity_manager for any known feishu session ID
            if "feishu" not in bridges_to_notify:
                try:
                    for k, v in identity_manager.identity_map.items():
                        if k.startswith("feishu:") and v == "resident":
                            raw_feishu_id = k.split("feishu:", 1)[1]
                            bridges_to_notify["feishu"] = raw_feishu_id
                            self.resident_bridges["feishu"] = raw_feishu_id
                            break
                    if "feishu" not in bridges_to_notify:
                        default_feishu_id = os.getenv("FEISHU_DEFAULT_CHAT_ID") or os.getenv("FEISHU_DEFAULT_RECEIVE_ID")
                        if default_feishu_id:
                            bridges_to_notify["feishu"] = default_feishu_id
                            self.resident_bridges["feishu"] = default_feishu_id
                except Exception as fe_err:
                    logger.debug(f"Feishu fallback lookup error: {fe_err}")
        else:
            # Only send to Gateway (Web UI)
            bridges_to_notify = {"gateway": "global"}

        for channel, cid in bridges_to_notify.items():
            try:
                out_msg = OutboundMessage(
                    channel=channel, session_id=cid, content=content, type=type, media=media or []
                )
                await self.message_bus.publish_outbound(out_msg)
                logger.debug(f"Proactive notification sent via {channel}")
            except Exception as e:
                logger.error(f"Failed to send proactive notification via {channel}: {e}")

    # 1. User Contact
    async def process_user_instruction(self, content: str, broadcast: bool = False) -> Message:
        # 1. Standardize Session ID
        session_id = identity_manager.resolve_unified_id("resident", "resident")
        msg_id = str(uuid.uuid4())

        # 1. Log User Message
        user_msg = Message(
            id=msg_id,
            content=content,
            sender="resident",
            timestamp=datetime.now(UTC),
            session_id=session_id,
        )
        self.history.append(user_msg)
        self.resident_memory.log_interaction(
            "resident", content, msg_type="chat", session_id=session_id
        )  # Log to private memory

        # 2. Agent response via Pipeline
        msg_obj = InboundMessage(
            channel="resident", sender_id="resident", content=content, session_id=session_id
        )
        # Pass through the pipeline with Ralph Wiggum loop wrapping
        response_text, _, _ = await self._run_ralph_wiggum_loop(msg_obj)

        # 3. Notify Resident (Targeted or Broadcast depending on caller)
        await self.notify_resident(response_text, session_id=session_id, broadcast=broadcast)

        # Return the last Message object from history
        return self.history[-1] if self.history else None

    async def steer_session(self, session_id: str, action: str, instruction: str = "") -> dict[str, Any]:
        """
        In-flight steering endpoint helper (/steer).
        Interprets steering or cancellation signals for an active or new pipeline session.
        """
        norm_session_id = self._normalize_session_id(session_id)

        matched_ctx = None
        for sid, ctx in self.active_pipelines.items():
            if sid == session_id or sid == norm_session_id or self._normalize_session_id(sid) == norm_session_id:
                matched_ctx = ctx
                break

        if matched_ctx:
            if action.lower() == "cancel":
                matched_ctx.stop_execution = True
                logger.info(f"Steer: Session {session_id} cancelled by user.")
                return {"success": True, "status": "cancelled", "message": "已成功取消当前任务"}
            else:
                matched_ctx.steer_instructions.append(instruction)
                matched_ctx.steering_flag = True
                logger.info(f"Steer: Injected steering directive to session {session_id}: {instruction}")
                return {"success": True, "status": "steered", "message": "已注入行中纠偏指令，智能体正在调整策略..."}
        else:
            if action.lower() == "steer" and instruction:
                asyncio.create_task(self.process_user_instruction(instruction))
                return {"success": True, "status": "idle_routed", "message": "智能体当前处于空闲状态，打断指令已作为新对话接收"}
            return {"success": False, "status": "no_active_session", "message": "当前会话没有正在运行中的任务"}

    # 2. Community Contact (P2P Listener)
    async def process_network_inbox(self, verbose: bool = False):
        """Poll P2P inbox and process messages."""
        if verbose:
            logger.info("Checking P2P inbox...")

        import base64
        import os

        if not p2p_service.local_node:
            return

        if self._is_processing_inbox:
            logger.debug("process_network_inbox already running, skipping overlapping poll.")
            return

        self._is_processing_inbox = True
        try:
            # Robust Hydration: If memory inbox is empty, check if we need to load from disk
            if not p2p_service.local_node.inbox:
                self._hydrate_system_state()

            inbox = p2p_service.local_node.inbox
            while inbox:
                msg = inbox.pop(0)

                if not isinstance(msg, dict):
                    logger.warning(f"Malformed P2P message discarded (not a dict): {msg}")
                    continue

                try:
                    sender_id = msg.get("sender_id")
                    content = msg.get("content")
                    msg_type = msg.get("message_type", msg.get("type"))

                    # Filter out system messages that are handled elsewhere (e.g., in handle_p2p_message)
                    if msg_type == "SYSTEM_ERROR":
                        continue

                    receive_time = datetime.now(UTC).timestamp()
                    # 1. De-duplication
                    m_id = msg.get("message_id")
                    if m_id:
                        if m_id in self.processed_message_ids:
                            continue
                        self.processed_message_ids.add(m_id)

                    # Normalize Sender ID (Hex ID)
                    sender_id = self._normalize_session_id(sender_id) or "unknown_sender"

                    # 1.1 Self-Message Filtering
                    if p2p_service.local_node and sender_id == p2p_service.local_node.node_id:
                        logger.debug(f"Skipping self-received P2P message {m_id}")
                        continue

                    # [ICE WARMUP] Proactively initiate WebRTC if message is direct
                    if sender_id and sender_id != "unknown_sender":
                        asyncio.create_task(p2p_service.warmup_webrtc(sender_id))

                    # 1.2 Identify Message Nature (Refactored)
                    raw_type = str(msg.get("message_type", msg.get("type", ""))).lower()

                    # Package Type: What is being sent? (chat, file, gossip, error)
                    package_type = "chat"
                    if raw_type == "file" or (isinstance(content, dict) and "data" in content):
                        package_type = "file"
                    elif raw_type == "gossip":
                        package_type = "gossip"
                    elif raw_type == "system_error":
                        package_type = "error"

                    # Recipient Type: How is it addressed? (direct, group)
                    recipient_id = self._normalize_session_id(msg.get("recipient_id"))
                    recipient_type = "direct"
                    if raw_type == "group":
                        recipient_type = "group"
                    elif recipient_id and p2p_service.local_node:
                        if recipient_id in p2p_service.local_node.group_ids:
                            recipient_type = "group"

                    # Process based on type
                    sender_display = sender_id[:8] if sender_id else "unknown"
                    logger.info(
                        f"Processing P2P {package_type} from {sender_display} (addressed to {recipient_type})..."
                    )

                    # Determine effective session_id (The session key)
                    effective_session_id = sender_id
                    if recipient_type == "group" and recipient_id:
                        effective_session_id = recipient_id

                    effective_session_id = (
                        self._normalize_session_id(effective_session_id) or "unknown_session"
                    )

                    # Use 'content' text if available
                    text_content = str(content)
                    if isinstance(content, dict) and "text" in content:
                        text_content = content["text"]

                    # Special Handling for FILE type
                    if package_type == "file" and isinstance(content, dict) and "data" in content:
                        try:
                            file_name = content.get("info", "downloaded_file")
                            file_data = base64.b64decode(content["data"])

                            download_dir = "data/downloads"
                            os.makedirs(download_dir, exist_ok=True)
                            s_id_short = sender_id[:8] if sender_id else "unknown"
                            file_path = os.path.join(download_dir, f"{s_id_short}_{file_name}")

                            with open(file_path, "wb") as f:
                                f.write(file_data)

                            text_content = f"Received file: {file_name} (Saved to {file_path})"
                            # Update content for history log
                        except Exception as e:
                            text_content = f"Failed to receive file: {e}"
                            logger.error(text_content)

                    # Use Pipeline
                    msg_obj = InboundMessage(
                        channel="p2p",
                        sender_id=sender_id,
                        content=text_content,
                        session_id=effective_session_id,
                        metadata={
                            "message_id": m_id,
                            "package_type": package_type,
                            "recipient_type": recipient_type,
                        },
                    )

                    # 2. Log Inbound Message to history
                    msg_ts = msg.get("timestamp") or msg.get("metadata", {}).get("timestamp")
                    original_ts = None
                    try:
                        if isinstance(msg_ts, str):
                            msg_ts = datetime.fromisoformat(msg_ts)
                            # Ensure aware immediately
                            if msg_ts.tzinfo is None:
                                msg_ts = msg_ts.replace(tzinfo=UTC)
                            original_ts = msg_ts
                        elif not msg_ts:
                            msg_ts = datetime.now(UTC)
                        else:
                            # Ensure aware immediately
                            if hasattr(msg_ts, "tzinfo") and msg_ts.tzinfo is None:
                                msg_ts = msg_ts.replace(tzinfo=UTC)
                            original_ts = msg_ts
                    except:
                        msg_ts = datetime.now(UTC)

                    # Calculate and log delivery latency
                    if original_ts:
                        try:
                            # Ensure UTC for comparison
                            calc_ts = original_ts
                            if calc_ts.tzinfo is None:
                                calc_ts = calc_ts.replace(tzinfo=UTC)
                            latency = (datetime.now(UTC) - calc_ts).total_seconds()
                            logger.info(
                                f"P2P Latency (Polling): Receiving message {m_id} from {sender_id}. Latency: {latency:.3f}s"
                            )
                        except Exception as le:
                            logger.debug(f"Could not calculate latency (Polling): {le}")

                    self.history.append(
                        Message(
                            id=m_id or str(uuid.uuid4()),
                            content=text_content,
                            sender=sender_id,
                            timestamp=msg_ts,
                            session_id=effective_session_id,
                        )
                    )
                    self.resident_memory.log_interaction(
                        sender_id,
                        text_content,
                        msg_type=package_type,
                        session_id=effective_session_id,
                        timestamp=msg_ts,
                        msg_id=m_id,
                    )

                    # DUAL BROADCAST: Inform UI and other listeners
                    await self.message_bus.publish_outbound(
                        OutboundMessage(
                            channel="gateway",
                            session_id=effective_session_id,
                            content=text_content,
                            type="chat",
                            sender=sender_id,
                            timestamp=msg_ts,
                        )
                    )
                    # Also publish to p2p for internal listeners
                    await self.message_bus.publish_outbound(
                        OutboundMessage(
                            channel="p2p",
                            session_id=effective_session_id,
                            content=text_content,
                            type="chat",
                            sender=sender_id,
                            timestamp=msg_ts,
                        )
                    )

                    # 2.5 Loop Prevention: Check for pure acknowledgment/status confirmations
                    if await self.is_pure_acknowledgment(text_content):
                        logger.info(
                            f"Loop prevention: message from {sender_id} is a pure acknowledgment/status confirmation. Storing in history without triggering LLM pipeline."
                        )
                        s_id_short = sender_id[:8] if sender_id else "unknown"
                        await self.message_bus.publish_outbound(
                            OutboundMessage(
                                channel="gateway",
                                session_id=effective_session_id,
                                content=f"Loop prevention: received pure acknowledgment/status confirmation from {s_id_short}. Stored in history without auto-processing.",
                                type="thought",
                            )
                        )
                        continue

                    # 3. Check for lapsed messages (30 mins = 1800 seconds)
                    now = datetime.now(UTC)
                    delay_seconds = (now - msg_ts).total_seconds()
                    skip_delay = False

                    if delay_seconds > 1800 and inbox:
                        # Only skip lapsed messages if there are MORE messages in the queue
                        logger.info(
                            f"Lapsed message detected ({int(delay_seconds)}s delay) with {len(inbox)} more in queue. Skipping agent processing for session {effective_session_id}."
                        )
                        await self.message_bus.publish_outbound(
                            OutboundMessage(
                                channel="gateway",
                                session_id=effective_session_id,
                                content=f"Message received with {int(delay_seconds / 60)}m delay. Stored in history without auto-processing.",
                                type="thought",
                            )
                        )
                        continue
                    elif delay_seconds > 1800 and not inbox:
                        # Last message in queue but lapsed: process it immediately, skip reply delay
                        logger.info(
                            f"Lapsed message detected ({int(delay_seconds)}s delay) but it's the LAST in queue. Processing immediately."
                        )
                        skip_delay = True

                    # 3.5 Smart Reply Delay: Calculate remaining delay
                    if not skip_delay:
                        configured_delay = getattr(self, "p2p_reply_delay", 5)
                        remaining_delay = max(0, configured_delay - delay_seconds)
                        if remaining_delay > 0:
                            logger.info(
                                f"P2P Reply Delay: waiting {remaining_delay:.1f}s (configured={configured_delay}s, elapsed={delay_seconds:.1f}s)"
                            )
                            await asyncio.sleep(remaining_delay)
                        else:
                            logger.info(
                                f"P2P Reply Delay: already elapsed ({delay_seconds:.1f}s >= {configured_delay}s). Processing immediately."
                            )

                    # 4. Run Pipeline to get Response (with Thinking & Replied Receipts)
                    try:
                        if m_id and sender_id != "unknown_sender":
                            asyncio.create_task(p2p_service.send_receipt(sender_id, m_id, "thinking"))

                        pipeline_task = self._run_ralph_wiggum_loop(msg_obj)
                        response_text, _, _ = await asyncio.wait_for(
                            pipeline_task, timeout=900.0
                        )  # 15 min timeout (Extended for long network tasks)

                        if m_id and sender_id != "unknown_sender":
                            asyncio.create_task(p2p_service.send_receipt(sender_id, m_id, "replied"))
                    except TimeoutError:
                        logger.error(
                            f"P2P processing PIPELINE TIMEOUT for message from {sender_id}. Skipped."
                        )
                        response_text = "Processing timed out."
                        if m_id and sender_id != "unknown_sender":
                            asyncio.create_task(p2p_service.send_receipt(sender_id, m_id, "failed"))

                    # 5. Agent's Final Answer is for internal record, NOT sent over P2P.
                    # All outbound P2P communication must be done explicitly by the LLM via `send_p2p_message` tool.
                    if (
                        response_text
                        and "[NO_RESPONSE_NEEDED]" not in str(response_text)
                        and response_text != "No response generated."
                    ):
                        # Log the agent's final conclusion of this P2P interaction to local history so the resident sees it
                        self.history.append(
                            Message(
                                id=str(uuid.uuid4()),
                                content=f"[Agent completed P2P task]: {response_text}",
                                sender="agent",
                                timestamp=datetime.now(UTC),
                                session_id=effective_session_id,
                            )
                        )
                        # Ensure Gateway knows processing is done
                        s_id_short = sender_id[:8] if sender_id else "unknown"
                        await self.message_bus.publish_outbound(
                            OutboundMessage(
                                channel="gateway",
                                session_id=effective_session_id,
                                content=f"Agent processed P2P message from {s_id_short}",
                                type="thought",
                            )
                        )
                except asyncio.CancelledError:
                    logger.warning(
                        f"Process Network Inbox was cancelled during message processing from {sender_id}. This usually happens on timeout or shutdown."
                    )
                    self._is_processing_inbox = False
                    raise
                except Exception as e:
                    logger.error(f"Error processing P2P message from {sender_id}: {e}")
                    # Optional: Push back to inbox or Dead Letter Queue?
                    # For now, just log to history so user sees something failed

                    # Ensure effective_session_id is defined for logging
                    try:
                        err_session_id = effective_session_id
                    except UnboundLocalError:
                        err_session_id = sender_id or "unknown"

                    self.history.append(
                        Message(
                            id=str(uuid.uuid4()),
                            content=f"Error processing P2P message: {e}",
                            sender="system",
                            timestamp=datetime.now(UTC),
                            session_id=err_session_id,
                        )
                    )

            # 6. Clear Disk Inbox after processing batch
            # We don't delete here anymore; hydration handles renaming to .processing
            # CRITICAL: Save system state after processing messages to persist deduplication IDs
            self._save_system_state()

            # 3. Post-Process: Clear disk inbox
            # Since we already pop(0) from in-memory inbox, and p2p_service.local_node.save_message
            # appends to the file, we can safely clear the file now that this specific batch is done.
            # (Actually better to only clear what we processed, but for simplicity, clearing the file
            # is effective since any NEW messages during processing will be in the next batch or appended after this clearing).
            node_id = p2p_service.local_node.node_id
            inbox_path = self.data_dir / "p2p" / f"inbox_{node_id}.jsonl"
            if inbox_path.exists():
                try:
                    with open(inbox_path, "w", encoding="utf-8") as f:
                        pass  # Truncate file
                    logger.debug(f"Cleared disk inbox {inbox_path.name}")
                except Exception as e:
                    logger.error(f"Failed to clear disk inbox: {e}")

        finally:
            self._is_processing_inbox = False

    # 3. Scheduled Task
    async def trigger_scheduled_task(self):
        logger.info(f"Executing Scheduled Brief Generation for field: {self.research_field}...")

        summary = "No report generated."
        if self.reporter:
            interests = [self.research_field]
            summary = await self.reporter.generate_daily_brief(interests)
            await self.reporter.send_report_to_resident(summary)

        elif self.llm:
            msg_obj = InboundMessage(
                channel="system",
                sender_id="scheduler",
                content="Generate a brief daily summary for the resident.",
                session_id="system",
            )
            summary, _, _ = await self._run_ralph_wiggum_loop(msg_obj)
        else:
            summary = "Agent offline."

        # Push to history/frontend AND broadcast to bridges
    async def run_evolution_watcher(self):
        """Periodic task for the Autonomous Self-Evolving Agent Collective.
        Evaluates system performance, checks for architecture proposals, and audits active AIPs.
        """
        logger.info("[EvolutionWatcher] Running periodic self-evolution cycle...")
        try:
            from app.services.evolution_service import evolution_service

            draft_aips = [aip for aip in evolution_service.aips.values() if aip.status == "draft"]

            # If no pending draft AIPs exist, trigger proactive LLM auto-exploration
            if not draft_aips and self.llm:
                logger.info("[EvolutionWatcher] No pending draft AIPs found. Triggering proactive exploration...")
                new_aip = await evolution_service.auto_explore_and_propose(llm_client=self.llm)
                if new_aip:
                    draft_aips = [new_aip]

            # Audit active draft AIPs
            for aip in draft_aips:
                logger.info(f"[EvolutionWatcher] Auditing draft proposal {aip.aip_id}...")
                vote = await evolution_service.audit_aip(aip.aip_id, llm_client=self.llm)
                if vote.approval:
                    await evolution_service.verify_in_sandbox(aip.aip_id)
                    p2p_service = getattr(self, "p2p_service", None)
                    await evolution_service.broadcast_aip(aip.aip_id, p2p_service=p2p_service)
        except Exception as e:
            logger.error(f"[EvolutionWatcher] Error in self-evolution cycle: {e}")

    async def run_literature_watcher(self):
        """Periodic task to watch for new literature, evaluate quality, and share with community.
        
        Improvements (2026-08-02):
        1. Split research_field by ';' into separate topics
        2. Use semantic search for better matching
        3. Merge and deduplicate results across topics
        """
        logger.info(f"Starting Periodic Literature Watcher for topic: {self.research_field}")
        
        # 1. Initialize Skill Service (Dynamic Import)
        import sys
        skill_path = str(self.backend_dir / "skills" / "literature-watcher" / "scripts")
        if skill_path not in sys.path:
            sys.path.append(skill_path)
        
        try:
            from watcher_service import WatcherService
            watcher = WatcherService()
            
            # Fetch resident feedback preferences from memory
            res_prefs = {}
            if self.resident_memory:
                res_prefs = self.resident_memory.get_research_preferences()

            # 2. Split research field into separate topics
            raw_topics = [t.strip() for t in self.research_field.split(";") if t.strip()]
            if not raw_topics:
                raw_topics = [self.research_field]  # Fallback to single topic
            
            logger.info(f"Literature Watcher: Searching {len(raw_topics)} topics: {raw_topics}")
            
            # 3. Search for new papers for EACH topic (using semantic search)
            all_new_papers = []
            seen_ids = set()  # For deduplication across topics
            
            for topic in raw_topics:
                logger.info(f"Literature Watcher: Searching topic '{topic}'...")
                try:
                    # Use semantic search (already enabled in watcher_service.py)
                    topic_papers = await asyncio.to_thread(
                        watcher.get_incremental_papers,
                        topic,
                        interval_days=7,
                        positive_keywords=res_prefs.get("positive_keywords"),
                        negative_keywords=res_prefs.get("negative_keywords"),
                        llm=self.llm,
                        enable_expansion=True,
                    )
                    
                    # Deduplicate across topics
                    for paper in topic_papers:
                        paper_id = paper.get("id") or paper.get("doi") or paper.get("title", "")
                        if paper_id and paper_id not in seen_ids:
                            seen_ids.add(paper_id)
                            all_new_papers.append(paper)
                    
                    logger.info(f"Literature Watcher: Found {len(topic_papers)} papers for topic '{topic}'")
                except Exception as topic_err:
                    logger.error(f"Literature Watcher: Failed to search topic '{topic}': {topic_err}")
                    continue
            
            if not all_new_papers:
                logger.info("No new literature found in this cycle.")
                # 即使没有新论文，也发送状态报告，让居民知道任务在正常运行
                await self._send_literature_watcher_status_report(
                    topics_searched=raw_topics,
                    keywords_used=res_prefs,
                    interval_days=7,
                    papers_found=0,
                    watcher=watcher,
                )
                return

            logger.info(f"Found {len(all_new_papers)} unique new papers across all topics.")
            
            # 4. Evaluate and Act (using LLM)
            high_quality_count = 0
            shared_count = 0

            for paper in all_new_papers:
                # Use LLM to decide quality and sharing, taking resident preferences into account
                decision = await self._evaluate_and_share_paper(paper, research_prefs=res_prefs)
                
                # A. Internal Log & Resident Notification
                if decision.get("is_high_quality"):
                    high_quality_count += 1
                    self.resident_memory.log_interaction(
                        "literature_watcher",
                        f"High-Quality Paper Found: {paper['title']}\nSummary: {decision.get('summary')}",
                        "research",
                        session_id="resident"
                    )
                    
                    # Push a direct notice to UI
                    await self.notify_resident(
                        f"📚 [文献追踪] 发现高质量新文献：\n《{paper['title']}》\n\n💡 理由：{decision.get('summary')}"
                    )
                    
                # B. P2P Community Share (Autonomous Decision)
                if decision.get("should_share"):
                    shared_count += 1
                    await self._share_paper_with_community(paper, decision.get("discussion_starter"))
                
                # C. Save to skill history so we don't process it again in the next run
                await asyncio.to_thread(watcher.save_to_history, [paper])

            logger.info(f"Literature Watcher Cycle Complete. High Quality: {high_quality_count}, Shared: {shared_count}")

        except Exception as e:
            logger.error(f"Literature Watcher process failed: {e}")

    async def _evaluate_and_share_paper(self, paper: dict, research_prefs: dict = None) -> dict:
        """Ask LLM to evaluate the paper and decide on sharing with the network."""
        if not self.llm:
            return {"is_high_quality": False, "should_share": False}

        prefs_str = "None specified."
        if research_prefs:
            pos = ", ".join(research_prefs.get("positive_keywords", [])) or "None"
            neg = ", ".join(research_prefs.get("negative_keywords", [])) or "None"
            summary = research_prefs.get("feedback_summary", "")
            prefs_str = f"Preferred Topics: [{pos}]\nExclude Topics: [{neg}]\nSummary: {summary}"

        prompt = f"""
        You are a proactive Research Agent in the Bit-Politeia network. 
        You just found a new paper during your periodic monitoring.
        
        PAPER DETAILS:
        Title: {paper.get('title')}
        Authors: {paper.get('authors')}
        Abstract: {paper.get('abstract', 'No abstract available.')}
        
        RESIDENT ACADEMIC PREFERENCES & FEEDBACK:
        {prefs_str}

        TASK:
        1. Evaluate if this paper is high quality and highly relevant to your research field: {self.research_field}, aligning with the resident's preferences.
        2. Decide if you should share and discuss this with other autonomous nodes in the P2P community to foster scientific collaboration.
        3. Create a brief internal summary in {self.agent_language} explaining why it's important.
        4. If sharing, create a "Discussion Starter" in {self.agent_language} (e.g. "I found this interesting because... What do you think about X?").
        
        RESPONSE FORMAT (Strict JSON):
        {{
            "is_high_quality": boolean,
            "should_share": boolean,
            "summary": "string explaining importance",
            "discussion_starter": "string for community discussion"
        }}
        """
        try:
            from langchain_core.messages import HumanMessage
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            
            content = response.content.strip()
            # Clean potential markdown fences
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            return json.loads(content)
        except Exception as e:
            logger.error(f"LLM Paper evaluation error: {e}")
            # Fallback: Treat as low quality to be safe
            return {"is_high_quality": False, "should_share": False}

    async def _share_paper_with_community(self, paper: dict, discussion_starter: str):
        """Broadcast the paper discussion to peers in the P2P community."""
        share_content = (
            f"📢 [研究分享] 我发现了一篇值得关注的文献：\n\n"
            f"《{paper.get('title')}》\n\n"
            f"💬 我的观点：{discussion_starter}\n\n"
            f"🔗 链接: {paper.get('url', 'N/A')}\n"
            f"🆔 DOI: {paper.get('doi', 'N/A')}"
        )
        
        logger.info(f"Autonomous Share: Disseminating paper '{paper['title']}' to community.")
        
        # 1. Identify Peers (Target top reputation peers or active nodes)
        if p2p_service.network_manager:
            peers = list(p2p_service.network_manager.nodes.keys())
            
            # Exclude self
            if p2p_service.local_node:
                self_id = p2p_service.local_node.node_id
                peers = [p for p in peers if p != self_id]
            
            # Limit sharing to a few nodes to prevent network-wide spam
            # In the future, this could be filtered by node interests
            target_peers = peers[:3] 
            
            for peer_id in target_peers:
                try:
                    await self.send_p2p_message(peer_id, share_content)
                except Exception as e:
                    logger.warning(f"Failed to share paper with peer {peer_id}: {e}")

    async def _send_literature_watcher_status_report(
        self,
        topics_searched: list,
        keywords_used: dict,
        interval_days: int,
        papers_found: int,
        watcher: Any = None,
    ):
        """Send a status report when no new papers are found, to confirm the task is running normally."""
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        
        # Build keywords summary
        pos_keywords = keywords_used.get("positive_keywords", [])
        neg_keywords = keywords_used.get("negative_keywords", [])
        
        keywords_str = ""
        if pos_keywords:
            keywords_str += f"**正面关键词**: {', '.join(pos_keywords[:5])}{'...' if len(pos_keywords) > 5 else ''}\n"
        if neg_keywords:
            keywords_str += f"**排除关键词**: {', '.join(neg_keywords[:5])}{'...' if len(neg_keywords) > 5 else ''}\n"
        if not keywords_str:
            keywords_str = "未设置关键词过滤\n"
        
        # Get history stats if watcher is available
        history_stats = ""
        if watcher:
            try:
                history = watcher.get_history_stats()
                if history:
                    total = history.get("total_records", 0)
                    last_check = history.get("last_check", "未知")
                    history_stats = f"\n**历史记录**: 共 {total} 篇已处理论文"
                    if last_check and last_check != "未知":
                        history_stats += f"，上次检查: {last_check[:10]}"
            except Exception:
                pass
        
        report = f"""## 📊 文献监控状态报告

**执行时间**: {now}
**研究领域**: {'; '.join(topics_searched)}
**回溯天数**: {interval_days} 天

### 搜索结果
- **找到新论文**: {papers_found} 篇
- **关键词过滤**: 
{keywords_str}{history_stats}

### 状态
✅ 文献监控任务正常运行

---
*下次执行时间: 明天 00:30 UTC*
"""
        
        # Notify resident
        await self.notify_resident(report)
        logger.info("Literature Watcher: Status report sent to resident (no new papers found)")

    # 4. Ad-hoc Task: Periodic Participation Reward
    async def trigger_adhoc_task(self):
        if not self.ledger or not p2p_service.local_node:
            return

        node_id = p2p_service.local_node.node_id
        reward_amount = 0.1  # 50.0
        details = "Periodic Participation Reward (UBI)"

        # Credit the balance
        self.ledger.credit(node_id, reward_amount)
        new_bal = self.ledger.get_balance(node_id)
        logger.info(
            f"Node {node_id[:8]} received periodic income: {reward_amount}. New Balance: {new_bal}"
        )

        # Log to private memory for resident visibility
        self.resident_memory.log_interaction(
            "system",
            f"Received {reward_amount} STATER as Participation Reward.",
            "income",
            session_id="resident",
        )

        # Push a visual notice to history AND broadcast to bridges
        await self.notify_resident(
            f"💰 [Economy] Received {reward_amount} STATER Participation Reward."
        )

    async def get_history(self) -> list[Message]:
        return self.history

    async def get_status(self) -> AgentStatus:
        """Get current agent status including ledger and network info."""
        # Ensure status object is up to date with instance attributes
        self.status.name = getattr(self, "name", "Agent")
        self.status.personality = getattr(self, "personality", "Professional and helpful")
        self.status.model = getattr(self, "model", None)
        self.status.base_url = getattr(self, "base_url", None)

        if p2p_service.local_node:
            node_id = p2p_service.local_node.node_id
            self.status.node_id = node_id

            # 1. Sync Ledger Balance
            if self.ledger:
                self.status.balance = self.ledger.get_balance(node_id)

            # 2. Update Relay Connection Status
            if p2p_service.network_manager and hasattr(p2p_service.network_manager, "relay_client"):
                rc = p2p_service.network_manager.relay_client
                self.status.relay_connected = rc.running and rc.websocket is not None
            else:
                # Fallback to network status dict
                net_status = p2p_service.get_network_status()
                self.status.relay_connected = net_status.get("relay_connected", False)

            logger.debug(
                f"Status Sync: UUID {node_id[:8]} Balance {self.status.balance} Relay: {self.status.relay_connected}"
            )
        else:
            logger.warning("Status Sync Partial: P2P service not fully initialized")

        return self.status

    def _hydrate_history(self):
        """Load recent history from persistent storage into Agent in-memory history.

        Loading strategy:
        1. If memory/history_summary.md exists (compressed archive), inject it as
           a synthetic 'system' message at the front of the history. This gives
           the LLM context about older conversations.
        2. Load the most recent MAX_IN_MEMORY_HISTORY raw messages from JSONL.

        Full history remains safely persisted in JSONL files on disk and is
        accessible via search_history/get_all_history APIs.
        """
        from .memory_store import memory_store

        MAX_IN_MEMORY_HISTORY = 500

        self.history = []

        # Step 1: Load compressed history summary (if available)
        compressed_summary = memory_store.read_history_summary()
        if compressed_summary and len(compressed_summary) > 100:
            # Inject as a synthetic system message so pipeline can use it for context
            # Truncate to reasonable size (max 15k chars) to avoid overloading context
            summary_content = compressed_summary[:15000]
            if len(compressed_summary) > 15000:
                summary_content += "\n\n[... 摘要过长，已截断 ...]"

            self.history.append(
                Message(
                    id="compressed-history-summary",
                    content=f"[COMPRESSED HISTORY SUMMARY]\n{summary_content}",
                    sender="system",
                    timestamp=datetime.now(UTC),
                    session_id="system",
                    msg_type="system",
                )
            )
            logger.info(
                f"AgentService: Loaded compressed history summary ({len(compressed_summary)} chars) "
                f"from history_summary.md"
            )

        # Step 2: Load recent raw messages
        disk_history = self.resident_memory.get_all_history()
        total_on_disk = len(disk_history)

        recent_entries = disk_history[-MAX_IN_MEMORY_HISTORY:] if total_on_disk > MAX_IN_MEMORY_HISTORY else disk_history

        for entry in recent_entries:
            self.history.append(
                Message(
                    id=entry.get("id", str(uuid.uuid4())),
                    content=entry.get("content", ""),
                    sender=entry.get("sender", "unknown"),
                    timestamp=datetime.fromisoformat(entry.get("timestamp"))
                    if entry.get("timestamp")
                    else datetime.now(UTC),
                    session_id=entry.get("session_id") or entry.get("chat_id"),
                    status=entry.get("status"),
                    msg_type=entry.get("type", "chat"),
                )
            )

        has_summary = "with compressed summary" if compressed_summary else "no compressed summary"
        if total_on_disk > MAX_IN_MEMORY_HISTORY:
            logger.info(
                f"AgentService: Loaded {len(self.history)}/{total_on_disk} messages "
                f"({has_summary}, older {total_on_disk - MAX_IN_MEMORY_HISTORY} messages archived on disk)."
            )
        else:
            logger.info(
                f"AgentService: Loaded {len(self.history)} messages from persistent storage ({has_summary})."
            )

    def _trim_in_memory_history(self):
        """Trim in-memory history to prevent unbounded growth during long sessions.

        Called periodically (e.g., from cron jobs or after processing messages).
        Original messages are already persisted to JSONL on disk, so trimming
        the in-memory list is safe.
        """
        MAX_IN_MEMORY_HISTORY = 500
        if len(self.history) > MAX_IN_MEMORY_HISTORY:
            trimmed_count = len(self.history) - MAX_IN_MEMORY_HISTORY
            self.history = self.history[-MAX_IN_MEMORY_HISTORY:]
            logger.info(
                f"Trimmed in-memory history: removed {trimmed_count} oldest messages, "
                f"keeping {MAX_IN_MEMORY_HISTORY} most recent."
            )

    def _save_system_state(self):
        """Save deduplication IDs and other internal states to disk."""
        try:
            import json

            system_dir = self.data_dir / "system"
            system_dir.mkdir(parents=True, exist_ok=True)

            # SLIDING WINDOW: Limit to 10,000 IDs to prevent JSON file bloat and memory pressure
            id_list = list(self.processed_message_ids)
            if len(id_list) > 10000:
                id_list = id_list[-10000:]

            state = {
                "processed_message_ids": id_list,
                "notified_governance_ids": list(self.notified_governance_ids),
                "notified_error_signatures": list(self.notified_error_signatures),
                "resident_bridges": self.resident_bridges,
                "balance": self.status.balance,
                "reputation": self.status.reputation,
                "last_updated": datetime.now(UTC).isoformat(),
            }
            state_path = system_dir / "agent_state.json"

            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            # logger.debug(f"Saved system state: {len(self.processed_message_ids)} IDs.")
        except Exception as e:
            logger.error(f"Failed to save system state: {e}")

    def _hydrate_system_state(self):
        """Load deduplication IDs and hydrate P2P inbox from disk."""
        try:
            import json
            import os

            system_dir = self.data_dir / "system"
            state_path = system_dir / "agent_state.json"
            if os.path.exists(state_path):
                with open(state_path, encoding="utf-8") as f:
                    state = json.load(f)
                    all_ids = state.get("processed_message_ids", [])
                    # Limit to 10,000 recent IDs on load
                    self.processed_message_ids = set(all_ids[-10000:])
                    self.notified_governance_ids = set(state.get("notified_governance_ids", []))
                    self.notified_error_signatures = set(state.get("notified_error_signatures", []))
                    self.resident_bridges = state.get("resident_bridges", {})
                    self.status.balance = state.get("balance", 0.0)
                    self.status.reputation = state.get("reputation", 10)
                    logger.info(
                        f"Hydrated {len(self.processed_message_ids)} de-dup IDs, balance={self.status.balance}, reputation={self.status.reputation}"
                    )

            # 2. Hydrate P2P Inbox
            # Wait for node initialization if needed? Usually called after config?
            # Actually __init__ calls it, but p2p_service might not have local_node yet.
            # Local node is created in P2PService.initialize_node.
            # So hydration should happen after initialize_node.
            # Let's adjust where _hydrate_system_state is called or make it safe.

            from .p2p_service import p2p_service

            if not p2p_service.local_node:
                return

            node_id = p2p_service.local_node.node_id
            p2p_dir = self.data_dir / "p2p"
            inbox_path = p2p_dir / f"inbox_{node_id}.jsonl"
            proc_path = p2p_dir / f"inbox_{node_id}.jsonl.processing"

            # --- COMPATIBILITY MIGRATION ---
            if len(node_id) == 64:
                import uuid

                public_key = p2p_service.local_node.public_key
                old_uuid_id = str(uuid.uuid5(uuid.NAMESPACE_OID, public_key))
                old_inbox_path = p2p_dir / f"inbox_{old_uuid_id}.jsonl"

                if old_inbox_path.exists() and not inbox_path.exists():
                    logger.info(f"Migrating P2P Inbox: {old_uuid_id} -> {node_id}")
                    try:
                        os.rename(old_inbox_path, inbox_path)
                    except Exception as e:
                        logger.error(f"Failed to migrate inbox file: {e}")
            # -------------------------------

            # ATOMIC HANDOFF: Rename main inbox to .processing before reading
            if inbox_path.exists():
                try:
                    if proc_path.exists():
                        # Append to existing processing file if it exists (e.g. from crash)
                        with open(proc_path, "a", encoding="utf-8") as pf:
                            with open(inbox_path, encoding="utf-8") as ifile:
                                pf.write(ifile.read())
                        os.remove(inbox_path)
                    else:
                        os.rename(inbox_path, proc_path)
                except Exception as e:
                    logger.error(f"Failed to rename inbox for atomic processing: {e}")
                    return

            if proc_path.exists():
                pending_messages = []
                try:
                    with open(proc_path, encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                try:
                                    msg_data = json.loads(line)
                                    m_id = msg_data.get("message_id")
                                    if not m_id or m_id not in self.processed_message_ids:
                                        pending_messages.append(msg_data)
                                except:
                                    continue
                except Exception as e:
                    logger.warning(f"Error reading processing inbox: {e}")

                if pending_messages:
                    logger.info(f"Hydrated {len(pending_messages)} messages from {proc_path.name}")
                    p2p_service.local_node.inbox.extend(pending_messages)

                # Delete the processing file once successfully (re)hydrated into memory
                try:
                    os.remove(proc_path)
                except Exception as e:
                    logger.error(f"Failed to delete processing file: {e}")
        except Exception as e:
            logger.error(f"Failed to hydrate system state: {e}")

    async def search_history(
        self, query: str = None, date_from: str = None, date_to: str = None
    ) -> list[Message]:
        results = self.resident_memory.search_history(query, date_from, date_to)
        messages = []
        for entry in results:
            messages.append(
                Message(
                    id=entry.get("id", str(uuid.uuid4())),
                    content=entry.get("content", ""),
                    sender=entry.get("sender", "unknown"),
                    timestamp=datetime.fromisoformat(entry.get("timestamp")),
                    session_id=entry.get("session_id") or entry.get("chat_id"),
                )
            )
        return messages

    async def check_core_node_election_trigger(self):
        """
        Background task for Temporary Core Node to trigger a formal election
        based on community_rules.json scaling and governance history.
        """
        if not self.governance_manager or not p2p_service.local_node:
            return

        local_node_id = p2p_service.local_node.node_id
        from .community_config import community_config

        # We only trigger if we belong to a group
        for group_id, group in p2p_service.local_node.network_manager.groups.items():
            # 1. Determine target core node count from rules
            required_count = 1
            ratios = community_config.rules.get("core_nodes", {}).get("selection_ratios", [])
            member_count = len(group.members)
            for ratio in ratios:
                r_min, r_max = ratio.get("range", [0, 0])
                if r_min <= member_count <= r_max:
                    required_count = ratio.get("count", 1)
                    break

            # 2. Check if a core node election has EVER been started for this group
            active_history = [
                e
                for e in self.governance_manager.active_elections.values()
                if e.group_id == group_id and e.election_type == ElectionType.CORE_NODE
            ]
            finished_history = [
                e
                for e in self.governance_manager.finished_elections.values()
                if e.group_id == group_id and e.election_type == ElectionType.CORE_NODE
            ]

            ever_started = len(active_history) > 0 or len(finished_history) > 0

            # 3. RULE EVALUATION:
            # - Trigger if pop >= 3 but never had a formal election (Condition 1)
            # - Trigger if current core count < rule-based target (Condition 2)
            should_trigger = (member_count >= 3 and not ever_started) or (
                len(group.core_node_ids) < required_count
            )

            if should_trigger:
                # Are WE the primary initiator (the first in the core list)?
                if group.core_node_ids and local_node_id == group.core_node_ids[0]:
                    # Check if an election is ALREADY active right now in locally to avoid spam
                    if not active_history:
                        logger.info(
                            f"Governance: Triggering CORE_NODE election for {group_id}. Reason: Pop={member_count}, EverStarted={ever_started}, Count={len(group.core_node_ids)}, Required={required_count}"
                        )

                        # Generate candidates from group members
                        candidates = list(group.members)

                        # Initiate via governance manager (broadcasts via P2P)
                        await self.initiate_election(
                            group_id=group_id,
                            election_type=ElectionType.CORE_NODE,
                            candidates=candidates,
                            duration_minutes=30,
                        )

    async def sync_network(self):
        """Periodically refresh network topology."""
        if p2p_service._initialized:
            await p2p_service.network_manager.sync_topology()
            # Also check governance triggers
            await self.check_core_node_election_trigger()

    async def get_peers(self) -> list[dict]:
        """Get list of known peers from network manager."""
        if not p2p_service._initialized:
            return []

        peers = []
        # Get all nodes from network manager
        for node_id, node in p2p_service.network_manager.nodes.items():
            # Skip self
            if node_id == p2p_service.local_node.node_id:
                continue

            peers.append(
                {
                    "node_id": node_id,
                    "name": node.name,
                    "public_key": node.public_key,
                    "endpoint": node.endpoint,
                    "status": "online" if node.is_online else "offline",
                    "last_seen": node.last_seen.isoformat()
                    if hasattr(node, "last_seen") and node.last_seen
                    else datetime.now(UTC).isoformat(),
                }
            )
        return peers

    async def get_groups(self) -> list[dict]:
        """Get list of known groups from P2P service."""
        return p2p_service.get_groups()

    async def _check_compliance(self, content: str, recipient_id: str) -> tuple[bool, str]:
        """Audit message content against community rules."""
        if not self.llm or "[security suppression:" in content.lower():
            return True, ""


        sys_prompt = (
            "You are the Compliance Officer agent. "
            "Audit the following message for community rule violations (impolite, hate speech, spam, illegal). "
            "Reply EXACTLY with 'APPROVED' if compliant, or 'REJECTED: <reason>' if not."
        )
        msg_text = f"Target: {recipient_id}\nContent: {content}"

        try:
            # We use a distinct invocation to avoid polluting the main context
            response = await self.llm.ainvoke(
                [SystemMessage(content=sys_prompt), HumanMessage(content=msg_text)]
            )
            res_text = response.content.strip()

            if "REJECTED" in res_text:
                parts = res_text.split("REJECTED", 1)
                reason = parts[1].strip().lstrip(":").strip()
                return False, reason

            return True, ""
        except Exception as e:
            logger.error(f"Compliance Check Error: {e}")
            return True, ""  # Fail open if LLM fails

    # Governance Wrappers
    async def create_proposal(
        self, group_id: str, content: str, duration_minutes: int = 60
    ) -> dict:
        if not self.governance_manager:
            return {"error": "Governance Manager not initialized"}

        # Fetch eligible voters from group members
        eligible_voters = set()
        if p2p_service.local_node and group_id in p2p_service.local_node.network_manager.groups:
            group = p2p_service.local_node.network_manager.groups[group_id]
            eligible_voters = group.members.copy()

        proposal, election = self.governance_manager.initiate_proposal(
            group_id, content, duration_minutes, eligible_voters=eligible_voters
        )

        # Broadcast via P2P - Wait for broadcast to complete with timeout (Fixed: was asyncio.create_task without await)
        try:
            await asyncio.wait_for(
                p2p_service.broadcast_governance_event(
                    group_id,
                    "proposal",
                    {"proposal": proposal.to_dict(), "election": election.to_dict()},
                ),
                timeout=10.0,
            )
            logger.info(f"Proposal broadcast successfully for group {group_id}")
        except TimeoutError:
            logger.warning(f"Proposal broadcast timeout for group {group_id}")
        except Exception as e:
            logger.error(f"Proposal broadcast failed for group {group_id}: {e}")

        return {"proposal": proposal.to_dict(), "election": election.to_dict()}

    async def get_proposals(self) -> list[dict]:
        if not self.governance_manager:
            return []
        # Return list of proposals
        return [p.to_dict() for p in self.governance_manager.proposals.values()]

    async def get_research_proposals(self, group_id: str = None) -> list[dict]:
        """Get research proposals with optional filtering."""
        if not self.governance_manager:
            return []
        return self.governance_manager.get_research_proposals(group_id=group_id)

    async def get_research_proposal(self, election_id: str) -> dict:
        """Get detailed information about a research proposal."""
        if not self.governance_manager:
            return {}
        return self.governance_manager.get_research_proposal(election_id)

    async def submit_research_evaluation(
        self, election_id: str, score: float, feedback: str, reward_amount: float = 0
    ) -> tuple[bool, str]:
        """Submit an evaluation for a research publication."""
        if not self.governance_manager:
            return False, "Governance manager not initialized"
        
        if not p2p_service.local_node:
            return False, "P2P node not initialized"
        
        evaluator_id = p2p_service.local_node.node_id
        return self.governance_manager.submit_research_evaluation(
            election_id=election_id,
            evaluator_id=evaluator_id,
            score=score,
            feedback=feedback,
            reward_amount=reward_amount,
        )

    async def delete_proposal(self, proposal_id: str) -> bool:
        """Remove a proposal and its associated election."""
        if self.governance_manager:
            return self.governance_manager.delete_proposal(proposal_id)
        return False

    async def get_elections(self) -> list[dict]:
        """Get list of active and recently finished elections."""
        if not self.governance_manager:
            return []

        # PROACTIVE SYNC: Finalize any elections that just expired
        self.governance_manager.finalize_expired_elections()

        elections = []
        # 1. Active Elections
        for e in self.governance_manager.active_elections.values():
            data = e.to_dict()
            data["tally"] = e.tally()
            data["is_active"] = True
            elections.append(data)

        # 2. Finished Elections (History)
        if hasattr(self.governance_manager, "finished_elections"):
            for e in self.governance_manager.finished_elections.values():
                data = e.to_dict()
                data["tally"] = e.tally()
                data["is_active"] = False
                elections.append(data)

        return elections

    async def delete_election(self, election_id: str) -> bool:
        """Remove a specific election."""
        if self.governance_manager:
            return self.governance_manager.delete_election(election_id)
        return False

    async def cast_vote(
        self, election_id: str, approval: bool, reason: str = "", candidate_id: str = None
    ) -> dict:
        if not self.governance_manager:
            return {"error": "Governance Manager not initialized"}

        if not p2p_service.local_node:
            return {"error": "Local node not initialized"}

        voter_id = p2p_service.local_node.node_id

        vote = Vote(
            voter_id=voter_id,
            candidate_id=candidate_id,
            approval=approval,
            reason=reason,
            timestamp=datetime.now(UTC),
        )

        success = self.governance_manager.receive_ballot(election_id, [vote])
        if success:
            # Broadcast via P2P (方案 3: 同步等待 + 超时保护)
            election = self.governance_manager.active_elections[election_id]
            try:
                # 同步等待广播完成，最多等待 5 秒
                await asyncio.wait_for(
                    p2p_service.broadcast_governance_event(
                        election.group_id,
                        "vote",
                        {"election_id": election_id, "vote": vote.to_dict()},
                    ),
                    timeout=5.0,
                )
                logger.info(f"Vote broadcast successfully for election {election_id[:8]}")
            except TimeoutError:
                logger.warning(
                    f"Vote broadcast timeout for election {election_id[:8]}, adding to retry queue"
                )
                # 加入重试队列（可后续实现）
            except Exception as e:
                logger.error(f"Vote broadcast failed for election {election_id[:8]}: {e}")

            return {"status": "success", "election_id": election_id}
        else:
            return {"status": "failed", "reason": "Vote rejected (invalid or closed)"}

    async def receive_p2p_message(self, message: P2PMessage) -> dict:
        """Handle incoming P2P message via HTTP endpoint."""
        if not p2p_service.local_node:
            logger.error("Received HTTP P2P message but node not initialized")
            return {"status": "error", "message": "Node not initialized"}

        try:
            # Convert Pydantic model to dict for Node's receive_message
            msg_dict = message.dict()
            # Convert datetime string to object if needed, Node handles it.
            await p2p_service.local_node.receive_message(msg_dict)
            return {"status": "success", "message_id": message.message_id}
        except Exception as e:
            logger.error(f"Error processing incoming direct HTTP P2P message: {e}")
            return {"status": "error", "message": str(e)}

    async def send_p2p_message(
        self,
        recipient_id: str,
        content: Any,
        is_retry: bool = False,
        original_msg_id: str = None,
        bypass_throttle: bool = False,
        **kwargs,
    ) -> dict:
        """
        Send a P2P message to a specific peer.
        This method handles both WebRTC data channel (fast) and HTTP/Relay (reliable) paths.
        """
        print(
            f"\n[DEBUG] send_p2p_message called for {recipient_id}, content: {str(content)[:50]}...",
            flush=True,
        )

        # Initialize throttle state variables to avoid UnboundLocalError in return/log paths
        elapsed = 0
        cooldown_seconds = int(os.getenv("AGENT_P2P_COOLDOWN_SECONDS", getattr(self, "p2p_cooldown_seconds", 300)))
        is_in_cooldown = False

        if not p2p_service._initialized:
            logger.error(
                f"P2P Message attempt failed: P2PService NOT INITIALIZED (target={recipient_id})"
            )
            return {"success": False, "error": "P2P not initialized"}

        # Normalize text for moderation and display
        text_to_check = content
        if isinstance(content, dict):
            text_to_check = content.get("text", str(content))
        elif not isinstance(content, str):
            text_to_check = str(content)

        # 1. Moderation Check - Skip if retry
        if not is_retry:
            is_compliant, reason = await self._check_compliance(text_to_check, recipient_id)
            if not is_compliant:
                msg = f"⚠️ Message Refused: {reason}"

                # Log refusal to history so user sees it in chat
                self.history.append(
                    Message(
                        id=str(uuid.uuid4()),
                        content=msg,
                        sender="agent",
                        timestamp=datetime.now(UTC),
                        session_id=recipient_id,
                    )
                )
                self.resident_memory.log_interaction(
                    "agent", msg, "moderation", session_id=recipient_id, status="failed"
                )

                return {"success": False, "status": "refused", "reason": reason}
        else:
            logger.info(f"Retrying message {original_msg_id} - skipping compliance check.")

        # 2. Identify Message Nature (Refactored)
        # Package Type: What is being sent?
        package_type = kwargs.get("package_type")
        if not package_type:
            # Fallback for legacy calls or tool-invoked calls
            msg_type_kwarg = kwargs.get("message_type")
            if msg_type_kwarg in ["file", "gossip", "chat"]:
                package_type = msg_type_kwarg
            elif isinstance(content, dict) and "data" in content:
                package_type = "file"
            else:
                package_type = "chat"

        # Recipient Type: How is it addressed?
        recipient_type = "direct"
        if kwargs.get("message_type") == "group":
            recipient_type = "group"
        else:
            from .p2p_service import p2p_service as _p2p

            local_node = _p2p.local_node
            if local_node and recipient_id in local_node.group_ids:
                recipient_type = "group"

        # 3. Log Outbound Message (History) - Skip if retry (we update status later)
        # Normalize recipient_id for history and UI consistency
        norm_target = self._normalize_session_id(recipient_id)
        msg_id = original_msg_id if is_retry and original_msg_id else str(uuid.uuid4())

        # Use a single UTC timestamp for consistent tracking
        msg_timestamp = datetime.now(UTC)

        if not is_retry:
            # 2.5 P2P Rate Limiting (Throttling) for non-resident sessions
            if not bypass_throttle and recipient_id != "resident":
                session = session_manager.get_session(recipient_id, "p2p")

                last_reply_iso = session.metadata.get("last_p2p_reply_at")
                # cooldown_seconds is initialized at top

                if last_reply_iso:
                    try:
                        last_reply_at = datetime.fromisoformat(last_reply_iso)
                        if last_reply_at.tzinfo is None:
                            last_reply_at = last_reply_at.replace(tzinfo=UTC)

                        elapsed = (datetime.now(UTC) - last_reply_at).total_seconds()
                        if elapsed < cooldown_seconds:
                            is_in_cooldown = True
                    except Exception as te:
                        logger.error(f"Error parsing last_p2p_reply_at: {te}")

                if is_in_cooldown:
                    # Buffer the message instead of sending
                    session.metadata["pending_reply"] = text_to_check
                    session.metadata["pending_reply_at"] = datetime.now(UTC).isoformat()
                    session_manager.save_session(session)

                    logger.info(
                        f"P2P Throttled: Message to {recipient_id} buffered (Cooldown active: {int(elapsed)}s < {cooldown_seconds}s)"
                    )

                    # Inform Gateway that it's buffered
                    await self.message_bus.publish_outbound(
                        OutboundMessage(
                            channel="gateway",
                            session_id=self._normalize_session_id(recipient_id),
                            content="**[P2P 5min 冷却期限制]**: 回覆已暫存，將在冷卻結束後自動發送（或在下次喚醒時更新）。",
                            type="thought",
                        )
                    )

                    return {
                        "success": True,
                        "status": "buffered",
                        "cooldown_remaining": int(
                            cooldown_seconds - (elapsed if "elapsed" in locals() else 0)
                        ),
                    }

            # If we reach here, we are sending (either not throttled or bypass=True)
            # Reset metadata for non-resident sessions
            if recipient_id != "resident":
                session = session_manager.get_session(recipient_id, "p2p")
                session.metadata["last_p2p_reply_at"] = datetime.now(UTC).isoformat()
                session.metadata["pending_reply"] = None
                session_manager.save_session(session)

            self.processed_message_ids.add(msg_id)  # Track our own messages to avoid loopback
            msg_obj = Message(
                id=msg_id,
                content=f"{text_to_check}",
                sender="agent",
                timestamp=msg_timestamp,
                session_id=norm_target,
                status="pending",
                metadata={"is_p2p": True},
            )
            self.history.append(msg_obj)
            self.resident_memory.log_interaction(
                "agent",
                text_to_check,
                msg_type=package_type,
                session_id=norm_target,
                status="pending",
                msg_id=msg_id,
            )
        else:
            logger.info(f"Retrying message {msg_id} - skipping duplicate history log.")

        # Dual broadcast to UI (Initial Pending)
        await self.message_bus.publish_outbound(
            OutboundMessage(
                channel="gateway",
                session_id=norm_target,
                content=f"{text_to_check}",
                type=package_type,
                sender="agent",
                timestamp=msg_timestamp,
                metadata={
                    "message_id": msg_id,
                    "status": "pending",
                    "package_type": package_type,
                    "recipient_type": recipient_type,
                },
            )
        )

        # Publish to p2p for internal tracking if needed
        await self.message_bus.publish_outbound(
            OutboundMessage(
                channel="p2p",
                session_id=recipient_id,  # Use raw recipient for P2P routing
                content=f"{text_to_check}",
                type="chat",
                sender="agent",
                timestamp=msg_timestamp,
                metadata={
                    "message_id": msg_id,
                    "recipient_id": recipient_id,
                    "package_type": package_type,
                },
            )
        )

        # 3. Direct Transmission
        # PROACTIVE TOPOLOGY CHECK: Log if we actually know this peer or group
        peer_name = "Unknown"
        is_group = False

        # Check nodes first
        target_node = p2p_service.network_manager.nodes.get(recipient_id)
        if target_node:
            peer_name = target_node.name
            logger.info(f"Recipient {recipient_id} identified as peer '{peer_name}' in topology.")
        # Check groups
        elif recipient_id in p2p_service.network_manager.groups:
            peer_name = p2p_service.network_manager.groups[recipient_id].name
            is_group = True
            logger.info(f"Recipient {recipient_id} identified as group '{peer_name}'.")
        else:
            logger.warning(
                f"Recipient {recipient_id} NOT found in local topology nodes or groups. It might be an offline node or a new group."
            )

        target_label = f"Group: {peer_name}" if is_group else peer_name
        logger.info(f"Transmitting P2P message to {recipient_id} ({target_label})...")

        try:
            # Differentiate simple string vs complex dictionary payload
            if isinstance(content, dict):
                msg_content = content
                webrtc_payload_dict = content.copy()
                webrtc_payload_dict["message_id"] = msg_id  # CRITICAL: Include unique ID
                webrtc_payload_dict["timestamp"] = (
                    msg_timestamp.isoformat()
                )  # PROPAGATE SOURCE TIMESTAMP
                if "message_type" not in webrtc_payload_dict:
                    webrtc_payload_dict["message_type"] = "DIRECT"
                import json

                webrtc_payload = json.dumps(webrtc_payload_dict)
            else:
                msg_content = {"text": text_to_check}
                import json

                webrtc_payload = json.dumps(
                    {
                        "text": text_to_check,
                        "message_type": "DIRECT",
                        "message_id": msg_id,
                        "timestamp": msg_timestamp.isoformat(),  # PROPAGATE SOURCE TIMESTAMP
                    }
                )

            # Map to protocol message types
            # GROUP messages should NOT use WebRTC (WebRTC is for peer-to-peer)
            # Only use WebRTC for DIRECT TEXT messages
            use_webrtc = recipient_type == "direct" and package_type == "chat"

            sent_via_webrtc = False
            if use_webrtc:
                sent_via_webrtc = await p2p_service.webrtc_manager.send_message(
                    recipient_id, webrtc_payload
                )

            if sent_via_webrtc:
                logger.info(
                    f"[{recipient_id}] Message transmitted via WebRTC: {text_to_check[:100]}..."
                )
                success_final = True
                mode = "webrtc"
            else:
                # Fallback to HTTP/Relay (or direct for GROUP messages)
                # For GROUP messages, use broadcast_to_group if available, otherwise use send_message
                if recipient_type == "group":
                    # Use the dedicated group broadcast method
                    success = await p2p_service.broadcast_to_group(
                        recipient_id, text_to_check, message_id=msg_id, timestamp=msg_timestamp
                    )
                    mode = "group_broadcast"
                else:
                    # Pass the unique business-level msg_id to the protocol layer
                    success = await p2p_service.send_message(
                        recipient_id,
                        msg_content,
                        msg_type=package_type,
                        message_id=msg_id,
                        timestamp=msg_timestamp,
                    )
                    mode = "http_relay"
                if success:
                    success_final = True
                    # Log based on transmission mode
                    if mode == "group_broadcast":
                        logger.info(
                            f"[{recipient_id}] Group Broadcast successfully initiated: {text_to_check[:100]}..."
                        )
                    else:
                        logger.info(
                            f"[{recipient_id}] Message transmitted via HTTP/Relay: {text_to_check[:100]}..."
                        )
                    # Trigger Upgrade if simple text and not already connected/connecting
                    # CRITICAL: Only for DIRECT messages!
                    if not isinstance(content, dict) and recipient_type == "direct":
                        pc = p2p_service.webrtc_manager.pcs.get(recipient_id.lower())
                        if not pc or (
                            pc.signalingState == "stable"
                            and pc.connectionState not in ["connecting", "connected"]
                        ):
                            asyncio.create_task(
                                p2p_service.webrtc_manager.initiate_connection(recipient_id)
                            )
                else:
                    logger.error(
                        f"[{recipient_id}] FINAL FAILURE: Failed to transmit P2P message via ANY path (target={recipient_id})"
                    )
                    success_final = False

            # 4. Update Status and Notify Gateway
            new_status = "sent" if success_final else "failed"

            # Find the message object to update status
            target_msg = None
            for m in reversed(self.history):
                if m.id == msg_id:
                    target_msg = m
                    break

            if target_msg:
                target_msg.status = new_status

            self.resident_memory.update_message_status(msg_id, new_status, topic=package_type)

            await self.message_bus.publish_outbound(
                OutboundMessage(
                    channel="gateway",
                    session_id=norm_target,
                    content=msg_id,
                    type="status_update",
                    metadata={"message_id": msg_id, "status": new_status},
                )
            )

            if success_final:
                return {"success": True, "mode": mode}
            else:
                return {"success": False, "error": "All transport paths failed"}

        except Exception as e:
            logger.error(f"Failed to transmit P2P message to {recipient_id}: {e}")
            return {"success": False, "error": str(e)}

    async def handle_remote_delivery_error(self, message_id: str, error_content: Any):
        """
        Handle asynchronous delivery failure reported by the P2P network (e.g., from Relay).
        Updates local history and notifies the UI.
        """
        logger.warning(f"Handling remote delivery error for message {message_id}: {error_content}")

        # 1. Update status in local memory history
        found_in_history = False
        target_session_id = "resident"  # Default to main resident chat

        for msg in self.history:
            # Check both internal UUID (msg.id) and P2P network ID (msg.metadata.message_id)
            p2p_msg_id = msg.metadata.get("message_id") if msg.metadata else None
            if msg.id == message_id or p2p_msg_id == message_id:
                msg.status = "failed"
                if not msg.metadata:
                    msg.metadata = {}
                msg.metadata["delivery_error"] = str(error_content)
                target_session_id = msg.session_id
                found_in_history = True
                logger.info(f"Updated message {msg.id} status to 'failed' in active history.")
                break

        # 2. Update status in persistent resident memory (JSONL logs)
        self.resident_memory.update_message_status(message_id, "failed")

        # 3. Notify Gateway/UI via Message Bus
        await self.message_bus.publish_outbound(
            OutboundMessage(
                channel="gateway",
                session_id=target_session_id,
                content=message_id,
                type="status_update",
                metadata={
                    "message_id": message_id,
                    "status": "failed",
                    "error": str(error_content),
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        )

        if found_in_history:
            logger.info(f"Successfully updated status to 'failed' for message {message_id}")
        else:
            logger.debug(
                f"Message ID {message_id} not found in current history buffer. Still updated disk logs."
            )

    async def get_chat_history_with_peer(self, peer_id: str, limit: int = 20) -> str:
        """
        Retrieves the persistent chat history for a specific peer from the SessionManager.
        This provides the LLM with explicitly requested historical context across sessions.
        """
        from ..services.session_service import session_manager

        # We try to get the session from disk/memory
        session = session_manager.get_session(peer_id, "p2p")
        if not session or not session.history_slice:
            return f"No persistent chat history found with peer {peer_id}."

        # The history_slice contains LangChain BaseMessage objects (or dicts if serialized)
        formatted_history = []

        # Take the last 'limit' messages
        messages_to_process = session.history_slice[-limit:] if limit > 0 else session.history_slice

        for msg in messages_to_process:
            # Handle both instantiated LangChain objects and serialized dicts
            if isinstance(msg, dict):
                role = msg.get("type", "unknown")
                content = msg.get("content", "")
            else:
                role = msg.type if hasattr(msg, "type") else "unknown"
                content = msg.content if hasattr(msg, "content") else str(msg)

            if role == "ai":
                formatted_history.append(f"Me (Agent): {content}")
            elif role == "human":
                formatted_history.append(f"Peer ({peer_id}): {content}")
            else:
                formatted_history.append(f"{role}: {content}")

        if not formatted_history:
            return f"Chat history exists but is empty for peer {peer_id}."

        header = (
            f"--- Chat History with Peer {peer_id} (Last {len(formatted_history)} messages) ---\n"
        )
        return header + "\n".join(formatted_history)

    async def get_archive_chain(self) -> list[dict]:
        """Get local blockchain archive."""
        if not self.archive_manager:
            return []

        # Format chain for frontend
        chain_data = []
        for block in self.archive_manager.chain.chain:
            # We convert block to dict. ArchiveChain.Block is a dataclass so we can use asdict or manual
            from dataclasses import asdict

            chain_data.append(asdict(block))

        return chain_data

    # Governance Methods accessed by Tools
    async def initiate_election(
        self,
        group_id: str,
        candidates: list[str],
        election_type: ElectionType = ElectionType.CORE_NODE,
        duration_minutes: int = 60,
    ) -> str:
        """Initiate a formal election and notify the network and resident."""
        if not self.governance_manager:
            return "Governance Manager not initialized"

        logger.info(
            f"Governance: Initiating {election_type.value} for group {group_id} with {len(candidates)} candidates."
        )

        # 1. Create locally in GovernanceManager
        # Note: If it's a CORE_NODE election, it uses the specialized initiate_election
        if election_type == ElectionType.CORE_NODE:
            election = self.governance_manager.initiate_election(
                group_id, candidates, duration_minutes
            )
        else:
            # Fallback/Generic creation for other types if needed
            election = self.governance_manager.initiate_election(
                group_id, candidates, duration_minutes
            )

        # 2. Add eligible voters if group info is available
        if p2p_service.local_node and group_id in p2p_service.local_node.network_manager.groups:
            group = p2p_service.local_node.network_manager.groups[group_id]
            election.eligible_voters = group.members.copy()

        # 3. Broadcast via P2P
        try:
            await asyncio.wait_for(
                p2p_service.broadcast_governance_event(
                    group_id, "election", {"election": election.to_dict()}
                ),
                timeout=10.0,
            )
        except Exception as e:
            logger.error(f"Election broadcast failed for group {group_id}: {e}")

        return str(election.election_id)

    async def submit_proposal(self, group_id: str, content: str) -> str:
        """Alias for create_proposal returning string for tool compatibility."""
        result = await self.create_proposal(group_id, content)
        if "error" in result:
            return result["error"]
        return f"Proposal {result['proposal']['proposal_id']} initiated. Voting ID: {result['election']['election_id']}"

    async def publish_research(
        self, group_id: str, content: str, pdf_hash: str, duration_minutes: int = 60
    ) -> str:
        if not self.governance_manager:
            return "Governance Manager not initialized"

        # Fetch eligible voters from group members
        eligible_voters = set()
        if p2p_service.local_node and group_id in p2p_service.local_node.network_manager.groups:
            group = p2p_service.local_node.network_manager.groups[group_id]
            eligible_voters = group.members.copy()

        proposal, election = self.governance_manager.initiate_research_publication(
            group_id, content, pdf_hash, duration_minutes, eligible_voters=eligible_voters
        )

        # Broadcast via P2P - Wait for broadcast to complete with timeout (Fixed: was asyncio.create_task without await)
        try:
            await asyncio.wait_for(
                p2p_service.broadcast_governance_event(
                    group_id,
                    "proposal",
                    {"proposal": proposal.to_dict(), "election": election.to_dict()},
                ),
                timeout=10.0,
            )
            logger.info(f"Research proposal broadcast successfully for group {group_id}")
        except TimeoutError:
            logger.warning(f"Research proposal broadcast timeout for group {group_id}")
        except Exception as e:
            logger.error(f"Research proposal broadcast failed for group {group_id}: {e}")

        return f"Research published {proposal.pdf_hash}. Evaluation ID: {election.election_id}"

    async def vote_election(self, election_id: str, votes_data: list[dict]) -> str:
        """
        Submit a ballot.
        votes_data: List of dicts with {"candidate_id": str, "approve": bool, "reason": str, "reward_amount": float}
        """
        if not self.governance_manager:
            return "Governance failed"

        ballot = []
        for v_data in votes_data:
            ballot.append(
                Vote(
                    voter_id=self.governance_manager.node_id,
                    candidate_id=v_data.get("candidate_id"),  # Can be None for proposal
                    timestamp=datetime.now(UTC),
                    approval=v_data.get("approve", False),
                    reason=v_data.get("reason", ""),
                    reward_amount=v_data.get("reward_amount", 0.0),
                )
            )

        success = self.governance_manager.receive_ballot(election_id, ballot)
        if success:
            # Broadcast via P2P - Wait for broadcast to complete with timeout
            election = self.governance_manager.active_elections[election_id]
            broadcast_tasks = []
            for v in ballot:
                task = asyncio.create_task(
                    p2p_service.broadcast_governance_event(
                        election.group_id, "vote", {"election_id": election_id, "vote": v.to_dict()}
                    )
                )
                broadcast_tasks.append(task)

            # Wait for all broadcasts to complete (with timeout)
            try:
                await asyncio.wait_for(
                    asyncio.gather(*broadcast_tasks, return_exceptions=True), timeout=10.0
                )
                logger.info(
                    f"Vote broadcast successfully for election {election_id[:8]} ({len(ballot)} votes)"
                )
            except TimeoutError:
                logger.warning(f"Vote broadcast timeout for election {election_id[:8]}")
                return "Ballot registered locally but broadcast timed out"
            except Exception as e:
                logger.error(f"Vote broadcast failed for election {election_id[:8]}: {e}")
                return f"Ballot registered locally but broadcast failed: {e}"

            return "Ballot registered and broadcast successfully"
        else:
            return "Ballot rejected (invalid, closed, or validation failed)"

    async def get_election_info(self, election_id: str, include_content: bool = False) -> dict:
        if not self.governance_manager:
            return {"error": "Governance Manager not initialized"}

        # 1. Search Active Elections
        election = self.governance_manager.active_elections.get(election_id)

        # 2. Search Finished Elections if not found in Active
        if not election:
            election = self.governance_manager.finished_elections.get(election_id)

        if not election:
            return {"error": f"Election {election_id} not found in active or finished records."}

        result = election.tally()

        # 3. Optionally include full proposal content
        if include_content and election.proposal_id:
            proposal = self.governance_manager.proposals.get(election.proposal_id)
            if proposal:
                result["proposal_content"] = proposal.content
                result["initiator_id"] = proposal.initiator_id
                result["timestamp"] = (
                    proposal.timestamp.isoformat()
                    if hasattr(proposal.timestamp, "isoformat")
                    else proposal.timestamp
                )

        return result

    async def get_governance_list(self, limit: int = 20, status: str = "all") -> str:
        if not self.governance_manager:
            return "Governance Manager not initialized"

        report = "--- Governance Transactions ---\n"

        # 1. Gather Items
        items = []
        if status.lower() in ["active", "all"]:
            for eid, e in self.governance_manager.active_elections.items():
                snippet = ""
                if e.proposal_id:
                    prop = self.governance_manager.proposals.get(e.proposal_id)
                    if prop:
                        snippet = f" | 内容: {prop.content[:40]}..."
                items.append(
                    {
                        "id": eid,
                        "type": e.election_type.value,
                        "status": "ACTIVE",
                        "group": e.group_id,
                        "snippet": snippet,
                    }
                )

        if status.lower() in ["finished", "all"]:
            for eid, e in self.governance_manager.finished_elections.items():
                snippet = ""
                if e.proposal_id:
                    prop = self.governance_manager.proposals.get(e.proposal_id)
                    if prop:
                        snippet = f" | 内容: {prop.content[:40]}..."
                items.append(
                    {
                        "id": eid,
                        "type": e.election_type.value,
                        "status": "FINISHED",
                        "group": e.group_id,
                        "snippet": snippet,
                    }
                )

        # Sort: ACTIVE first, then alphabetical ID
        items.sort(key=lambda x: (0 if x["status"] == "ACTIVE" else 1, x["id"]))

        # 2. Format output
        display_items = items[:limit]
        if not display_items:
            return "No governance transactions found."

        for item in display_items:
            report += f"ID: {item['id']} | Type: {item['type']} | Status: {item['status']} | Group: {item['group'][:8]}...{item['snippet']}\n"

        if len(items) > limit:
            report += f"\n... and {len(items) - limit} more legacy items."

        return report

    # Reputation Methods
    async def evaluate_peer(self, target_id: str, scores: dict) -> str:
        if not self.reputation_manager:
            return "Reputation Manager not initialized"

        rater_id = self.reputation_manager.node_id
        eval_obj = self.reputation_manager.submit_evaluation(rater_id, target_id, scores)

        if eval_obj:
            return f"Evaluation recorded: {eval_obj.evaluation_id}"
        else:
            return "Evaluation failed. Check scores (0-100)."

    async def get_peer_reputation(self, target_id: str) -> dict:
        if not self.reputation_manager:
            return {}
        return self.reputation_manager.get_reputation(target_id)

    # Archive Methods
    async def run_archiving(self) -> str:
        """
        Trigger archiving of current state since the last block.
        Only generates a block if there are new transactions, votes, or messages.
        """
        if not self.archive_manager:
            return "Archive Manager not initialized"

        # 1. Determine time window
        last_block = self.archive_manager.chain.latest_block
        last_ts = datetime.fromtimestamp(last_block.timestamp, tz=UTC)
        now = datetime.now(UTC)

        logger.info(f"Archiving cycle: Checking for new activity since {last_ts.isoformat()}...")

        # 2. Gather data since last_ts

        # 2.1 Gather Votes
        new_votes = []
        if self.governance_manager:
            # Check both active and finished elections
            all_election_sets = [
                self.governance_manager.active_elections.values(),
                self.governance_manager.finished_elections.values(),
            ]
            for elections in all_election_sets:
                for election in elections:
                    for vote_list in election.votes.values():
                        for v in vote_list:
                            v_ts = v.timestamp
                            if v_ts.tzinfo is None:
                                v_ts = v_ts.replace(tzinfo=UTC)

                            if v_ts > last_ts:
                                new_votes.append(v)

        # 2.2 Gather P2P Messages (Excluding resident and system)
        new_messages = []
        for msg in self.history:
            msg_ts = msg.timestamp
            if msg_ts.tzinfo is None:
                msg_ts = msg_ts.replace(tzinfo=UTC)

            if msg_ts > last_ts:
                is_p2p = False
                if msg.metadata and isinstance(msg.metadata, dict):
                    is_p2p = msg.metadata.get("is_p2p", False) or msg.metadata.get("channel") == "p2p"
                elif msg.session_id and msg.session_id != "resident":
                    is_p2p = True

                if is_p2p and msg.sender != "system":
                    new_messages.append(msg.model_dump() if hasattr(msg, "model_dump") else msg.dict())

        # 2.3 Gather Transactions since last block
        new_txs = []
        if self.ledger:
            for tx in self.ledger.transactions:
                tx_ts = tx.timestamp
                if tx_ts.tzinfo is None:
                    tx_ts = tx_ts.replace(tzinfo=UTC)
                if tx_ts > last_ts:
                    new_txs.append(tx.to_dict())

        # 2.4 Gather Proposals / Research since last block
        new_research = []
        if self.governance_manager:
            for proposal in self.governance_manager.proposals.values():
                p_ts = proposal.timestamp
                if p_ts.tzinfo is None:
                    p_ts = p_ts.replace(tzinfo=UTC)
                if p_ts > last_ts:
                    new_research.append(proposal)

        # 3. Decision: Should we generate a block?
        has_activity = (
            len(new_votes) > 0 or len(new_messages) > 0 or len(new_txs) > 0 or len(new_research) > 0
        )

        if not has_activity:
            logger.info("No new activity detected since last block. Skipping archive generation.")
            return "No activity to archive."

        # 4. Create Block
        logger.info(
            f"Generating archive block with {len(new_votes)} votes, {len(new_messages)} messages, {len(new_txs)} transactions and {len(new_research)} proposals..."
        )
        block = self.archive_manager.create_daily_archive(
            votes=[str(v) for v in new_votes],
            txs=[str(t) for t in new_txs],
            research=[str(r) for r in new_research],
            messages=new_messages,
        )

        return f"SUCCESS: Archived Block #{block.index} Hash: {block.hash[:16]}..."

    async def run_nightly_maintenance_pipeline(self):
        """
        Unified Nightly Maintenance Pipeline:
        Executes sequentially at 02:00 UTC:
        1. Cognitive Memory Consolidation (ConsolidationService)
        2. History Context Compression (ContextManager)
        3. Blockchain Block Archiving (ArchiveManager)
        """
        logger.info("==================================================")
        logger.info("[Nightly Pipeline] Starting Unified Maintenance Pipeline...")
        logger.info("==================================================")

        # Step 1: Cognitive Memory Consolidation
        try:
            if self.consolidation_service:
                logger.info("[Nightly Pipeline 1/3] Step 1: Memory Consolidation starting...")
                await self.consolidation_service.run_daily_consolidation()
                logger.info("[Nightly Pipeline 1/3] Step 1: Memory Consolidation completed.")
            else:
                logger.info("[Nightly Pipeline 1/3] ConsolidationService uninitialized, skipped.")
        except Exception as e:
            logger.error(f"[Nightly Pipeline 1/3] Memory consolidation failed: {e}")

        # Step 2: History Context Compression
        try:
            if self.context_manager:
                logger.info("[Nightly Pipeline 2/3] Step 2: History Compression starting...")
                res = await self.context_manager.compress_archived_history()
                comp_count = res.get("compressed_count", 0) if isinstance(res, dict) else 0
                logger.info(f"[Nightly Pipeline 2/3] Step 2: History Compression completed ({comp_count} messages summarized).")
            else:
                logger.info("[Nightly Pipeline 2/3] ContextManager uninitialized, skipped.")
        except Exception as e:
            logger.error(f"[Nightly Pipeline 2/3] History compression failed: {e}")

        # Step 3: Blockchain Block Archiving
        try:
            if self.archive_manager:
                logger.info("[Nightly Pipeline 3/3] Step 3: Blockchain Block Archiving starting...")
                res_str = await self.run_archiving()
                logger.info(f"[Nightly Pipeline 3/3] Step 3: Block Archiving completed ({res_str}).")
            else:
                logger.info("[Nightly Pipeline 3/3] ArchiveManager uninitialized, skipped.")
        except Exception as e:
            logger.error(f"[Nightly Pipeline 3/3] Block archiving failed: {e}")

        logger.info("==================================================")
        logger.info("[Nightly Pipeline] Maintenance Pipeline Finished Successfully.")
        logger.info("==================================================")

    async def check_tasks_monitor(self):
        """Background job to check status of long-term tasks."""
        if not self.task_manager:
            return

        if not self.llm:
            logger.info(
                "Task Monitor: Agent LLM not yet configured. Postponing startup task check by 5 seconds..."
            )
            from datetime import timedelta

            self.scheduler.add_job(
                "app.services.agent_service:check_tasks_monitor_proxy",
                trigger="date",
                run_date=datetime.now(UTC) + timedelta(seconds=5),
                id="task_monitor_startup_retry",
                replace_existing=True,
            )
            return

        active_tasks = self.task_manager.get_active_tasks()
        if not active_tasks:
            return

        logger.info(f"Task Monitor: Checking {len(active_tasks)} active tasks...")

        for task in active_tasks:
            # Logic: If pending, move to active and poke immediately
            if task.status == TaskStatus.PENDING:
                logger.info(f"Task Monitor: Activating pending task '{task.goal}'")
                task.update_status(TaskStatus.ACTIVE)
                self.task_manager.save_tasks()

                poke_msg = InboundMessage(
                    channel="internal",
                    sender_id="system",
                    session_id="resident",
                    content=(
                        f'[INTERNAL MONITOR]: 发现一个待处理的新任务 "{task.goal}"。请立刻开始执行任务并更新 Checkpoint。\n'
                        f"[CRITICAL INSTRUCTION: You are awakened by an automated background loop. You are an AUTONOMOUS agent. "
                        f"You MUST proactively take action by calling a tool (e.g. send_p2p_message, execute_shell_command) to push the task forward. "
                        f"Do NOT ask the resident for permission or instructions on how to proceed unless completely blocked. "
                        f"Do NOT output conversational text just to acknowledge this message. If you have absolutely nothing to do, output exactly [NO_RESPONSE_NEEDED].]"
                    ),
                )
                asyncio.create_task(self._run_ralph_wiggum_loop(poke_msg))

            elif task.status == TaskStatus.ACTIVE:
                last_update = task.updated_at
                now = datetime.now(UTC)
                # If no update for 30 mins, or if it's a fresh start check
                # Note: On a fresh reboot, this might still be > 1800s if the task was saved long ago
                if (now - last_update).total_seconds() > 1800:
                    logger.info(
                        f"Task Monitor: Task '{task.goal}' seems idle. Triggering self-poke."
                    )

                    # Synthesize an internal message
                    poke_msg = InboundMessage(
                        channel="internal",
                        sender_id="system",
                        session_id="resident",
                        content=(
                            f'[INTERNAL MONITOR]: 正在推进长期任务 "{task.goal}"。当前状态: {task.status}。请检查 Checkpoint 并决定下一步行动。\n'
                            f"[CRITICAL INSTRUCTION: You are awakened by an automated background loop. You are an AUTONOMOUS agent. "
                            f"You MUST proactively take action by calling a tool (e.g. send_p2p_message, execute_shell_command) to push the task forward. "
                            f"Do NOT ask the resident for permission or instructions on how to proceed unless completely blocked. "
                            f"Do NOT output conversational text just to acknowledge this message. If you have absolutely nothing to do, output exactly [NO_RESPONSE_NEEDED].]"
                        ),
                    )

                    # Run the loop in the background
                    asyncio.create_task(self._run_ralph_wiggum_loop(poke_msg))

                    # Explicitly bump the updated_at timestamp to reset the 30-minute idle clock
                    # This prevents the monitor from spamming the agent if the monitor interval is shorter than 30 mins
                    task.updated_at = datetime.now(UTC)
                    self.task_manager.save_tasks()
                else:
                    logger.info(
                        f"Task Monitor: Task '{task.goal}' is ongoing (Updated {(now - last_update).total_seconds() / 60:.1f}m ago)."
                    )
            elif task.status == TaskStatus.BLOCKED:
                logger.info(
                    f"Task Monitor: Task '{task.goal}' is BLOCKED. Waiting for resumption condition."
                )

    async def check_governance_proposals(self):
        """Background job to scan for unhandled governance proposals and notify the agent."""
        if not self.governance_manager or not self.llm:
            return

        # PROACTIVE SYNC: Finalize any elections that just expired
        self.governance_manager.finalize_expired_elections()

        active_elections = self.governance_manager.active_elections
        my_id = p2p_service.local_node.node_id if p2p_service.local_node else None
        if not my_id:
            return

        logger.debug(f"Governance Monitor: Checking {len(active_elections)} active elections...")
        found_new = False

        # 1. Check active elections for agent votes
        for eid, election in active_elections.items():
            if election.election_type != ElectionType.PROPOSAL_VOTE:
                continue

            if my_id in election.votes:
                continue

            if eid in self.notified_governance_ids:
                continue

            proposal_id = election.proposal_id
            proposal = self.governance_manager.proposals.get(proposal_id)
            if not proposal:
                logger.warning(
                    f"Governance Monitor: Election {eid} found but proposal {proposal_id} is missing."
                )
                continue

            logger.info(
                f"Governance Monitor: New unhandled proposal detected: {proposal_id}. Awakening agent..."
            )

            poke_msg = InboundMessage(
                channel="internal",
                sender_id="system",
                session_id="resident",
                content=(
                    f"[治理监控]: 系统检测到一项新的社区提案 (ID: {proposal_id}) 需要您的评审。\n"
                    f"提案发起人: {proposal.initiator_id[:8]}\n"
                    f"提案内容: {proposal.content}\n"
                    f"投票截止日期: {election.end_time}\n"
                    f"所在小组: {proposal.group_id}\n\n"
                    f"[自治指令]: 请评估该提案的价值和风险。您可以直接调用 `cast_vote` 工具进行投票，或者如果您认为该提案需要更深入的研究，请使用 `publish_research` 发表您的专业见解以引导社区共识。"
                ),
            )

            asyncio.create_task(self._run_ralph_wiggum_loop(poke_msg))
            self.notified_governance_ids.add(eid)
            found_new = True

        # 2. Check finished elections for pending payouts - NOTIFY ONLY, do NOT auto-execute
        # Rewards must be manually distributed by core nodes via execute_governance_payout()
        finished_elections = self.governance_manager.finished_elections
        for eid, election in list(finished_elections.items()):
            if election.payout_status != "pending":
                continue

            notify_key = f"payout_{eid}"
            if notify_key in self.notified_governance_ids:
                continue

            # Calculate expected payout amount for notification purposes only
            tally = election.tally()
            payout_amount = election.payout_amount
            payout_recipient = election.initiator_id

            if election.election_type == ElectionType.RESEARCH_EVALUATION:
                if payout_amount <= 0:
                    # Calculate from average score if not set
                    avg_score = tally.get("average_amount", 0.0)
                    if avg_score >= 4.0:
                        payout_amount = 200.0
                    elif avg_score >= 3.0:
                        payout_amount = 100.0
                    elif avg_score >= 2.0:
                        payout_amount = 50.0
                    else:
                        election.payout_status = "no_reward"
                        self.governance_manager.save_state()
                        continue
                    # Store calculated amount
                    election.payout_amount = payout_amount
                    self.governance_manager.save_state()

            elif election.election_type == ElectionType.PROPOSAL_VOTE:
                if not tally.get("passed", False):
                    election.payout_status = "no_reward"
                    self.governance_manager.save_state()
                    continue
                if payout_amount <= 0:
                    proposal = self.governance_manager.proposals.get(election.proposal_id)
                    if proposal:
                        import re
                        match = re.search(r'(?:budget|funding|reward|金额|金額|预算):\s*(\d+(?:\.\d+)?)', proposal.content, re.IGNORECASE)
                        if match:
                            payout_amount = float(match.group(1))
                            election.payout_amount = payout_amount
                            self.governance_manager.save_state()
                        else:
                            election.payout_status = "no_reward"
                            self.governance_manager.save_state()
                            continue
                    else:
                        election.payout_status = "no_reward"
                        self.governance_manager.save_state()
                        continue
            else:
                election.payout_status = "no_reward"
                self.governance_manager.save_state()
                continue

            # === NOTIFY ONLY: Do NOT auto-execute payout ===
            # Core nodes must manually trigger payout via execute_governance_payout()
            logger.info(
                f"Governance Monitor: Pending payout notification for election {eid} ({election.election_type.value}): "
                f"Recipient={payout_recipient[:8]}, Amount={payout_amount}, Attempts={election.payout_attempts}/{election.max_payout_attempts}"
            )

            payout_poke_msg = InboundMessage(
                channel="internal",
                sender_id="system",
                session_id="resident",
                content=(
                    f"[治理与资金监控]: 检测到一项待发放的奖励 (选举ID: {eid})。\n"
                    f"类型: {election.election_type.value}\n"
                    f"受益人: {payout_recipient[:8]} (Node ID: {payout_recipient})\n"
                    f"奖励金额: {payout_amount} STATER\n"
                    f"发放尝试: {election.payout_attempts}/{election.max_payout_attempts}\n\n"
                    f"[重要]: 奖励发放需由核心节点(Core Nodes)手动执行。\n"
                    f"核心节点可调用 `execute_governance_payout(election_id='{eid}')` 来执行发放。\n"
                    f"非核心节点无权执行此操作。"
                ),
            )

            asyncio.create_task(self._run_ralph_wiggum_loop(payout_poke_msg))
            self.notified_governance_ids.add(notify_key)
            found_new = True

        if found_new:
            self._save_system_state()

    async def get_latest_archive_report(self) -> dict:
        if not self.archive_manager:
            return {}
        return self.archive_manager.generate_report()

    async def handle_p2p_handoff(self, sender_id: str, payload: dict):
        """Process incoming task handoff from another agent."""
        handoff_id = payload.get("handoff_id")
        task = payload.get("task")
        context = payload.get("context", "")
        inputs = payload.get("inputs", {})

        logger.info(f"Received Task Handoff {handoff_id} from {sender_id}: {task}")

        # 1. Internal Log
        await self.message_bus.publish_outbound(
            OutboundMessage(
                channel="gateway",
                session_id="system",
                content=f"Delegated Task Received: {task}",
                type="thought",
                metadata={"handoff_id": handoff_id, "sender_id": sender_id},
            )
        )

        # 2. Resolve Task using standard Agent Flow
        prompt = f"""
        [DELEGATED TASK from {sender_id}]
        Objective: {task}
        Context: {context}
        Inputs: {json.dumps(inputs)}
        
        Execute this task and provide a concise result.
        """

        try:
            result_content = await self.process_directed_task(prompt)

            # 3. Send Result Back
            result_payload = {
                "type": "task_result",
                "handoff_id": handoff_id,
                "output": result_content,
            }
            await self.send_p2p_message(sender_id, result_payload)
            logger.info(f"Sent Task Result for {handoff_id} back to {sender_id}")

        except Exception as e:
            logger.error(f"Error executing handoff {handoff_id}: {e}")
            await self.send_p2p_message(
                sender_id, {"type": "task_result", "handoff_id": handoff_id, "error": str(e)}
            )

    async def process_directed_task(self, prompt: str) -> str:
        """Run the agent on a specific task prompt."""
        # For now, simulate execution. In reality, this would trigger a clean chain run.
        return f"Executed: {prompt[:100]}... [SIMULATED SUCCESS]"

    async def handle_p2p_result(self, sender_id: str, payload: dict):
        """Process result from a previously delegated task."""
        handoff_id = payload.get("handoff_id")
        output = payload.get("output")
        error = payload.get("error")

        logger.info(f"Received Task Result for {handoff_id} from {sender_id}")

        msg = (
            f"Task Result ({handoff_id}): {output}"
            if not error
            else f"Task Error ({handoff_id}): {error}"
        )
        await self.message_bus.publish_outbound(
            OutboundMessage(
                channel="gateway",
                session_id="system",
                content=msg,
                type="thought",
                metadata={"handoff_id": handoff_id, "sender_id": sender_id},
            )
        )

    async def _system_health_monitor(self):
        """Periodic job to scan logs for errors and trigger autonomous repair."""
        log_path = "backend/data/logs/p2p_network.log"
        if not os.path.exists(log_path):
            return

        try:
            with open(log_path, encoding="utf-8") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 10000))
                chunk = f.read()

            lines = chunk.splitlines()
            # Only look for actual ERROR or CRITICAL lines
            errors = [l for l in lines if "ERROR: " in l or "CRITICAL: " in l]

            for error in errors:
                # Basic signature extraction
                sig = ""
                if " - ERROR: " in error:
                    sig = error.split(" - ERROR: ", 1)[1][:100]
                elif " - CRITICAL: " in error:
                    sig = error.split(" - CRITICAL: ", 1)[1][:100]
                else:
                    sig = error[-100:]

                if sig and sig not in self.notified_error_signatures:
                    logger.info(f"Self-Reflection: Detected new error signature: {sig}")
                    self.notified_error_signatures.add(sig)
                    self._save_system_state()

                    # Notify the resident via thought
                    await self.message_bus.publish_outbound(
                        OutboundMessage(
                            channel="gateway",
                            session_id="system_health",
                            content=f"System Health Alert: Error signature detected: {sig}. Launching autonomous repair sub-agent...",
                            type="thought",
                        )
                    )

                    # Launch the sub-agent task
                    asyncio.create_task(self._run_autonomous_repair_subagent(error))

                    # Only notify one new error per scan to avoid overwhelming the agent
                    break

        except Exception as e:
            logger.error(f"Error in system_health_monitor job: {e}")

    async def _run_autonomous_repair_subagent(self, error_message: str):
        """Invoke a specialized sub-agent to diagnose and fix a system error."""
        if not self.api_key or os.environ.get("ENABLE_SELF_HEALING", "false").lower() not in (
            "true",
            "1",
            "yes",
        ):
            return

        logger.info(f"Sub-Agent: Starting autonomous repair for error: {error_message[:100]}...")

        try:
            # 1. Initialize specialized LLM for repair
            raw_repair_llm = ChatOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                model=self.model,
                temperature=0.2,  # Lower temperature for precision repair
            )
            url_str = (self.base_url or "").lower()
            enable_parallel = "api.openai.com" in url_str or "aliyuncs.com" in url_str or "dashscope" in url_str
            if enable_parallel:
                repair_llm = raw_repair_llm.bind_tools(REPAIR_TOOLS)
            else:
                try:
                    repair_llm = raw_repair_llm.bind_tools(REPAIR_TOOLS, parallel_tool_calls=False)
                except Exception:
                    repair_llm = raw_repair_llm.bind_tools(REPAIR_TOOLS)

            repair_tools_map = {t.name: t for t in REPAIR_TOOLS}

            # 2. Build initial context
            messages = [
                SystemMessage(content=SELF_HEALING_SUBAGENT_PROMPT),
                HumanMessage(
                    content=f"The following error was detected in your logs:\n\n{error_message}\n\nPlease analyze and repair it."
                ),
            ]

            # 3. Execution Loop (simplified ReAct)
            max_iters = 10
            for i in range(max_iters):
                try:
                    response = await repair_llm.ainvoke(messages)
                    messages.append(response)

                    # Extract Reasoning/Thought
                    thought = ""
                    if "reasoning_content" in response.additional_kwargs:
                        thought = response.additional_kwargs["reasoning_content"]
                    elif response.content:
                        thought = response.content

                    # Emit thought to UI
                    if thought:
                        await self.message_bus.publish_outbound(
                            OutboundMessage(
                                channel="gateway",
                                session_id="system_health",
                                content=f"[Repair Sub-Agent] {thought}",
                                type="thought",
                            )
                        )

                    if not response.tool_calls:
                        break

                    for tc in response.tool_calls:
                        t_name = tc["name"]
                        t_args = tc["args"]
                        t_id = tc["id"]

                        await self.message_bus.publish_outbound(
                            OutboundMessage(
                                channel="gateway",
                                session_id="system_health",
                                content=f"[Repair Sub-Agent] Invoking {t_name}...",
                                type="tool_call",
                                metadata={"tool": t_name, "args": t_args},
                            )
                        )

                        if t_name in repair_tools_map:
                            logger.info(f"Repair Sub-Agent Invoking Tool: {t_name}")
                            output = await repair_tools_map[t_name].ainvoke(t_args)
                            messages.append(
                                ToolMessage(tool_call_id=t_id, content=str(output), name=t_name)
                            )
                        else:
                            messages.append(
                                ToolMessage(
                                    tool_call_id=t_id,
                                    content=f"Error: Tool {t_name} not found.",
                                    name=t_name,
                                )
                            )
                except Exception as e:
                    logger.error(f"Error in repair sub-agent iteration {i}: {e}")
                    break

            logger.info("Sub-Agent: Autonomous repair task completed.")
        except Exception as e:
            logger.error(f"Failed to run autonomous repair sub-agent: {e}")

    async def run_coding_subagent(
        self, task_description: str, target_path: str, context_notes: str = ""
    ) -> str:
        """Invoke a specialized Coding Sub-Agent to write/modify Python code, verify AST syntax, and confirm file existence."""
        if not self.api_key:
            return "Error: LLM API Key is not configured."

        import hashlib
        from ..agent.coding_fleet import coding_fleet
        from ..agent.tool_registry import tool_registry

        session_id = f"coding_{hashlib.md5(target_path.encode()).hexdigest()[:8]}"
        session = coding_fleet.create_session(session_id, task_description, target_path)

        logger.info(f"Coding Sub-Agent (Session: {session_id}): Starting task for target: {target_path}")

        async with coding_fleet.get_semaphore():
            file_lock = await coding_fleet.acquire_file_lock(target_path)
            async with file_lock:
                try:
                    # 1. Initialize dedicated LLM with low temperature
                    raw_coding_llm = ChatOpenAI(
                        base_url=self.base_url,
                        api_key=self.api_key,
                        model=self.model,
                        temperature=0.1,
                    )
                    url_str = (self.base_url or "").lower()
                    enable_parallel = "api.openai.com" in url_str or "aliyuncs.com" in url_str or "dashscope" in url_str
                    if enable_parallel:
                        coding_llm = raw_coding_llm.bind_tools(CODING_TOOLS)
                    else:
                        try:
                            coding_llm = raw_coding_llm.bind_tools(CODING_TOOLS, parallel_tool_calls=False)
                        except Exception:
                            coding_llm = raw_coding_llm.bind_tools(CODING_TOOLS)

                    coding_tools_map = {t.name: t for t in CODING_TOOLS}

                    # Ensure parent directory exists
                    abs_target_path = os.path.abspath(target_path)
                    os.makedirs(os.path.dirname(abs_target_path), exist_ok=True)

                    # 2. Build initial context
                    user_prompt = (
                        f"### TASK ASSIGNMENT ###\n"
                        f"Task Description: {task_description}\n"
                        f"Target File Path: {target_path} (Absolute: {abs_target_path})\n"
                        f"Context/Notes: {context_notes}\n\n"
                        f"INSTRUCTIONS:\n"
                        f"1. Read any necessary files or inspect data if needed.\n"
                        f"2. Write complete, well-commented Python code to '{target_path}'.\n"
                        f"3. Run 'check_python_syntax' on '{target_path}' to verify zero AST syntax errors.\n"
                        f"4. Run 'verify_file_exists' on '{target_path}' to verify disk file existence.\n"
                    )

                    messages = [
                        SystemMessage(content=CODING_SUBAGENT_PROMPT),
                        HumanMessage(content=user_prompt),
                    ]

                    syntax_verified = False
                    file_exists_verified = False
                    max_iters = 15

                    for i in range(max_iters):
                        try:
                            response = await coding_llm.ainvoke(messages)
                            messages.append(response)

                            # Extract reasoning/thought
                            thought = ""
                            if "reasoning_content" in response.additional_kwargs:
                                thought = response.additional_kwargs["reasoning_content"]
                            elif response.content:
                                thought = response.content

                            if thought:
                                await self.message_bus.publish_outbound(
                                    OutboundMessage(
                                        channel="gateway",
                                        session_id="coding_subagent",
                                        content=f"💻 [编程子智能体] {thought}",
                                        type="thought",
                                    )
                                )

                            if not response.tool_calls:
                                break

                            for tc in response.tool_calls:
                                t_name = tc["name"]
                                t_args = tc["args"]
                                t_id = tc["id"]

                                await self.message_bus.publish_outbound(
                                    OutboundMessage(
                                        channel="gateway",
                                        session_id="coding_subagent",
                                        content=f"💻 [编程子智能体] Invoking {t_name}...",
                                        type="tool_call",
                                        metadata={"tool": t_name, "args": t_args},
                                    )
                                )

                                if t_name in coding_tools_map:
                                    logger.info(f"Coding Sub-Agent Invoking Tool: {t_name} with {t_args}")
                                    meta = tool_registry.get_meta(t_name)
                                    if meta:
                                        output = await tool_registry.execute(t_name, target_file=target_path, **t_args)
                                    else:
                                        output = await coding_tools_map[t_name].ainvoke(t_args)
                                    out_str = str(output)

                                    if t_name == "check_python_syntax" and "PASSED" in out_str:
                                        syntax_verified = True
                                    if t_name == "verify_file_exists" and "VERIFICATION_PASSED" in out_str:
                                        file_exists_verified = True

                                    messages.append(
                                        ToolMessage(tool_call_id=t_id, content=out_str, name=t_name)
                                    )
                                else:
                                    messages.append(
                                        ToolMessage(
                                            tool_call_id=t_id,
                                            content=f"Error: Tool {t_name} not found.",
                                            name=t_name,
                                        )
                                    )

                            # Update session checkpoint
                            coding_fleet.update_checkpoint(
                                session_id,
                                checkpoint=f"iteration_{i+1}",
                                created_files=[target_path] if os.path.exists(abs_target_path) else [],
                                status="running"
                            )

                        except Exception as iter_err:
                            logger.error(f"Error in coding sub-agent iteration {i}: {iter_err}")
                            break

                    # Final physical verification check
                    final_exists = os.path.exists(abs_target_path) and os.path.getsize(abs_target_path) > 0

                    if final_exists and (syntax_verified or file_exists_verified):
                        coding_fleet.update_checkpoint(
                            session_id,
                            checkpoint="completed",
                            created_files=[target_path],
                            status="completed"
                        )
                        report = (
                            f"SUCCESS: Coding Sub-Agent completed task.\n"
                            f"File Location: {target_path} (Absolute: {abs_target_path})\n"
                            f"File Size: {os.path.getsize(abs_target_path)} bytes\n"
                            f"AST Syntax Verified: {'YES' if syntax_verified else 'CHECKED_ON_DISK'}\n"
                            f"Status: Code is saved and verified ready for resident execution."
                        )
                        logger.info(f"Coding Sub-Agent: Task completed successfully for {target_path}")
                        return report
                    elif final_exists:
                        try:
                            import ast

                            with open(abs_target_path, "r", encoding="utf-8") as f:
                                ast.parse(f.read())
                            coding_fleet.update_checkpoint(
                                session_id,
                                checkpoint="completed_ast_fallback",
                                created_files=[target_path],
                                status="completed"
                            )
                            report = (
                                f"SUCCESS: Coding Sub-Agent completed task.\n"
                                f"File Location: {target_path}\n"
                                f"File Size: {os.path.getsize(abs_target_path)} bytes\n"
                                f"AST Syntax Verified: YES (Fallback check passed)\n"
                                f"Status: Code is saved and verified ready for resident execution."
                            )
                            return report
                        except Exception as syn_e:
                            coding_fleet.update_checkpoint(session_id, checkpoint="failed_ast", status="failed")
                            return f"FAILED: Code file was created at {target_path} but failed AST syntax check: {syn_e}"
                    else:
                        coding_fleet.update_checkpoint(session_id, checkpoint="failed_no_file", status="failed")
                        return f"FAILED: Coding Sub-Agent did not generate a non-empty file at target path '{target_path}'."

                except Exception as e:
                    coding_fleet.update_checkpoint(session_id, checkpoint=f"error_{e}", status="failed")
                    logger.error(f"Failed to run coding sub-agent: {e}")
                    return f"Error executing coding sub-agent: {e!s}"

    async def check_unhandled_messages(self):
        """Watchdog: Scan all active sessions for unhandled inbound messages older than 5 minutes."""
        try:
            from ..bus.events import InboundMessage

            now = datetime.now(UTC)
            five_minutes_ago = now - timedelta(minutes=5)

            # Gather all unique session IDs from history
            session_ids = set()
            for msg in self.history:
                sid = getattr(msg, "session_id", None)
                if sid and sid not in ["resident", "system", "system_health", "global"]:
                    session_ids.add(sid)

            for sid in session_ids:
                # Find the last inbound message for this session
                last_inbound = None
                for msg in reversed(self.history):
                    if (
                        getattr(msg, "session_id", None) == sid
                        and getattr(msg, "sender", "") != "agent"
                    ):
                        last_inbound = msg
                        break

                if not last_inbound:
                    continue

                # Check if the last message in this session is from the agent (i.e., already handled)
                last_msg_in_session = None
                for msg in reversed(self.history):
                    if getattr(msg, "session_id", None) == sid:
                        last_msg_in_session = msg
                        break

                if last_msg_in_session and getattr(last_msg_in_session, "sender", "") == "agent":
                    continue  # Already responded

                # Check if the last inbound is older than 5 minutes
                msg_ts = getattr(last_inbound, "timestamp", None)
                if msg_ts:
                    if msg_ts.tzinfo is None:
                        msg_ts = msg_ts.replace(tzinfo=UTC)
                    if msg_ts < five_minutes_ago:
                        msg_id = getattr(last_inbound, "id", "unknown")
                        if msg_id in self.notified_watchdog_ids:
                            continue  # Already triggered for this message

                        logger.warning(
                            f"[WATCHDOG] Unhandled message detected in session {sid[:8]}... (msg_id={msg_id}, age={(now - msg_ts).total_seconds():.0f}s). Triggering immediate processing."
                        )
                        self.notified_watchdog_ids.add(msg_id)

                        # Trigger immediate processing via pipeline
                        poke_msg = InboundMessage(
                            channel="p2p",
                            sender_id=getattr(last_inbound, "sender", sid),
                            session_id=sid,
                            content=getattr(last_inbound, "content", ""),
                            metadata={"watchdog": True, "original_msg_id": msg_id},
                        )
                        asyncio.create_task(self._run_ralph_wiggum_loop(poke_msg))

            # Prune old watchdog IDs (keep last 200)
            if len(self.notified_watchdog_ids) > 200:
                self.notified_watchdog_ids = set(list(self.notified_watchdog_ids)[-100:])

        except Exception as e:
            logger.error(f"Error in check_unhandled_messages watchdog: {e}")

    async def gossip_state_sync(self):
        """
        Periodic Gossip state synchronization for eventual consistency.
        Requests state sync from group members to catch missed proposals/votes.
        """
        try:
            if not p2p_service._initialized or not self.governance_manager:
                return

            # Get all groups the local node is a member of
            my_groups = p2p_service.get_my_groups()
            if not my_groups:
                return

            logger.info(f"[GossipSync] Starting periodic state sync for {len(my_groups)} groups")

            for group_id in my_groups:
                try:
                    # Request state sync from this group
                    await p2p_service.network_manager.request_state_sync(group_id)
                    # Small delay between groups to avoid flooding
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.debug(f"[GossipSync] Failed to sync group {group_id}: {e}")

            logger.info(f"[GossipSync] Completed state sync for {len(my_groups)} groups")

        except Exception as e:
            logger.error(f"Error in gossip_state_sync: {e}")

    async def trigger_system_restart(self, reason: str):
        """Writes a restart signal file for the code supervisor to process."""
        logger.warning(f"SYSTEM RESTART REQUESTED BY AGENT. Reason: {reason}")

        import json
        import os

        signal_path = self.backend_dir / "data" / "code_updates" / "restart.signal"
        os.makedirs(signal_path.parent, exist_ok=True)

        with open(signal_path, "w") as f:
            f.write(json.dumps({"reason": reason, "timestamp": datetime.now(UTC).isoformat()}))

        logger.info(f"Restart signal written to {signal_path}. Supervisor will process shortly.")
        return True


# Standalone Proxy Functions for Scheduler
# These avoid pickling the 'self' (AgentService instance) which contains the unpickleable scheduler.
# -------------------------------------------------------------------------


async def trigger_scheduled_task_proxy():
    """Proxy for agent_service.trigger_scheduled_task"""
    if agent_service:
        await agent_service.trigger_scheduled_task()


async def trigger_adhoc_task_proxy():
    """Proxy for agent_service.trigger_adhoc_task"""
    if agent_service:
        await agent_service.trigger_adhoc_task()


async def process_network_inbox_proxy():
    """Proxy for agent_service.process_network_inbox"""
    if agent_service:
        await agent_service.process_network_inbox()


async def sync_network_proxy():
    """Proxy for agent_service.sync_network"""
    if agent_service:
        await agent_service.sync_network()


async def run_consolidation_proxy():
    """Proxy for agent_service.consolidation_service.run_daily_consolidation"""
    if agent_service and agent_service.consolidation_service:
        await agent_service.consolidation_service.run_daily_consolidation()


async def run_archiving_proxy():
    """Proxy for agent_service.run_archiving"""
    if agent_service:
        await agent_service.run_archiving()


async def check_tasks_monitor_proxy():
    """Proxy for agent_service.check_tasks_monitor"""
    if agent_service:
        await agent_service.check_tasks_monitor()


async def check_governance_proposals_proxy():
    """Proxy for agent_service.check_governance_proposals"""
    if agent_service:
        await agent_service.check_governance_proposals()


async def retry_failed_messages_proxy():
    """Proxy for agent_service._retry_failed_messages"""
    if agent_service:
        await agent_service._retry_failed_messages()


async def system_health_monitor_proxy():
    """Proxy for agent_service._system_health_monitor"""
    if agent_service:
        await agent_service._system_health_monitor()


async def check_unhandled_messages_proxy():
    """Proxy for agent_service.check_unhandled_messages"""
    if agent_service:
        await agent_service.check_unhandled_messages()


async def gossip_state_sync_proxy():
    """Proxy for agent_service.gossip_state_sync"""
    if agent_service:
        await agent_service.gossip_state_sync()


async def flush_throttled_messages_proxy():
    """Proxy for agent_service._flush_throttled_messages"""
    if agent_service:
        await agent_service._flush_throttled_messages()


async def code_supervisor_proxy():
    """Integrated code supervisor: polls pending.json and processes code updates."""
    if not agent_service:
        return
    import json
    from pathlib import Path
    from datetime import datetime

    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    WATCH_FILE = PROJECT_ROOT / "backend" / "data" / "code_updates" / "pending.json"

    if not WATCH_FILE.exists():
        return

    logger.info(f"[CodeSupervisor] Detected pending update at {WATCH_FILE}")
    try:
        processing_file = WATCH_FILE.with_suffix(".json.processing")
        if WATCH_FILE.exists():
            WATCH_FILE.rename(processing_file)

        import sys
        scripts_dir = str(PROJECT_ROOT / "backend" / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import code_supervisor

        with open(processing_file, encoding="utf-8") as f:
            request = json.load(f)

        success = await asyncio.to_thread(code_supervisor.process_update, request)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if success:
            processing_file.rename(processing_file.parent / f"success_{timestamp}.json")
        else:
            processing_file.rename(processing_file.parent / f"failed_{timestamp}.json")
    except Exception as e:
        logger.error(f"[CodeSupervisor] Error processing code update: {e}")
        if WATCH_FILE.exists():
            try:
                WATCH_FILE.unlink()
            except Exception:
                pass


async def run_literature_watcher_proxy():
    """Proxy for agent_service.run_literature_watcher"""
    if agent_service:
        await agent_service.run_literature_watcher()


async def run_evolution_watcher_proxy():
    """Proxy for agent_service.run_evolution_watcher"""
    if agent_service:
        await agent_service.run_evolution_watcher()


async def compress_history_proxy():
    """Proxy for periodic history compression."""
    if agent_service and agent_service.context_manager:
        try:
            result = await agent_service.context_manager.compress_archived_history()
            if result["compressed_count"] > 0:
                logger.info(
                    f"History compression job complete: {result['compressed_count']} messages → "
                    f"{result['summary_chars']} chars summary."
                )
        except Exception as e:
            logger.error(f"History compression job failed: {e}")


async def nightly_maintenance_pipeline_proxy():
    """Proxy for agent_service.run_nightly_maintenance_pipeline"""
    if agent_service:
        await agent_service.run_nightly_maintenance_pipeline()


agent_service = AgentService()
