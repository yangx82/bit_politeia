from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Message(BaseModel):
    id: str
    content: str
    sender: str  # "user" or "agent"
    timestamp: datetime
    chat_id: Optional[str] = None

class ChatRequest(BaseModel):
    content: str

class ConfigRequest(BaseModel):
    base_url: str
    api_key: str
    model: str = "gpt-4o"
    research_field: Optional[str] = "AI Governance"
    bootstrap_url: Optional[str] = "http://localhost:8000"
    verbose_llm: bool = False
    bootstrap_verify: bool = True
    name: Optional[str] = "Agent"
    personality: Optional[str] = "Professional and helpful"

class AgentStatus(BaseModel):
    is_online: bool
    name: Optional[str] = None
    personality: Optional[str] = None
    reputation: int
    balance: float
    current_group: Optional[str] = None
    public_key: Optional[str] = None
    node_id: Optional[str] = None
    relay_connected: bool = False

class P2PMessage(BaseModel):
    message_id: str
    sender_id: str
    recipient_id: str
    message_type: str
    content: dict
    timestamp: datetime
    signature: str
    nonce: str

class ProposalModel(BaseModel):
    proposal_id: str
    initiator_id: str
    group_id: str
    content: str
    timestamp: datetime
    scope: str
    status: str
    pdf_hash: Optional[str] = None
    
    class Config:
        from_attributes = True

class VoteRequest(BaseModel):
    election_id: str
    candidate_id: Optional[str] = None
    approval: bool = True
    reason: str = ""
    reward_amount: float = 0.0

class ElectionModel(BaseModel):
    election_id: str
    group_id: str
    election_type: str
    initiator_id: str
    start_time: datetime
    end_time: datetime
    status: str
    candidates: List[str]
    proposal_id: Optional[str] = None
    results: Optional[dict] = None # For tally results

class ProposalCreateRequest(BaseModel):
    group_id: str
    content: str
    duration_minutes: int = 60

