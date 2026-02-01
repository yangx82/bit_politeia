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

class AgentStatus(BaseModel):
    is_online: bool
    reputation: int
    balance: float
    current_group: Optional[str] = None
    public_key: Optional[str] = None
