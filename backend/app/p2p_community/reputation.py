from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

@dataclass
class Evaluation:
    evaluation_id: str
    rater_id: str
    target_id: str
    scores: Dict[str, int] # e.g. {"contribution": 80, "reliability": 90}
    timestamp: datetime = field(default_factory=datetime.now)
    signature: str = "" # To be implemented

class ReputationManager:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.evaluations: List[Evaluation] = [] # Local storage of evaluations received or made
        # In a real P2P system, this would be a distributed store or DHT lookup

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
