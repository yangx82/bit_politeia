import asyncio
import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Set
from ..models.schemas import Message, AgentStatus, P2PMessage
from .crypto_service import crypto_service
from .transaction_manager import transaction_manager
from .p2p_service import p2p_service
from .group_service import group_service
from .group_service import group_service
from ..bus.queue import message_bus
from ..bus.events import InboundMessage, OutboundMessage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Placeholder for LangChain
# from langchain.llms import OpenAI 

logger = logging.getLogger(__name__)
p2p_logger = logging.getLogger("p2p_network")

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from ..agent.prompts import AGENT_SYSTEM_PROMPT
from ..agent.tools import AGENT_TOOLS
from ..agent.tools_meta import create_tool_tool
from .skill_manager import skill_manager
from ..agent.context import ContextBuilder
from ..p2p_community.governance import GovernanceManager, Vote, ElectionType
import json

from ..p2p_community.economy import Ledger, Transaction
from ..p2p_community.reputation import ReputationManager, Evaluation
from ..p2p_community.blockchain import ArchiveManager
from .resident_memory_service import ResidentMemory, ResidentReporter
from .memory_store import memory_store
from .knowledge_base import knowledge_base

from .consolidation import ConsolidationService
from .task_manager import TaskManager, TaskStatus

class AgentService:
    def __init__(self):
        self.history: list[Message] = []
        self.processed_message_ids: set[str] = set() # For de-duplication
        self.notified_governance_ids: Set[str] = set() # Track proposals shared with agent
        self.notified_error_signatures: Set[str] = set() # Track error signatures for self-reflection
        self._is_processing_inbox = False # Concurrency Guard
        self.status = AgentStatus(is_online=True, reputation=10, balance=100.0)
        self.message_bus = message_bus
        self.resident_bridges: Dict[str, str] = {} # Bridge Name -> Chat/OpenID
        
        # Resolve absolute path to backend/data
        from pathlib import Path
        current_file = Path(__file__).resolve()
        self.backend_dir = current_file.parent.parent.parent
        self.data_dir = self.backend_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Scheduler (Memory-only to avoid DB trigger persistence conflicts with hardcoded boot jobs)
        try:
            job_defaults = {
                'coalesce': True, # Merge multiple missed runs into one
                'max_instances': 3,
                'misfire_grace_time': 60 # Generous grace time to prevent skipping on boot load
            }
            self.scheduler = AsyncIOScheduler(job_defaults=job_defaults)
            logger.info(f"Scheduler initialized with Memory persistence.")
        except Exception as e:
            logger.error(f"Failed to init scheduler: {e}")
            self.scheduler = AsyncIOScheduler()

        # Scheduler will be started in start_scheduler() called by main.py lifespan
        self.base_url = None
        self.api_key = None
        self.llm = None
        
        # Identity Config Path
        self.config_path = "agent_config.json"
        
        # P2P Reply Delay Default
        from dotenv import load_dotenv
        import os
        load_dotenv()
        self.p2p_reply_delay = 60 
        
        # Initialization logic (Moved to __init__)
        self.tools_map = {t.name: t for t in AGENT_TOOLS}
        self.governance_manager = None 
        self.reputation_manager = None
        self.archive_manager = None
        self.ledger = Ledger() 
        self.resident_memory = ResidentMemory() 
        self.reporter = None 
        self.research_field = "AI Governance"
        self.task_manager = TaskManager()
        self.context_builder = ContextBuilder(task_manager=self.task_manager)
        self.consolidation_service = ConsolidationService(self)
        
        # Identity Defaults
        self.name = "Anonym"
        self.personality = "Professional and helpful"
        self.agent_language = "中文"

        # Hydrate History and System State from Disk
        self._hydrate_history()
        self._hydrate_system_state()
        self.verbose_llm = False

    def start_scheduler(self):
        """Start the scheduler and add background jobs."""
        try:
            # Add jobs only once
            if not getattr(self, '_jobs_added', False):
                self.scheduler.add_job("app.services.agent_service:trigger_scheduled_task_proxy", 'interval', hours=12, misfire_grace_time=60, id="periodic_brief_job", replace_existing=True) 
                self.scheduler.add_job("app.services.agent_service:process_network_inbox_proxy", 'interval', seconds=30, misfire_grace_time=15, id="network_inbox_job", replace_existing=True) 
                self.scheduler.add_job("app.services.agent_service:sync_network_proxy", 'interval', minutes=2, id="sync_network_job", replace_existing=True) 
                self.scheduler.add_job("app.services.agent_service:run_consolidation_proxy", 'cron', hour=2, minute=0, id="nightly_consolidation_job", replace_existing=True)
                self.scheduler.add_job("app.services.agent_service:check_tasks_monitor_proxy", 'interval', minutes=5, next_run_time=datetime.now(timezone.utc), id="task_monitor_job", replace_existing=True)
                self.scheduler.add_job("app.services.agent_service:check_governance_proposals_proxy", 'interval', minutes=10, next_run_time=datetime.now(timezone.utc), id="governance_monitor_job", replace_existing=True)
                self.scheduler.add_job("app.services.agent_service:retry_failed_messages_proxy", 'interval', minutes=10, next_run_time=datetime.now(timezone.utc), id="retry_messages_job", replace_existing=True)
                self.scheduler.add_job("app.services.agent_service:self_reflection_proxy", 'interval', minutes=15, id="self_reflection_job", replace_existing=True)
                self._jobs_added = True
                logger.info("Scheduler background jobs registered successfully.")

            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("Scheduler started successfully.")
            else:
                logger.info("Scheduler already running, jobs ensured.")
        except Exception as e:
            logger.error(f"Failed to start scheduler/jobs: {e}")

    async def _retry_failed_messages(self):
        """10-minute automatic retry for failed/pending P2P messages."""
        logger.info("Starting automatic retry for failed/pending P2P messages...")
        
        # 1. Find candidates (last 2 hours for safety, but focus on the 10min window)
        # focus on the 10min window
        now = datetime.now(timezone.utc)
        ten_minutes_ago = now - timedelta(minutes=10)
        one_minute_ago = now - timedelta(minutes=1)
        
        # We only retry messages that failed recently (within the last 10 mins).
        # We use a 1-minute grace period to avoid double-sending messages that are still connecting.
        retry_candidates = []
        for msg in self.history:
            if msg.sender == "agent" and msg.status in ["failed", "pending", None]:
                if ten_minutes_ago <= msg.timestamp <= one_minute_ago:
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
                # Avoid retrying if it's not a P2P session (resident or system)
                if recipient_id in ["resident", "system"] or "[" in recipient_id:
                    continue
                    
                logger.info(f"Triggering automatic retry for message {msg.id} to {recipient_id}")
                await self.send_p2p_message(
                    recipient_id=recipient_id,
                    content=msg.content,
                    is_retry=True,
                    original_msg_id=msg.id
                )
            except Exception as e:
                logger.error(f"Failed to retry message {msg.id}: {e}")

    # ... remaining of file ...

    def _get_host_info(self) -> str:
        """Detect current host environment (OS, Shell, CWD) for the agent."""
        import platform
        import os
        
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
            info += "- **Constraint**: Use Windows-compatible commands (e.g., `dir` instead of `ls`).\n"
        else:
            info += "- **File System**: POSIX-style paths (e.g., /home/user/...)\n"
            info += "- **Constraint**: Use POSIX-compatible commands (e.g., `ls` instead of `dir`).\n"
            
        return info
    
    def _normalize_session_id(self, sid: str) -> str:
        """Standardize Session/Chat IDs to Hex 64-char format if it looks like a P2P ID."""
        if not sid: return sid
        # Strip potential prefixes
        if sid.startswith("[p2p] "):
            sid = sid[6:]
        # If it's a known name, try to resolve to Node ID
        if p2p_service._initialized and p2p_service.network_manager:
            for node_id, node in p2p_service.network_manager.nodes.items():
                if node.name == sid:
                    return node_id
        return sid


    async def configure_agent(self, base_url: str, api_key: str, model: str = "gpt-4o", research_field: str = "AI Governance", bootstrap_url: str = None, verbose_llm: bool = False, bootstrap_verify: bool = True, name: str = None, personality: str = None, p2p_reply_delay: int = 5, agent_language: str = "中文", ralph_wiggum_mode: bool = False):
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
        self.agent_language = agent_language
        self.ralph_wiggum_mode = ralph_wiggum_mode
        
        # Save to JSON
        self._save_config({
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
            "ralph_wiggum_mode": self.ralph_wiggum_mode
        })
        
        logger.info(f"Agent Configured: Name={self.name}, Model={model}")
        
        # Persist configuration to .env
        try:
            from dotenv import set_key, find_dotenv
            env_file = find_dotenv()
            if not env_file:
                # Create .env if not found
                import os
                # Force standard path: backend/.env or just .env in CWD
                # Ideally, we should look for where managing script is running
                env_file = ".env"
                if not os.path.exists(env_file):
                     open(env_file, 'a').close()
            
            set_key(env_file, "AGENT_BASE_URL", self.base_url)
            set_key(env_file, "AGENT_API_KEY", self.api_key)
            set_key(env_file, "AGENT_MODEL", self.model)
            set_key(env_file, "AGENT_RESEARCH_FIELD", self.research_field)
            # if bootstrap_url:
            set_key(env_file, "AGENT_BOOTSTRAP_URL", self.bootstrap_url)
            set_key(env_file, "AGENT_VERBOSE_LLM", "true" if self.verbose_llm else "false")
            set_key(env_file, "AGENT_BOOTSTRAP_VERIFY", "true" if self.bootstrap_verify else "false")
            set_key(env_file, "AGENT_NAME",self.name)
            set_key(env_file, "AGENT_PERSONALITY",self.personality)
            set_key(env_file, "AGENT_P2P_REPLY_DELAY", str(self.p2p_reply_delay))
            set_key(env_file, "AGENT_LANGUAGE", self.agent_language)
            set_key(env_file, "AGENT_RALPH_WIGGUM_MODE", "true" if self.ralph_wiggum_mode else "false")
            logger.info(f"Settings saved to {env_file}")
        except Exception as e:
            logger.error(f"Failed to save configuration to .env: {e}")
        
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
            s.connect(('10.255.255.255', 1))
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
        self.governance_manager = GovernanceManager(node_id, storage_path=gov_path)
        self.reputation_manager = ReputationManager(node_id)
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
            self.ledger.credit(real_node_id, 1000.0)
        
        # Initialize LLM with Tools
        try:
            # Clear proxy env vars that use unsupported schemes (e.g. socks://)
            # httpx (used internally by langchain/OpenAI) doesn't support socks without extras
            import os
            for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 
                              'http_proxy', 'https_proxy', 'all_proxy']:
                if proxy_var in os.environ and 'socks' in os.environ[proxy_var].lower():
                    logger.info(f"Clearing unsupported proxy env var: {proxy_var}={os.environ[proxy_var]}")
                    del os.environ[proxy_var]
            
            # Common fix: Ensure base_url for OpenAI-compatible proxies ends with /v1
            logger.info(f"Initializing ChatOpenAI with base_url: {base_url}")
            
            raw_llm = ChatOpenAI(
                base_url=base_url,
                api_key=api_key,
                model=model, 
                temperature=0.7
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
            
            # Combine standard tools with skill tools
            all_tools = AGENT_TOOLS + skill_tools + [create_tool_tool]
            
            # Update system prompt with skill index (Progressive Disclosure) AND IDENTITY
            skill_index_prompt = skill_manager.get_skill_index()
            
            # INJECT IDENTITY INTO PROMPT
            identity_section = f"\n\nYOUR IDENTITY CONFIGURATION:\nName: {self.name}\nPersonality Guidelines: {self.personality}\n"
            
            # INJECT DYNAMIC HOST INFO
            host_info = self._get_host_info()
            
            self.current_system_prompt = AGENT_SYSTEM_PROMPT + identity_section + host_info + "\n" + skill_index_prompt
            
            self.llm = raw_llm.bind_tools(all_tools)
            self.tools_map = {t.name: t for t in all_tools}
            
            logger.info(f"Agent LLM Initialized. Active Tools: {list(self.tools_map.keys())}")
            
            # Hydrate system state (inbox, de-dup IDs) after potential initialization
            self._hydrate_system_state()
            
        except Exception as e:
            logger.error(f"Failed to initialize Agent LLM: {e}")
            
        return self.status

    # ... (process_message, etc.) ...
    
    def load_config_from_env(self):
        """Load configuration from environment variables."""
        from dotenv import load_dotenv
        load_dotenv()
        import os
        base_url = os.getenv("AGENT_BASE_URL")
        api_key = os.getenv("AGENT_API_KEY")
        model = os.getenv("AGENT_MODEL", "gpt-4o")
        research_field = os.getenv("AGENT_RESEARCH_FIELD", "AI Governance")
        bootstrap_url = os.getenv("AGENT_BOOTSTRAP_URL", "https://bootstrap.bitpoliteia.com")
        verbose_llm = os.getenv("AGENT_VERBOSE_LLM", "true").lower() == "true"
        bootstrap_verify = os.getenv("AGENT_BOOTSTRAP_VERIFY", "true").lower() == "true"
        name = os.getenv("AGENT_NAME", "Anonym")
        personality = os.getenv("AGENT_PERSONALITY", "Professional, helfpful, and humorous")
        p2p_reply_delay = int(os.getenv("AGENT_P2P_REPLY_DELAY", "5"))
        agent_language = os.getenv("AGENT_LANGUAGE", "中文")
        ralph_wiggum_mode = os.getenv("AGENT_RALPH_WIGGUM_MODE", "false").lower() == "true"
        
        # Load identity from JSON config explicitly to override ENV
        json_config = self._load_config()
        name = json_config.get("name", name)
        personality = json_config.get("personality", personality)
        p2p_reply_delay = json_config.get("p2p_reply_delay", p2p_reply_delay)
        agent_language = json_config.get("agent_language", agent_language)
        ralph_wiggum_mode = json_config.get("ralph_wiggum_mode", ralph_wiggum_mode)
            
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
                "agent_language": agent_language,
                "ralph_wiggum_mode": ralph_wiggum_mode
            }
        return None

    # Financial Methods
    async def transfer_funds(self, payee_id: str, amount: float, details: str) -> str:
        if not self.ledger:
            return "Ledger not initialized"
            
        payer_id = self.governance_manager.node_id if self.governance_manager else "unknown"
        tx = self.ledger.create_transaction(payer_id, payee_id, amount, details)
        
        if tx:
            return f"Transfer successful. TX ID: {tx.transaction_id}"
        else:
            return "Transfer failed. Insufficient funds or invalid amount."

    def _load_config(self) -> dict:
        """Load agent configuration from JSON file."""
        import json
        import os
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load agent config: {e}")
        return {}

    def _save_config(self, config: dict):
        """
        Save agent configuration to JSON file.
        excludes sensitive keys that should be in .env
        """
        import json
        
        # Keys to exclude from JSON (they go to .env)
        EXCLUDED_KEYS = {"api_key", "base_url", "bootstrap_url", "model", "research_field"}
        
        try:
            # Merge with existing
            current = self._load_config()
            
            # Update only non-excluded keys
            for k, v in config.items():
                if k not in EXCLUDED_KEYS:
                    current[k] = v
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(current, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save agent config: {e}")

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
        from ..agent.pipeline import PipelineContext, SenseStage, PlanStage, ExecuteStage, ConsolidateStage, RetrospectiveStage, NotifyStage, ArchiveStage
        from ..services.session_service import session_manager
        
        # 0. Get or Create Session
        session = session_manager.get_session(msg.sender_id, msg.channel)
        
        # [ICE WARMUP] Start handshake in background during reasoning/delay
        if msg.sender_id and msg.channel == "p2p":
            asyncio.create_task(p2p_service.warmup_webrtc(msg.sender_id))

        # Refactored P2P Delay: Move delay to cognitive layer (Pipeline Start)
        delay_val = getattr(self, 'p2p_reply_delay', 60)
        
        if msg.channel == "p2p" and delay_val > 0:
            # Calculate remaining delay relative to message timestamp
            # This ensures that the total delay is consistent regardless of transit time.
            now = datetime.now(timezone.utc)
            # If msg.timestamp is offset-naive and now is naive, they compare fine.
            # Assuming both are local or both are UTC.
            target_time = msg.timestamp + timedelta(seconds=delay_val)
            remaining_seconds = (target_time - now).total_seconds()
            
            if remaining_seconds > 0:
                # 1. Notify Gateway that we are thinking (so UI shows status)
                ui_session_id = self._normalize_session_id(msg.session_id)
                await self.message_bus.publish_outbound(OutboundMessage(
                    channel="gateway",
                    session_id=ui_session_id,
                    content=f"... (Finalizing research... {int(remaining_seconds)}s remaining) ...",
                    type="thought"
                ))
                await asyncio.sleep(remaining_seconds)
        #     p2p_logger.info(f"DEBUG: Delay FINISHED for {msg.sender_id}")
        # elif msg.channel == "p2p":
        #     p2p_logger.info(f"DEBUG: P2P Delay SKIPPED. Reason: msg.channel={msg.channel}, delay_val={delay_val}")
        # else:
        #     p2p_logger.info(f"DEBUG: Pipeline delay NOT APPLICABLE for channel={msg.channel}")

        context = PipelineContext(session=session, input_message=msg)
        
        stages = [
            SenseStage(),
            PlanStage(),
            ExecuteStage(),
            ConsolidateStage(),
            RetrospectiveStage(),
            NotifyStage(),
            ArchiveStage()
        ]
        
        logger.info(f"Starting pipeline execution for user {msg.sender_id} (Session: {session.session_id})")
        
        # 1. Preliminary Stage: Sense
        await stages[0].run(context, self)
        
        # 2. Main Loop: Plan & Execute (ReAct)
        max_iterations = 50
        iteration = 0
        while not context.stop_execution and iteration < max_iterations:
            iteration += 1
            await stages[1].run(context, self) # Plan
            if not context.stop_execution:
                await stages[2].run(context, self) # Execute
        
        # 3. Wrapping Up: Consolidate, Retrospective, Notify, Archive
        await stages[3].run(context, self) # Consolidate
        session_manager.save_session(context.session) # Save intermediate
        await stages[4].run(context, self) # Retrospective
        await stages[5].run(context, self) # Notify
        await stages[6].run(context, self) # Archive
        session_manager.save_session(context.session) # Final save
        
        if iteration >= max_iterations:
            logger.warning(f"Pipeline hit max iterations ({max_iterations}) for session {context.session.session_id}")
            return (context.final_answer or f"ReAct Loop Timeout: The agent reached its maximum reasoning limit ({max_iterations} steps) without concluding a final answer. Please break down your request."), True, "MAX_ITERATIONS"
            
        return (context.final_answer or "No response generated. (LLM returned an empty message)"), context.continuation_req, context.continuation_reason
        
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
            
            if not getattr(self, 'ralph_wiggum_mode', False) or not cont_req:
                return response_text, cont_req, cont_reason
                
            logger.warning(f"Ralph Wiggum Mode: Triggering Epoch {epoch+1}/{max_epochs} for {msg.session_id} due to {cont_reason}")
            
            # Send status update to Gateway so user sees it's auto-recovering
            await self.message_bus.publish_outbound(OutboundMessage(
                channel="gateway",
                session_id=msg.sender_id,
                content=f"[Ralph Wiggum Auto-Heal Activated] Re-initiating loop {epoch+1}/{max_epochs} due to: {cont_reason}",
                type="thought"
            ))
            
            # Compress context or inject error message to heal
            if cont_reason == "MAX_ITERATIONS":
                prompt = "System Control: You hit the 50-step execution limit. Summarize your current progress over the last 50 steps, clarify what is missing, and state your next tool call to continue."
            else:
                prompt = f"System Control: Execution interrupted by API Error: {cont_reason}. Diagnose the issue, drop redundant context if it was a token length error, and adjust your strategy before continuing."
                
            # Create a synthetic inbound message to re-trigger the loop
            current_msg = InboundMessage(
                channel=msg.channel,
                sender_id="system", 
                session_id=msg.session_id,
                content=prompt,
                metadata={"epoch": epoch}
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
                    status_prefix = f"[STATUS: {msg.status.upper()}] " if msg.status and msg.status in ["pending", "failed"] else ""
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
                agent_language=self.agent_language
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
                    logger.info(f"\n[AGENTS] Iteration {iteration} Response Content:\n{response.content}")
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
                        type="thought"
                    )
                    await self.message_bus.publish_outbound(thought_msg)
                
                # Check for Tool Calls
                if response.tool_calls:
                    messages.append(response) # Add AIMessage with tool_calls
                    
                    # Execute Tools
                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        args = tool_call["args"]
                        tool_call_id = tool_call["id"]
                        
                        # Emit Tool Call Event
                        await self.message_bus.publish_outbound(OutboundMessage(
                            channel="gateway",
                            session_id="global",
                            content=f"Invoking {tool_name} with {args}",
                            type="tool_call",
                            metadata={"tool": tool_name, "args": args}
                        ))
                        
                        if tool_name in self.tools_map:
                            logger.info(f"Agent Invoking Tool: {tool_name} with {args}")
                            tool_func = self.tools_map[tool_name]
                            try:
                                tool_output = await tool_func.ainvoke(args)
                            except Exception as te:
                                tool_output = f"Error: {te}"
                                
                            # Self-Improvement Error Detector Hook
                            error_patterns = [
                                "error:", "Error:", "ERROR:", "failed", "FAILED",
                                "command not found", "No such file", "Permission denied",
                                "fatal:", "Exception", "Traceback", "npm ERR!",
                                "ModuleNotFoundError", "SyntaxError", "TypeError",
                                "exit code", "non-zero"
                            ]
                            
                            output_str = str(tool_output)
                            contains_error = any(pattern in output_str for pattern in error_patterns)
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
                                
                            messages.append(ToolMessage(tool_call_id=tool_call_id, content=output_str, name=tool_name))
                            
                            # Emit Tool Result Event
                            out_msg = OutboundMessage(
                                channel="gateway",
                                session_id="global",
                                content=f"Result: {output_str[:200]}...",
                                type="tool_result",
                                metadata={"tool": tool_name, "result": output_str}
                            )
                            # print(f"[DEBUG-AG] Publishing Tool Result: {tool_name}")
                            await self.message_bus.publish_outbound(out_msg)

                        else:
                            messages.append(ToolMessage(tool_call_id=tool_call_id, content=f"Error: Tool {tool_name} not found", name=tool_name))
                    
                    # Continue loop to let LLM process tool outputs
                    continue
                else:
                    # No tool calls, this is the final response
                    final_content = response.content
                    logger.info(f"Agent Final Response (to {source}): {str(final_content)[:200]}...")
                    break
            
            # Fallback if loop limitation reached
            if final_content is None:
                final_content = "I reached my thought limit effectively. " + (response.content if response else "")
                
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
        raw_session_id = self._normalize_session_id(msg.session_id)
        formatted_sender = msg.sender_id # Default
        
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
        msg_ts = msg.metadata.get('timestamp')
        original_ts = None
        try:
            if isinstance(msg_ts, str):
                msg_ts = datetime.fromisoformat(msg_ts)
                if msg_ts.tzinfo is None:
                    msg_ts = msg_ts.replace(tzinfo=timezone.utc)
                original_ts = msg_ts
            elif not msg_ts:
                msg_ts = datetime.now(timezone.utc)
            else:
                # Ensure existing datetime object is aware
                if hasattr(msg_ts, 'tzinfo') and msg_ts.tzinfo is None:
                    msg_ts = msg_ts.replace(tzinfo=timezone.utc)
                original_ts = msg_ts
        except:
            msg_ts = datetime.now(timezone.utc)

        # Calculate and log delivery latency
        if original_ts:
            try:
                # Ensure UTC for comparison
                calc_ts = original_ts
                if calc_ts.tzinfo is None:
                    calc_ts = calc_ts.replace(tzinfo=timezone.utc)
                latency = (datetime.now(timezone.utc) - calc_ts).total_seconds()
                logger.info(f"P2P Latency: Receiving message {msg.metadata.get('message_id')} from {msg.sender_id} via {msg.channel}. Latency: {latency:.3f}s")
            except Exception as le:
                logger.debug(f"Could not calculate latency: {le}")

        user_msg_obj = Message(
            id=msg.metadata.get("message_id") or str(uuid.uuid4()),
            content=msg.content,
            sender=formatted_sender,
            timestamp=msg_ts,
            session_id=history_session_id
        )
        self.history.append(user_msg_obj)
        self.resident_memory.log_interaction(formatted_sender, msg.content, msg_type="chat", session_id=history_session_id, timestamp=msg_ts, msg_id=msg.metadata.get("message_id"))

        # 1.5 DUAL BROADCAST: Inform Gateway of inbound P2P message
        if msg.channel == "p2p":
             await self.message_bus.publish_outbound(OutboundMessage(
                 channel="gateway",
                 session_id=history_session_id,
                 content=msg.content,
                 sender=formatted_sender,
                 type="chat"
             ))

        # 2. Pipeline Execution
        # p2p_logger.info(f"DEBUG: process_bus_message calling run_pipeline. Channel={msg.channel}, Sender={msg.sender_id}")
        response_text, cont_req, cont_reason = await self._run_ralph_wiggum_loop(msg)

        # 3. Reply via Bus
        reply_id = str(uuid.uuid4())
        is_internal_report = False
        
        if response_text and "[NO_RESPONSE_NEEDED]" in str(response_text):
            logger.info(f"P2P Logic: Conversation terminated by agent via [NO_RESPONSE_NEEDED] for session_id={raw_session_id}")
            is_internal_report = True
        elif response_text and str(response_text).strip() and response_text != "No response generated.":
            out_msg = OutboundMessage(
                channel=msg.channel,
                session_id=raw_session_id, # Must use RAW ID for transport
                content=response_text,
                reply_to=msg.metadata.get("message_id"),
                metadata={"message_id": reply_id}
            )
            await self.message_bus.publish_outbound(out_msg)
            
            # 3.5 DUAL BROADCAST: Push Agent response to Gateway immediately
            if msg.channel == "p2p":
                 await self.message_bus.publish_outbound(OutboundMessage(
                     channel="gateway",
                     session_id=history_session_id,
                     content=response_text,
                     type="chat",
                     metadata={"message_id": reply_id}
                 ))

        # 4. Log Reply to history
        target_session = "resident" if is_internal_report else history_session_id
        target_status = None if is_internal_report else "sent"
        
        agent_msg_obj = Message(
             id=reply_id,
             content=response_text,
             sender="agent",
             timestamp=datetime.now(timezone.utc),
             session_id=target_session,
             status=target_status
        )
        self.history.append(agent_msg_obj)
        self.resident_memory.log_interaction("agent", response_text, msg_type="chat", session_id=target_session, status=target_status)
    async def notify_resident(self, content: str, type: str = "agent_message", session_id: str = "resident", broadcast: bool = True, media: list = None):
        """
        Notify the resident. 
        If broadcast=True, sends to all known bridges (Feishu, etc.).
        If broadcast=False, only sends to local Gateway (Web UI).
        """
        logger.info(f"Notifying resident (broadcast={broadcast}): {content[:50]}...")
        
        # 1. Log to history (Web UI)
        msg_id = str(uuid.uuid4())
        self.history.append(Message(
            id=msg_id,
            content=content,
            sender="agent",
            timestamp=datetime.now(timezone.utc),
            session_id=session_id
        ))
        self.resident_memory.log_interaction("agent", content, msg_type="chat", session_id=session_id)
        
        # 2. Broadcast or Targeted Send
        if broadcast:
            bridges_to_notify = self.resident_bridges.copy()
            if "gateway" not in bridges_to_notify:
                 bridges_to_notify["gateway"] = "global"
        else:
            # Only send to Gateway (Web UI)
            bridges_to_notify = {"gateway": "global"}
             
        for channel, cid in bridges_to_notify.items():
            try:
                out_msg = OutboundMessage(
                    channel=channel,
                    session_id=cid,
                    content=content,
                    type=type,
                    media=media or []
                )
                await self.message_bus.publish_outbound(out_msg)
                logger.debug(f"Proactive notification sent via {channel}")
            except Exception as e:
                logger.error(f"Failed to send proactive notification via {channel}: {e}")

    # 1. User Contact
    async def process_user_instruction(self, content: str, broadcast: bool = False) -> Message:
        # 1. Log User Message
        user_msg = Message(
            id=str(uuid.uuid4()),
            content=content,
            sender="user",
            timestamp=datetime.now(timezone.utc),
            session_id="resident"
        )
        self.history.append(user_msg)
        self.resident_memory.log_interaction("resident", content, msg_type="chat", session_id="resident") # Log to private memory
        
        # 2. Agent response via Pipeline
        msg_obj = InboundMessage(
            channel="resident",
            sender_id="resident",
            content=content,
            session_id="resident"
        )
        # Pass through the pipeline with Ralph Wiggum loop wrapping
        response_text, _, _ = await self._run_ralph_wiggum_loop(msg_obj)
        
        # 3. Notify Resident (Targeted or Broadcast depending on caller)
        await self.notify_resident(response_text, session_id="resident", broadcast=broadcast)
        
        # Return the last Message object from history
        return self.history[-1] if self.history else None

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
                sender_id = msg.get('sender_id')
                content = msg.get('content')
                msg_type = msg.get('message_type', msg.get('type'))
                
                # Filter out system messages that are handled elsewhere (e.g., in handle_p2p_message)
                if msg_type == "SYSTEM_ERROR":
                    continue
                
                try:
                    receive_time = datetime.now(timezone.utc).timestamp()
                    # 1. De-duplication
                    m_id = msg.get('message_id')
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
                    raw_type = str(msg.get('message_type', msg.get('type', ''))).lower()
                    
                    # Package Type: What is being sent? (chat, file, gossip, error)
                    package_type = "chat"
                    if raw_type == "file" or (isinstance(content, dict) and "data" in content):
                        package_type = "file"
                    elif raw_type == "gossip":
                        package_type = "gossip"
                    elif raw_type == "system_error":
                        package_type = "error"
                    
                    # Recipient Type: How is it addressed? (direct, group)
                    recipient_id = self._normalize_session_id(msg.get('recipient_id'))
                    recipient_type = "direct"
                    if raw_type == "group":
                        recipient_type = "group"
                    elif recipient_id and p2p_service.local_node:
                        if recipient_id in p2p_service.local_node.group_ids:
                            recipient_type = "group"
                    
                    # Process based on type
                    sender_display = sender_id[:8] if sender_id else "unknown"
                    logger.info(f"Processing P2P {package_type} from {sender_display} (addressed to {recipient_type})...")
                    
                    # Determine effective session_id (The session key)
                    effective_session_id = sender_id
                    if recipient_type == "group" and recipient_id:
                        effective_session_id = recipient_id
                    
                    effective_session_id = self._normalize_session_id(effective_session_id) or "unknown_session"

                    # Use 'content' text if available
                    text_content = str(content)
                    if isinstance(content, dict) and 'text' in content:
                        text_content = content['text']
                    
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
                        metadata={"message_id": m_id, "package_type": package_type, "recipient_type": recipient_type}
                    )
                    
                    # 2. Log Inbound Message to history
                    msg_ts = msg.get('timestamp') or msg.get('metadata', {}).get('timestamp')
                    original_ts = None
                    try:
                        if isinstance(msg_ts, str):
                            msg_ts = datetime.fromisoformat(msg_ts)
                            # Ensure aware immediately
                            if msg_ts.tzinfo is None:
                                msg_ts = msg_ts.replace(tzinfo=timezone.utc)
                            original_ts = msg_ts
                        elif not msg_ts:
                            msg_ts = datetime.now(timezone.utc)
                        else:
                            # Ensure aware immediately
                            if hasattr(msg_ts, 'tzinfo') and msg_ts.tzinfo is None:
                                msg_ts = msg_ts.replace(tzinfo=timezone.utc)
                            original_ts = msg_ts
                    except:
                        msg_ts = datetime.now(timezone.utc)

                    # Calculate and log delivery latency
                    if original_ts:
                        try:
                            # Ensure UTC for comparison
                            calc_ts = original_ts
                            if calc_ts.tzinfo is None:
                                calc_ts = calc_ts.replace(tzinfo=timezone.utc)
                            latency = (datetime.now(timezone.utc) - calc_ts).total_seconds()
                            logger.info(f"P2P Latency (Polling): Receiving message {m_id} from {sender_id}. Latency: {latency:.3f}s")
                        except Exception as le:
                            logger.debug(f"Could not calculate latency (Polling): {le}")

                    self.history.append(Message(
                        id=m_id or str(uuid.uuid4()), 
                        content=text_content, 
                        sender=sender_id, 
                        timestamp=msg_ts,
                        session_id=effective_session_id
                    ))
                    self.resident_memory.log_interaction(sender_id, text_content, msg_type=package_type, session_id=effective_session_id, timestamp=msg_ts, msg_id=m_id)
                    
                    # DUAL BROADCAST: Inform UI and other listeners
                    await self.message_bus.publish_outbound(OutboundMessage(
                        channel="gateway",
                        session_id=effective_session_id,
                        content=text_content,
                        type="chat",
                        sender=sender_id,
                        timestamp=msg_ts
                    ))
                    # Also publish to p2p for internal listeners
                    await self.message_bus.publish_outbound(OutboundMessage(
                        channel="p2p",
                        session_id=effective_session_id,
                        content=text_content,
                        type="chat",
                        sender=sender_id,
                        timestamp=msg_ts
                    ))
                    
                    # 3. Run Pipeline to get Response
                    # p2p_logger.info(f"DEBUG: process_network_inbox calling run_pipeline. Channel={msg_obj.channel}, Sender={msg_obj.sender_id}")
                    response_text, _, _ = await self._run_ralph_wiggum_loop(msg_obj)
                    
                    # 4. Agent's Final Answer is for internal record, NOT sent over P2P.
                    # All outbound P2P communication must be done explicitly by the LLM via `send_p2p_message` tool.
                    if response_text and "[NO_RESPONSE_NEEDED]" not in str(response_text) and response_text != "No response generated.":
                        # Log the agent's final conclusion of this P2P interaction to local history so the resident sees it
                        self.history.append(Message(
                            id=str(uuid.uuid4()),
                            content=f"[Agent completed P2P task]: {response_text}",
                            sender="agent",
                            timestamp=datetime.now(timezone.utc),
                            session_id=effective_session_id
                        ))
                        # Ensure Gateway knows processing is done
                        s_id_short = sender_id[:8] if sender_id else "unknown"
                        await self.message_bus.publish_outbound(OutboundMessage(
                            channel="gateway",
                            session_id=effective_session_id,
                            content=f"Agent processed P2P message from {s_id_short}",
                            type="thought"
                        ))
                except asyncio.CancelledError:
                    logger.warning(f"Process Network Inbox was cancelled during message processing from {sender_id}. This usually happens on timeout or shutdown.")
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

                    self.history.append(Message(
                        id=str(uuid.uuid4()),
                        content=f"Error processing P2P message: {e}",
                        sender="system",
                        timestamp=datetime.now(timezone.utc),
                        session_id=err_session_id
                    ))
            
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
                    with open(inbox_path, 'w', encoding='utf-8') as f:
                        pass # Truncate file
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
                session_id="system"
             )
             summary, _, _ = await self._run_ralph_wiggum_loop(msg_obj)
        else:
             summary = "Agent offline."
             
        # Push to history/frontend AND broadcast to bridges
        await self.notify_resident(summary)

    # 4. Ad-hoc Task: Periodic Participation Reward
    async def trigger_adhoc_task(self):
        if not self.ledger or not p2p_service.local_node:
            return
            
        node_id = p2p_service.local_node.node_id
        reward_amount = 0.1#50.0
        details = "Periodic Participation Reward (UBI)"
        
        # Credit the balance
        self.ledger.credit(node_id, reward_amount)
        new_bal = self.ledger.get_balance(node_id)
        logger.info(f"Node {node_id[:8]} received periodic income: {reward_amount}. New Balance: {new_bal}")
        
        # Log to private memory for resident visibility
        self.resident_memory.log_interaction(
            "system", 
            f"Received {reward_amount} STATER as Participation Reward.", 
            "income",
            session_id="resident"
        )
        
        # Push a visual notice to history AND broadcast to bridges
        await self.notify_resident(f"💰 [Economy] Received {reward_amount} STATER Participation Reward.")

    async def get_history(self) -> list[Message]:
        return self.history

    async def get_status(self) -> AgentStatus:
        # Sync balance from ledger before returning
        if self.ledger and p2p_service.local_node:
            node_id = p2p_service.local_node.node_id
            self.status.balance = self.ledger.get_balance(node_id)
            
            # Sync relay status
            net_status = p2p_service.get_network_status()
            self.status.relay_connected = net_status.get("relay_connected", False)
            
            logger.info(f"Status Sync: UUID {node_id[:8]} Balance {self.status.balance} Relay: {self.status.relay_connected}")
        else:
            logger.warning("Status Sync Failed: P2P local_node not initialized")
        return self.status

    def _hydrate_history(self):
        """Load history from resident_memory.json into Agent history."""
        disk_history = self.resident_memory.get_all_history()
        self.history = []
        for entry in disk_history:
            self.history.append(Message(
                id=entry.get('id', str(uuid.uuid4())),
                content=entry.get('content', ''),
                sender=entry.get('sender', 'unknown'),
                timestamp=datetime.fromisoformat(entry.get('timestamp')) if entry.get('timestamp') else datetime.now(timezone.utc),
                session_id=entry.get('session_id') or entry.get('chat_id'),
                status=entry.get('status')
            ))
        logger.info(f"AgentService: Loaded {len(self.history)} messages from persistent storage.")

    def _save_system_state(self):
        """Save deduplication IDs and other internal states to disk."""
        try:
            import json
            import os
            
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
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            state_path = system_dir / "agent_state.json"
            
            with open(state_path, 'w', encoding='utf-8') as f:
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
                with open(state_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    all_ids = state.get("processed_message_ids", [])
                    # Limit to 10,000 recent IDs on load
                    self.processed_message_ids = set(all_ids[-10000:])
                    self.notified_governance_ids = set(state.get("notified_governance_ids", []))
                    self.notified_error_signatures = set(state.get("notified_error_signatures", []))
                    self.resident_bridges = state.get("resident_bridges", {})
                    logger.info(f"Hydrated {len(self.processed_message_ids)} de-dup IDs, {len(self.notified_governance_ids)} gov notifications, and {len(self.resident_bridges)} resident bridges.")
            
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
                        with open(proc_path, 'a', encoding='utf-8') as pf:
                            with open(inbox_path, 'r', encoding='utf-8') as ifile:
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
                    with open(proc_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip():
                                try:
                                    msg_data = json.loads(line)
                                    m_id = msg_data.get('message_id')
                                    if not m_id or m_id not in self.processed_message_ids:
                                        pending_messages.append(msg_data)
                                except: continue
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

    async def search_history(self, query: str = None, date_from: str = None, date_to: str = None) -> list[Message]:
        results = self.resident_memory.search_history(query, date_from, date_to)
        messages = []
        for entry in results:
            messages.append(Message(
                id=entry.get('id', str(uuid.uuid4())),
                content=entry.get('content', ''),
                sender=entry.get('sender', 'unknown'),
                timestamp=datetime.fromisoformat(entry.get('timestamp')),
                session_id=entry.get('session_id') or entry.get('chat_id')
            ))
        return messages

    async def sync_network(self):
        """Periodically refresh network topology."""
        if p2p_service._initialized:
            await p2p_service.network_manager.sync_topology()

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
                
            from datetime import timezone
            peers.append({
                "node_id": node_id,
                "name": node.name,
                "public_key": node.public_key,
                "endpoint": node.endpoint,
                "status": "online" if node.is_online else "offline",
                "last_seen": node.last_seen.isoformat() if hasattr(node, 'last_seen') and node.last_seen else datetime.now(timezone.utc).isoformat()
            })
        return peers

    async def get_groups(self) -> list[dict]:
        """Get list of known groups from P2P service."""
        return p2p_service.get_groups()

    async def _check_compliance(self, content: str, recipient_id: str) -> tuple[bool, str]:
        """Audit message content against community rules."""
        if not self.llm:
            return True, "" 

        sys_prompt = (
            "You are the Compliance Officer agent. "
            "Audit the following message for community rule violations (impolite, hate speech, spam, illegal). "
            "Reply EXACTLY with 'APPROVED' if compliant, or 'REJECTED: <reason>' if not."
        )
        msg_text = f"Target: {recipient_id}\nContent: {content}"
        
        try:
            # We use a distinct invocation to avoid polluting the main context
            response = await self.llm.ainvoke([
                SystemMessage(content=sys_prompt),
                HumanMessage(content=msg_text)
            ])
            res_text = response.content.strip()
            
            if "REJECTED" in res_text:
                parts = res_text.split("REJECTED", 1)
                reason = parts[1].strip().lstrip(":").strip()
                return False, reason
                
            return True, ""
        except Exception as e:
            logger.error(f"Compliance Check Error: {e}")
            return True, "" # Fail open if LLM fails


    # Governance Wrappers
    async def create_proposal(self, group_id: str, content: str, duration_minutes: int = 60) -> dict:
        if not self.governance_manager:
            return {"error": "Governance Manager not initialized"}
        
        # Fetch eligible voters from group members
        eligible_voters = set()
        if p2p_service.local_node and group_id in p2p_service.local_node.network_manager.groups:
             group = p2p_service.local_node.network_manager.groups[group_id]
             eligible_voters = group.members.copy()
             
        proposal, election = self.governance_manager.initiate_proposal(group_id, content, duration_minutes, eligible_voters=eligible_voters)
        
        # Broadcast via P2P
        asyncio.create_task(p2p_service.broadcast_governance_event(
            group_id, 
            "proposal", 
            {"proposal": proposal.to_dict(), "election": election.to_dict()}
        ))
        return {
            "proposal": proposal.to_dict(),
            "election": election.to_dict()
        }

    async def get_proposals(self) -> list[dict]:
        if not self.governance_manager:
            return []
        # Return list of proposals
        return [p.to_dict() for p in self.governance_manager.proposals.values()]

    async def delete_proposal(self, proposal_id: str) -> bool:
        """Remove a proposal and its associated election."""
        if self.governance_manager:
            return self.governance_manager.delete_proposal(proposal_id)
        return False

    async def get_elections(self) -> list[dict]:
        if not self.governance_manager:
            return []
        
        elections = []
        for e in self.governance_manager.active_elections.values():
            data = e.to_dict()
            # Add realtime tally
            data["tally"] = e.tally()
            elections.append(data)
        return elections

    async def delete_election(self, election_id: str) -> bool:
        """Remove a specific election."""
        if self.governance_manager:
            return self.governance_manager.delete_election(election_id)
        return False

    async def cast_vote(self, election_id: str, approval: bool, reason: str = "", candidate_id: str = None) -> dict:
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
            timestamp=datetime.now(timezone.utc)
        )
        
        success = self.governance_manager.receive_ballot(election_id, [vote])
        if success:
            # Broadcast via P2P
            election = self.governance_manager.active_elections[election_id]
            asyncio.create_task(p2p_service.broadcast_governance_event(
                election.group_id, 
                "vote", 
                {"election_id": election_id, "vote": vote.to_dict()}
            ))
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

    async def send_p2p_message(self, recipient_id: str, content: Any, is_retry: bool = False, original_msg_id: str = None, **kwargs) -> dict:
        """
        Send a P2P message to a specific peer.
        This method handles both WebRTC data channel (fast) and HTTP/Relay (reliable) paths.
        """
        print(f"\n[DEBUG] send_p2p_message called for {recipient_id}, content: {str(content)[:50]}...", flush=True)
        if not p2p_service._initialized:
             logger.error(f"P2P Message attempt failed: P2PService NOT INITIALIZED (target={recipient_id})")
             return {"success": False, "error": "P2P not initialized"}
             
        # Normalize text for moderation and display
        text_to_check = content
        if isinstance(content, dict):
            text_to_check = content.get('text', str(content))
        elif not isinstance(content, str):
            text_to_check = str(content)

        # 1. Moderation Check - Skip if retry
        if not is_retry:
            is_compliant, reason = await self._check_compliance(text_to_check, recipient_id)
            if not is_compliant:
                msg = f"⚠️ Message Refused: {reason}"
                
                # Log refusal to history so user sees it in chat
                self.history.append(Message(
                    id=str(uuid.uuid4()),
                    content=msg,
                    sender="agent",
                    timestamp=datetime.now(timezone.utc),
                    session_id=recipient_id
                ))
                self.resident_memory.log_interaction("agent", msg, "moderation", session_id=recipient_id, status="failed")
                
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
        from datetime import timezone
        msg_timestamp = datetime.now(timezone.utc)
        
        if not is_retry:
            self.processed_message_ids.add(msg_id) # Track our own messages to avoid loopback
            msg_obj = Message(
                id=msg_id,
                content=f"{text_to_check}",
                sender="agent",
                timestamp=msg_timestamp,
                session_id=norm_target,
                status="pending"
            )
            self.history.append(msg_obj)
            self.resident_memory.log_interaction("agent", text_to_check, msg_type=package_type, session_id=norm_target, status="pending", msg_id=msg_id)
        else:
            logger.info(f"Retrying message {msg_id} - skipping duplicate history log.")
        
        # Dual broadcast to UI (Initial Pending)
        await self.message_bus.publish_outbound(OutboundMessage(
            channel="gateway",
            session_id=norm_target,
            content=f"{text_to_check}",
            type=package_type,
            sender="agent",
            timestamp=msg_timestamp,
            metadata={"message_id": msg_id, "status": "pending", "package_type": package_type, "recipient_type": recipient_type}
        ))
        
        # Publish to p2p for internal tracking if needed
        await self.message_bus.publish_outbound(OutboundMessage(
            channel="p2p",
            session_id=recipient_id, # Use raw recipient for P2P routing
            content=f"{text_to_check}",
            type="chat",
            sender="agent",
            timestamp=msg_timestamp,
            metadata={"message_id": msg_id, "recipient_id": recipient_id, "package_type": package_type}
        ))
        
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
            logger.warning(f"Recipient {recipient_id} NOT found in local topology nodes or groups. It might be an offline node or a new group.")

        target_label = f"Group: {peer_name}" if is_group else peer_name
        logger.info(f"Transmitting P2P message to {recipient_id} ({target_label})...")
        
        try:
            # Differentiate simple string vs complex dictionary payload
            if isinstance(content, dict):
                msg_content = content
                webrtc_payload_dict = content.copy()
                webrtc_payload_dict["message_id"] = msg_id # CRITICAL: Include unique ID
                webrtc_payload_dict["timestamp"] = msg_timestamp.isoformat() # PROPAGATE SOURCE TIMESTAMP
                if "message_type" not in webrtc_payload_dict:
                    webrtc_payload_dict["message_type"] = "DIRECT"
                import json
                webrtc_payload = json.dumps(webrtc_payload_dict)
            else:
                msg_content = {"text": text_to_check}
                import json
                webrtc_payload = json.dumps({
                    "text": text_to_check, 
                    "message_type": "DIRECT", 
                    "message_id": msg_id,
                    "timestamp": msg_timestamp.isoformat() # PROPAGATE SOURCE TIMESTAMP
                })

            
            # Map to protocol message types
            # GROUP messages should NOT use WebRTC (WebRTC is for peer-to-peer)
            # Only use WebRTC for DIRECT TEXT messages
            use_webrtc = (recipient_type == "direct" and package_type == "chat")
            
            sent_via_webrtc = False
            if use_webrtc:
                sent_via_webrtc = await p2p_service.webrtc_manager.send_message(recipient_id, webrtc_payload)
            
            if sent_via_webrtc:
                logger.info(f"[{recipient_id}] Message transmitted via WebRTC: {text_to_check[:100]}...")
                success_final = True
                mode = "webrtc"
            else:
                # Fallback to HTTP/Relay (or direct for GROUP messages)
                # For GROUP messages, use broadcast_to_group if available, otherwise use send_message
                if recipient_type == "group":
                    # Use the dedicated group broadcast method
                    success = await p2p_service.broadcast_to_group(
                        recipient_id,
                        text_to_check,
                        message_id=msg_id,
                        timestamp=msg_timestamp
                    )
                    mode = "group_broadcast"
                else:
                    # Pass the unique business-level msg_id to the protocol layer
                    success = await p2p_service.send_message(
                        recipient_id, 
                        msg_content, 
                        msg_type=package_type,
                        message_id=msg_id,
                        timestamp=msg_timestamp
                    )
                    mode = "http_relay"
                if success:
                    success_final = True
                    # Log based on transmission mode
                    if mode == "group_broadcast":
                        logger.info(f"[{recipient_id}] Group Broadcast successfully initiated: {text_to_check[:100]}...")
                    else:
                        logger.info(f"[{recipient_id}] Message transmitted via HTTP/Relay: {text_to_check[:100]}...")
                    # Trigger Upgrade if simple text and not already connected/connecting
                    # CRITICAL: Only for DIRECT messages!
                    if not isinstance(content, dict) and recipient_type == "direct":
                        pc = p2p_service.webrtc_manager.pcs.get(recipient_id.lower())
                        if not pc or (pc.signalingState == "stable" and pc.connectionState not in ["connecting", "connected"]):
                            asyncio.create_task(p2p_service.webrtc_manager.initiate_connection(recipient_id))
                else:
                    logger.error(f"[{recipient_id}] FINAL FAILURE: Failed to transmit P2P message via ANY path (target={recipient_id})")
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
            
            await self.message_bus.publish_outbound(OutboundMessage(
                channel="gateway",
                session_id=norm_target,
                content=msg_id,
                type="status_update",
                metadata={"message_id": msg_id, "status": new_status}
            ))

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
        target_session_id = "resident" # Default to main resident chat
        
        for msg in self.history:
            # Check both internal UUID (msg.id) and P2P network ID (msg.metadata.message_id)
            p2p_msg_id = msg.metadata.get("message_id") if msg.metadata else None
            if msg.id == message_id or p2p_msg_id == message_id:
                msg.status = "failed"
                if not msg.metadata: msg.metadata = {}
                msg.metadata["delivery_error"] = str(error_content)
                target_session_id = msg.session_id
                found_in_history = True
                logger.info(f"Updated message {msg.id} status to 'failed' in active history.")
                break
        
        # 2. Update status in persistent resident memory (JSONL logs)
        self.resident_memory.update_message_status(message_id, "failed")
        
        # 3. Notify Gateway/UI via Message Bus
        await self.message_bus.publish_outbound(OutboundMessage(
            channel="gateway",
            session_id=target_session_id,
            content=message_id,
            type="status_update",
            metadata={
                "message_id": message_id,
                "status": "failed",
                "error": str(error_content),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ))
        
        if found_in_history:
            logger.info(f"Successfully updated status to 'failed' for message {message_id}")
        else:
            logger.debug(f"Message ID {message_id} not found in current history buffer. Still updated disk logs.")

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
            
        header = f"--- Chat History with Peer {peer_id} (Last {len(formatted_history)} messages) ---\n"
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
    async def start_election(self, group_id: str, candidates: list[str]) -> str:
        if not self.governance_manager:
            return "Governance Manager not initialized"
        
        # P2P: In a real system, we'd broadcast this. 
        # For simulation, we create it locally.
        election = self.governance_manager.initiate_election(group_id, candidates)
        
        # Set eligible voters from Group info (if available via p2p_service)
        # Mocking for now as we don't have full group state reflection yet
        # p2p_service.network_manager.groups.get(group_id)
        if p2p_service.local_node and group_id in p2p_service.local_node.network_manager.groups:
             group = p2p_service.local_node.network_manager.groups[group_id]
             election.eligible_voters = group.members.copy()
        
        # Broadcast via P2P
        asyncio.create_task(p2p_service.broadcast_governance_event(
            group_id, 
            "proposal", 
            {"proposal": {"proposal_id": "", "content": "Election"}, "election": election.to_dict()} # Minimal proposal for election
        ))
        
        return str(election.election_id)

    async def submit_proposal(self, group_id: str, content: str) -> str:
        """Alias for create_proposal returning string for tool compatibility."""
        result = await self.create_proposal(group_id, content)
        if "error" in result:
            return result["error"]
        return f"Proposal {result['proposal']['proposal_id']} initiated. Voting ID: {result['election']['election_id']}"

    async def publish_research(self, group_id: str, content: str, pdf_hash: str, duration_minutes: int = 60) -> str:
         if not self.governance_manager:
            return "Governance Manager not initialized"
            
         # Fetch eligible voters from group members
         eligible_voters = set()
         if p2p_service.local_node and group_id in p2p_service.local_node.network_manager.groups:
              group = p2p_service.local_node.network_manager.groups[group_id]
              eligible_voters = group.members.copy()

         proposal, election = self.governance_manager.initiate_research_publication(group_id, content, pdf_hash, duration_minutes, eligible_voters=eligible_voters)
             
         # Broadcast via P2P
         asyncio.create_task(p2p_service.broadcast_governance_event(
            group_id, 
            "proposal", 
            {"proposal": proposal.to_dict(), "election": election.to_dict()}
         ))
             
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
            ballot.append(Vote(
                 voter_id=self.governance_manager.node_id,
                 candidate_id=v_data.get("candidate_id"), # Can be None for proposal
                 timestamp=datetime.now(timezone.utc),
                 approval=v_data.get("approve", False),
                 reason=v_data.get("reason", ""),
                 reward_amount=v_data.get("reward_amount", 0.0)
            ))
        
        success = self.governance_manager.receive_ballot(election_id, ballot)
        if success:
             # Broadcast via P2P
             election = self.governance_manager.active_elections[election_id]
             for v in ballot:
                 asyncio.create_task(p2p_service.broadcast_governance_event(
                     election.group_id, 
                     "vote", 
                     {"election_id": election_id, "vote": v.to_dict()}
                 ))
             return "Ballot registered locally"
        else:
             return "Ballot rejected (invalid, closed, or validation failed)"

    async def get_election_info(self, election_id: str) -> dict:
        if not self.governance_manager or election_id not in self.governance_manager.active_elections:
             return {"error": "Election not found"}
        
        election = self.governance_manager.active_elections[election_id]
        return election.tally()

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
        Trigger manual archiving of current state.
        In a real system, this would clear pending buffers.
        """
        if not self.archive_manager:
            return "Archive Manager not initialized"

        # Gather data (Mocking getting ALL history for now, normally just pending)
        # Getting all votes from all elections
        all_votes = []
        if self.governance_manager:
            for election in self.governance_manager.active_elections.values():
                for vote in election.votes.values():
                    # Handle both list of votes and single vote based on ballot structure
                    # election.votes is a Dict[str, List[Vote]]
                    for v in vote:
                        if v.voter_id == self.governance_manager.node_id:
                            all_votes.append(v)
        
        # Getting transactions (Ledger doesn't expose per-node tx list easily in this mock, using empty for now or implementing)
        # Assuming Ledger has get_transactions_for_node
        my_txs = []
        # if self.ledger... 
        
        # Gathering P2P messages exclusively
        p2p_messages = []
        for msg in self.history:
            # ONLY log messages that are part of an actual conversation (ignore system pings)
            if msg.session_id != "resident" and msg.sender != "system":
                p2p_messages.append(msg.dict())

        # Create Block
        block = self.archive_manager.create_daily_archive(
            votes=[str(v) for v in all_votes],  # Serialize
            txs=[str(t) for t in my_txs],
            research=[],
            messages=p2p_messages
        )
        
        return f"Archived Block #{block.index} Hash: {block.hash}"

    async def check_tasks_monitor(self):
        """Background job to check status of long-term tasks."""
        if not self.task_manager:
            return
            
        if not self.llm:
            logger.info("Task Monitor: Agent LLM not yet configured. Postponing startup task check by 5 seconds...")
            from datetime import timedelta
            self.scheduler.add_job(
                "app.services.agent_service:check_tasks_monitor_proxy", 
                trigger='date', 
                run_date=datetime.now(timezone.utc) + timedelta(seconds=5), 
                id="task_monitor_startup_retry", 
                replace_existing=True
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
                        f"[INTERNAL MONITOR]: 发现一个待处理的新任务 \"{task.goal}\"。请立刻开始执行任务并更新 Checkpoint。\n"
                        f"[CRITICAL INSTRUCTION: You are awakened by an automated background loop. You are an AUTONOMOUS agent. "
                        f"You MUST proactively take action by calling a tool (e.g. send_p2p_message, execute_shell_command) to push the task forward. "
                        f"Do NOT ask the resident for permission or instructions on how to proceed unless completely blocked. "
                        f"Do NOT output conversational text just to acknowledge this message. If you have absolutely nothing to do, output exactly [NO_RESPONSE_NEEDED].]"
                    )
                )
                asyncio.create_task(self._run_ralph_wiggum_loop(poke_msg))
                
            elif task.status == TaskStatus.ACTIVE:
                last_update = task.updated_at
                now = datetime.now(timezone.utc)
                # If no update for 30 mins, or if it's a fresh start check
                # Note: On a fresh reboot, this might still be > 1800s if the task was saved long ago
                if (now - last_update).total_seconds() > 1800:
                    logger.info(f"Task Monitor: Task '{task.goal}' seems idle. Triggering self-poke.")
                    
                    # Synthesize an internal message
                    poke_msg = InboundMessage(
                        channel="internal",
                        sender_id="system",
                        session_id="resident",
                        content=(
                            f"[INTERNAL MONITOR]: 正在推进长期任务 \"{task.goal}\"。当前状态: {task.status}。请检查 Checkpoint 并决定下一步行动。\n"
                            f"[CRITICAL INSTRUCTION: You are awakened by an automated background loop. You are an AUTONOMOUS agent. "
                            f"You MUST proactively take action by calling a tool (e.g. send_p2p_message, execute_shell_command) to push the task forward. "
                            f"Do NOT ask the resident for permission or instructions on how to proceed unless completely blocked. "
                            f"Do NOT output conversational text just to acknowledge this message. If you have absolutely nothing to do, output exactly [NO_RESPONSE_NEEDED].]"
                        )
                    )
                    
                    # Run the loop in the background
                    asyncio.create_task(self._run_ralph_wiggum_loop(poke_msg))
                    
                    # Explicitly bump the updated_at timestamp to reset the 30-minute idle clock
                    # This prevents the monitor from spamming the agent if the monitor interval is shorter than 30 mins
                    task.updated_at = datetime.now(timezone.utc)
                    self.task_manager.save_tasks()
                else:
                    logger.info(f"Task Monitor: Task '{task.goal}' is ongoing (Updated {(now-last_update).total_seconds()/60:.1f}m ago).")
            elif task.status == TaskStatus.BLOCKED:
                 logger.info(f"Task Monitor: Task '{task.goal}' is BLOCKED. Waiting for resumption condition.")

    async def check_governance_proposals(self):
        """Background job to scan for unhandled governance proposals and notify the agent."""
        if not self.governance_manager or not self.llm:
            return
            
        active_elections = self.governance_manager.active_elections
        # Find elections we haven't voted in AND haven't been notified about locally
        my_id = p2p_service.local_node.node_id if p2p_service.local_node else None
        if not my_id:
            return
        
        logger.debug(f"Governance Monitor: Checking {len(active_elections)} active elections...")
        found_new = False

        for eid, election in active_elections.items():
            # Focus on proposal votes
            if election.election_type != ElectionType.PROPOSAL_VOTE:
                continue
            
            # Skip if we already voted
            if my_id in election.votes:
                continue
                
            # Skip if we were already notified (Check both instance state and persistence)
            if eid in self.notified_governance_ids:
                continue
            
            # Found a new proposal!
            proposal_id = election.proposal_id
            proposal = self.governance_manager.proposals.get(proposal_id)
            if not proposal:
                logger.warning(f"Governance Monitor: Election {eid} found but proposal {proposal_id} is missing.")
                continue
            
            logger.info(f"Governance Monitor: New unhandled proposal detected: {proposal_id}. Awakening agent...")
            
            # Create internal probe message
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
                )
            )
            
            # Fire and forget pipeline execution
            asyncio.create_task(self._run_ralph_wiggum_loop(poke_msg))
            
            # Mark as notified and mark for persistence
            self.notified_governance_ids.add(eid)
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
        await self.message_bus.publish_outbound(OutboundMessage(
            channel="gateway",
            session_id="system", 
            content=f"Delegated Task Received: {task}",
            type="thought",
            metadata={"handoff_id": handoff_id, "sender_id": sender_id}
        ))

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
                "output": result_content
            }
            await self.send_p2p_message(sender_id, result_payload)
            logger.info(f"Sent Task Result for {handoff_id} back to {sender_id}")

        except Exception as e:
            logger.error(f"Error executing handoff {handoff_id}: {e}")
            await self.send_p2p_message(sender_id, {
                "type": "task_result",
                "handoff_id": handoff_id,
                "error": str(e)
            })

    async def process_directed_task(self, prompt: str) -> str:
        """Run the agent on a specific task prompt."""
        # For now, simulate execution. In reality, this would trigger a clean chain run.
        return f"Executed: {prompt[:100]}... [SIMULATED SUCCESS]"

    async def get_status(self) -> AgentStatus:
        """Get current agent status."""
        # Ensure status object is up to date with instance attributes
        self.status.name = self.name
        self.status.personality = self.personality
        
        # P2P Info
        if p2p_service.local_node:
            self.status.node_id = p2p_service.local_node.node_id
            
            # Update Relay Connection Status
            if p2p_service.network_manager and hasattr(p2p_service.network_manager, 'relay_client'):
                rc = p2p_service.network_manager.relay_client
                self.status.relay_connected = rc.running and rc.websocket is not None
            
            # TODO: Get actual balance, reputation
            
        return self.status

    async def handle_p2p_result(self, sender_id: str, payload: dict):
        """Process result from a previously delegated task."""
        handoff_id = payload.get("handoff_id")
        output = payload.get("output")
        error = payload.get("error")
        
        logger.info(f"Received Task Result for {handoff_id} from {sender_id}")
        
        msg = f"Task Result ({handoff_id}): {output}" if not error else f"Task Error ({handoff_id}): {error}"
        await self.message_bus.publish_outbound(OutboundMessage(
            channel="gateway",
            session_id="system",
            content=msg,
            type="thought",
            metadata={"handoff_id": handoff_id, "sender_id": sender_id}
        ))

    async def _self_reflection(self):
        """Periodic job to scan logs for errors and trigger autonomous repair."""
        log_path = "backend/data/logs/p2p_network.log"
        if not os.path.exists(log_path):
            return
            
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
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
                    
                    # Notify the agent via a focused session
                    from .events import InboundMessage
                    await self.message_bus.publish_inbound(InboundMessage(
                        sender_id="system",
                        session_id="system_health",
                        content=f"System Health Alert: The following error was detected in your logs:\n\n{error}\n\nPlease help investigate the cause. You can use 'view_file' to examine relevant modules and 'submit_code_fix' to suggest a patch.",
                        type="DIRECT"
                    ))
                    # Only notify one new error per scan to avoid overwhelming the agent
                    break
                    
        except Exception as e:
            logger.error(f"Error in self_reflection job: {e}")

# -------------------------------------------------------------------------
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

async def self_reflection_proxy():
    """Proxy for agent_service._self_reflection"""
    if agent_service:
        await agent_service._self_reflection()


agent_service = AgentService()
