from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import uuid
import logging
import json
import os

logger = logging.getLogger(__name__)

@dataclass
class Evaluation:
    evaluation_id: str
    rater_id: str
    target_id: str
    scores: Dict[str, int] # e.g. {"contribution": 80, "reliability": 90}
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    signature: str = "" # To be implemented

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(d["timestamp"], datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Evaluation':
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)

class ReputationManager:
    def __init__(self, node_id: str, storage_path: Optional[str] = None):
        self.node_id = node_id
        self.evaluations: List[Evaluation] = [] # Local storage of evaluations received or made
        self.storage_path = storage_path
        
        if self.storage_path:
            self.load_state()

    def submit_evaluation(self, rater_id: str, target_id: str, scores: Dict[str, int]) -> Optional[Evaluation]:
        # Validate scores (0-100)
        for dim, score in scores.items():
            if not (0 <= score <= 100):
                logger.warning(f"Invalid score for {dim}: {score}. Must be 0-100.")
                return None
        
        eval_obj = Evaluation(
            evaluation_id=str(uuid.uuid4()),
            rater_id=rater_id,
            target_id=target_id,
            scores=scores
        )
        self.evaluations.append(eval_obj)
        logger.info(f"Evaluation submitted: {rater_id} -> {target_id}: {scores}")
        
        self.save_state()
        return eval_obj

    def get_reputation(self, target_id: str) -> Dict[str, float]:
        """
        Calculate average reputation scores for a target node based on available evaluations.
        """
        target_evals = [e for e in self.evaluations if e.target_id == target_id]
        if not target_evals:
            return {}
        
        # Aggregate scores by dimension
        totals: Dict[str, float] = {}
        counts: Dict[str, int] = {}
        
        for e in target_evals:
            for dim, score in e.scores.items():
                totals[dim] = totals.get(dim, 0.0) + score
                counts[dim] = counts.get(dim, 0) + 1
        
        averages = {dim: totals[dim] / counts[dim] for dim in totals}
        return averages

    def get_overall_score(self, target_id: str) -> float:
        """
        Calculate a single weighted reputation score (0-100).
        Currently just a simple average of all dimensions.
        """
        averages = self.get_reputation(target_id)
        if not averages:
            return 0.0
        return sum(averages.values()) / len(averages)

    def get_group_rankings(self, node_ids: List[str]) -> List[tuple[str, float]]:
        """
        Rank a list of nodes by their overall reputation score.
        Returns a list of (node_id, score) sorted by score descending.
        """
        scores = []
        for nid in node_ids:
            scores.append((nid, self.get_overall_score(nid)))
        
        return sorted(scores, key=lambda x: x[1], reverse=True)

    def save_state(self):
        if not self.storage_path:
            return
            
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            data = [e.to_dict() for e in self.evaluations]
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # logger.debug(f"Reputation saved to {self.storage_path}")
        except Exception as e:
            logger.error(f"Failed to save reputation: {e}")

    def load_state(self):
        if not self.storage_path or not os.path.exists(self.storage_path):
            return
            
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.evaluations = [Evaluation.from_dict(e) for e in data]
                logger.info(f"Reputation loaded: {len(self.evaluations)} evaluations.")
        except Exception as e:
            logger.error(f"Failed to load reputation: {e}")
