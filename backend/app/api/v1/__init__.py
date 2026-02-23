from fastapi import APIRouter, Depends, HTTPException, Body
from ...models.schemas import ChatRequest, ConfigRequest, Message, AgentStatus, P2PMessage
from ...services.agent_service import agent_service
from ...services.crypto_service import crypto_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
print("\n[!!!] API init loaded from " + __file__ + " [!!!]\n")

@router.post("/config", response_model=AgentStatus)
async def configure_agent(request: ConfigRequest):
    log_msg = f"Received ConfigRequest: {request.dict()}"
    logger.info(log_msg)
    print(f"\n>>> DEBUG: {log_msg}\n") # Guaranteed to show in stdout
    # Safely get research_field and bootstrap_url with fallback to avoid crash
    rf = getattr(request, 'research_field', 'AI Governance')
    bu = getattr(request, 'bootstrap_url', 'http://localhost:8000')
    await agent_service.configure_agent(
        request.base_url, 
        request.api_key, 
        request.model, 
        rf,
        bu,
        request.verbose_llm,
        request.bootstrap_verify,
        request.name,
        request.personality
    )
    return await get_status()

@router.post("/chat/instruction", response_model=Message)
async def send_instruction(request: ChatRequest):
    return await agent_service.process_user_instruction(request.content)

@router.get("/history", response_model=list[Message])
async def get_history():
    history = await agent_service.get_history()
    # DEBUG: Print last few messages to check chat_id/sender format
    if history:
        print(f"\n[DEBUG-HISTORY] Last message: sender={history[-1].sender}, chat_id={history[-1].chat_id}")
    return history

@router.get("/history/search", response_model=list[Message])
async def search_history(q: str = None, date_from: str = None, date_to: str = None):
    return await agent_service.search_history(q, date_from, date_to)

@router.post("/p2p/message")
async def receive_p2p_message(message: P2PMessage):
    return await agent_service.receive_p2p_message(message)

@router.get("/debug/inbox")
async def debug_inbox():
    """Debug: Get current contents of P2P inbox."""
    from ...services.p2p_service import p2p_service
    if p2p_service.local_node:
        return {"inbox": p2p_service.local_node.inbox, "node_id": p2p_service.local_node.node_id}
    return {"error": "Node not initialized"}

# Frontend P2P Endpoints
@router.get("/p2p/peers")
async def get_peers():
    """Get list of connected P2P nodes."""
    return await agent_service.get_peers()

@router.get("/p2p/groups")
async def get_groups():
    """Get list of P2P groups."""
    return await agent_service.get_groups()

@router.post("/p2p/send")
async def send_p2p_message(payload: dict = Body(...)):
    """Send a suggestion to the agent to send a P2P message."""
    target_id = payload.get("target_id")
    content = payload.get("content")
    if not target_id or not content:
        raise HTTPException(status_code=400, detail="target_id and content required")
    
    text_content = content.get("text") if isinstance(content, dict) else str(content)
    
    instruction = (
        f"【RESIDENT SUGGESTION】 I suggest you send the following message to '{target_id}':\n"
        f"\"{text_content}\"\n"
        f"Please evaluate this, and if you agree, use the 'send_p2p_message' tool to send it."
    )
    
    import asyncio
    asyncio.create_task(agent_service.process_user_instruction(instruction))
    return {"status": "suggestion_forwarded", "message": "Suggestion forwarded to your agent. Please check the Chat for their decision."}

@router.get("/archive/chain")
async def get_archive_chain():
    """Get the local blockchain archive."""
    return await agent_service.get_archive_chain()

@router.post("/archive/generate")
async def generate_archive_block():
    """Manually trigger generation of a new archive block."""
    result = await agent_service.run_archiving()
    return {"message": result}

@router.get("/status", response_model=AgentStatus)
async def get_status():
    status = await agent_service.get_status()
    # Inject Public Key from Crypto Service
    status.public_key = crypto_service.get_public_key_string()
    status.public_key = crypto_service.get_public_key_string()
    return status

from ...models.schemas import ProposalModel, ProposalCreateRequest, VoteRequest, ElectionModel

@router.get("/governance/proposals", response_model=list[dict])
async def get_proposals():
    """Get all proposals."""
    return await agent_service.get_proposals()

@router.post("/governance/proposals")
async def create_proposal(request: ProposalCreateRequest):
    """Send a suggestion to the agent to create a new proposal."""
    instruction = (
        f"【RESIDENT SUGGESTION】 I suggest you initiate a new governance proposal for group '{request.group_id}'.\n"
        f"Proposal Content: '{request.content}'.\n"
        f"Suggested duration: {request.duration_minutes} minutes.\n"
        f"Please evaluate this, and if you agree, use the 'create_proposal' tool to broadcast it to the network."
    )
    import asyncio
    asyncio.create_task(agent_service.process_user_instruction(instruction))
    return {"status": "suggestion_forwarded", "message": "Suggestion forwarded to your agent. Please check the Chat for their decision."}

@router.get("/governance/elections", response_model=list[dict])
async def get_elections():
    """Get active elections."""
    return await agent_service.get_elections()

@router.post("/governance/vote")
async def cast_vote(request: VoteRequest):
    """Send a suggestion to the agent to cast a vote."""
    vote_str = "Approve" if request.approval else "Reject"
    instruction = (
        f"【RESIDENT SUGGESTION】 I suggest you vote '{vote_str}' on election '{request.election_id}'.\n"
        f"My reason: '{request.reason}'.\n"
        f"Please evaluate this, and if you agree, use the 'vote_election' tool to cast the vote."
    )
    import asyncio
    asyncio.create_task(agent_service.process_user_instruction(instruction))
    return {"status": "suggestion_forwarded", "message": "Suggestion forwarded to your agent. Please check the Chat for their decision."}
