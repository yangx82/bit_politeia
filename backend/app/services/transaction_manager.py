from typing import List, Dict

class TransactionManager:
    def __init__(self):
        self.transactions = []
        self.payee = []
        self.payer = []

    def aggregate_transactions(self, group_transactions: List[Dict]) -> Dict:
        """
        Hierarchical aggregation of transactions.
        Simple summation logic for demo.
        """
        total_income = 0.0
        total_expense = 0.0
        total_count_in = 0
        total_count_ex = 0
        details = []
        payee = []
        payer = []
        
        for tx in group_transactions:
            # Verify tx...
            # payer = tx.get("payer", [])
            # payee = tx.get("payee", [])
            income = tx.get("income", 0.0)
            expense = tx.get("expense",0.0)
            tx_count_in = tx.get("tx_count_in",0)
            tx_count_ex = tx.get("tx_count_ex",0)

            total_income += income
            total_expense += expense
            total_count_in += tx_count_in
            total_count_ex += tx_count_ex
            
            details.append(tx["id"])
            
            tx_type = tx.get("type")
            if tx_type == "payee":
                payee.append(tx)
            elif tx_type == "payer":
                payer.append(tx)            
        
        self.payee = payee
        self.payer = payer
        
        return {
            "type": "aggregation",
            "income": total_income,
            "expense": total_expense,
            "tx_count_in": total_count_in,
            "tx_count_ex": total_count_ex,
            "tx_ids": details
        }
    
    def confirm_transactions(self, tx_record_received: List[Dict]) -> Dict:
        
        for tx in self.payer:
            # Verify tx...
            tx_id = tx.get("id")
            expense = tx.get("expense",0.0)
            node_id = tx.get('peer_id')
            for tx2 in tx_record_received:
                tx_id2 = tx2.get("id")
                expense = tx2.get("expense",0.0)
                group_id = tx2.get('peer_id')
                if tx_id == tx_id2:
                    if income == expense:
                        notify_p2p('tx_confirmed',[node_id,group_id],[tx_id,True])
                    else:
                        notify_p2p('tx_confirmed',[node_id,group_id],[tx_id,False])
        
        for tx in self.payee:
            tx["id"] = group_id
            income = tx.get("income", 0.0)
            target_id = tx.get('counterpart')
            notify_p2p('confirm_transaction',target_id,tx)
            
        return
        

transaction_manager = TransactionManager()
