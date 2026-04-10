from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any
from datetime import datetime, timedelta, timezone
import uuid
import logging
from pathlib import Path
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
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scope: str = "group" # group or inclusive_subgroups
    status: str = "discussed" # discussed, voting, passed, failed
    pdf_hash: Optional[str] = None # For research proposals

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "initiator_id": self.initiator_id,
            "group_id": self.group_id,
            "content": self.content,
            "timestamp": self.timestamp if isinstance(self.timestamp, str) else self.timestamp.isoformat(),
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
            # Support both datetime object and ISO string
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data["timestamp"], str) else data["timestamp"],
            scope=data.get("scope", "group"),
            status=data.get("status", "discussed"),
            pdf_hash=data.get("pdf_hash")
        )

@dataclass
class Vote:
    voter_id: str
    candidate_id: Optional[str] = None # For Election. For Proposal, can be None or "yes"/"no" placeholders
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    signature: str = ""
    approval: bool = True # True=Approve/Yes, False=Reject/No
    reason: str = "" # Mandatory for proposal votes
    reward_amount: float = 0.0 # For research evaluation

    def to_dict(self) -> dict:
        return {
            "voter_id": self.voter_id,
            "candidate_id": self.candidate_id,
            "timestamp": self.timestamp if isinstance(self.timestamp, str) else self.timestamp.isoformat(),
            "signature": self.signature,
            "approval": self.approval,
            "reason": self.reason,
            "reward_amount": self.reward_amount
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            voter_id=data["voter_id"],
            candidate_id=data.get("candidate_id"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data["timestamp"], str) else data["timestamp"],
            signature=data.get("signature", ""),
            approval=data.get("approval", True),
            reason=data.get("reason", ""),
            reward_amount=data.get("reward_amount", 0.0)
        )

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
        from ..services.community_config import community_config
        quorum_ratio = community_config.rules.get("election", {}).get("quorum_ratio", 0.8)
        return self.participation_rate >= quorum_ratio

    def tally(self) -> Dict[str, Any]:
        # Only mark as invalid if the election has ENDED and quorum is not met.
        # If it's still active, it's always valid to encourage participation.
        now = datetime.now(timezone.utc)
        if now > self.end_time and not self.is_quorum_met():
            return {
                "valid": False, 
                "reason": f"Quorum not met (<{int(self.participation_rate*100)}%). Required: 80%.", 
                "winners": [],
                "participation_rate": self.participation_rate
            }

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
                "total_votes": total_cast,
                "participation_rate": self.participation_rate
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
            "approvals": sum(counts.values()), # Total positive votes for all candidates
            "rejections": 0,
            "total_votes": self.total_votes,
            "participation_rate": self.participation_rate
        }
    
    def to_dict(self) -> dict:
        return {
            "election_id": self.election_id,
            "group_id": self.group_id,
            "election_type": self.election_type.value,
            "initiator_id": self.initiator_id,
            "start_time": self.start_time if isinstance(self.start_time, str) else self.start_time.isoformat(),
            "end_time": self.end_time if isinstance(self.end_time, str) else self.end_time.isoformat(),
            "candidates": self.candidates,
            "proposal_id": self.proposal_id,
            "content": self.content if hasattr(self, 'content') and self.content else (f"Selection of core nodes for group {self.group_id}" if self.election_type == ElectionType.CORE_NODE else "Community Vote"),
            "eligible_voters": list(self.eligible_voters),
            "votes": {k: [v.to_dict() for v in val] for k, val in self.votes.items()},
            "status": self.status,
            "target_positions": self.target_positions,
            "excluded_voters": list(self.excluded_voters),
            "participation_rate": self.participation_rate
        }

    @classmethod
    def from_dict(cls, data: dict):
        # Helper function to ensure timezone-aware datetime
        def parse_datetime(dt_value):
            if isinstance(dt_value, str):
                parsed = datetime.fromisoformat(dt_value)
                # If timezone-naive, assume UTC
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            elif isinstance(dt_value, datetime):
                # If timezone-naive, assume UTC
                if dt_value.tzinfo is None:
                    return dt_value.replace(tzinfo=timezone.utc)
                return dt_value
            return dt_value
        
        e = cls(
            election_id=data["election_id"],
            group_id=data["group_id"],
            election_type=ElectionType(data["election_type"]),
            initiator_id=data["initiator_id"],
            start_time=parse_datetime(data["start_time"]),
            end_time=parse_datetime(data["end_time"]),
            candidates=data.get("candidates", []),
            proposal_id=data.get("proposal_id"),
            eligible_voters=set(data.get("eligible_voters", [])),
            status=data.get("status", "active"),
            target_positions=data.get("target_positions", 1),
            excluded_voters=set(data.get("excluded_voters", []))
        )
        if "votes" in data:
            e.votes = {k: [Vote.from_dict(v) for v in val] for k, val in data["votes"].items()}
        return e

class GovernanceManager:
    """Manages elections and proposals for a node."""
    def __init__(self, node_id: str, storage_path: str = "backend/data/governance_store.json"):
        self.node_id = node_id
        self.storage_path = Path(storage_path)
        
        # Ensure data directory exists
        path_obj = Path(self.storage_path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        self.proposals: Dict[str, Proposal] = {}
        self.active_elections: Dict[str, Election] = {}
        self.finished_elections: Dict[str, Election] = {}
        self.load_state()
        
    def save_state(self):
        import json
        data = {
            "proposals": {k: v.to_dict() for k, v in self.proposals.items()},
            "active_elections": {k: v.to_dict() for k, v in self.active_elections.items()},
            "finished_elections": {k: v.to_dict() for k, v in self.finished_elections.items()}
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
                
            for k, v in data.get("active_elections", data.get("elections", {})).items():
                self.active_elections[k] = Election.from_dict(v)
            
            for k, v in data.get("finished_elections", {}).items():
                self.finished_elections[k] = Election.from_dict(v)
                
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
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(minutes=duration_minutes),
            candidates=candidates,
            eligible_voters=set()
        )
        self.active_elections[election_id] = election
        self.save_state()
        return election

    def initiate_proposal(self, group_id: str, content: str, duration_minutes: int = 60, eligible_voters: Optional[Set[str]] = None) -> tuple[Proposal, Election]:
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
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(minutes=duration_minutes),
            proposal_id=proposal_id,
            eligible_voters=eligible_voters if eligible_voters is not None else set()
        )
        self.active_elections[election_id] = election
        self.save_state()
        return proposal, election

    def initiate_research_publication(self, group_id: str, content: str, pdf_hash: str, duration_minutes: int = 60, eligible_voters: Optional[Set[str]] = None) -> tuple[Proposal, Election]:
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
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(minutes=duration_minutes),
            proposal_id=proposal_id,
            eligible_voters=eligible_voters if eligible_voters is not None else set(),
            excluded_voters={self.node_id} # Exclude author from quorum/voting
        )
        self.active_elections[election_id] = election
        self.save_state()
        return proposal, election

    def finalize_expired_elections(self):
        """Move elections from active to finished if they have passed their end_time."""
        now = datetime.now(timezone.utc)
        expired_ids = []
        for eid, e in self.active_elections.items():
            end_time = e.end_time
            # Ensure timezone-aware comparison
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            if now > end_time:
                expired_ids.append(eid)
        
        if not expired_ids:
            return
            
        for eid in expired_ids:
            election = self.active_elections.pop(eid)
            election.status = "finished"
            self.finished_elections[eid] = election
            logger.info(f"Governance: Finalized expired election {eid}")
            
        self.save_state()

    def receive_ballot(self, election_id: str, votes: List[Vote]) -> bool:
        # First, sync state to ensure we're not voting in something that just expired
        self.finalize_expired_elections()
        
        if election_id not in self.active_elections:
            return False
            
        election = self.active_elections[election_id]
        if not votes:
            return False
            
        voter_id = votes[0].voter_id
        # Simplified eligibility check implementation for saving state demo
        # Real implementation would check against eligible_voters
        # if voter_id not in election.eligible_voters: ...
        
        if datetime.now(timezone.utc) > election.end_time:
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

    def delete_proposal(self, proposal_id: str) -> bool:
        """Remove a proposal and its associated election from the store."""
        removed = False
        if proposal_id in self.proposals:
            del self.proposals[proposal_id]
            removed = True
            
        # Also remove associated election if exists
        elections_to_remove = [eid for eid, e in self.active_elections.items() if e.proposal_id == proposal_id]
        for eid in elections_to_remove:
            del self.active_elections[eid]
            removed = True
            
        if removed:
            self.save_state()
            logger.info(f"Governance: Removed proposal {proposal_id} and its elections.")
        return removed

    def delete_election(self, election_id: str) -> bool:
        """Remove a specific election from the store."""
        if election_id in self.active_elections:
            del self.active_elections[election_id]
            self.save_state()
            logger.info(f"Governance: Removed election {election_id}.")
            return True
        return False

    def receive_p2p_event(self, event_type: str, content: dict) -> bool:
        """
        Ingest governance events from the P2P network.
        """
        try:
            if event_type == "proposal":
                # Check for election data in proposal message
                election_data = content.get("election")
                proposal_data = content.get("proposal")
                
                if not election_data or not proposal_data:
                    logger.warning("Governance P2P: Malformed proposal/election message.")
                    return False
                
                election_id = election_data.get("election_id")
                if election_id in self.active_elections:
                    logger.debug(f"Governance P2P: Election {election_id} already exists locally.")
                    return True
                
                # Ingest Proposal
                proposal = Proposal.from_dict(proposal_data)
                self.proposals[proposal.proposal_id] = proposal
                
                # Ingest Election
                election = Election.from_dict(election_data)
                self.active_elections[election.election_id] = election
                
                logger.info(f"Governance P2P: Successfully ingested remote proposal {proposal.proposal_id}")
                self.save_state()
                return True
                
            elif event_type == "vote":
                election_id = content.get("election_id")
                vote_data = content.get("vote")
                
                if not election_id or not vote_data:
                    logger.warning("Governance P2P: Malformed vote message.")
                    return False
                
                if election_id not in self.active_elections:
                    # Should we buffer votes? For now, we only accept votes for known elections.
                    logger.warning(f"Governance P2P: Received vote for unknown election {election_id}")
                    return False
                
                # Ingest Vote
                vote = Vote.from_dict(vote_data)
                return self.receive_ballot(election_id, [vote])
                
            elif event_type == "election":
                election_data = content.get("election")
                if not election_data:
                    logger.warning("Governance P2P: Malformed standalone election message.")
                    return False
                
                election_id = election_data.get("election_id")
                if election_id in self.active_elections:
                    logger.debug(f"Governance P2P: Election {election_id} already exists locally.")
                    return True
                
                # Ingest Standalone Election
                election = Election.from_dict(election_data)
                self.active_elections[election.election_id] = election
                logger.info(f"Governance P2P: Successfully ingested remote election {election_id}")
                self.save_state()
                return True
                
            elif event_type == "group_config":
                group_id = content.get("group_id")
                core_node_ids = content.get("core_node_ids")
                
                if not group_id or core_node_ids is None:
                    logger.warning("Governance P2P: Malformed group_config message.")
                    return False
                
                # Update local group policy
                group = None
                from ..services.agent_service import agent_service
                if agent_service and agent_service.p2p_service and agent_service.p2p_service.network_manager:
                     group = agent_service.p2p_service.network_manager.get_group(group_id)
                
                if group:
                    group.update_core_nodes(core_node_ids)
                    logger.info(f"Governance P2P: Applied group configuration update for {group_id}")
                    return True
                return False
                
            return False
        except Exception as e:
            logger.error(f"Governance P2P Error: {e}")
            return False
