from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

@dataclass
class Transaction:
    transaction_id: str
    payer_id: str
    payee_id: str
    amount: float
    details: str
    timestamp: datetime = field(default_factory=datetime.now)
    signature: str = "" # To be implemented

class Ledger:
    def __init__(self):
        self.balances: Dict[str, float] = {}
        self.transactions: List[Transaction] = []

    def get_balance(self, node_id: str) -> float:
        return self.balances.get(node_id, 0.0)

    def credit(self, node_id: str, amount: float):
        if amount < 0:
            raise ValueError("Cannot credit negative amount")
        self.balances[node_id] = self.balances.get(node_id, 0.0) + amount

    def verify_transaction(self, tx: Transaction) -> bool:
        if tx.amount <= 0:
            logger.warning(f"Invalid transaction amount: {tx.amount}")
            return False
            
        payer_balance = self.get_balance(tx.payer_id)
        if payer_balance < tx.amount:
            logger.warning(f"Insufficient funds for {tx.payer_id}. Balance: {payer_balance}, Required: {tx.amount}")
            return False
            
        return True

    def record_transaction(self, tx: Transaction) -> bool:
        if not self.verify_transaction(tx):
            return False
            
        # Execute Transfer
        self.balances[tx.payer_id] -= tx.amount
        self.balances[tx.payee_id] = self.balances.get(tx.payee_id, 0.0) + tx.amount
        
        self.transactions.append(tx)
        logger.info(f"Transaction recorded: {tx.transaction_id} from {tx.payer_id} to {tx.payee_id} amount {tx.amount}")
        return True
    
    def create_transaction(self, payer_id: str, payee_id: str, amount: float, details: str) -> Optional[Transaction]:
        tx = Transaction(
            transaction_id=str(uuid.uuid4()),
            payer_id=payer_id,
            payee_id=payee_id,
            amount=amount,
            details=details
        )
        if self.record_transaction(tx):
            return tx
        return None
