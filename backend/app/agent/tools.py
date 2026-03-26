import logging
from typing import Optional
from langchain_core.tools import tool
from ..services.p2p_service import p2p_service

logger = logging.getLogger(__name__)

@tool
async def send_p2p_message(recipient_id: str, content: str, message_type: str = "DIRECT") -> str:
    """
    Send a P2P message to another node or group in the network.
    
    IMPORTANT SAFETY RULES:
    - NEVER use this tool to ask your Resident (human user) for advice or instructions. Use 'ask_resident' instead.
    - If you are in a GROUP CONVERSATION (check your system prompt context), use the Group ID as the 'recipient_id' and 'GROUP' as the 'message_type' to reply to all members.
    - Only use 'DIRECT' if you want to send a private message to a specific node.
    
    Args:
        recipient_id: The UUID of the target Node or Group.
        content: The text content of the message.
        message_type: Type of message. Options: 'DIRECT' (one-to-one), 'GROUP' (broadcast to group), 'GOSSIP' (network wide).
    """
    try:
        # print(f"[DEBUG-TOOL] send_p2p_message invoked for {recipient_id}")
        # Use AgentService wrapper to ensure consistent logging and WebRTC fallback logic
        from app.services.agent_service import agent_service
        
        result = await agent_service.send_p2p_message(recipient_id, content)
        
        if result.get("success"):
             mode = result.get("mode", "unknown")
             return f"Message sent to {recipient_id} via {mode}: SUCCESS"
        else:
             return f"Failed to send message: {result.get('error')}"
             
    except Exception as e:
        logger.error(f"Tool Error sending message: {e}")
        return f"Error sending message: {str(e)}"

@tool
async def send_file(recipient_id: str, file_path: str, description: str = "File") -> str:
    """
    Send a local file to another node.
    Args:
        recipient_id: The UUID of the target Node.
        file_path: Absolute path to the local file to send.
        description: Brief description of the file.
    """
    import base64
    import os
    
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"
        
    try:
        file_name = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            file_data = f.read()
            
        encoded_data = base64.b64encode(file_data).decode('utf-8')
        
        payload = {
            "text": f"Sending file: {file_name} - {description}",
            "info": file_name,
            "data": encoded_data,
            "mime": "application/octet-stream" # Simplified
        }
        
        # We need to manually specify the 'file' message type.
        # Ideally p2p_service.send_message should support 'file' string mapping to MessageType.FILE
        # Since we modified MessageType enum, we can pass "file" or MessageType.FILE.value
        
        from app.services.agent_service import agent_service
        # Note: we pass 'file' as the message_type parameter to agent_service.send_p2p_message
        result = await agent_service.send_p2p_message(recipient_id, payload, message_type='file')
        success = result.get('success', False)
        
        if success:
            # Tell the agent exactly where it was sent from or how it was sent
            return f"Successfully queued file {file_name} for {recipient_id}"
        else:
            return "Failed to send file (Network Error)"
            
    except Exception as e:
        return f"Error sending file: {str(e)}"

@tool
async def submit_code_fix(file_path: str, new_content: str, explanation: str) -> str:
    """
    Submits a code fix for self-repair. 
    The fix will be validated by a background supervisor and applied if tests pass.
    Note: Provide the FULL content for 'new_content'. file_path should be relative to project root.
    
    Args:
        file_path: Relative path to the file to modify (e.g., 'backend/app/services/agent_service.py').
        new_content: The complete new content for the file.
        explanation: Why this fix is being applied and what it fixes.
    """
    import os
    import json
    from datetime import datetime
    from pathlib import Path
    
    # Absolute path: project_root/backend/data/code_updates/pending.json
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    WATCH_SETTING = str(PROJECT_ROOT / "data" / "code_updates" / "pending.json")
    STALE_TIMEOUT_SECONDS = 60
    
    if os.path.exists(WATCH_SETTING):
        # Check if the file is stale (older than 60 seconds)
        try:
            file_age = datetime.now().timestamp() - os.path.getmtime(WATCH_SETTING)
            if file_age < STALE_TIMEOUT_SECONDS:
                return f"Error: A pending code update is already being processed ({int(file_age)}s ago). Please wait and try again."
            else:
                logger.warning(f"Stale pending.json detected ({int(file_age)}s old). Overwriting.")
                os.remove(WATCH_SETTING)
        except Exception:
            os.remove(WATCH_SETTING)
        
    try:
        os.makedirs(os.path.dirname(WATCH_SETTING), exist_ok=True)
        
        request = {
            "file_path": file_path,
            "new_content": new_content,
            "explanation": explanation,
            "timestamp": datetime.now().isoformat()
        }
        
        with open(WATCH_SETTING, "w", encoding="utf-8") as f:
            json.dump(request, f, indent=4)
            
        return f"SUCCESS: Code fix for {file_path} submitted to supervisor. It will be validated and applied shortly."
    except Exception as e:
        return f"Error submitting code fix: {str(e)}"

@tool
async def get_my_status() -> str:
    """
    Get the current status of the agent, including Node ID, Group memberships, 
    and the full network topology (groups and nodes).
    """
    # 1. Local Identity
    local_node = p2p_service.local_node
    my_id = local_node.node_id if local_node else "Not Initialized"
    my_name = local_node.name if local_node else "Unknown"
    my_groups = list(local_node.group_ids) if local_node else []
    
    # 2. Network Topology
    info = p2p_service.get_network_status()
    
    status_report = f"--- My Status ---\nName: {my_name}\nNode ID: {my_id}\nGroups: {my_groups}\n\n--- Network Topology ---\n{json.dumps(info, indent=2)}"
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
async def search_chat_history(peer_name_or_id: str, limit: int = 10) -> str:
    """
    Search and retrieve persistent chat history with a specific peer.
    Use this when the resident asks about past conversations or when you need to recall context from previous sessions.
    
    Args:
        peer_name_or_id: The Name or Node ID (UUID/Hex) of the peer.
        limit: Number of recent messages to retrieve (default 10).
    """
    try:
        from ..services.agent_service import agent_service
        from ..services.p2p_service import p2p_service
        
        target_id = peer_name_or_id.strip()
        
        # 1. Try to resolve by name using local topology
        network_status = p2p_service.get_network_status()
        resolved_id = None
        
        if network_status and "nodes" in network_status:
            for node_id, node_data in network_status["nodes"].items():
                if node_data.get("name", "").lower() == target_id.lower():
                    resolved_id = node_id
                    break
        
        if resolved_id:
            target_id = resolved_id
            
        result = await agent_service.get_chat_history_with_peer(target_id, limit)
        return result
    except Exception as e:
        return f"Failed to retrieve chat history: {str(e)}"

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
        from app.services.skill_manager import skill_manager
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
        
        from app.services.agent_service import agent_service
        await agent_service.send_p2p_message(recipient_id, payload)
        return f"Task delegated to {recipient_id}. Handoff ID: {handoff_id}. Awaiting result..."
        
    except Exception as e:
        logger.error(f"Failed to delegate task: {e}")
        return f"Error: {str(e)}"

# Import execution tool
from ..agent.tools_exec import execute_shell_command
from ..agent.tools_fs import list_dir, read_file, write_file, edit_file, copy_files, move_files
from ..agent.tools_web import fetch_web_page
from ..agent.tools_cron import schedule_reminder, list_reminders, cancel_reminder, start_scheduler, get_scheduler_status
from ..agent.tools_task import TASK_TOOLS

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
        
        # Use proactive notification helper (Broadcasts to all bridges)
        await agent_service.notify_resident(question)
        
        return f"Question sent to resident: {question}"
    except Exception as e:
        return f"Error asking resident: {str(e)}"

@tool
async def send_file_to_resident(file_path: str, description: str = "") -> str:
    """
    Send a local file (document, image, etc.) to the local resident (human user) via their connected channels (Feishu/Telegram/Web).
    Args:
        file_path: The absolute or relative path to the local file you want to send.
        description: Optional text message to accompany the file.
    """
    try:
        import os
        from app.services.agent_service import agent_service
        
        if not os.path.exists(file_path):
            return f"Error: File not found at {file_path}"
            
        file_name = os.path.basename(file_path)
        ext = file_name.lower().split('.')[-1]
        
        # Simple type inference
        file_type = "image" if ext in ["jpg", "jpeg", "png", "gif"] else "file"
        
        media_payload = [{
            "type": file_type,
            "path": os.path.abspath(file_path),
            "name": file_name
        }]
        
        msg_text = description if description else f"Here is the file: {file_name}"
        
        # Pass media as kwargs to notify_resident
        await agent_service.notify_resident(content=msg_text, media=media_payload)
        
        return f"Successfully sent {file_name} to the resident."
    except Exception as e:
        return f"Error sending file to resident: {str(e)}"

@tool
async def update_core_memory(content: str) -> str:
    """
    Update or append to the agent's core long-term memory (MEMORY.md).
    Use this to save critical rules, user preferences, or "thought stamps" that you must never forget.
    This memory is loaded into your system prompt on every interaction.
    """
    try:
        from app.services.memory_store import memory_store
        # Read existing
        existing = memory_store.read_long_term()
        if existing and not existing.endswith("\n"):
            existing += "\n"
            
        new_content = existing + content if existing else content
        memory_store.write_long_term(new_content)
        return "Successfully appended to core long-term memory."
    except Exception as e:
        return f"Error updating core memory: {str(e)}"

@tool
async def append_daily_note(content: str) -> str:
    """
    Append a note or summary to today's daily diary (YYYY-MM-DD.md).
    Use this to journal important events, findings, or daily progress.
    """
    try:
        from app.services.memory_store import memory_store
        memory_store.append_today(content)
        return "Successfully appended to today's daily note."
    except Exception as e:
        return f"Error appending to daily note: {str(e)}"

# List of Tools to bind to the agent
AGENT_TOOLS = [
    send_p2p_message, send_file, ask_resident, send_file_to_resident, get_my_status, read_community_rules, update_system_parameter, 
    search_chat_history, update_core_memory, append_daily_note,
    propose_election, submit_proposal, publish_research, cast_ballot, get_election_status, 
    pay_resident, check_my_balance, generate_archive, get_latest_block, search_web, 
    read_skill_guide, execute_shell_command,
    list_dir, read_file, write_file, edit_file, copy_files, move_files,
    fetch_web_page,
    schedule_reminder, list_reminders, cancel_reminder,
    start_scheduler, get_scheduler_status,
    delegate_task,
] + TASK_TOOLS

# Specialized toolset for the Self-Healing Sub-Agent
REPAIR_TOOLS = [
    list_dir, read_file, write_file, edit_file, # Exploration & Basic Edit
    submit_code_fix # The actual repair submission
]
