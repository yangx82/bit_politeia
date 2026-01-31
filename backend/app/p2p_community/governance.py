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

class GovernanceManager:
    """Manages elections and proposals for a node."""
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.active_elections: Dict[str, Election] = {}
        self.proposals: Dict[str, Proposal] = {}
        
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
        return proposal, election

    def receive_ballot(self, election_id: str, votes: List[Vote]) -> bool:
        if election_id not in self.active_elections:
            return False
            
        election = self.active_elections[election_id]
        if not votes:
            return False
            
        voter_id = votes[0].voter_id
        if voter_id not in election.eligible_voters:
            logger.warning(f"Ineligible voter {voter_id} for election {election_id}")
            return False
        
        if voter_id in election.excluded_voters:
            logger.warning(f"Excluded voter {voter_id} attempted to vote in {election_id}")
            return False
            
        if datetime.now() > election.end_time:
            logger.warning(f"Vote received after deadline for {election_id}")
            return False

        # Validation Logic
        if election.election_type == ElectionType.CORE_NODE:
            # Validate approvals <= target
            approvals = 0
            for v in votes:
                if v.approval:
                    approvals += 1
            if approvals > election.target_positions:
                logger.warning(f"Invalid ballot: Too many approvals")
                return False
        
        elif election.election_type == ElectionType.PROPOSAL_VOTE:
            # Validate Reason exists
            for v in votes:
                if not v.reason or len(v.reason.strip()) == 0:
                     logger.warning("Invalid ballot: Proposal vote requires reason.")
                     # Rule: "并附上理由"
                     return False
        
        elif election.election_type == ElectionType.RESEARCH_EVALUATION:
             for v in votes:
                if v.reward_amount < 0:
                     logger.warning("Invalid ballot: Negative reward amount.")
                     return False
                if not v.reason or len(v.reason.strip()) == 0:
                     logger.warning("Invalid ballot: Research evaluation requires reason.")
                     return False

        election.votes[voter_id] = votes
        return True
