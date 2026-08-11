import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
UTC = timezone.utc
from enum import Enum
from pathlib import Path
from typing import Any

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
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    scope: str = "group"  # group or inclusive_subgroups
    status: str = "discussed"  # discussed, voting, passed, failed
    pdf_hash: str | None = None  # For research proposals

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "initiator_id": self.initiator_id,
            "group_id": self.group_id,
            "content": self.content,
            "timestamp": self.timestamp
            if isinstance(self.timestamp, str)
            else self.timestamp.isoformat(),
            "scope": self.scope,
            "status": self.status,
            "pdf_hash": self.pdf_hash,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            proposal_id=data["proposal_id"],
            initiator_id=data["initiator_id"],
            group_id=data["group_id"],
            content=data["content"],
            # Support both datetime object and ISO string
            timestamp=datetime.fromisoformat(data["timestamp"])
            if isinstance(data["timestamp"], str)
            else data["timestamp"],
            scope=data.get("scope", "group"),
            status=data.get("status", "discussed"),
            pdf_hash=data.get("pdf_hash"),
        )


@dataclass
class Vote:
    voter_id: str
    candidate_id: str | None = (
        None  # For Election. For Proposal, can be None or "yes"/"no" placeholders
    )
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    signature: str = ""
    approval: bool = True  # True=Approve/Yes, False=Reject/No
    reason: str = ""  # Mandatory for proposal votes
    reward_amount: float = 0.0  # For research evaluation

    def to_dict(self) -> dict:
        return {
            "voter_id": self.voter_id,
            "candidate_id": self.candidate_id,
            "timestamp": self.timestamp
            if isinstance(self.timestamp, str)
            else self.timestamp.isoformat(),
            "signature": self.signature,
            "approval": self.approval,
            "reason": self.reason,
            "reward_amount": self.reward_amount,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            voter_id=data["voter_id"],
            candidate_id=data.get("candidate_id"),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if isinstance(data["timestamp"], str)
            else data["timestamp"],
            signature=data.get("signature", ""),
            approval=data.get("approval", True),
            reason=data.get("reason", ""),
            reward_amount=data.get("reward_amount", 0.0),
        )


@dataclass
class Election:
    election_id: str
    group_id: str
    election_type: ElectionType
    initiator_id: str
    start_time: datetime
    end_time: datetime
    candidates: list[str] = field(default_factory=list)  # For Core Node Election
    proposal_id: str | None = None  # For Proposal Vote
    eligible_voters: set[str] = field(default_factory=set)
    votes: dict[str, list[Vote]] = field(default_factory=dict)
    status: str = "active"
    target_positions: int = 1
    excluded_voters: set[str] = field(default_factory=set)  # e.g. Proposal author
    payout_status: str = "pending"  # "pending", "paid", "failed", "no_reward", "insufficient_evaluations"
    payout_amount: float = 0.0  # Total reward amount to distribute
    payout_attempts: int = 0  # Number of payout attempts made
    max_payout_attempts: int = 3  # Maximum retry attempts before marking as failed
    payout_last_attempt: datetime | None = None  # Timestamp of last attempt
    payout_error: str | None = None  # Last error message if payout failed

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

    def tally(self) -> dict[str, Any]:
        # Only mark as invalid if the election has ENDED and quorum is not met.
        # If it's still active, it's always valid to encourage participation.
        now = datetime.now(UTC)
        if now > self.end_time and not self.is_quorum_met():
            return {
                "valid": False,
                "reason": f"Quorum not met (<{int(self.participation_rate * 100)}%). Required: 80%.",
                "winners": [],
                "participation_rate": self.participation_rate,
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
                "participation_rate": self.participation_rate,
            }

        elif self.election_type == ElectionType.RESEARCH_EVALUATION:
            # Tally for Research Reward
            evaluations = []
            total_amount = 0.0

            for ballot in self.votes.values():
                for vote in ballot:
                    evaluations.append(
                        {
                            "voter_id": vote.voter_id,
                            "amount": vote.reward_amount,
                            "reason": vote.reason,
                        }
                    )
                    total_amount += vote.reward_amount

            avg_amount = total_amount / len(evaluations) if evaluations else 0.0

            return {
                "valid": True,
                "evaluations": evaluations,
                "average_amount": avg_amount,
                "total_evaluators": len(evaluations),
            }

        # Original Tally for Candidates
        counts = dict.fromkeys(self.candidates, 0)
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
            "approvals": sum(counts.values()),  # Total positive votes for all candidates
            "rejections": 0,
            "total_votes": self.total_votes,
            "participation_rate": self.participation_rate,
        }

    def to_dict(self) -> dict:
        return {
            "election_id": self.election_id,
            "group_id": self.group_id,
            "election_type": self.election_type.value,
            "initiator_id": self.initiator_id,
            "start_time": self.start_time
            if isinstance(self.start_time, str)
            else self.start_time.isoformat(),
            "end_time": self.end_time
            if isinstance(self.end_time, str)
            else self.end_time.isoformat(),
            "candidates": self.candidates,
            "proposal_id": self.proposal_id,
            "content": self.content
            if hasattr(self, "content") and self.content
            else (
                f"Selection of core nodes for group {self.group_id}"
                if self.election_type == ElectionType.CORE_NODE
                else "Community Vote"
            ),
            "eligible_voters": list(self.eligible_voters),
            "votes": {k: [v.to_dict() for v in val] for k, val in self.votes.items()},
            "status": self.status,
            "target_positions": self.target_positions,
            "excluded_voters": list(self.excluded_voters),
            "participation_rate": self.participation_rate,
            "payout_status": self.payout_status,
            "payout_amount": self.payout_amount,
            "payout_attempts": self.payout_attempts,
            "max_payout_attempts": self.max_payout_attempts,
            "payout_last_attempt": self.payout_last_attempt.isoformat() if self.payout_last_attempt else None,
            "payout_error": self.payout_error,
        }

    @classmethod
    def from_dict(cls, data: dict):
        # Helper function to ensure timezone-aware datetime
        def parse_datetime(dt_value):
            if isinstance(dt_value, str):
                parsed = datetime.fromisoformat(dt_value)
                # If timezone-naive, assume UTC
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed
            elif isinstance(dt_value, datetime):
                # If timezone-naive, assume UTC
                if dt_value.tzinfo is None:
                    return dt_value.replace(tzinfo=UTC)
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
            excluded_voters=set(data.get("excluded_voters", [])),
            payout_status=data.get("payout_status", "pending"),
            payout_amount=data.get("payout_amount", 0.0),
            payout_attempts=data.get("payout_attempts", 0),
            max_payout_attempts=data.get("max_payout_attempts", 3),
            payout_last_attempt=parse_datetime(data["payout_last_attempt"]) if data.get("payout_last_attempt") else None,
            payout_error=data.get("payout_error"),
        )
        if "votes" in data:
            e.votes = {k: [Vote.from_dict(v) for v in val] for k, val in data["votes"].items()}
        return e


class GovernanceManager:
    """Manages elections and proposals for a node."""

    def __init__(self, node_id: str, storage_path: str = "backend/data/governance_store.json"):
        import threading
        self._lock = threading.Lock()
        self.node_id = node_id
        self.storage_path = Path(storage_path)

        # Ensure data directory exists
        path_obj = Path(self.storage_path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        self.proposals: dict[str, Proposal] = {}
        self.active_elections: dict[str, Election] = {}
        self.finished_elections: dict[str, Election] = {}
        self.load_state()

    def save_state(self):
        import json

        data = {
            "proposals": {k: v.to_dict() for k, v in self.proposals.items()},
            "active_elections": {k: v.to_dict() for k, v in self.active_elections.items()},
            "finished_elections": {k: v.to_dict() for k, v in self.finished_elections.items()},
        }
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save governance state: {e}")

    def load_state(self):
        import json
        import os

        if not os.path.exists(self.storage_path):
            return

        try:
            with open(self.storage_path, encoding="utf-8") as f:
                data = json.load(f)

            for k, v in data.get("proposals", {}).items():
                self.proposals[k] = Proposal.from_dict(v)

            for k, v in data.get("active_elections", data.get("elections", {})).items():
                self.active_elections[k] = Election.from_dict(v)

            for k, v in data.get("finished_elections", {}).items():
                self.finished_elections[k] = Election.from_dict(v)

            logger.info(
                f"Loaded {len(self.proposals)} proposals and {len(self.active_elections)} elections."
            )
        except Exception as e:
            logger.error(f"Failed to load governance state: {e}")

    def submit_research_evaluation(self, election_id: str, evaluator_id: str, score: float, feedback: str, reward_amount: float = 0) -> tuple[bool, str]:
        """Submit an evaluation for a research publication.
        
        Args:
            election_id: The election/proposal ID
            evaluator_id: The evaluator's node ID
            score: Quality score (0-5)
            feedback: Evaluation feedback text
            reward_amount: Proposed reward amount (deprecated, calculated from score)
        """
        if election_id not in self.active_elections:
            return False, "Election not found"

        election = self.active_elections[election_id]

        # Check if already evaluated by this evaluator (votes are keyed by voter_id)
        if evaluator_id in election.votes:
            return False, "Already evaluated by this evaluator"

        # Check if evaluator is the author (excluded from voting)
        if evaluator_id in election.excluded_voters:
            return False, "Author cannot evaluate their own research"

        # Validate score range
        if not (0 <= score <= 5):
            return False, "Score must be between 0 and 5"

        # Create vote for research evaluation
        # Store score in reward_amount field for averaging in finalize
        vote = Vote(
            voter_id=evaluator_id,
            candidate_id=None,  # Research evaluation doesn't have candidates
            timestamp=datetime.now(UTC),
            approval=score >= 3.0,  # Approve if score >= 3
            reason=feedback,
            reward_amount=score,  # Store score for averaging
        )

        # Store vote keyed by voter_id (matching receive_ballot pattern)
        election.votes[evaluator_id] = [vote]

        # Check if we have enough evaluations
        evaluation_count = len(election.votes)
        eligible_count = len(election.eligible_voters - election.excluded_voters)
        # Require at least 2 evaluations, or 50% of eligible voters (whichever is smaller)
        required_count = max(2, min(eligible_count, (eligible_count + 1) // 2))
        
        logger.info(f"Research evaluation: {evaluation_count}/{required_count} for election {election_id[:8]}")
        
        if evaluation_count >= required_count:
            success, msg = self.finalize_research_evaluation(election_id)
            if success:
                logger.info(f"Research evaluation finalized: {msg}")
            else:
                logger.warning(f"Failed to finalize research evaluation: {msg}")

        self.save_state()
        return True, f"Evaluation submitted successfully ({evaluation_count}/{required_count} evaluations)"

    def finalize_research_evaluation(self, election_id: str) -> tuple[bool, str]:
        """Finalize a research evaluation and calculate rewards.
        
        Updates:
        - Election status → finished
        - Proposal status → evaluated
        - Election payout_status → pending (for reward distribution)
        - Calculate and store payout_amount based on average score
        """
        if election_id not in self.active_elections:
            return False, "Election not found"

        election = self.active_elections[election_id]
        
        # Collect all votes
        all_votes = []
        for voter_votes in election.votes.values():
            all_votes.extend(voter_votes)

        if not all_votes:
            return False, "No evaluations submitted"

        # Calculate average score (stored in reward_amount field)
        total_score = sum(v.reward_amount for v in all_votes)
        avg_score = total_score / len(all_votes)

        # Update proposal status to "evaluated"
        if election.proposal_id and election.proposal_id in self.proposals:
            proposal = self.proposals[election.proposal_id]
            proposal.status = "evaluated"
            logger.info(f"Proposal {election.proposal_id[:8]} status updated to 'evaluated'")

        # Calculate payout amount based on average score (0-5 scale)
        # Convert to 0-100 stater range
        election.payout_amount = avg_score * 20.0  # 5.0 → 100 stater
        election.payout_attempts = 0  # Reset attempts counter
        
        # Move to finished elections and mark payout as pending
        election.status = "finished"
        election.payout_status = "pending"
        self.finished_elections[election_id] = election
        del self.active_elections[election_id]

        self.save_state()
        return True, f"Research evaluation finalized. Average score: {avg_score:.2f}, payout amount: {election.payout_amount:.1f} stater, payout pending."

    def get_research_proposals(self, group_id: str = None, status: str = None) -> list[dict]:
        """Get research proposals with optional filtering."""
        results = []

        # Search in active elections
        for election_id, election in self.active_elections.items():
            if election.election_type != ElectionType.RESEARCH_EVALUATION:
                continue
            if group_id and election.group_id != group_id:
                continue

            proposal = self.proposals.get(election.proposal_id)
            if not proposal:
                continue

            proposal_data = proposal.to_dict()
            proposal_data["election_id"] = election_id
            proposal_data["status"] = "active"
            proposal_data["evaluations_count"] = len(election.votes)
            results.append(proposal_data)

        # Search in finished elections
        for election_id, election in self.finished_elections.items():
            if election.election_type != ElectionType.RESEARCH_EVALUATION:
                continue
            if group_id and election.group_id != group_id:
                continue

            proposal = self.proposals.get(election.proposal_id)
            if not proposal:
                continue

            proposal_data = proposal.to_dict()
            proposal_data["election_id"] = election_id
            proposal_data["status"] = "completed"
            proposal_data["evaluations_count"] = len(election.votes)
            results.append(proposal_data)

        return results

    def get_research_proposal(self, election_id: str) -> dict:
        """Get detailed information about a research proposal."""
        election = self.active_elections.get(election_id) or self.finished_elections.get(election_id)
        if not election:
            return {}

        proposal = self.proposals.get(election.proposal_id)
        if not proposal:
            return {}

        proposal_data = proposal.to_dict()
        proposal_data["election_id"] = election_id
        proposal_data["status"] = "active" if election.status == "active" else "completed"
        
        # Collect all evaluations
        evaluations = []
        for voter_id, voter_votes in election.votes.items():
            for v in voter_votes:
                evaluations.append({
                    "evaluator_id": v.voter_id,
                    "score": v.reward_amount,
                    "feedback": v.reason,
                    "timestamp": v.timestamp.isoformat() if hasattr(v.timestamp, 'isoformat') else str(v.timestamp),
                })
        
        proposal_data["evaluations"] = evaluations
        proposal_data["evaluations_count"] = len(evaluations)

        return proposal_data

    def initiate_election(
        self, group_id: str, candidates: list[str], duration_minutes: int = 60
    ) -> Election:
        election_id = str(uuid.uuid4())
        election = Election(
            election_id=election_id,
            group_id=group_id,
            election_type=ElectionType.CORE_NODE,
            initiator_id=self.node_id,
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(minutes=duration_minutes),
            candidates=candidates,
            eligible_voters=set(),
        )
        self.active_elections[election_id] = election
        self.save_state()
        return election

    def initiate_proposal(
        self,
        group_id: str,
        content: str,
        duration_minutes: int = 60,
        eligible_voters: set[str] | None = None,
    ) -> tuple[Proposal, Election]:
        proposal_id = str(uuid.uuid4())
        proposal = Proposal(
            proposal_id=proposal_id, initiator_id=self.node_id, group_id=group_id, content=content
        )
        self.proposals[proposal_id] = proposal

        # Immediately start voting (Simulating Host action)
        election_id = str(uuid.uuid4())
        election = Election(
            election_id=election_id,
            group_id=group_id,
            election_type=ElectionType.PROPOSAL_VOTE,
            initiator_id=self.node_id,  # Host logic simplified
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(minutes=duration_minutes),
            proposal_id=proposal_id,
            eligible_voters=eligible_voters if eligible_voters is not None else set(),
        )
        self.active_elections[election_id] = election
        self.save_state()
        return proposal, election

    def initiate_research_publication(
        self,
        group_id: str,
        content: str,
        pdf_hash: str,
        duration_minutes: int = 60,
        eligible_voters: set[str] | None = None,
    ) -> tuple[Proposal, Election]:
        proposal_id = str(uuid.uuid4())
        proposal = Proposal(
            proposal_id=proposal_id,
            initiator_id=self.node_id,
            group_id=group_id,
            content=content,
            pdf_hash=pdf_hash,
        )
        self.proposals[proposal_id] = proposal

        election_id = str(uuid.uuid4())
        election = Election(
            election_id=election_id,
            group_id=group_id,
            election_type=ElectionType.RESEARCH_EVALUATION,
            initiator_id=self.node_id,
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(minutes=duration_minutes),
            proposal_id=proposal_id,
            eligible_voters=eligible_voters if eligible_voters is not None else set(),
            excluded_voters={self.node_id},  # Exclude author from quorum/voting
        )
        self.active_elections[election_id] = election
        self.save_state()
        return proposal, election

    def finalize_expired_elections(self) -> list[str]:
        """Move elections from active to finished if they have passed their end_time.
        
        For RESEARCH_EVALUATION elections:
        - If enough evaluations collected → payout_status = "pending" (rewards will be distributed)
        - If not enough evaluations → payout_status = "insufficient_evaluations" (no rewards)
        """
        with self._lock:
            now = datetime.now(UTC)
            expired_ids = []
            for eid, e in list(self.active_elections.items()):
                end_time = e.end_time
                # Ensure timezone-aware comparison
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=UTC)
                if now > end_time:
                    expired_ids.append(eid)

            if not expired_ids:
                return []

            for eid in expired_ids:
                election = self.active_elections.pop(eid, None)
                if not election:
                    continue
                election.status = "finished"
            
            # Special handling for RESEARCH_EVALUATION elections
            if election.election_type == ElectionType.RESEARCH_EVALUATION:
                evaluation_count = len(election.votes)
                eligible_count = len(election.eligible_voters - election.excluded_voters)
                required_count = max(2, min(eligible_count, (eligible_count + 1) // 2))
                
                if evaluation_count >= required_count:
                    # Enough evaluations - mark for reward distribution
                    election.payout_status = "pending"
                    logger.info(f"Research election {eid[:8]} expired with sufficient evaluations ({evaluation_count}/{required_count}), payout pending")
                else:
                    # Not enough evaluations - no rewards
                    election.payout_status = "insufficient_evaluations"
                    logger.warning(f"Research election {eid[:8]} expired with insufficient evaluations ({evaluation_count}/{required_count}), no rewards")
                
                # Update proposal status
                if election.proposal_id and election.proposal_id in self.proposals:
                    proposal = self.proposals[election.proposal_id]
                    if evaluation_count >= required_count:
                        proposal.status = "evaluated"
                    else:
                        proposal.status = "evaluation_failed"
            
            self.finished_elections[eid] = election
            logger.info(f"Governance: Finalized expired election {eid}")

        self.save_state()
        return expired_ids

    def receive_ballot(self, election_id: str, votes: list[Vote]) -> bool:
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

        if datetime.now(UTC) > election.end_time:
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
        elections_to_remove = [
            eid for eid, e in self.active_elections.items() if e.proposal_id == proposal_id
        ]
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
                # Proposal content can be wrapped in {"proposal": ..., "election": ...} or be a raw proposal dict
                if isinstance(content, dict) and "proposal" in content and isinstance(content["proposal"], dict):
                    proposal_data = content["proposal"]
                    election_data = content.get("election")
                elif isinstance(content, dict) and "proposal_id" in content:
                    proposal_data = content
                    election_data = content.get("election")
                else:
                    logger.warning(f"Governance P2P: Malformed proposal message (missing proposal dict): {content}")
                    return False

                if not proposal_data:
                    logger.warning("Governance P2P: Malformed proposal message.")
                    return False

                # Ingest Proposal
                proposal = Proposal.from_dict(proposal_data)
                self.proposals[proposal.proposal_id] = proposal

                # Ingest Election if attached and not already known
                if election_data and isinstance(election_data, dict):
                    election_id = election_data.get("election_id")
                    if election_id and election_id in self.active_elections:
                        logger.debug(f"Governance P2P: Election {election_id} already exists locally.")
                    elif election_id:
                        election = Election.from_dict(election_data)
                        self.active_elections[election.election_id] = election

                logger.info(
                    f"Governance P2P: Successfully ingested remote proposal {proposal.proposal_id}"
                )
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
                    logger.warning(
                        f"Governance P2P: Received vote for unknown election {election_id}"
                    )
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

                if (
                    agent_service
                    and agent_service.p2p_service
                    and agent_service.p2p_service.network_manager
                ):
                    group = agent_service.p2p_service.network_manager.get_group(group_id)

                if group:
                    group.update_core_nodes(core_node_ids)
                    logger.info(
                        f"Governance P2P: Applied group configuration update for {group_id}"
                    )
                    return True
                return False

            return False
        except Exception as e:
            logger.error(f"Governance P2P Error: {e}")
            return False
