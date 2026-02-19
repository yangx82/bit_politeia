from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any
from datetime import datetime, timedelta
import uuid
import logging
from .models import Node

logger = logging.getLogger(__name__)

class ElectionType(Enum):
    CORE_NODE = "core_node_election"
    PROPOSAL_VOTE = "proposal_vote"
    RESEARCH_EVALUATION = "research_evaluation"

@dataclass
class Proposal:
    proposal_id: str
    initiator_id: str
    group_id: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    scope: str = "group" # group or inclusive_subgroups
    status: str = "discussed" # discussed, voting, passed, failed
    pdf_hash: Optional[str] = None # For research proposals

@dataclass
class Vote:
    voter_id: str
    candidate_id: Optional[str] = None # For Election. For Proposal, can be None or "yes"/"no" placeholders
    timestamp: datetime = field(default_factory=datetime.now)
    signature: str = ""
    approval: bool = True # True=Approve/Yes, False=Reject/No
    reason: str = "" # Mandatory for proposal votes
    reward_amount: float = 0.0 # For research evaluation

@dataclass
class Election:
    election_id: str
    group_id: str
    election_type: ElectionType
    initiator_id: str
    start_time: datetime
    end_time: datetime
    candidates: List[str] = field(default_factory=list) # For Core Node Election
    proposal_id: Optional[str] = None # For Proposal Vote
    eligible_voters: Set[str] = field(default_factory=set) 
    votes: Dict[str, List[Vote]] = field(default_factory=dict)
    status: str = "active"
    target_positions: int = 1
    excluded_voters: Set[str] = field(default_factory=set) # e.g. Proposal author

    @property
    def total_votes(self) -> int:
        return len(self.votes)

    @property
    def participation_rate(self) -> float:
        effective_voters = self.eligible_voters - self.excluded_voters
        if not effective_voters:
            return 0.0
        return len(self.votes) / len(effective_voters)

    def is_quorum_met(self) -> bool:
        return self.participation_rate > 0.8

    def tally(self) -> Dict[str, Any]:
        if not self.is_quorum_met():
            return {"valid": False, "reason": "Quorum not met (<80%)", "winners": []}

        if self.election_type == ElectionType.PROPOSAL_VOTE:
            # Tally for Proposal
            approvals = 0
            rejections = 0
            abstentions = 0 
            
            for ballot in self.votes.values():
                for vote in ballot:
                    if vote.approval:
                        approvals += 1
                    else:
                        rejections += 1
            
            total_cast = approvals + rejections + abstentions
            passed = False
            if total_cast > 0 and (approvals / total_cast) > 0.5:
                passed = True
            
            return {
                "valid": True,
                "passed": passed,
                "approvals": approvals,
                "rejections": rejections,
                "total_votes": total_cast
            }

        elif self.election_type == ElectionType.RESEARCH_EVALUATION:
            # Tally for Research Reward
            evaluations = []
            total_amount = 0.0
            
            for ballot in self.votes.values():
                for vote in ballot:
                    evaluations.append({
                        "voter_id": vote.voter_id,
                        "amount": vote.reward_amount,
                        "reason": vote.reason
                    })
                    total_amount += vote.reward_amount
            
            avg_amount = total_amount / len(evaluations) if evaluations else 0.0
            
            return {
                "valid": True,
                "evaluations": evaluations,
                "average_amount": avg_amount,
                "total_evaluators": len(evaluations)
            }

        # Original Tally for Candidates
        counts = {c: 0 for c in self.candidates}
        for ballot in self.votes.values():
            for vote in ballot:
                if vote.candidate_id and vote.candidate_id in counts:
                     if vote.approval:
                         counts[vote.candidate_id] += 1
        
        winners = []
        sorted_candidates = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        
        threshold = self.total_votes / 2
        for cand, count in sorted_candidates:
            if count > threshold:
                winners.append(cand)
            
            if len(winners) >= self.target_positions:
                break
        
        return {
            "valid": True,
            "winners": winners,
            "counts": counts,
            "total_votes": self.total_votes
        }
    
    def to_dict(self) -> dict:
        return {
            "election_id": self.election_id,
            "group_id": self.group_id,
            "election_type": self.election_type.value,
            "initiator_id": self.initiator_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "candidates": self.candidates,
            "proposal_id": self.proposal_id,
            "eligible_voters": list(self.eligible_voters),
            "votes": {k: [v.to_dict() for v in val] for k, val in self.votes.items()},
            "status": self.status,
            "target_positions": self.target_positions,
            "excluded_voters": list(self.excluded_voters)
        }

    @classmethod
    def from_dict(cls, data: dict):
        e = cls(
            election_id=data["election_id"],
            group_id=data["group_id"],
            election_type=ElectionType(data["election_type"]),
            initiator_id=data["initiator_id"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]),
            candidates=data.get("candidates", []),
            proposal_id=data.get("proposal_id"),
            eligible_voters=set(data.get("eligible_voters", [])),
            status=data.get("status", "active"),
            target_positions=data.get("target_positions", 1),
            excluded_voters=set(data.get("excluded_voters", []))
        )
        if "votes" in data:
            e.votes = {k: [Vote(**v) for v in val] for k, val in data["votes"].items()}
        return e

@dataclass
class Proposal:
    proposal_id: str
    initiator_id: str
    group_id: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    scope: str = "group"
    status: str = "discussed"
    pdf_hash: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "initiator_id": self.initiator_id,
            "group_id": self.group_id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "scope": self.scope,
            "status": self.status,
            "pdf_hash": self.pdf_hash
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            proposal_id=data["proposal_id"],
            initiator_id=data["initiator_id"],
            group_id=data["group_id"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            scope=data.get("scope", "group"),
            status=data.get("status", "discussed"),
            pdf_hash=data.get("pdf_hash")
        )

@dataclass
class Vote:
    voter_id: str
    candidate_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    signature: str = ""
    approval: bool = True
    reason: str = ""
    reward_amount: float = 0.0

    def to_dict(self) -> dict:
        return {
            "voter_id": self.voter_id,
            "candidate_id": self.candidate_id,
            "timestamp": self.timestamp.isoformat(),
            "signature": self.signature,
            "approval": self.approval,
            "reason": self.reason,
            "reward_amount": self.reward_amount
        }

class GovernanceManager:
    """Manages elections and proposals for a node."""
    def __init__(self, node_id: str, storage_path: str = "governance_store.json"):
        self.node_id = node_id
        self.storage_path = storage_path
        self.active_elections: Dict[str, Election] = {}
        self.proposals: Dict[str, Proposal] = {}
        self.load_state()
        
    def save_state(self):
        import json
        data = {
            "proposals": {k: v.to_dict() for k, v in self.proposals.items()},
            "elections": {k: v.to_dict() for k, v in self.active_elections.items()}
        }
        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save governance state: {e}")

    def load_state(self):
        import json
        import os
        if not os.path.exists(self.storage_path):
            return
            
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            for k, v in data.get("proposals", {}).items():
                self.proposals[k] = Proposal.from_dict(v)
                
            for k, v in data.get("elections", {}).items():
                self.active_elections[k] = Election.from_dict(v)
                
            logger.info(f"Loaded {len(self.proposals)} proposals and {len(self.active_elections)} elections.")
        except Exception as e:
            logger.error(f"Failed to load governance state: {e}")

    def initiate_election(self, group_id: str, candidates: List[str], duration_minutes: int = 60) -> Election:
        election_id = str(uuid.uuid4())
        election = Election(
            election_id=election_id,
            group_id=group_id,
            election_type=ElectionType.CORE_NODE,
            initiator_id=self.node_id,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(minutes=duration_minutes),
            candidates=candidates,
            eligible_voters=set()
        )
        self.active_elections[election_id] = election
        self.save_state()
        return election

    def initiate_proposal(self, group_id: str, content: str, duration_minutes: int = 60) -> tuple[Proposal, Election]:
        proposal_id = str(uuid.uuid4())
        proposal = Proposal(
            proposal_id=proposal_id,
            initiator_id=self.node_id,
            group_id=group_id,
            content=content
        )
        self.proposals[proposal_id] = proposal
        
        # Immediately start voting (Simulating Host action)
        election_id = str(uuid.uuid4())
        election = Election(
            election_id=election_id,
            group_id=group_id,
            election_type=ElectionType.PROPOSAL_VOTE,
            initiator_id=self.node_id, # Host logic simplified
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(minutes=duration_minutes),
            proposal_id=proposal_id,
            eligible_voters=set()
        )
        self.active_elections[election_id] = election
        self.save_state()
        return proposal, election

    def initiate_research_publication(self, group_id: str, content: str, pdf_hash: str, duration_minutes: int = 60) -> tuple[Proposal, Election]:
        proposal_id = str(uuid.uuid4())
        proposal = Proposal(
            proposal_id=proposal_id,
            initiator_id=self.node_id,
            group_id=group_id,
            content=content,
            pdf_hash=pdf_hash
        )
        self.proposals[proposal_id] = proposal
        
        election_id = str(uuid.uuid4())
        election = Election(
            election_id=election_id,
            group_id=group_id,
            election_type=ElectionType.RESEARCH_EVALUATION,
            initiator_id=self.node_id,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(minutes=duration_minutes),
            proposal_id=proposal_id,
            eligible_voters=set(),
            excluded_voters={self.node_id} # Exclude author from quorum/voting
        )
        self.active_elections[election_id] = election
        self.save_state()
        return proposal, election

    def receive_ballot(self, election_id: str, votes: List[Vote]) -> bool:
        if election_id not in self.active_elections:
            return False
            
        election = self.active_elections[election_id]
        if not votes:
            return False
            
        voter_id = votes[0].voter_id
        # Simplified eligibility check implementation for saving state demo
        # Real implementation would check against eligible_voters
        # if voter_id not in election.eligible_voters: ...
        
        if datetime.now() > election.end_time:
            logger.warning(f"Vote received after deadline for {election_id}")
            return False

        # Validation Logic (Preserved from original)
        if election.election_type == ElectionType.CORE_NODE:
            # Validate approvals <= target
            approvals = 0
            for v in votes:
                if v.approval:
                    # ALLOW WRITE-INS
                    if v.candidate_id and v.candidate_id not in election.candidates:
                         election.candidates.append(v.candidate_id)
                    approvals += 1
            if approvals > election.target_positions:
                return False
        
        elif election.election_type == ElectionType.PROPOSAL_VOTE:
            for v in votes:
                if not v.reason or len(v.reason.strip()) == 0:
                     return False
        
        elif election.election_type == ElectionType.RESEARCH_EVALUATION:
             for v in votes:
                if v.reward_amount < 0:
                     return False
                if not v.reason or len(v.reason.strip()) == 0:
                     return False

        election.votes[voter_id] = votes
        self.save_state()
        return True
