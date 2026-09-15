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
    status: str = "draft"  # draft, proposed, debating, voting, sandbox_passed, pr_submitted, merged, rejected, preflight_rejected, stalled, abandoned, archived
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    signature: str = ""
    public_key: str = ""
    quality_report: dict[str, Any] = field(default_factory=dict)
    failure_count: int = 0

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
            "signature": self.signature,
            "public_key": self.public_key,
            "quality_report": self.quality_report,
            "failure_count": self.failure_count,
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
            signature=data.get("signature", ""),
            public_key=data.get("public_key", ""),
            quality_report=data.get("quality_report", {}),
            failure_count=data.get("failure_count", 0),
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

    @property
    def network_participation_rate(self) -> float:
        total_network = len(self.eligible_voters)
        if not total_network:
            return 0.0
        return len(self.votes) / total_network

    @property
    def effective_voters_count(self) -> int:
        return len(self.eligible_voters - self.excluded_voters)

    @property
    def network_voters_count(self) -> int:
        return len(self.eligible_voters)

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
                "network_participation_rate": self.network_participation_rate,
                "effective_voters_count": total_effective,
                "network_voters_count": len(self.eligible_voters),
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

            effective_count = len(self.eligible_voters - self.excluded_voters)
            return {
                "valid": valid,
                "evaluations": evaluations,
                "average_amount": avg_amount,
                "total_evaluators": len(evaluations),
                "total_votes": len(self.votes),
                "participation_rate": self.participation_rate,
                "network_participation_rate": self.network_participation_rate,
                "effective_voters_count": effective_count,
                "network_voters_count": len(self.eligible_voters),
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

        effective_count = len(self.eligible_voters - self.excluded_voters)
        return {
            "valid": valid,
            "winners": winners,
            "counts": counts,
            "approvals": sum(counts.values()),  # Total positive votes for all candidates
            "rejections": 0,
            "total_votes": self.total_votes,
            "participation_rate": self.participation_rate,
            "network_participation_rate": self.network_participation_rate,
            "effective_voters_count": effective_count,
            "network_voters_count": len(self.eligible_voters),
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
            "network_participation_rate": round(self.network_participation_rate, 4),
            "effective_voters_count": len(self.eligible_voters - self.excluded_voters),
            "network_voters_count": len(self.eligible_voters),
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

        # Topology auto-healing: merge active group members and known network peers
        try:
            from ..services.p2p_service import p2p_service
            if p2p_service.local_node and hasattr(p2p_service.local_node, "network_manager") and p2p_service.local_node.network_manager:
                nm = p2p_service.local_node.network_manager
                if group_id in nm.groups:
                    voters_set.update(nm.groups[group_id].members)
                if hasattr(nm, "nodes") and nm.nodes:
                    voters_set.update(nm.nodes.keys())
        except Exception as ex:
            logger.debug(f"[Governance] initiate_proposal topology lookup: {ex}")

        if self.node_id:
            voters_set.add(self.node_id)

        # Conflict of Interest / Initiator Recusal:
        # The author of a proposal cannot vote on their own proposal (PROPOSAL_VOTE).
        excluded_set = {self.node_id} if self.node_id else set()

        election = Election(
            election_id=election_id,
            group_id=group_id,
            election_type=ElectionType.PROPOSAL_VOTE,
            initiator_id=self.node_id,
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(minutes=duration_minutes),
            proposal_id=proposal_id,
            eligible_voters=voters_set,
            excluded_voters=excluded_set,
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

        election = self.active_elections.get(election_id)
        if not election:
            # If recently early-terminated (e.g. early_passed/early_rejected),
            # allow remaining voters to record votes within deadline for complete audit trail
            election = self.finished_elections.get(election_id)

        if not election or not votes:
            return False

        voter_id = votes[0].voter_id

        # 1. Proposer Recusal: excluded voters cannot cast ballots
        if voter_id in election.excluded_voters or (election.initiator_id and voter_id == election.initiator_id):
            logger.warning(
                f"[Governance] Voter {voter_id[:8]} is in excluded_voters or is initiator (conflict of interest/recusal) for election {election_id[:8]}, rejecting."
            )
            return False

        # 2. Whitelist check: if eligible_voters is configured, voter must be eligible (or auto-healed if recognized node)
        if election.eligible_voters and voter_id not in election.eligible_voters:
            try:
                from ..services.p2p_service import p2p_service
                is_recognized = False
                if p2p_service.local_node and hasattr(p2p_service.local_node, "network_manager") and p2p_service.local_node.network_manager:
                    nm = p2p_service.local_node.network_manager
                    if election.group_id in nm.groups and voter_id in nm.groups[election.group_id].members:
                        is_recognized = True
                    elif hasattr(nm, "nodes") and voter_id in nm.nodes:
                        is_recognized = True
                if is_recognized:
                    election.eligible_voters.add(voter_id)
                    logger.info(f"[Governance] Auto-healed voter {voter_id[:8]} into eligible_voters for election {election_id[:8]}")
                else:
                    logger.warning(f"[Governance] Voter {voter_id[:8]} not in eligible_voters for election {election_id[:8]}, rejecting.")
                    return False
            except Exception:
                logger.warning(f"[Governance] Voter {voter_id[:8]} not in eligible_voters for election {election_id[:8]}, rejecting.")
                return False

        if datetime.now(UTC) > election.end_time:
            logger.warning(f"Vote received after deadline for {election_id}")
            return False

        # 3. Duplicate vote check
        if voter_id in election.votes:
            logger.warning(f"[Governance] Voter {voter_id[:8]} has already voted in {election_id[:8]}, rejecting duplicate.")
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

                        # Auto-healing: ensure eligible_voters includes all known group members and peers
                        try:
                            from ..services.p2p_service import p2p_service
                            if p2p_service.local_node and hasattr(p2p_service.local_node, "network_manager") and p2p_service.local_node.network_manager:
                                nm = p2p_service.local_node.network_manager
                                if election.group_id in nm.groups:
                                    election.eligible_voters.update(nm.groups[election.group_id].members)
                                if hasattr(nm, "nodes") and nm.nodes:
                                    election.eligible_voters.update(nm.nodes.keys())
                        except Exception as ex:
                            logger.debug(f"[Governance] Ingestion topology auto-heal: {ex}")

                        # Ensure local node is in eligible_voters if belonging to group/network
                        if self.node_id:
                            election.eligible_voters.add(self.node_id)

                        # Enforce proposer recusal on proposal votes
                        if election.election_type == ElectionType.PROPOSAL_VOTE and election.initiator_id:
                            election.excluded_voters.add(election.initiator_id)

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
                                # Validate remote identity signature if present
                                if remote_aip.signature and remote_aip.public_key:
                                    from ..services.aip_quality_gate import ProposalSignatureVerifier
                                    is_valid, err_msg = ProposalSignatureVerifier.verify_proposal_signature(
                                        aip_id=remote_aip.aip_id,
                                        initiator_id=remote_aip.initiator_id,
                                        title=remote_aip.title,
                                        description=remote_aip.description,
                                        proposed_diff=remote_aip.proposed_diff,
                                        signature=remote_aip.signature,
                                        public_key_pem=remote_aip.public_key,
                                    )
                                    if not is_valid:
                                        logger.warning(
                                            f"Governance P2P: Dropping spoofed/invalid remote AIP {remote_aip_id}: {err_msg}"
                                        )
                                        self.proposals.pop(proposal.proposal_id, None)
                                        if election_data and isinstance(election_data, dict):
                                            self.active_elections.pop(election_data.get("election_id"), None)
                                        return False

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

                # Auto-healing: ensure eligible_voters includes all known group members and peers
                try:
                    from ..services.p2p_service import p2p_service
                    if p2p_service.local_node and hasattr(p2p_service.local_node, "network_manager") and p2p_service.local_node.network_manager:
                        nm = p2p_service.local_node.network_manager
                        if election.group_id in nm.groups:
                            election.eligible_voters.update(nm.groups[election.group_id].members)
                        if hasattr(nm, "nodes") and nm.nodes:
                            election.eligible_voters.update(nm.nodes.keys())
                except Exception as ex:
                    logger.debug(f"[Governance] Standalone election topology auto-heal: {ex}")

                # Ensure local node is in eligible_voters if belonging to group/network
                if self.node_id:
                    election.eligible_voters.add(self.node_id)

                # Enforce proposer recusal on proposal votes
                if election.election_type == ElectionType.PROPOSAL_VOTE and election.initiator_id:
                    election.excluded_voters.add(election.initiator_id)

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


# ========================================================
# [Autonomous Evolution Patch] AIP-5A40-01A6A6: Reputation-Weighted Quadratic Voting with Governance Integration
# ========================================================
import threading
import logging
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import math

logger = logging.getLogger(__name__)


class ReputationWeightedQuadraticVoting:
    """Thread-safe reputation-weighted quadratic voting with deduplication and balance checking.
    
    Voting power = vote_count * sqrt(reputation)
    Cost = voting_power^2
    
    This is NOT EigenTrust. Reputation values are externally managed.
    """
    
    def __init__(self, initial_reputations: Optional[Dict[str, float]] = None):
        self._lock = threading.Lock()
        self._reputations: Dict[str, float] = {}
        self._votes: Dict[str, Dict[str, int]] = defaultdict(dict)  # proposal_id -> {voter_id: vote_count}
        self._balances: Dict[str, float] = defaultdict(float)
        
        if initial_reputations:
            for node_id, rep in initial_reputations.items():
                try:
                    self._reputations[node_id] = self._validate_reputation(rep)
                except (ValueError, TypeError) as e:
                    logger.error(f"Invalid initial reputation for {node_id}: {e}")
    
    def _validate_reputation(self, reputation: float) -> float:
        """Bounds check reputation value [0.0, 1.0]."""
        try:
            rep = float(reputation)
            if math.isnan(rep) or math.isinf(rep):
                raise ValueError(f"Reputation must be finite, got {rep}")
            return max(0.0, min(1.0, rep))
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid reputation value: {e}")
    
    def _validate_vote_count(self, votes: int) -> int:
        """Bounds check vote count [0, 1000]."""
        try:
            votes = int(votes)
            return max(0, min(1000, votes))
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid vote count: {e}")
    
    def update_reputation(self, node_id: str, reputation: float) -> None:
        """Update node reputation with thread safety."""
        try:
            with self._lock:
                self._reputations[node_id] = self._validate_reputation(reputation)
                logger.debug(f"Updated reputation for {node_id}: {reputation}")
        except Exception as e:
            logger.error(f"Failed to update reputation for {node_id}: {e}")
            raise
    
    def update_balance(self, node_id: str, balance: float) -> None:
        """Update node balance for vote cost verification."""
        try:
            with self._lock:
                self._balances[node_id] = max(0.0, float(balance))
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid balance for {node_id}: {e}")
            raise ValueError(f"Invalid balance: {e}")
    
    def cast_votes(self, voter_id: str, proposal_id: str, vote_count: int) -> float:
        """Cast quadratic votes weighted by reputation with deduplication and balance check.
        
        Returns cost if successful, raises exception if validation fails.
        """
        try:
            vote_count = self._validate_vote_count(vote_count)
            
            with self._lock:
                # Vote deduplication: prevent double-voting
                if voter_id in self._votes[proposal_id]:
                    raise ValueError(f"Voter {voter_id} has already voted on proposal {proposal_id}")
                
                # Get reputation (default 0.5 for new voters)
                reputation = self._reputations.get(voter_id, 0.5)
                
                # Calculate cost
                weighted_votes = vote_count * math.sqrt(reputation)
                cost = weighted_votes ** 2
                
                # Balance checking
                current_balance = self._balances.get(voter_id, 0.0)
                if current_balance < cost:
                    raise ValueError(
                        f"Insufficient balance for {voter_id}: required {cost:.2f}, "
                        f"available {current_balance:.2f}"
                    )
                
                # Record vote (deduplicated - overwrites if somehow called again)
                self._votes[proposal_id][voter_id] = vote_count
                
                # Deduct balance
                self._balances[voter_id] = current_balance - cost
                
                logger.info(
                    f"Vote cast: {voter_id} -> {proposal_id}, "
                    f"votes={vote_count}, cost={cost:.2f}, rep={reputation:.2f}"
                )
                
                return cost
                
        except ValueError as e:
            logger.warning(f"Vote casting failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in cast_votes: {e}")
            raise RuntimeError(f"Vote casting system error: {e}")
    
    def get_proposal_results(self, proposal_id: str) -> Dict[str, Tuple[int, float]]:
        """Get weighted vote totals for a proposal.
        
        Returns: Dict[voter_id, (raw_votes, weighted_votes)]
        """
        try:
            with self._lock:
                results = {}
                for voter_id, vote_count in self._votes[proposal_id].items():
                    reputation = self._reputations.get(voter_id, 0.5)
                    weighted = vote_count * math.sqrt(reputation)
                    results[voter_id] = (vote_count, weighted)
                return results
        except Exception as e:
            logger.error(f"Error getting proposal results: {e}")
            raise RuntimeError(f"Failed to retrieve proposal results: {e}")
    
    def calculate_quadratic_cost(self, vote_count: int, reputation: float = 0.5) -> float:
        """Calculate cost for given votes and reputation."""
        try:
            vote_count = self._validate_vote_count(vote_count)
            reputation = self._validate_reputation(reputation)
            weighted = vote_count * math.sqrt(reputation)
            return weighted ** 2
        except Exception as e:
            logger.error(f"Error calculating cost: {e}")
            raise
    
    def has_voted(self, voter_id: str, proposal_id: str) -> bool:
        """Check if voter has already voted on proposal."""
        with self._lock:
            return voter_id in self._votes[proposal_id]
    
    def get_voter_balance(self, voter_id: str) -> float:
        """Get current balance for voter."""
        with self._lock:
            return self._balances.get(voter_id, 0.0)


# Integration interface for governance.py
def integrate_with_governance(governance_module):
    """Integration point for governance.py
    
    Example usage in governance.py:
        from .reputation_voting import ReputationWeightedQuadraticVoting
        
        voting_system = ReputationWeightedQuadraticVoting()
        
        def cast_governance_vote(voter_id, proposal_id, vote_count):
            cost = voting_system.cast_votes(voter_id, proposal_id, vote_count)
            # Record vote in governance ledger
            return cost
    """
    logger.info("Reputation-weighted quadratic voting integrated with governance module")
    return ReputationWeightedQuadraticVoting()


# Integration interface for agent_service.py
def integrate_with_agent_service(agent_service_module):
    """Integration point for agent_service.py
    
    Example usage in agent_service.py:
        from .reputation_voting import ReputationWeightedQuadraticVoting
        
        voting_system = ReputationWeightedQuadraticVoting()
        
        def update_agent_reputation(agent_id, reputation):
            voting_system.update_reputation(agent_id, reputation)
            
        def update_agent_balance(agent_id, balance):
            voting_system.update_balance(agent_id, balance)
    """
    logger.info("Reputation-weighted quadratic voting integrated with agent service")
    return ReputationWeightedQuadraticVoting()


def test_reputation_weighted_quadratic_voting():
    """Comprehensive test suite."""
    print("Running tests...")
    
    # Test 1: Basic quadratic cost calculation
    voting = ReputationWeightedQuadraticVoting({'node1': 1.0, 'node2': 0.25})
    cost = voting.calculate_quadratic_cost(4, 1.0)
    assert cost == 16.0, f"Expected 16.0, got {cost}"
    print("✓ Test 1: Basic cost calculation")
    
    # Test 2: Reputation weighting
    cost_low_rep = voting.calculate_quadratic_cost(4, 0.25)
    assert cost_low_rep == 4.0, f"Expected 4.0, got {cost_low_rep}"
    print("✓ Test 2: Reputation weighting")
    
    # Test 3: Bounds checking
    voting.update_reputation('test', 1.5)
    assert voting._reputations['test'] == 1.0, "Reputation should be capped at 1.0"
    print("✓ Test 3: Bounds checking")
    
    # Test 4: Vote deduplication
    voting.update_balance('voter1', 100.0)
    voting.cast_votes('voter1', 'prop1', 2)
    try:
        voting.cast_votes('voter1', 'prop1', 3)  # Should fail - already voted
        assert False, "Should have raised ValueError for double voting"
    except ValueError as e:
        assert "already voted" in str(e).lower()
    print("✓ Test 4: Vote deduplication")
    
    # Test 5: Balance checking
    voting.update_balance('voter2', 5.0)
    try:
        voting.cast_votes('voter2', 'prop2', 10)  # Cost would be 100 * 0.5 = 50
        assert False, "Should have raised ValueError for insufficient balance"
    except ValueError as e:
        assert "insufficient balance" in str(e).lower()
    print("✓ Test 5: Balance checking")
    
    # Test 6: Exception handling
    try:
        voting.update_reputation('bad_node', 'not_a_number')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("✓ Test 6: Exception handling")
    
    # Test 7: has_voted check
    assert voting.has_voted('voter1', 'prop1') == True
    assert voting.has_voted('voter1', 'prop2') == False
    print("✓ Test 7: has_voted check")
    
    print("\nAll tests passed! ✓")


if __name__ == '__main__':
    test_reputation_weighted_quadratic_voting()


# ========================================================
# [Autonomous Evolution Patch] AIP-5A40-8DED81: QuadraticVotingHelper for Bit Politeia
# ========================================================
"""Governance helpers for Bit Politeia: quadratic voting, reputation decay, tally auditing."""

import hashlib
import json
import threading
from typing import Dict


class QuadraticVotingHelper:
    """Quadratic voting cost calculator. Cost scales quadratically to prevent vote concentration."""

    _MAX_COST = 10**8

    def __init__(self, max_budget: int = 1000) -> None:
        if not isinstance(max_budget, int) or max_budget <= 0 or max_budget > 10000:
            raise ValueError("max_budget must be an integer in (0, 10000]")
        self._max_budget = max_budget
        self._lock = threading.Lock()

    @property
    def max_budget(self) -> int:
        """Current budget ceiling."""
        return self._max_budget

    def calculate_cost(self, vote_count: int) -> int:
        """Return quadratic cost capped at _MAX_COST for overflow protection."""
        if not isinstance(vote_count, int) or vote_count < 0:
            raise ValueError("vote_count must be a non-negative integer")
        cost = vote_count ** 2
        return min(cost, self._MAX_COST)

    def validate_vote(self, vote_count: int, budget: int) -> bool:
        """Check whether *budget* can afford *vote_count* quadratic votes."""
        with self._lock:
            return budget >= self.calculate_cost(vote_count)

    def allocate_votes(self, budget: int) -> int:
        """Calculate maximum votes affordable with given budget: floor(sqrt(budget))."""
        if not isinstance(budget, int) or isinstance(budget, bool):
            raise ValueError("budget must be an integer")
        if budget < 0:
            raise ValueError("budget must be non-negative")
        with self._lock:
            import math
            return int(math.isqrt(budget))


class ReputationDecayCalculator:
    """Time-based reputation decay with configurable half-life for dynamic governance weighting."""

    def __init__(self, half_life_hours: float = 168.0) -> None:
        half_life_hours = float(half_life_hours)
        if half_life_hours <= 0.0 or half_life_hours > 8760.0:
            raise ValueError("half_life_hours must be in (0.0, 8760.0]")
        self._half_life = half_life_hours

    def decay(self, reputation: float, elapsed_hours: float) -> float:
        """Apply exponential decay; result clamped to [0.0, 1.0]."""
        reputation = float(reputation)
        elapsed_hours = float(elapsed_hours)
        if not (0.0 <= reputation <= 1.0):
            raise ValueError("reputation must be in [0.0, 1.0]")
        if elapsed_hours < 0.0:
            raise ValueError("elapsed_hours must be >= 0.0")
        factor = 0.5 ** (elapsed_hours / self._half_life)
        return max(0.0, min(1.0, reputation * factor))


class ProposalTallyAuditor:
    """Deterministic tally verification using cryptographic hashing for audit trails."""

    def compute_tally_hash(self, votes: Dict[str, int]) -> str:
        """SHA-256 hex digest of canonically-sorted vote dict."""
        if not isinstance(votes, dict):
            raise TypeError("votes must be a dict")
        payload = json.dumps(dict(sorted(votes.items())), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def verify_tally(self, votes: Dict[str, int], expected_hash: str) -> bool:
        """Return True when the computed hash matches *expected_hash*."""
        return self.compute_tally_hash(votes) == expected_hash

    def detect_sybil_heuristic(self, voter_id: str, recent_votes: list, max_burst: int = 5, window_seconds: float = 60.0) -> bool:
        """
        Detect Sybil burst rate-limiting violations based on sliding window heuristic.
        Returns True if more than max_burst votes occur within window_seconds.
        """
        if not isinstance(recent_votes, list):
            raise ValueError("recent_votes must be a list of timestamps")
        if len(recent_votes) <= max_burst:
            return False
        sorted_ts = sorted(float(t) for t in recent_votes)
        for i in range(len(sorted_ts) - max_burst):
            if sorted_ts[i + max_burst] - sorted_ts[i] < float(window_seconds):
                return True
        return False


# --------------- Unit Tests ---------------
def test_governance_helpers() -> None:
    # Quadratic cost: 5 votes -> cost 25
    assert QuadraticVotingHelper(max_budget=100).calculate_cost(5) == 25
    # Half-life decay: 1.0 after one half-life -> ~0.5
    assert abs(ReputationDecayCalculator(half_life_hours=168.0).decay(1.0, 168.0) - 0.5) < 0.01
    # Tally round-trip verification
    assert ProposalTallyAuditor().verify_tally(
        {'a': 1, 'b': 2},
        ProposalTallyAuditor().compute_tally_hash({'a': 1, 'b': 2})
    ) is True


if __name__ == "__main__":
    test_governance_helpers()
    print("All governance helper tests passed.")
