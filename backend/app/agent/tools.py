import logging
from typing import Optional
from langchain_core.tools import tool
from ..services.p2p_service import p2p_service

logger = logging.getLogger(__name__)

@tool
async def send_p2p_message(recipient_id: str, content: str, message_type: str = "DIRECT") -> str:
    """
    Send a P2P message to another node or group in the network.
    
    Args:
        recipient_id: The UUID of the target Node or Group.
        content: The text content of the message.
        message_type: Type of message. Options: 'DIRECT' (one-to-one), 'GROUP' (broadcast to group), 'GOSSIP' (network wide).
    """
    try:
        # P2P Service expects a dict content usually, but we handle text here
        payload = {"text": content}
        
        # P2P Service send_message might be sync or async? 
        # In p2p_service.py it is `async def send_message`.
        # We need to map message_type string to what service expects.
        
        # NOTE: p2p_service.send_message might need update to handle types or we use lower level network manager
        # But p2p_service is the high level entry.
        
        # Let's assume p2p_service.send_message(target_id, content, msg_type) signature based on my previous edits
        # or we might need to use `broadcast_message` for groups.
        
        if message_type.upper() == "GROUP":
             await p2p_service.broadcast_message(recipient_id, payload)
             return f"Broadcasted to group {recipient_id}"
        elif message_type.upper() == "DIRECT":
             await p2p_service.send_message(recipient_id, payload)
             return f"Sent direct message to {recipient_id}"
        else:
             # Default or GOSSIP
             await p2p_service.send_message(recipient_id, payload) # Fallback
             return f"Sent message to {recipient_id}"
             
    except Exception as e:
        logger.error(f"Tool Error sending message: {e}")
        return f"Error sending message: {str(e)}"

@tool
async def get_my_status() -> str:
    """
    Get the current status of the agent, including Node ID, Group memberships, 
    and the full network topology (groups and nodes).
    """
    # 1. Local Identity
    my_id = p2p_service.local_node.node_id if p2p_service.local_node else "Not Initialized"
    my_groups = list(p2p_service.local_node.group_ids) if p2p_service.local_node else []
    
    # 2. Network Topology
    info = p2p_service.get_network_status()
    
    status_report = f"--- My Status ---\nNode ID: {my_id}\nGroups: {my_groups}\n\n--- Network Topology ---\n{json.dumps(info, indent=2)}"
    return status_report

import json

from app.services.community_config import community_config
# Note: In a real app, we'd avoid circular imports. AgentService usually holds the governance manager.
# For tools to access it, we might need a global accessor or pass it via state.
# Assuming agent_service instance is globally available or we can access via a getter.

@tool
async def read_community_rules() -> str:
    """
    Read the current community organization rules (JSON format).
    Useful for checking election criteria, group sizes, etc.
    """
    return community_config.get_all_rules_text()

@tool
async def update_system_parameter(parameter_path: str, value: str) -> str:
    """
    Update a system parameter in the community rules.
    Args:
        parameter_path: Dot-notation path (e.g., 'organization.group_size.max')
        value: New value (string, will be parsed to int/float if possible)
    """
    # Simple type inference
    try:
        if value.lower() == 'true':
            parsed_value = True
        elif value.lower() == 'false':
            parsed_value = False
        elif '.' in value and value.replace('.', '', 1).isdigit():
            parsed_value = float(value)
        elif value.isdigit():
            parsed_value = int(value)
        else:
            parsed_value = value
            
        success = community_config.update_parameter(parameter_path, parsed_value)
        if success:
            return f"Successfully updated {parameter_path} to {parsed_value}"
        else:
            return f"Failed to update {parameter_path}"
    except Exception as e:
        return f"Error updating parameter: {str(e)}"

@tool
async def propose_election(group_id: str, candidate_ids: str) -> str:
    """
    Propose a new election for a group.
    Args:
        group_id: The UUID of the group.
        candidate_ids: Comma-separated list of candidate Node IDs.
    """
    try:
        import app.services.agent_service
        candidates = [c.strip() for c in candidate_ids.split(',')]
        # Access global service (pattern used in this file for p2p_service)
        result = await app.services.agent_service.agent_service.start_election(group_id, candidates)
        return f"Election initiated: {result}"
    except Exception as e:
        return f"Failed to start election: {str(e)}"

@tool
async def submit_proposal(group_id: str, content: str) -> str:
    """
    Submit a proposal for the group. 
    The proposal will be voted on.
    Args:
        group_id: UUID of the group.
        content: Text content of the proposal (e.g., "Change rule X").
    """
    try:
        import app.services.agent_service
        result = await app.services.agent_service.agent_service.submit_proposal(group_id, content)
        return result
    except Exception as e:
        return f"Failed to submit proposal: {str(e)}"

@tool
async def publish_research(group_id: str, content: str, pdf_hash: str) -> str:
    """
    Publish a research proposal for reward evaluation.
    Args:
        group_id: UUID of the group.
        content: Description/Title of the research.
        pdf_hash: Hash of the research paper PDF.
    """
    try:
        import app.services.agent_service
        result = await app.services.agent_service.agent_service.publish_research(group_id, content, pdf_hash)
        return result
    except Exception as e:
        return f"Failed to publish research: {str(e)}"

@tool
async def pay_resident(payee_id: str, amount: float, details: str = "Payment") -> str:
    """
    Transfer funds to another resident (node).
    Args:
        payee_id: The public key/Node ID of the recipient.
        amount: Amount to transfer (must be positive).
        details: Reason or description for the payment.
    """
    import app.services.agent_service 
    try:
        result = await app.services.agent_service.agent_service.transfer_funds(payee_id, amount, details)
        return result
    except Exception as e:
        return f"Payment failed: {str(e)}"

@tool
async def check_my_balance() -> str:
    """
    Check your current account balance.
    Returns:
        String stating the current balance.
    """
    try:
        import app.services.agent_service
        balance = await app.services.agent_service.agent_service.get_balance()
        return f"Current Balance: {balance}"
    except Exception as e:
        return f"Failed to check balance: {str(e)}"

@tool
async def cast_ballot(election_id: str, ballot_json: str) -> str:
    """
    Cast a full ballot in an active election or proposal vote.
    Args:
        election_id: The UUID of the election/proposal vote.
        ballot_json: JSON string representing a list of votes. 
                     Format for Election: '[{"candidate_id": "c1", "approve": true}, ...]'
                     Format for Proposal: '[{"approve": true, "reason": "My reasoning..."}, ...]'
                     Format for Research: '[{"reward_amount": 100.0, "reason": "Good work"}, ...]'
    """
    try:
        import json
        votes_data = json.loads(ballot_json)
        if not isinstance(votes_data, list):
            return "Error: ballot_json must be a list"
        
        import app.services.agent_service  
        result = await app.services.agent_service.agent_service.vote_election(election_id, votes_data)
        return f"Ballot cast result: {result}"
    except Exception as e:
        return f"Failed to vote: {str(e)}"

@tool
async def get_election_status(election_id: str) -> str:
    """
    Get the status and current tally of an election.
    """
    try:
        import app.services.agent_service
        status = await app.services.agent_service.agent_service.get_election_info(election_id)
        return str(status)
    except Exception as e:
        return f"Error getting status: {str(e)}"
        
@tool
async def generate_archive() -> str:
    """
    Trigger the creation of a local archive block.
    Snapshots votes, transactions, and research into a new block.
    """
    try:
        import app.services.agent_service
        result = await app.services.agent_service.agent_service.run_archiving()
        return result
    except Exception as e:
        return f"Archiving failed: {str(e)}"

@tool
async def get_latest_block() -> str:
    """
    Get the latest block summary from the local archive chain.
    """
    try:
        import app.services.agent_service
        report = await app.services.agent_service.agent_service.get_latest_archive_report()
        return str(report)
    except Exception as e:
        return f"Failed to get block: {str(e)}"

@tool
async def search_web(query: str) -> str:
    """
    Perform a web search to find information about a topic.
    Useful for research, fact-checking, or finding latest community updates.
    """
    try:
        from app.services.knowledge_base import knowledge_base
        return knowledge_base.web_researcher.search(query)
    except Exception as e:
        return f"Search failed: {str(e)}"

@tool
async def read_skill_guide(skill_name: str) -> str:
    """
    Read the detailed usage guide (Instructions) for a specific skill.
    Call this BEFORE using any tool from a skill you are unfamiliar with.
    """
    try:
        from app.agent.skill_manager import skill_manager
        # Ensure latest skills are loaded or just read from cache
        # skill_manager.load_skills() # Optional: reload if needed
        return skill_manager.get_skill_instruction(skill_name)
    except Exception as e:
        return f"Failed to read skill guide: {str(e)}"

@tool
async def delegate_task(recipient_id: str, task: str, context: Optional[str] = None, inputs_json: Optional[str] = None) -> str:
    """
    Delegate a structured task to another agent. 
    Use this for multi-agent collaboration or offloading complex sub-tasks.
    Args:
        recipient_id: Node ID of the target agent.
        task: The high-level objective.
        context: Optional background info or context.
        inputs_json: Optional JSON string of input parameters.
    """
    try:
        inputs = json.loads(inputs_json) if inputs_json else {}
        # We'll use p2p_service to route this. 
        # The receiver's AgentService should have a handler for 'task_handoff'.
        
        # Unique Handoff ID
        import uuid
        handoff_id = str(uuid.uuid4())
        
        payload = {
            "type": "task_handoff",
            "handoff_id": handoff_id,
            "task": task,
            "context": context,
            "inputs": inputs
        }
        
        await p2p_service.send_message(recipient_id, payload)
        return f"Task delegated to {recipient_id}. Handoff ID: {handoff_id}. Awaiting result..."
        
    except Exception as e:
        logger.error(f"Failed to delegate task: {e}")
        return f"Error: {str(e)}"

# Import execution tool
from ..agent.tools_exec import execute_shell_command
from ..agent.tools_fs import list_dir, read_file, write_file, edit_file
from ..agent.tools_web import fetch_web_page
from ..agent.tools_cron import schedule_reminder, list_reminders, cancel_reminder, start_scheduler, get_scheduler_status

@tool
async def ask_resident(question: str) -> str:
    """
    Ask the local resident (human user) for advice, instructions, or approval.
    The question will appear in the resident's chat window.
    """
    try:
        from app.services.agent_service import agent_service
        from app.models.schemas import Message
        from datetime import datetime
        import uuid
        
        # Log to agent's history so it shows in UI
        agent_service.history.append(Message(
            id=str(uuid.uuid4()),
            content=question,
            sender="agent",
            timestamp=datetime.now(),
            chat_id="resident"
        ))
        
        # Also log to resident memory
        agent_service.resident_memory.log_interaction("agent", question, msg_type="chat")
        
        return f"Question sent to resident: {question}"
    except Exception as e:
        return f"Error asking resident: {str(e)}"

# List of tools to bind to the agent
AGENT_TOOLS = [
    send_p2p_message, ask_resident, get_my_status, read_community_rules, update_system_parameter, 
    propose_election, submit_proposal, publish_research, cast_ballot, get_election_status, 
    pay_resident, check_my_balance, generate_archive, get_latest_block, search_web, 
    read_skill_guide, execute_shell_command,
    list_dir, read_file, write_file, edit_file,
    fetch_web_page,
    schedule_reminder, list_reminders, cancel_reminder,
    start_scheduler, get_scheduler_status,
    delegate_task
]
