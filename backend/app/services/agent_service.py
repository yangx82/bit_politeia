import asyncio
from typing import Any
import uuid
import logging
from datetime import datetime
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

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from ..agent.prompts import AGENT_SYSTEM_PROMPT
from ..agent.tools import AGENT_TOOLS
from ..agent.tools_meta import create_tool_tool
from .skill_manager import skill_manager
from ..agent.context import ContextBuilder
from ..p2p_community.governance import GovernanceManager, Vote
import json

from ..p2p_community.economy import Ledger, Transaction
from ..p2p_community.reputation import ReputationManager, Evaluation
from ..p2p_community.blockchain import ArchiveManager
from .resident_link import ResidentMemory, ResidentReporter
from .memory_store import memory_store
from .knowledge_base import knowledge_base

from .consolidation import ConsolidationService

class AgentService:
    def __init__(self):
        self.history: list[Message] = []
        self.processed_message_ids: set[str] = set() # For de-duplication
        self.status = AgentStatus(is_online=True, reputation=10, balance=100.0)
        self.message_bus = message_bus
        self.resident_bridges: Dict[str, str] = {} # Bridge Name -> Chat/OpenID
        
        # Scheduler with Persistence
        try:
            from pathlib import Path
            import os
            
            # Resolve absolute path to backend/data
            # app/services/agent_service.py -> app/services -> app -> backend
            current_file = Path(__file__).resolve()
            self.backend_dir = current_file.parent.parent.parent
            self.data_dir = self.backend_dir / "data"
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
            db_path = self.data_dir / "jobs.sqlite"
            
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
            from apscheduler.executors.pool import ThreadPoolExecutor
            
            jobstores = {
                # Use 4 slashes for absolute path in unix/windows
                'default': SQLAlchemyJobStore(url=f'sqlite:///{db_path}')
            }
            executors = {} # Default: AsyncIOExecutor() handles coroutines
            job_defaults = {
                'coalesce': True, # Merge multiple missed runs into one
                'max_instances': 3
            }
            self.scheduler = AsyncIOScheduler(jobstores=jobstores, job_defaults=job_defaults)
            logger.info(f"Scheduler initialized with SQLite persistence at {db_path}.")
        except ImportError:
            logger.warning("SQLAlchemy not found, using MemoryJobStore (No persistence).")
            self.scheduler = AsyncIOScheduler()
        except Exception as e:
            logger.error(f"Failed to init persistent scheduler: {e}. Fallback to Memory.")
            self.scheduler = AsyncIOScheduler()

        # Scheduler will be started in start_scheduler() called by main.py lifespan
        self.base_url = None
        self.api_key = None
        self.llm = None
        
    def start_scheduler(self):
        """Start the scheduler if not running."""
        try:
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("Scheduler started successfully.")
            else:
                logger.info("Scheduler already running.")
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
        self.tools_map = {t.name: t for t in AGENT_TOOLS}
        self.governance_manager = None 
        self.reputation_manager = None
        self.archive_manager = None
        self.ledger = Ledger() # Initialize Ledger
        self.resident_memory = ResidentMemory() 
        self.reporter = None # initialized after config
        self.research_field = "AI Governance"
        self.context_builder = ContextBuilder()
        self.consolidation_service = ConsolidationService(self)
        
        # Identity
        self.config_path = "agent_config.json"
        
        # 1. Load from JSON (Identity)
        json_config = self._load_config()
        
        # 2. Load from ENV (Credentials & Overrides)
        from dotenv import load_dotenv
        import os
        load_dotenv()
        
        self.name = json_config.get("name") or os.getenv("AGENT_NAME") or "Agent"
        self.personality = json_config.get("personality") or os.getenv("AGENT_PERSONALITY") or "Professional and helpful"
        
        # Hydrate History and System State from Disk
        self._hydrate_history()
        self._hydrate_system_state()
        self.verbose_llm = False # Control flag for console output
        
        # Start Scheduler with robustness
        # IMPORTANT: We must use the standalone proxy functions defined at module level 
        # to avoid PicklingError (cannot pickle 'scheduler' attribute of 'self').
        # The proxy functions import 'agent_service' global instance.
        
        # We need to import them or rely on them being available in the namespace when this runs?
        # Actually, they are defined AFTER this class in the file.
        # So we can't use them here directly if we run __init__ before they are defined.
        # BUT, add_job takes a callable. If we use a string ref "app.services.agent_service:trigger_scheduled_task_proxy", it works even better for persistence!
        
        # Using string references for robust persistence
        self.scheduler.add_job("app.services.agent_service:trigger_scheduled_task_proxy", 'interval', hours=12, misfire_grace_time=60, id="periodic_brief_job", replace_existing=True) 
        self.scheduler.add_job("app.services.agent_service:trigger_adhoc_task_proxy", 'interval', hours=24, misfire_grace_time=60, jitter=10, id="periodic_reward_job", replace_existing=True) 
        self.scheduler.add_job("app.services.agent_service:process_network_inbox_proxy", 'interval', seconds=10, misfire_grace_time=5, id="network_inbox_job", replace_existing=True) 
        self.scheduler.add_job("app.services.agent_service:sync_network_proxy", 'interval', seconds=60, id="sync_network_job", replace_existing=True) 
        
        # Nightly Consolidation (2:00 AM)
        self.scheduler.add_job("app.services.agent_service:run_consolidation_proxy", 'cron', hour=2, minute=0, id="nightly_consolidation_job", replace_existing=True)


    async def configure_agent(self, base_url: str, api_key: str, model: str = "gpt-4o", research_field: str = "AI Governance", bootstrap_url: str = None, verbose_llm: bool = False, bootstrap_verify: bool = True, name: str = None, personality: str = None):
        try:
             self.scheduler.start()
        except Exception:
             pass 
             
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.research_field = research_field
        self.verbose_llm = verbose_llm
        
        if name:
            self.name = name
            self.status.name = name
        if personality:
            self.personality = personality
            self.status.personality = personality
        
        # Save to JSON
        self._save_config({
            "name": self.name,
            "personality": self.personality,
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "research_field": research_field,
            "bootstrap_url": bootstrap_url,
            "verbose_llm": verbose_llm,
            "bootstrap_verify": bootstrap_verify
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
            
            set_key(env_file, "AGENT_BASE_URL", base_url)
            set_key(env_file, "AGENT_API_KEY", api_key)
            set_key(env_file, "AGENT_MODEL", model)
            set_key(env_file, "AGENT_RESEARCH_FIELD", research_field)
            if bootstrap_url:
                set_key(env_file, "AGENT_BOOTSTRAP_URL", bootstrap_url)
            set_key(env_file, "AGENT_BOOTSTRAP_VERIFY", "true" if bootstrap_verify else "false")
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
        
        self.governance_manager = GovernanceManager(node_id)
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
            
            self.current_system_prompt = AGENT_SYSTEM_PROMPT + identity_section + "\n" + skill_index_prompt
            
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
        import os
        base_url = os.getenv("AGENT_BASE_URL")
        api_key = os.getenv("AGENT_API_KEY")
        model = os.getenv("AGENT_MODEL", "gpt-4o")
        research_field = os.getenv("AGENT_RESEARCH_FIELD", "AI Governance")
        bootstrap_url = os.getenv("AGENT_BOOTSTRAP_URL")
        bootstrap_verify = os.getenv("AGENT_BOOTSTRAP_VERIFY", "true").lower() == "true"
        
        if base_url and api_key:
            return {
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
                "research_field": research_field,
                "bootstrap_url": bootstrap_url,
                "bootstrap_verify": bootstrap_verify
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


    async def run_pipeline(self, msg: InboundMessage) -> str:
        """Execute the 6-stage pipeline for an inbound message."""
        from ..agent.pipeline import PipelineContext, SenseStage, PlanStage, ExecuteStage, ConsolidateStage, NotifyStage, ArchiveStage
        from ..services.session_service import session_manager
        
        # 0. Get or Create Session
        session = session_manager.get_session(msg.sender_id, msg.channel)
        
        context = PipelineContext(session=session, input_message=msg)
        
        stages = [
            SenseStage(),
            PlanStage(),
            ExecuteStage(),
            ConsolidateStage(),
            NotifyStage(),
            ArchiveStage()
        ]
        
        logger.info(f"Starting pipeline execution for user {msg.sender_id} (Session: {session.session_id})")
        
        # 1. Preliminary Stage: Sense
        await stages[0].run(context, self)
        
        # 2. Main Loop: Plan & Execute (ReAct)
        max_iterations = 20
        iteration = 0
        while not context.stop_execution and iteration < max_iterations:
            iteration += 1
            await stages[1].run(context, self) # Plan
            if not context.stop_execution:
                await stages[2].run(context, self) # Execute
        
        # 3. Wrapping Up: Consolidate, Notify, Archive
        await stages[3].run(context, self) # Consolidate
        session_manager.save_session(context.session) # Save intermediate
        await stages[4].run(context, self) # Notify
        await stages[5].run(context, self) # Archive
        session_manager.save_session(context.session) # Final save
        
        return context.final_answer or "No response generated."

    async def _think_and_act(self, context: str, source: str) -> str:
        """Core Agent Logic: Perceive -> Think -> Act (ReAct Loop)"""
        if not self.llm:
            return f"Agent not configured. Received from {source}: {context[:20]}..."
            
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
                    lc_history.append(AIMessage(content=msg.content))
                else:
                    lc_history.append(HumanMessage(content=f"[{msg.sender}] {msg.content}"))

            messages = self.context_builder.build_messages(
                history=lc_history, 
                current_message=context,
                rag_context=rag_context,
                network_identity=network_identity,
                source=source,
                name=self.name,
                personality=self.personality
            )
            
            # 2. ReAct Loop
            max_iterations = 50
            iteration = 0
            final_content = None
            
            while iteration < max_iterations:
                iteration += 1
                
                # Invoke LLM
                response = await self.llm.ainvoke(messages)
                
                if self.verbose_llm:
                    print(f"\n[AGENTS] Iteration {iteration} Response:\n{response.content}\n" + "-"*50)

                # Emit Thought to Bus (if content exists and it's not final answer yet or it's mixed)
                # Simple heuristic: if it has tool calls, the content is likely a "thought" explaining why.
                # If it has no tool calls, it might be the final answer, OR a chain-of-thought leading to it.
                # We'll emit everything as a thought first, except the final return.
                
                # We need the channel/chat_id context here. 
                # _think_and_act signature is (context, source). 'source' is a string description.
                # We need to pass the actual message metadata to _think_and_act to reply to the correct channel.
                # For now, we'll blast thoughts to 'gateway' channel specifically, or try to infer.
                # Actually, best to update _think_and_act signature or use a contextvar.
                # Let's extract channel/chat_id from 'source' string if possible or use a default 'debug' channel.
                # source format: "{msg.channel} user {msg.sender_id}" or "User (My Resident)"
                
                # BETTER: Just emit to 'gateway' channel for thoughts. The Gateway UI listens to 'gateway'.
                # The user on Telegram doesn't want to see thoughts.
                
                if response.content:
                    logger.info(f"Agent Thought: {str(response.content)[:200]}...")
                    thought_msg = OutboundMessage(
                        channel="gateway",
                        chat_id="global", # or derived from source
                        content=str(response.content),
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
                            chat_id="global",
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
                                
                            messages.append(ToolMessage(tool_call_id=tool_call_id, content=str(tool_output), name=tool_name))
                            
                            # Emit Tool Result Event
                            out_msg = OutboundMessage(
                                channel="gateway",
                                chat_id="global",
                                content=f"Result: {str(tool_output)[:200]}...",
                                type="tool_result",
                                metadata={"tool": tool_name, "result": str(tool_output)}
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
        # Format sender as "[Channel] UserID" so frontend sees it clearly
        formatted_sender = f"[{msg.channel}] {msg.sender_id}"
        
        # Ensure chat_id in history also carries the [Channel] prefix for merging logic
        # But keep raw chat_id for sending the reply back
        raw_chat_id = msg.chat_id
        history_chat_id = raw_chat_id
        
        # Determine history chat_id (Prefix if not resident)
        if msg.channel != "resident":
             history_chat_id = f"[{msg.channel}] {raw_chat_id}"
             # Update Resident Bridges registry for proactive notifications
             if msg.channel != "p2p":
                  self.resident_bridges[msg.channel] = raw_chat_id
                  self._save_system_state() # Persist the new bridge immediately

        user_msg_obj = Message(
            id=str(uuid.uuid4()),
            content=msg.content,
            sender=formatted_sender,
            timestamp=datetime.now(),
            chat_id=history_chat_id
        )
        self.history.append(user_msg_obj)
        self.resident_memory.log_interaction(formatted_sender, msg.content, msg_type="chat", chat_id=history_chat_id)

        # 2. Pipeline Execution
        response_text = await self.run_pipeline(msg)

        # 3. Reply via Bus
        out_msg = OutboundMessage(
            channel=msg.channel,
            chat_id=raw_chat_id, # Must use RAW ID for transport
            content=response_text,
            reply_to=msg.metadata.get("message_id")
        )
        await self.message_bus.publish_outbound(out_msg)

        # 4. Log Reply to history
        agent_msg_obj = Message(
             id=str(uuid.uuid4()),
             content=response_text,
             sender="agent",
             timestamp=datetime.now(),
             chat_id=history_chat_id # Log with Prefix so it merges
        )
        self.history.append(agent_msg_obj)
        self.resident_memory.log_interaction("agent", response_text, msg_type="chat", chat_id=history_chat_id)
    async def notify_resident(self, content: str, type: str = "agent_message", chat_id: str = "resident", broadcast: bool = True):
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
            timestamp=datetime.now(),
            chat_id=chat_id
        ))
        self.resident_memory.log_interaction("agent", content, msg_type="chat", chat_id=chat_id)
        
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
                    chat_id=cid,
                    content=content,
                    type=type
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
            timestamp=datetime.now(),
            chat_id="resident"
        )
        self.history.append(user_msg)
        self.resident_memory.log_interaction("resident", content, msg_type="chat", chat_id="resident") # Log to private memory
        
        # 2. Agent response via Pipeline
        msg_obj = InboundMessage(
            channel="resident",
            sender_id="resident",
            content=content,
            chat_id="resident"
        )
        response_text = await self.run_pipeline(msg_obj)
        
        # 3. Notify Resident (Targeted or Broadcast depending on caller)
        await self.notify_resident(response_text, chat_id="resident", broadcast=broadcast)
        
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
            
        inbox = p2p_service.local_node.inbox
        while inbox:
            msg = inbox.pop(0)
            sender_id = msg.get('sender_id')
            content = msg.get('content')
            msg_type = msg.get('message_type')
            
            try:
                # 1. De-duplication
                m_id = msg.get('message_id')
                if m_id:
                    if m_id in self.processed_message_ids:
                        continue
                    self.processed_message_ids.add(m_id)
                    self._save_system_state() # Persist de-dup IDs
                    # Keep set size reasonable (last 1000 IDs)
                    if len(self.processed_message_ids) > 1000:
                        # Convert to list to pop first element (simple FIFO)
                        l = list(self.processed_message_ids)
                        self.processed_message_ids = set(l[100:])
                        
                # Process based on type
                logger.info(f"Processing P2P message type {msg_type} from {sender_id[:8]}...")
                
                recipient_id = msg.get('recipient_id')
                
                # Determine chat_id: Group ID if group message, else Sender ID
                effective_chat_id = sender_id
                if msg_type == "GROUP" and recipient_id:
                    effective_chat_id = recipient_id

                # Use 'content' text if available
                text_content = str(content)
                if isinstance(content, dict) and 'text' in content:
                    text_content = content['text']
                
                # Special Handling for FILE type
                if msg_type == "file" and isinstance(content, dict) and "data" in content:
                    try:
                        file_name = content.get("info", "downloaded_file")
                        file_data = base64.b64decode(content["data"])
                        
                        download_dir = "data/downloads"
                        os.makedirs(download_dir, exist_ok=True)
                        file_path = os.path.join(download_dir, f"{sender_id[:8]}_{file_name}")
                        
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
                    chat_id=effective_chat_id,
                    metadata={"message_id": m_id, "message_type": msg_type}
                )
                
                # 2. Log Inbound Message to history
                self.history.append(Message(
                    id=str(uuid.uuid4()), 
                    content=text_content, 
                    sender=sender_id, 
                    timestamp=datetime.now(),
                    chat_id=effective_chat_id
                ))
                self.resident_memory.log_interaction(sender_id, text_content, msg_type="chat", chat_id=effective_chat_id)
                
                # 3. Run Pipeline to get Response
                response_text = await self.run_pipeline(msg_obj)
                
                # 4. Send Reply back to Peer
                await self.send_p2p_message(sender_id, response_text)
                
                # 5. Log Agent Response - remove redundant history.append
                # (handled inside send_p2p_message for consistency)
            except Exception as e:
                logger.error(f"Error processing P2P message from {sender_id}: {e}")
                # Optional: Push back to inbox or Dead Letter Queue?
                # For now, just log to history so user sees something failed
                self.history.append(Message(
                    id=str(uuid.uuid4()),
                    content=f"Error processing P2P message: {e}",
                    sender="system",
                    timestamp=datetime.now()
                ))
        
        # 6. Clear Disk Inbox after processing batch
        if p2p_service.local_node:
            try:
                import os
                node_id = p2p_service.local_node.node_id
                inbox_path = self.data_dir / "p2p" / f"inbox_{node_id}.jsonl"
                if os.path.exists(inbox_path):
                    # For safety, we could just clear it, as we've already 
                    # either processed messages OR they are now in the memory inbox.
                    # But if we clear it, then crash, we might lose messages currently in memory inbox.
                    # Correct way: the memory inbox IS the pending queue.
                    # We should probably only append to disk and never clear "the file", 
                    # but pruning is complex.
                    # Simplified for BP: clear the file once it's emptied from memory.
                    if not p2p_service.local_node.inbox:
                        os.remove(inbox_path)
            except Exception as ex:
                logger.error(f"Failed to clear disk inbox: {ex}")

    # 3. Scheduled Task
    async def trigger_scheduled_task(self):
        logger.info(f"Executing Scheduled Brief Generation for field: {self.research_field}...")
        
        summary = "No report generated."
        if self.reporter:
             interests = [self.research_field] 
             summary = await self.reporter.generate_daily_brief(interests)
             
             # Log this brief
             self.resident_memory.log_interaction("agent_report", summary, "report", chat_id="resident")
        
        elif self.llm:
             msg_obj = InboundMessage(
                channel="system",
                sender_id="scheduler",
                content="Generate a brief daily summary for the resident.",
                chat_id="system"
             )
             summary = await self.run_pipeline(msg_obj)
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
            chat_id="resident"
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
                timestamp=datetime.fromisoformat(entry.get('timestamp')) if entry.get('timestamp') else datetime.now(),
                chat_id=entry.get('chat_id')
            ))
        logger.info(f"AgentService: Loaded {len(self.history)} messages from persistent storage.")

    def _save_system_state(self):
        """Save deduplication IDs and other internal states to disk."""
        try:
            import json
            import os
            
            system_dir = self.data_dir / "system"
            system_dir.mkdir(parents=True, exist_ok=True)
            
            state = {
                "processed_message_ids": list(self.processed_message_ids),
                "last_sync": datetime.now().isoformat(),
                "resident_bridges": self.resident_bridges
            }
            state_path = system_dir / "agent_state.json"
            
            with open(state_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
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
                    self.processed_message_ids = set(state.get("processed_message_ids", []))
                    self.resident_bridges = state.get("resident_bridges", {})
                    logger.info(f"Hydrated {len(self.processed_message_ids)} de-dup IDs and {len(self.resident_bridges)} resident bridges.")
            
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
            inbox_path = self.data_dir / "p2p" / f"inbox_{node_id}.jsonl"
            
            if inbox_path.exists():
                pending_messages = []
                try:
                    with open(inbox_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip():
                                try:
                                    msg_data = json.loads(line)
                                    # Only add if not already processed (in case of crash between processing and clearing)
                                    m_id = msg_data.get('message_id')
                                    if not m_id or m_id not in self.processed_message_ids:
                                        pending_messages.append(msg_data)
                                except: continue
                except Exception as e:
                    logger.warning(f"Error reading inbox: {e}")
                
                if pending_messages:
                    logger.info(f"Hydrated {len(pending_messages)} pending messages from disk inbox.")
                    p2p_service.local_node.inbox.extend(pending_messages)
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
                chat_id=entry.get('chat_id')
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
                
            peers.append({
                "node_id": node_id,
                "name": node.name,
                "public_key": node.public_key,
                "endpoint": node.endpoint,
                "status": "online" if node.endpoint else "unknown", # Simple status check
                "last_seen": datetime.now().isoformat() # Placeholder for real last_seen
            })
        return peers

    async def get_groups(self) -> list[dict]:
        """Get list of known groups from P2P service."""
        return p2p_service.get_groups()

    async def _check_compliance(self, content: str, target_id: str) -> tuple[bool, str]:
        """Audit message content against community rules."""
        if not self.llm:
            return True, "" 

        sys_prompt = (
            "You are the Compliance Officer agent. "
            "Audit the following message for community rule violations (impolite, hate speech, spam, illegal). "
            "Reply EXACTLY with 'APPROVED' if compliant, or 'REJECTED: <reason>' if not."
        )
        msg_text = f"Target: {target_id}\nContent: {content}"
        
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
        
        proposal, election = self.governance_manager.initiate_proposal(group_id, content, duration_minutes)
        return {
            "proposal": proposal.to_dict(),
            "election": election.to_dict()
        }

    async def get_proposals(self) -> list[dict]:
        if not self.governance_manager:
            return []
        # Return list of proposals
        return [p.to_dict() for p in self.governance_manager.proposals.values()]

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
            timestamp=datetime.now()
        )
        
        success = self.governance_manager.receive_ballot(election_id, [vote])
        if success:
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

    async def send_p2p_message(self, target_id: str, content: Any) -> dict:
        """Send a P2P message to a specific peer."""
        print(f"\n[DEBUG] send_p2p_message called for {target_id}, content: {str(content)[:50]}...", flush=True)
        if not p2p_service._initialized:
             logger.error(f"P2P Message attempt failed: P2PService NOT INITIALIZED (target={target_id})")
             return {"success": False, "error": "P2P not initialized"}
             
        # Normalize content to string for moderation
        text_to_check = content
        if isinstance(content, dict) and 'text' in content:
            text_to_check = content['text']
        elif not isinstance(content, str):
            text_to_check = str(content)

        # 1. Moderation Check
        is_compliant, reason = await self._check_compliance(text_to_check, target_id)
        if not is_compliant:
            msg = f"⚠️ Message Refused: {reason}"
            
            # Log refusal to history so user sees it in chat
            self.history.append(Message(
                id=str(uuid.uuid4()),
                content=msg,
                sender="agent",
                timestamp=datetime.now(),
                chat_id=target_id
            ))
            self.resident_memory.log_interaction("agent", msg, "moderation", chat_id=target_id)
            
            return {"success": True, "status": "refused", "reason": reason}
             
        # 2. Send Strategy
        # 2. Send Strategy
        logger.info(f"Sending P2P message to {target_id}...")
        # print(f"[DEBUG-P2P] Attempting to send message to {target_id}")
        mode = "unknown"
        
        try:
            # Try WebRTC First
            import json
            webrtc_payload = json.dumps({"text": text_to_check, "message_type": "DIRECT"})
            sent_via_webrtc = await p2p_service.webrtc_manager.send_message(target_id, webrtc_payload)
            
            if sent_via_webrtc:
                logger.info(f"[{target_id}] Message sent via WebRTC: {text_to_check[:100]}...")
                mode = "webrtc"
            else:
                # Fallback to HTTP/Relay
                msg_content = {"text": text_to_check}
                await p2p_service.send_message(target_id, msg_content)
                logger.info(f"[{target_id}] Message sent via HTTP/Relay: {text_to_check[:100]}...")
                mode = "http"
                
                # Trigger Upgrade if simple text
                asyncio.create_task(p2p_service.webrtc_manager.initiate_connection(target_id))

            # Log to history
            self.history.append(Message(
                id=str(uuid.uuid4()),
                content=f"{text_to_check}",
                sender="agent",
                timestamp=datetime.now(),
                chat_id=target_id
            ))
            self.resident_memory.log_interaction("agent", text_to_check, msg_type="chat", chat_id=target_id)
            
            return {"success": True, "mode": mode}
            
        except Exception as e:
            logger.error(f"Failed to send P2P message: {e}")
            return {"success": False, "error": str(e)}

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


    async def get_peers(self) -> list[dict]:
        """Get list of connected peers from P2P service."""
        if not p2p_service._initialized:
             return []
        # Return list of Peer Info dicts
        # assuming network_manager.peers is Dict[node_id, NodeInfo]
        # or we use p2p_service.get_network_status() which returns summary
        # But frontend expects list of objects with node_id, name, etc.
        
        peers = []
        if hasattr(p2p_service, 'network_manager'):
             # Create a safe list
             for pid, p in p2p_service.network_manager.nodes.items():
                  # Peer object to dict
                  # Exclude local node from peers list?
                  if p2p_service.local_node and pid == p2p_service.local_node.node_id:
                      continue
                  peers.append(p.to_dict())
        return peers

    async def get_groups(self) -> list[dict]:
        """Get list of groups from P2P service."""
        return p2p_service.get_groups()

    async def receive_p2p_message(self, message: P2PMessage) -> dict:
        """Handle incoming P2P message from other nodes."""
        if not p2p_service._initialized:
            return {"success": False, "error": "P2P not initialized"}
        
        from ..p2p_community.message_protocol import SignedMessage
        signed_msg = SignedMessage.from_dict(message.dict())
        
        # Dispatch to network manager for internal routing/inbox delivery
        await p2p_service.network_manager.route_message(signed_msg)
        return {"success": True}

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
        
        return str(election.election_id)

    async def submit_proposal(self, group_id: str, content: str) -> str:
        if not self.governance_manager:
            return "Governance Manager not initialized"
            
        proposal, election = self.governance_manager.initiate_proposal(group_id, content)
        
        # Determine scope (mock behavior: if content implies sub-groups, set scope)
        if "all groups" in content.lower():
            proposal.scope = "inclusive_subgroups"
        
        # Mock eligible voters
        if p2p_service.local_node and group_id in p2p_service.local_node.network_manager.groups:
             group = p2p_service.local_node.network_manager.groups[group_id]
             election.eligible_voters = group.members.copy()
             
        return f"Proposal {proposal.proposal_id} initiated. Voting ID: {election.election_id}"

    async def publish_research(self, group_id: str, content: str, pdf_hash: str) -> str:
         if not self.governance_manager:
            return "Governance Manager not initialized"
            
         proposal, election = self.governance_manager.initiate_research_publication(group_id, content, pdf_hash)
         
         # Mock eligible voters (Same as proposal)
         if p2p_service.local_node and group_id in p2p_service.local_node.network_manager.groups:
             group = p2p_service.local_node.network_manager.groups[group_id]
             election.eligible_voters = group.members.copy()
             
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
                 timestamp=datetime.now(),
                 approval=v_data.get("approve", False),
                 reason=v_data.get("reason", ""),
                 reward_amount=v_data.get("reward_amount", 0.0)
            ))
        
        success = self.governance_manager.receive_ballot(election_id, ballot)
        if success:
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
            # Exclude resident-agent chat and system notifications
            if msg.chat_id != "resident" and msg.sender != "system":
                p2p_messages.append(msg.dict())

        # Create Block
        block = self.archive_manager.create_daily_archive(
            votes=[str(v) for v in all_votes],  # Serialize
            txs=[str(t) for t in my_txs],
            research=[],
            messages=p2p_messages
        )
        
        return f"Archived Block #{block.index} Hash: {block.hash}"

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
            id=str(uuid.uuid4()),
            content=f"Delegated Task Received: {task}",
            sender=sender_id,
            timestamp=datetime.now(),
            type="thought"
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
            await p2p_service.send_message(sender_id, result_payload)
            logger.info(f"Sent Task Result for {handoff_id} back to {sender_id}")

        except Exception as e:
            logger.error(f"Error executing handoff {handoff_id}: {e}")
            await p2p_service.send_message(sender_id, {
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
            id=str(uuid.uuid4()),
            content=msg,
            sender=sender_id,
            timestamp=datetime.now(),
            type="thought"
        ))



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


agent_service = AgentService()
