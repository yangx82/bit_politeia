from datetime import datetime

from pydantic import BaseModel


class Message(BaseModel):
    id: str
    content: str
    sender: str  # "user" or "agent"
    timestamp: datetime
    msg_type: str = "chat"  # chat, system, checkpoint, etc.
    session_id: str | None = None
    status: str | None = None  # pending, sent, failed
    metadata: dict | None = None  # For internal flags (e.g., is_p2p)


class ChatRequest(BaseModel):
    content: str


class ConfigRequest(BaseModel):
    base_url: str
    api_key: str
    model: str = "gpt-4o"
    research_field: str | None = "AI Governance"
    bootstrap_url: str | None = "http://localhost:8000"
    verbose_llm: bool = False
    bootstrap_verify: bool = True
    name: str | None = "Agent"
    personality: str | None = "Professional and helpful"
    p2p_reply_delay: int = 60
    agent_language: str = "中文"
    ralph_wiggum_mode: bool = False


class AgentStatus(BaseModel):
    is_online: bool
    name: str | None = None
    personality: str | None = None
    reputation: int
    balance: float
    current_group: str | None = None
    public_key: str | None = None
    node_id: str | None = None
    relay_connected: bool = False
    ralph_wiggum_mode: bool = False


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
    pdf_hash: str | None = None

    class Config:
        from_attributes = True


class VoteRequest(BaseModel):
    election_id: str
    candidate_id: str | None = None
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
    candidates: list[str]
    proposal_id: str | None = None
    results: dict | None = None  # For tally results


class ProposalCreateRequest(BaseModel):
    group_id: str
    content: str
    duration_minutes: int = 60
