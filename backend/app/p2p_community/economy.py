import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Transaction:
    transaction_id: str
    payer_id: str
    payee_id: str
    amount: float
    details: str
    category: str = "TRANSFER"  # e.g., TRANSFER, REWARD, PENALTY, GOVERNANCE
    context_id: str | None = None  # e.g., proposal_id, election_id, or message_id
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    signature: str = ""  # To be implemented

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(d["timestamp"], datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


class Ledger:
    def __init__(self, storage_path: str | None = None):
        import threading
        self._lock = threading.Lock()
        self.balances: dict[str, float] = {}
        self.transactions: list[Transaction] = []
        self.storage_path = storage_path
        self._event_callback = None  # Callback for transaction events

        if self.storage_path:
            self.load_state()

    def set_event_callback(self, callback):
        """Set callback function for transaction events.
        
        Args:
            callback: Async function that accepts (event_type, transaction_data)
        """
        self._event_callback = callback

    def get_balance(self, node_id: str) -> float:
        with self._lock:
            return self.balances.get(node_id, 0.0)

    def get_transaction_by_context(self, context_id: str, category: str = None) -> Transaction | None:
        """Find an existing transaction by context_id and optionally category.
        
        This is used for idempotency checks to prevent duplicate transactions
        for the same context (e.g., same election payout).
        
        Args:
            context_id: The context identifier (e.g., election_id)
            category: Optional category filter
            
        Returns:
            Transaction if found, None otherwise
        """
        with self._lock:
            for tx in self.transactions:
                if tx.context_id == context_id:
                    if category is None or tx.category == category:
                        return tx
            return None

    def credit(self, node_id: str, amount: float):
        if amount < 0:
            raise ValueError("Cannot credit negative amount")
        with self._lock:
            self.balances[node_id] = self.balances.get(node_id, 0.0) + amount
            self.save_state()

    def verify_transaction(self, tx: Transaction) -> bool:
        if tx.amount <= 0:
            logger.warning(f"Invalid transaction amount: {tx.amount}")
            return False

        if tx.payer_id == "system":
            # System account represents the mint/treasury and is allowed to issue infinite funds
            return True

        payer_balance = self.get_balance(tx.payer_id)
        if payer_balance < tx.amount:
            logger.warning(
                f"Insufficient funds for {tx.payer_id}. Balance: {payer_balance}, Required: {tx.amount}"
            )
            return False

        return True

    def record_transaction(self, tx: Transaction) -> bool:
        with self._lock:
            if not self.verify_transaction(tx):
                return False

            # === IDEMPOTENCY CHECK ===
            # Prevent duplicate transactions for the same context_id + category
            if tx.context_id:
                existing = self.get_transaction_by_context(tx.context_id, tx.category)
                if existing:
                    logger.warning(
                        f"Duplicate transaction blocked: context_id={tx.context_id}, category={tx.category} "
                        f"(existing tx: {existing.transaction_id})"
                    )
                    return False

            # Execute Transfer
            if tx.payer_id != "system":
                self.balances[tx.payer_id] = self.balances.get(tx.payer_id, 0.0) - tx.amount
            self.balances[tx.payee_id] = self.balances.get(tx.payee_id, 0.0) + tx.amount

            self.transactions.append(tx)
            logger.info(
                f"Transaction recorded: {tx.transaction_id} [{tx.category}] from {tx.payer_id[:8]} to {tx.payee_id[:8]} amount {tx.amount}"
            )

            self.save_state()

        # === BROADCAST TRANSACTION EVENT ===
        if self._event_callback:
            try:
                import asyncio
                event_data = tx.to_dict()
                # Handle both sync and async callbacks
                if asyncio.iscoroutinefunction(self._event_callback):
                    asyncio.ensure_future(self._event_callback("transaction.completed", event_data))
                else:
                    self._event_callback("transaction.completed", event_data)
            except Exception as e:
                logger.warning(f"Transaction event callback failed: {e}")

        return True

    def create_transaction(
        self,
        payer_id: str,
        payee_id: str,
        amount: float,
        details: str,
        category: str = "TRANSFER",
        context_id: str | None = None,
    ) -> Transaction | None:
        tx = Transaction(
            transaction_id=str(uuid.uuid4()),
            payer_id=payer_id,
            payee_id=payee_id,
            amount=amount,
            details=details,
            category=category,
            context_id=context_id,
        )
        if self.record_transaction(tx):
            return tx
        return None

    def save_state(self):
        if not self.storage_path:
            return

        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            data = {
                "balances": self.balances,
                "transactions": [tx.to_dict() for tx in self.transactions],
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # logger.debug(f"Ledger saved to {self.storage_path}")
        except Exception as e:
            logger.error(f"Failed to save ledger: {e}")

    def load_state(self):
        if not self.storage_path or not os.path.exists(self.storage_path):
            return

        try:
            with open(self.storage_path, encoding="utf-8") as f:
                data = json.load(f)
                self.balances = data.get("balances", {})
                self.transactions = [
                    Transaction.from_dict(tx) for tx in data.get("transactions", [])
                ]
                logger.info(
                    f"Ledger loaded: {len(self.balances)} balances, {len(self.transactions)} transactions."
                )
        except Exception as e:
            logger.error(f"Failed to load ledger: {e}")
