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
        bu
    )
    return await get_status()

@router.post("/chat/instruction", response_model=Message)
async def send_instruction(request: ChatRequest):
    return await agent_service.process_user_instruction(request.content)

@router.get("/history", response_model=list[Message])
async def get_history():
    return await agent_service.get_history()

@router.get("/history/search", response_model=list[Message])
async def search_history(q: str = None, date_from: str = None, date_to: str = None):
    return await agent_service.search_history(q, date_from, date_to)

@router.post("/p2p/message")
async def receive_p2p_message(message: P2PMessage):
    return await agent_service.receive_p2p_message(message)

# Frontend P2P Endpoints
@router.get("/p2p/peers")
async def get_peers():
    """Get list of connected P2P nodes."""
    return await agent_service.get_peers()

@router.post("/p2p/send")
async def send_p2p_message(payload: dict = Body(...)):
    """Send a direct P2P message."""
    target_id = payload.get("target_id")
    content = payload.get("content")
    if not target_id or not content:
        raise HTTPException(status_code=400, detail="target_id and content required")
    
    return await agent_service.send_p2p_message(target_id, content)

@router.get("/status", response_model=AgentStatus)
async def get_status():
    status = await agent_service.get_status()
    # Inject Public Key from Crypto Service
    status.public_key = crypto_service.get_public_key_string()
    return status
