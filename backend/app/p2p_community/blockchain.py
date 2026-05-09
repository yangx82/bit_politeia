import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Block:
    index: int
    prev_hash: str
    timestamp: float
    data: dict[str, Any]  # Contains summary, hashes of activities
    signature: str = ""
    hash: str = ""

    def calculate_hash(self) -> str:
        block_string = json.dumps(
            {
                "index": self.index,
                "prev_hash": self.prev_hash,
                "timestamp": self.timestamp,
                "data": self.data,
            },
            sort_keys=True,
        )
        return hashlib.sha256(block_string.encode()).hexdigest()


class ArchiveChain:
    def __init__(self, owner_id: str):
        self.owner_id = owner_id
        self.chain: list[Block] = []

        # Paths
        base_dir = Path(__file__).parent.parent.parent
        self.data_dir = base_dir / "data"
        self.db_path = self.data_dir / "blockchain.json"

        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Load or create Genesis
        if not self._load_from_disk():
            self._create_genesis_block()

    def _create_genesis_block(self):
        genesis = Block(
            index=0,
            prev_hash="0",
            timestamp=datetime.now(UTC).timestamp(),
            data={"note": "Genesis Block"},
        )
        genesis.hash = genesis.calculate_hash()
        self.chain.append(genesis)
        logger.info(f"ArchiveChain initialized for {self.owner_id}")
        self._save_to_disk()

    def _load_from_disk(self) -> bool:
        if not self.db_path.exists():
            return False
        try:
            with open(self.db_path, encoding="utf-8") as f:
                data = json.load(f)

            self.chain = []
            for item in data.get("chain", []):
                block = Block(
                    index=item["index"],
                    prev_hash=item["prev_hash"],
                    timestamp=item["timestamp"],
                    data=item["data"],
                    signature=item.get("signature", ""),
                    hash=item["hash"],
                )
                self.chain.append(block)

            if len(self.chain) > 0:
                logger.info(f"ArchiveChain loaded from disk. {len(self.chain)} blocks.")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to load blockchain from disk: {e}")
            return False

    def _save_to_disk(self):
        try:
            temp_path = self.db_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                payload = {"owner_id": self.owner_id, "chain": self.get_chain_dict()}
                json.dump(payload, f, indent=2)
            temp_path.replace(self.db_path)
        except Exception as e:
            logger.error(f"Failed to save blockchain to disk: {e}")

    @property
    def latest_block(self) -> Block:
        return self.chain[-1]

    def add_block(self, data: dict[str, Any], signature: str = "") -> Block:
        prev_block = self.latest_block
        new_block = Block(
            index=prev_block.index + 1,
            prev_hash=prev_block.hash,
            timestamp=datetime.now(UTC).timestamp(),
            data=data,
            signature=signature,
        )
        new_block.hash = new_block.calculate_hash()
        self.chain.append(new_block)
        logger.info(f"Block {new_block.index} added. Hash: {str(new_block.hash)[:8]}...")
        self._save_to_disk()
        return new_block

    def get_chain_dict(self) -> list[dict]:
        return [asdict(b) for b in self.chain]

    def validate_chain(self) -> bool:
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            prev = self.chain[i - 1]
            if current.hash != current.calculate_hash():
                return False
            if current.prev_hash != prev.hash:
                return False
        return True


class ArchiveManager:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.chain = ArchiveChain(node_id)

    def snapshot_local_state(
        self,
        votes: list[dict],
        transactions: list[dict],
        research: list[dict],
        messages: list[dict],
    ) -> dict[str, Any]:
        """
        Snapshot local state for archiving.
        Generates hashes of activity lists rather than storing full raw data in block (for efficiency).
        """
        # Calculate Merkle roots or simple hashes of lists
        votes_hash = self._hash_list(votes)
        tx_hash = self._hash_list(transactions)
        research_hash = self._hash_list(research)
        messages_hash = self._hash_list(messages)

        # Summary report
        summary = {
            "node_id": self.node_id,
            "vote_count": len(votes),
            "tx_count": len(transactions),
            "research_count": len(research),
            "message_count": len(messages),
            "votes_hash": votes_hash,
            "tx_hash": tx_hash,
            "research_hash": research_hash,
            "messages_hash": messages_hash,
            "period_end": datetime.now(UTC).isoformat(),
        }
        return summary

    def _hash_list(self, items: list[Any]) -> str:
        if not items:
            return ""
        s = json.dumps(items, sort_keys=True, default=str)
        return hashlib.sha256(s.encode()).hexdigest()

    def create_daily_archive(
        self, votes: list, txs: list, research: list, messages: list = None, signature: str = ""
    ) -> Block:
        if messages is None:
            messages = []
        data = self.snapshot_local_state(votes, txs, research, messages)
        return self.chain.add_block(data, signature)

    def generate_report(self) -> dict[str, Any]:
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
            "timestamp": latest.timestamp,
        }
