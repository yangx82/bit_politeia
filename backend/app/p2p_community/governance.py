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
    ARCHITECTURE_EVOLUTION = "architecture_evolution"


@dataclass
class AIPProposal:
    aip_id: str
    initiator_id: str
    title: str
    description: str
    target_files: list[str] = field(default_factory=list)
    proposed_diff: str = ""
    research_sources: list[str] = field(default_factory=list)
    sandbox_results: dict[str, Any] = field(default_factory=dict)
    status: str = "draft"  # draft, proposed, debating, voting, sandbox_passed, pr_submitted, merged, rejected
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        return {
            "aip_id": self.aip_id,
            "initiator_id": self.initiator_id,
            "title": self.title,
            "description": self.description,
            "target_files": self.target_files,
            "proposed_diff": self.proposed_diff,
            "research_sources": self.research_sources,
            "sandbox_results": self.sandbox_results,
            "status": self.status,
            "timestamp": self.timestamp.isoformat()
            if isinstance(self.timestamp, datetime)
            else self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            aip_id=data["aip_id"],
            initiator_id=data["initiator_id"],
            title=data.get("title", ""),
            description=data.get("description", ""),
            target_files=data.get("target_files", []),
            proposed_diff=data.get("proposed_diff", ""),
            research_sources=data.get("research_sources", []),
            sandbox_results=data.get("sandbox_results", {}),
            status=data.get("status", "draft"),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if isinstance(data.get("timestamp"), str)
            else data.get("timestamp", datetime.now(UTC)),
        )



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
        # Extract timestamp safely
        raw_ts = data.get("timestamp")
        if isinstance(raw_ts, str):
            try:
                ts = datetime.fromisoformat(raw_ts)
            except Exception:
                ts = datetime.now(UTC)
        elif isinstance(raw_ts, (int, float)):
            ts = datetime.fromtimestamp(raw_ts, tz=UTC)
        elif isinstance(raw_ts, datetime):
            ts = raw_ts
        else:
            ts = datetime.now(UTC)

        content = data.get("content") or data.get("text") or data.get("title") or data.get("description") or "Proposal without description"

        return cls(
            proposal_id=str(data.get("proposal_id") or str(uuid.uuid4())),
            initiator_id=str(data.get("initiator_id") or "unknown_node"),
            group_id=str(data.get("group_id") or "global"),
            content=str(content),
            timestamp=ts,
            scope=str(data.get("scope", "group")),
            status=str(data.get("status", "discussed")),
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
        now = datetime.now(UTC)

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

            effective_voters = self.eligible_voters - self.excluded_voters
            total_effective = len(effective_voters) if effective_voters else 0
            rem_voters = max(0, total_effective - len(self.votes))

            # Fast-Reject Early Termination:
            # If maximum possible approvals (current approvals + all remaining uncast votes) <= 50% of total voters,
            # or if rejections strictly exceed 50% of total voters, mathematically the proposal CANNOT pass under any circumstance.
            early_rejected = False
            if total_effective > 0:
                if (approvals + rem_voters) <= (total_effective / 2):
                    early_rejected = True
                    passed = False
                elif rejections > (total_effective / 2):
                    early_rejected = True
                    passed = False

            # Early-Pass Early Termination:
            # If approvals strictly exceed 50% of total eligible voters, mathematically the proposal HAS passed.
            early_passed = False
            if total_effective > 0:
                if approvals > (total_effective / 2):
                    early_passed = True
                    passed = True
                elif len(self.votes) >= total_effective and passed:
                    early_passed = True

            # Validity evaluation:
            # 1. If early_passed or early_rejected is triggered, majority consensus is mathematically guaranteed.
            #    Outcome is binding and valid regardless of remaining voter turnout.
            # 2. If active (now <= end_time), valid = True to encourage ongoing participation.
            # 3. If ended without early termination and participation < quorum, then valid = False (流拍).
            valid = True
            reason = None
            if not early_passed and not early_rejected:
                if now > self.end_time and not self.is_quorum_met():
                    valid = False
                    passed = False
                    reason = f"Quorum not met (<{int(self.participation_rate * 100)}%). Required: 80%."

            return {
                "valid": valid,
                "passed": passed,
                "early_rejected": early_rejected,
                "early_passed": early_passed,
                "approvals": approvals,
                "rejections": rejections,
                "total_votes": total_cast,
                "participation_rate": self.participation_rate,
                "reason": reason,
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

            valid = True
            reason = None
            if now > self.end_time and not self.is_quorum_met():
                valid = False
                reason = f"Quorum not met (<{int(self.participation_rate * 100)}%). Required: 80%."

            return {
                "valid": valid,
                "evaluations": evaluations,
                "average_amount": avg_amount,
                "total_evaluators": len(evaluations),
                "total_votes": len(self.votes),
                "participation_rate": self.participation_rate,
                "reason": reason,
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

        valid = True
        reason = None
        if now > self.end_time and not self.is_quorum_met():
            valid = False
            winners = []
            reason = f"Quorum not met (<{int(self.participation_rate * 100)}%). Required: 80%."

        return {
            "valid": valid,
            "winners": winners,
            "counts": counts,
            "approvals": sum(counts.values()),  # Total positive votes for all candidates
            "rejections": 0,
            "total_votes": self.total_votes,
            "participation_rate": self.participation_rate,
            "reason": reason,
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
            "eligible_voters": sorted(list(self.eligible_voters)),
            "votes": {k: [v.to_dict() for v in val] for k, val in sorted(self.votes.items())},
            "status": self.status,
            "target_positions": self.target_positions,
            "excluded_voters": sorted(list(self.excluded_voters)),
            "participation_rate": round(self.participation_rate, 4),
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

    def get_election_for_proposal(self, proposal_id: str) -> Election | None:
        """Finds the active or finished election associated with a proposal_id."""
        for e in self.active_elections.values():
            if e.proposal_id == proposal_id:
                return e
        for e in self.finished_elections.values():
            if e.proposal_id == proposal_id:
                return e
        return None

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
        auto_approve: bool = False,
    ) -> tuple[Proposal, Election]:
        proposal_id = str(uuid.uuid4())
        proposal = Proposal(
            proposal_id=proposal_id, initiator_id=self.node_id, group_id=group_id, content=content
        )
        self.proposals[proposal_id] = proposal

        # Immediately start voting (Simulating Host action)
        election_id = str(uuid.uuid4())
        voters_set = set(eligible_voters) if eligible_voters is not None else set()
        if auto_approve and self.node_id and voters_set:
            voters_set.add(self.node_id)

        election = Election(
            election_id=election_id,
            group_id=group_id,
            election_type=ElectionType.PROPOSAL_VOTE,
            initiator_id=self.node_id,  # Host logic simplified
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(minutes=duration_minutes),
            proposal_id=proposal_id,
            eligible_voters=voters_set,
        )

        if auto_approve and self.node_id:
            initiator_vote = Vote(
                voter_id=self.node_id,
                approval=True,
                reason="Proposal Initiator: Auto-voted APPROVE upon creation",
                timestamp=datetime.now(UTC),
            )
            election.votes[self.node_id] = [initiator_vote]

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
                # Dynamically check for early pass or early reject on proposal votes
                if e.election_type == ElectionType.PROPOSAL_VOTE and e.status not in ["early_rejected", "early_passed"]:
                    t = e.tally()
                    if t.get("early_rejected"):
                        e.status = "early_rejected"
                    elif t.get("early_passed"):
                        e.status = "early_passed"

                if now > end_time or getattr(e, "status", "") in ["early_rejected", "early_passed"]:
                    expired_ids.append(eid)

            if not expired_ids:
                return []

            for eid in expired_ids:
                election = self.active_elections.pop(eid, None)
                if not election:
                    continue
                # Mark status as finished so it is uniformly archived
                election.status = "finished"

                # Special handling for RESEARCH_EVALUATION elections
                if election.election_type == ElectionType.RESEARCH_EVALUATION:
                    evaluation_count = len(election.votes)
                    eligible_count = len(election.eligible_voters - election.excluded_voters)
                    required_count = max(2, min(eligible_count, (eligible_count + 1) // 2))

                    if evaluation_count >= required_count:
                        election.payout_status = "pending"
                        logger.info(f"Research election {eid[:8]} with sufficient evaluations ({evaluation_count}/{required_count}), payout pending")
                    else:
                        election.payout_status = "insufficient_evaluations"
                        logger.warning(f"Research election {eid[:8]} with insufficient evaluations ({evaluation_count}/{required_count}), no rewards")

                    # Update proposal status
                    if election.proposal_id and election.proposal_id in self.proposals:
                        proposal = self.proposals[election.proposal_id]
                        if evaluation_count >= required_count:
                            proposal.status = "evaluated"
                        else:
                            proposal.status = "evaluation_failed"

                elif election.election_type == ElectionType.PROPOSAL_VOTE:
                    tally_res = election.tally()
                    if election.proposal_id and election.proposal_id in self.proposals:
                        proposal = self.proposals[election.proposal_id]
                        if tally_res.get("passed"):
                            proposal.status = "passed"
                            self._handle_aip_passed(proposal)
                        else:
                            proposal.status = "failed"
                            try:
                                try:
                                    from app.services.evolution_service import evolution_service
                                    from app.services.crypto_service import crypto_service
                                except (ImportError, ModuleNotFoundError):
                                    from ..services.evolution_service import evolution_service
                                    from ..services.crypto_service import crypto_service
                                my_id = crypto_service.get_node_id()
                                if proposal.initiator_id in [my_id, "self"] or proposal.initiator_id.startswith(my_id[:8]):
                                    evolution_service.record_rejection_strike(
                                        reason=f"Proposal {proposal.proposal_id} rejected in governance voting ({tally_res.get('rejections', 0)} rejections).",
                                        aip_id=proposal.proposal_id,
                                    )
                            except Exception as ex:
                                logger.warning(f"Failed to record evolution rejection strike: {ex}")

                self.finished_elections[eid] = election
                logger.info(f"Governance: Finalized election {eid} (status={election.status})")

        self.save_state()
        return expired_ids

    def _handle_aip_passed(self, proposal: Proposal):
        """When an AIP passes community vote, trigger automated code landing & GitHub PR for proposing node."""
        import json
        import asyncio

        aip_id = None
        try:
            c_data = json.loads(proposal.content) if isinstance(proposal.content, str) else proposal.content
            if isinstance(c_data, dict) and c_data.get("type") == "architecture_evolution":
                aip_id = c_data.get("aip", {}).get("aip_id")
        except Exception:
            pass

        if not aip_id:
            aip_id = proposal.proposal_id

        try:
            try:
                from app.services.evolution_service import evolution_service
                from app.services.crypto_service import crypto_service
            except (ImportError, ModuleNotFoundError):
                from ..services.evolution_service import evolution_service
                from ..services.crypto_service import crypto_service

            my_id = crypto_service.get_node_id()

            # Find matching AIP proposal (handling legacy prefix if needed)
            aip = evolution_service.aips.get(aip_id)
            if not aip and aip_id:
                suffix = aip_id.split("-")[-1]
                for k, v in evolution_service.aips.items():
                    if k.endswith(suffix):
                        aip = v
                        aip_id = k
                        break

            if aip:
                aip.status = "passed"
                evolution_service._save_aips()
                evolution_service.record_approval_success()

            # Determine if this node is the proposer
            is_my_proposal = (
                proposal.initiator_id in [my_id, "self"]
                or proposal.initiator_id.startswith(my_id[:8])
                or (aip and (aip.initiator_id in [my_id, "self"] or aip.initiator_id.startswith(my_id[:8])))
            )

            if is_my_proposal and aip:
                if getattr(aip, "status", "") == "pr_submitted":
                    logger.info(f"[Governance] AIP {aip_id} has already been pushed to GitHub. Skipping duplicate push.")
                    return

                logger.info(f"[Governance] AIP {aip_id} PASSED! Proposing node ({my_id[:8]}) automatically pushing code to GitHub & creating PR...")

                try:
                    from app.services.agent_service import agent_service
                except (ImportError, ModuleNotFoundError):
                    try:
                        from ..services.agent_service import agent_service
                    except Exception:
                        agent_service = None

                async def _landing_job():
                    try:
                        res = await evolution_service.submit_pr(
                            aip_id=aip_id,
                            agent_service=agent_service,
                            auto_apply=True,
                            base_branch="feature/autonomous-evolution-engine",
                        )
                        logger.info(f"[Governance] Automated landing result for {aip_id}: {res}")
                    except Exception as landing_err:
                        logger.error(f"[Governance] Automated landing failed for {aip_id}: {landing_err}", exc_info=True)

                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_landing_job())
                except RuntimeError:
                    import threading
                    threading.Thread(target=lambda: asyncio.run(_landing_job()), daemon=True).start()

        except Exception as e:
            logger.error(f"[Governance] Error handling passed AIP {aip_id}: {e}", exc_info=True)

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

        # Check early termination (Fast-Reject or Early-Pass) for proposal vote
        if election.election_type == ElectionType.PROPOSAL_VOTE:
            tally_res = election.tally()
            if tally_res.get("early_rejected"):
                election.status = "early_rejected"
                logger.info(
                    f"[Governance] Fast-Reject triggered for election {election_id}: "
                    f"{tally_res.get('rejections')} rejections exceeded half of eligible voters."
                )
            elif tally_res.get("early_passed"):
                election.status = "early_passed"
                logger.info(
                    f"[Governance] Early-Pass triggered for election {election_id}: "
                    f"{tally_res.get('approvals')} approvals reached majority."
                )

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

                # Check if proposal is already known with identical state
                existing_proposal = self.proposals.get(proposal.proposal_id)
                existing_election = self.get_election_for_proposal(proposal.proposal_id)

                is_identical = False
                if existing_proposal and existing_proposal.status == proposal.status:
                    if not election_data and not existing_election:
                        is_identical = True
                    elif election_data and existing_election:
                        req_votes = len(election_data.get("votes", {}))
                        local_votes = len(existing_election.votes)
                        if req_votes == local_votes and election_data.get("status") == existing_election.status:
                            is_identical = True

                if is_identical:
                    logger.debug(f"Governance P2P: Proposal {proposal.proposal_id[:8]} already identical locally. Skipping.")
                    return True

                self.proposals[proposal.proposal_id] = proposal

                # Ingest Election if attached
                if election_data and isinstance(election_data, dict):
                    election_id = election_data.get("election_id")
                    if election_id:
                        election = Election.from_dict(election_data)
                        if election.status == "completed" or getattr(election, "is_finished", False):
                            self.finished_elections[election.election_id] = election
                            self.active_elections.pop(election.election_id, None)
                        else:
                            self.active_elections[election.election_id] = election

                logger.info(
                    f"Governance P2P: Successfully ingested remote proposal {proposal.proposal_id[:8]}"
                )

                # Auto-ingest into EvolutionService if it is an architecture evolution AIP
                try:
                    import json
                    c_data = json.loads(proposal.content) if isinstance(proposal.content, str) else proposal.content
                    if isinstance(c_data, dict) and c_data.get("type") == "architecture_evolution":
                        aip_data = c_data.get("aip")
                        if aip_data and isinstance(aip_data, dict):
                            from ..services.evolution_service import evolution_service, AIPProposal as ES_AIPProposal
                            remote_aip_id = aip_data.get("aip_id")
                            if remote_aip_id:
                                remote_aip = ES_AIPProposal.from_dict(aip_data)
                                evolution_service.aips[remote_aip_id] = remote_aip
                                evolution_service._save_aips()
                                logger.info(f"Governance P2P: Ingested remote AIP {remote_aip_id} into EvolutionService")
                except Exception as e:
                    logger.debug(f"Governance P2P: Non-AIP proposal content: {e}")

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
