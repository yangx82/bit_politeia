import pytest
from backend.app.p2p_community.blockchain import ArchiveManager, Block, ArchiveChain

@pytest.fixture
def archive_manager():
    return ArchiveManager("node_test")

def test_genesis_block(archive_manager):
    assert len(archive_manager.chain.chain) == 1
    genesis = archive_manager.chain.latest_block
    assert genesis.index == 0
    assert genesis.prev_hash == "0"
    
def test_block_creation_and_linking(archive_manager):
    data = {"test": "data"}
    block1 = archive_manager.chain.add_block(data)
    
    assert block1.index == 1
    assert block1.prev_hash == archive_manager.chain.chain[0].hash
    assert block1.hash != ""
    assert block1.hash == block1.calculate_hash()
    
    data2 = {"test": "data2"}
    block2 = archive_manager.chain.add_block(data2)
    assert block2.index == 2
    assert block2.prev_hash == block1.hash

def test_chain_validation(archive_manager):
    archive_manager.chain.add_block({"a": 1})
    archive_manager.chain.add_block({"b": 2})
    
    assert archive_manager.chain.validate_chain() == True
    
    # Tamper with chain
    archive_manager.chain.chain[1].data["a"] = 999
    # Hash mismatch
    assert archive_manager.chain.validate_chain() == False

def test_create_daily_archive(archive_manager):
    votes = [{"voter": "A", "target": "B"}]
    txs = [{"from": "A", "to": "B", "amt": 10}]
    
    block = archive_manager.create_daily_archive(votes, txs, [])
    
    assert block.index == 1
    summary = block.data
    assert summary["vote_count"] == 1
    assert summary["tx_count"] == 1
    assert summary["votes_hash"] != "" # Should be hashed
    assert summary["node_id"] == "node_test"

def test_generate_report(archive_manager):
    archive_manager.create_daily_archive([], [], [])
    report = archive_manager.generate_report()
    
    assert report["reporter_id"] == "node_test"
    assert report["block_index"] == 1
    assert "block_hash" in report
    assert "summary" in report
