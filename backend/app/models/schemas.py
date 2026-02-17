from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Message(BaseModel):
    id: str
    content: str
    sender: str  # "user" or "agent"
    timestamp: datetime

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
