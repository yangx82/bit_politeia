import asyncio
import uuid
import logging
from datetime import datetime
from ..models.schemas import Message, AgentStatus
from .crypto_service import crypto_service
from .transaction_manager import transaction_manager
from .p2p_service import p2p_service
from .group_service import group_service
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Placeholder for LangChain
# from langchain.llms import OpenAI 

logger = logging.getLogger(__name__)

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from ..agent.prompts import AGENT_SYSTEM_PROMPT
from ..agent.tools import AGENT_TOOLS
from ..p2p_community.governance import GovernanceManager, Vote
import json

from ..p2p_community.economy import Ledger, Transaction
from ..p2p_community.reputation import ReputationManager, Evaluation
from ..p2p_community.blockchain import ArchiveManager
from .resident_link import ResidentMemory, ResidentReporter
from .knowledge_base import knowledge_base

class AgentService:
    def __init__(self):
        self.history: list[Message] = []
        self.status = AgentStatus(is_online=True, reputation=10, balance=100.0)
        self.scheduler = AsyncIOScheduler()
        self.base_url = None
        self.api_key = None
        self.llm = None
        self.tools_map = {t.name: t for t in AGENT_TOOLS}
        self.governance_manager = None 
        self.reputation_manager = None
        self.archive_manager = None
        self.ledger = Ledger() # Initialize Ledger
        self.resident_memory = ResidentMemory() 
        self.reporter = None # initialized after config
        self.research_field = "AI Governance"
        
        # Hydrate History from Disk
        self._hydrate_history()
        
        # Start Scheduler with robustness
        self.scheduler.add_job(self.trigger_scheduled_task, 'interval', minutes=5, misfire_grace_time=60) 
        self.scheduler.add_job(self.trigger_adhoc_task, 'interval', minutes=5, misfire_grace_time=60, jitter=10) 
        self.scheduler.add_job(self.process_network_inbox, 'interval', seconds=5, misfire_grace_time=2) 

    async def configure_agent(self, base_url: str, api_key: str, model: str = "gpt-4o", research_field: str = "AI Governance"):
        try:
             self.scheduler.start()
        except Exception:
             pass 
             
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.research_field = research_field
        logger.info(f"Agent Configured with Base URL: {base_url}, Model: {model}, Field: {research_field}")
        
        # Initialize P2P Service
        node_id = crypto_service.get_public_key_string()
        await p2p_service.initialize(node_id)
        
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
        # Only credit if balance is 0 (prevents double-credit on re-config)
        if self.ledger.get_balance(real_node_id) == 0:
            self.ledger.credit(real_node_id, 1000.0)
        
        # Initialize LLM with Tools
        try:
            # Common fix: Ensure base_url for OpenAI-compatible proxies ends with /v1
            # But let's log it clearly so the user knows what's being used.
            logger.info(f"Initializing ChatOpenAI with base_url: {base_url}")
            
            raw_llm = ChatOpenAI(
                base_url=base_url,
                api_key=api_key,
                model=model, 
                temperature=0.7
            )
            self.llm = raw_llm.bind_tools(AGENT_TOOLS)
            logger.info("Agent LLM Initialized Successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Agent LLM: {e}")

    # ... (Rest of existing methods _think_and_act, process_user_instruction etc. remain unchanged) ...
    # I will replace the end of the file to append new methods
    
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


    async def _think_and_act(self, context: str, source: str) -> str:
        """Core Agent Logic: Perceive -> Think -> Act (Manual Loop)"""
        if not self.llm:
            return f"Agent not configured. Received from {source}: {context[:20]}..."
            
        try:
            # 1. Prepare Messages
            # Retrieve RAG Context
            rag_context = knowledge_base.search_web_and_context(context)
            
            # Retrieve P2P Network Context
            my_id = p2p_service.local_node.node_id if p2p_service.local_node else "unknown"
            my_groups = list(p2p_service.local_node.group_ids) if p2p_service.local_node else []
            
            messages = [
                SystemMessage(content=AGENT_SYSTEM_PROMPT),
                SystemMessage(content=f"Your Network Identity:\n- Node ID: {my_id}\n- My Groups: {my_groups}\n- My Monitoring Research Focus: {self.research_field}"),
                SystemMessage(content=f"Relevant Knowledge Context:\n{rag_context}"),
                HumanMessage(content=f"Message from {source}: {context}")
            ]
            
            # 2. Invoke LLM
            response = await self.llm.ainvoke(messages)
            
            # 3. Handle Tool Calls (Simple single-turn loop for now)
            if response.tool_calls:
                messages.append(response) # Add the AIMessage with tool_calls
                
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    args = tool_call["args"]
                    tool_call_id = tool_call["id"]
                    
                    if tool_name in self.tools_map:
                        logger.info(f"Agent Invoking Tool: {tool_name} with {args}")
                        tool_func = self.tools_map[tool_name]
                        # Tools are async functions wrapped by @tool, invocation might vary
                        # LangChain tools usually callable. ainvoke for async?
                        try:
                            # Direct invocation of proper tool
                            tool_output = await tool_func.ainvoke(args)
                        except Exception as te:
                            tool_output = f"Error: {te}"
                            
                        messages.append(ToolMessage(tool_call_id=tool_call_id, content=str(tool_output), name=tool_name))
                
                # 4. Final Response after tools
                final_response = await self.llm.ainvoke(messages)
                return final_response.content
            
            return response.content
            
        except Exception as e:
            logger.error(f"Agent Logic Error: {e}")
            return f"Error processing message: {e}"

    # 1. User Contact
    async def process_user_instruction(self, content: str) -> Message:
        user_msg = Message(
            id=str(uuid.uuid4()),
            content=content,
            sender="user",
            timestamp=datetime.now()
        )
        self.history.append(user_msg)
        self.resident_memory.log_interaction("resident", content) # Log to private memory
        
        # Agent response
        response_text = await self._think_and_act(content, "User (My Resident)")
        
        # Sign Response
        signature = crypto_service.sign_message(response_text)
        
        agent_msg = Message(
            id=str(uuid.uuid4()),
            content=f"{response_text}", 
            sender="agent",
            timestamp=datetime.now()
        )
        self.history.append(agent_msg)
        self.resident_memory.log_interaction("agent", response_text) # Log to private memory
        return agent_msg

    # 2. Community Contact (P2P Listener)
    async def process_network_inbox(self, verbose: bool = False):
        """Poll P2P inbox and process messages."""
        if verbose:
            logger.info("Checking P2P inbox...")

        if not p2p_service.local_node:
            return
            
        inbox = p2p_service.local_node.inbox
        while inbox:
            msg = inbox.pop(0)
            sender_id = msg.get('sender_id')
            content = msg.get('content')
            msg_type = msg.get('message_type')
            
            # Process based on type
            logger.info(f"Processing P2P message type {msg_type} from {sender_id[:8]}...")
            
            # Use 'content' text if available
            text_content = str(content)
            if isinstance(content, dict) and 'text' in content:
                text_content = content['text']
            
            thought_output = await self._think_and_act(text_content, f"Peer {sender_id[:8]}")
            
            # Archive interaction
            self.history.append(Message(
                id=str(uuid.uuid4()), 
                content=f"P2P({msg_type}): {thought_output[:50]}...", 
                sender=sender_id, 
                timestamp=datetime.now()
            ))

    # 3. Scheduled Task
    async def trigger_scheduled_task(self):
        logger.info(f"Executing Scheduled Brief Generation for field: {self.research_field}...")
        
        summary = "No report generated."
        if self.reporter:
             interests = [self.research_field] 
             summary = await self.reporter.generate_daily_brief(interests)
             
             # Log this brief
             self.resident_memory.log_interaction("agent_report", summary, "report")
        
        elif self.llm:
             summary = await self._think_and_act("Generate a brief daily summary for the resident.", "System Scheduler")
        else:
             summary = "Agent offline."
             
        # Push to history/frontend
        self.history.append(Message(
            id=str(uuid.uuid4()), 
            content=summary, 
            sender="agent", 
            timestamp=datetime.now()
        ))

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
            "income"
        )
        
        # Push a visual notice to history
        self.history.append(Message(
            id=str(uuid.uuid4()),
            content=f"💰 [Economy] Received {reward_amount} STATER Participation Reward.",
            sender="system",
            timestamp=datetime.now()
        ))

    async def get_history(self) -> list[Message]:
        return self.history

    async def get_status(self) -> AgentStatus:
        # Sync balance from ledger before returning
        if self.ledger and p2p_service.local_node:
            node_id = p2p_service.local_node.node_id
            self.status.balance = self.ledger.get_balance(node_id)
            logger.info(f"Status Sync: UUID {node_id[:8]} Balance {self.status.balance}")
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
                timestamp=datetime.fromisoformat(entry.get('timestamp'))
            ))
        logger.info(f"AgentService: Loaded {len(self.history)} messages from persistent storage.")

    async def search_history(self, query: str = None, date_from: str = None, date_to: str = None) -> list[Message]:
        results = self.resident_memory.search_history(query, date_from, date_to)
        messages = []
        for entry in results:
            messages.append(Message(
                id=entry.get('id', str(uuid.uuid4())),
                content=entry.get('content', ''),
                sender=entry.get('sender', 'unknown'),
                timestamp=datetime.fromisoformat(entry.get('timestamp'))
            ))
        return messages

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
            for election in self.governance_manager.elections.values():
                for vote in election.votes.values():
                    if vote.voter_id == self.governance_manager.node_id:
                        all_votes.append(vote)
        
        # Getting transactions (Ledger doesn't expose per-node tx list easily in this mock, using empty for now or implementing)
        # Assuming Ledger has get_transactions_for_node
        my_txs = []
        # if self.ledger... 
        
        # Create Block
        block = self.archive_manager.create_daily_archive(
            votes=[str(v) for v in all_votes],  # Serialize
            txs=[str(t) for t in my_txs],
            research=[]
        )
        
        return f"Archived Block #{block.index} Hash: {block.hash}"

    async def get_latest_archive_report(self) -> dict:
        if not self.archive_manager:
            return {}
        return self.archive_manager.generate_report()

agent_service = AgentService()
