import hashlib
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

@dataclass
class Block:
    index: int
    prev_hash: str
    timestamp: float
    data: Dict[str, Any] # Contains summary, hashes of activities
    signature: str = ""
    hash: str = ""

    def calculate_hash(self) -> str:
        block_string = json.dumps({
            "index": self.index,
            "prev_hash": self.prev_hash,
            "timestamp": self.timestamp,
            "data": self.data
        }, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()

class ArchiveChain:
    def __init__(self, owner_id: str):
        self.owner_id = owner_id
        self.chain: List[Block] = []
        self._create_genesis_block()

    def _create_genesis_block(self):
        genesis = Block(
            index=0,
            prev_hash="0",
            timestamp=datetime.now().timestamp(),
            data={"note": "Genesis Block"}
        )
        genesis.hash = genesis.calculate_hash()
        self.chain.append(genesis)
        logger.info(f"ArchiveChain initialized for {self.owner_id}")

    @property
    def latest_block(self) -> Block:
        return self.chain[-1]

    def add_block(self, data: Dict[str, Any], signature: str = "") -> Block:
        prev_block = self.latest_block
        new_block = Block(
            index=prev_block.index + 1,
            prev_hash=prev_block.hash,
            timestamp=datetime.now().timestamp(),
            data=data,
            signature=signature
        )
        new_block.hash = new_block.calculate_hash()
        self.chain.append(new_block)
        logger.info(f"Block {new_block.index} added. Hash: {new_block.hash[:8]}...")
        return new_block

    def get_chain_dict(self) -> List[Dict]:
        return [asdict(b) for b in self.chain]

    def validate_chain(self) -> bool:
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            prev = self.chain[i-1]
            if current.hash != current.calculate_hash():
                return False
            if current.prev_hash != prev.hash:
                return False
        return True

class ArchiveManager:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.chain = ArchiveChain(node_id)
        
    def snapshot_local_state(self, 
                             votes: List[Dict], 
                             transactions: List[Dict], 
                             research: List[Dict]) -> Dict[str, Any]:
        """
        Snapshot local state for archiving.
        Generates hashes of activity lists rather than storing full raw data in block (for efficiency).
        """
        # Calculate Merkle roots or simple hashes of lists
        votes_hash = self._hash_list(votes)
        tx_hash = self._hash_list(transactions)
        research_hash = self._hash_list(research)
        
        # Summary report
        summary = {
            "node_id": self.node_id,
            "vote_count": len(votes),
            "tx_count": len(transactions),
            "research_count": len(research),
            "votes_hash": votes_hash,
            "tx_hash": tx_hash,
            "research_hash": research_hash,
            "period_end": datetime.now().isoformat()
        }
        return summary

    def _hash_list(self, items: List[Any]) -> str:
        if not items:
            return ""
        s = json.dumps(items, sort_keys=True, default=str)
        return hashlib.sha256(s.encode()).hexdigest()

    def create_daily_archive(self, votes: List, txs: List, research: List, signature: str = "") -> Block:
        data = self.snapshot_local_state(votes, txs, research)
        return self.chain.add_block(data, signature)

    def generate_report(self) -> Dict[str, Any]:
        """
        Generate a report for upstream reporting.
        Includes latest block hash and summary.
        """
        latest = self.chain.latest_block
        return {
            "reporter_id": self.node_id,
            "block_index": latest.index,
            "block_hash": latest.hash,
            "summary": latest.data,
            "timestamp": latest.timestamp
        }
