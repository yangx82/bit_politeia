import pytest

from backend.app.p2p_community.economy import Ledger, Transaction


@pytest.fixture
def ledger():
    l = Ledger()
    l.credit("Alice", 100.0)
    return l


def test_ledger_credit():
    l = Ledger()
    l.credit("Bob", 50.0)
    assert l.get_balance("Bob") == 50.0

    with pytest.raises(ValueError):
        l.credit("Bob", -10.0)


def test_transaction_execution(ledger):
    # Valid transfer
    tx = ledger.create_transaction("Alice", "Bob", 40.0, "Lunch")
    assert tx is not None
    assert ledger.get_balance("Alice") == 60.0
    assert ledger.get_balance("Bob") == 40.0
    assert len(ledger.transactions) == 1


def test_insufficient_funds(ledger):
    # Alice has 100. Try to send 150.
    tx = ledger.create_transaction("Alice", "Bob", 150.0, "Car")
    assert tx is None
    assert ledger.get_balance("Alice") == 100.0  # Unchanged
    assert ledger.get_balance("Bob") == 0.0


def test_invalid_amount(ledger):
    tx = ledger.create_transaction("Alice", "Bob", -20.0, "Refund?")
    assert tx is None
    assert ledger.get_balance("Alice") == 100.0


def test_transaction_recording(ledger):
    tx = Transaction(
        transaction_id="tx1", payer_id="Alice", payee_id="Charlie", amount=10.0, details="Test"
    )
    success = ledger.record_transaction(tx)
    assert success == True
    assert ledger.get_balance("Charlie") == 10.0
