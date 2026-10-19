import sys
import site
import os

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

from datetime import datetime
from typing import Any

try:
    from pydantic import BaseModel
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items(): setattr(self, k, v)


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
    p2p_random_delay_max: float = 10.0
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
    model: str | None = None
    base_url: str | None = None


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


class ResearchPublishRequest(BaseModel):
    """Request to publish research."""
    group_id: str
    content: str
    pdf_hash: str
    duration_minutes: int = 60


class ResearchEvaluateRequest(BaseModel):
    """Request to evaluate research."""
    score: float = 0.0
    feedback: str
    reward_amount: float = 0.0


class ResearchProposalResponse(BaseModel):
    """Response for research proposal."""
    election_id: str
    group_id: str
    content: str
    pdf_hash: str
    status: str
    evaluations_count: int
    initiator_id: str
    start_time: str
    end_time: str


# ========================================================
# Multi-Agent High-Efficiency Collaboration SOP Schemas
# ========================================================

class AIPReviewCard(BaseModel):
    """Structured critique and assessment artifact submitted by peer nodes."""
    aip_id: str
    reviewer_id: str
    round: int = 1
    round_number: int = 1
    stance: str = "APPROVE"  # "APPROVE", "REJECT", "REQUEST_CHANGES"
    score: float = 0.0  # 0.0 - 10.0
    dimension_scores: dict[str, float] = {}  # correctness, security, modularity, necessity
    findings: list[str] = []
    critique_items: list[dict[str, Any]] = []  # [{"file": "...", "line_range": "...", "issue": "..."}]
    suggested_diff: str = ""
    suggested_action: str = ""
    confidence: float = 1.0
    timestamp: datetime | None = None

    class Config:
        from_attributes = True


class AIPConsensusReport(BaseModel):
    """Synthesis and arbitration decision published by the Core Node Arbiter."""
    aip_id: str
    session_id: str = ""
    arbiter_id: str = ""
    arbiter_node_id: str = ""
    current_round: int = 1
    decision: str = "PROCEED_TO_VOTE"  # "PROCEED_TO_VOTE", "REJECTED", "ROUND_2_AMENDMENT"
    average_score: float = 0.0
    approval_ratio: float = 0.0
    total_reviews: int = 0
    summary: str = ""
    synthesis_summary: str = ""
    timestamp: datetime | None = None

    class Config:
        from_attributes = True


class PreflightCheckResult(BaseModel):
    """Local static gate check result before broadcasting an AIP proposal."""
    aip_id: str = ""
    passed: bool = True
    score: float = 100.0
    ast_valid: bool = True
    dangerous_patterns_found: list[str] = []
    diff_non_empty: bool = True
    syntax_errors: list[str] = []
    missing_files: list[str] = []
    dependency_issues: list[str] = []
    summary: str = ""
    feedback: str = ""
    timestamp: datetime | None = None

    class Config:
        from_attributes = True

