import asyncio
import pytest
import time
from unittest.mock import AsyncMock

from backend.app.p2p_community.governance import GovernanceManager, ElectionType, Vote
from backend.app.services.agent_service import AgentService
from backend.app.agent.tools import cast_vote


@pytest.fixture
def governance_setup(tmp_path):
    init_db = str(tmp_path / 'initiator_gov.json')
    recv_db = str(tmp_path / 'receiver_gov.json')

    initiator_id = 'node_alpha_11111111'
    receiver_id = 'node_beta_22222222'

    service_init = AgentService()
    service_init.governance_manager = GovernanceManager(initiator_id, storage_path=init_db)
    service_init.llm = object()

    service_recv = AgentService()
    service_recv.governance_manager = GovernanceManager(receiver_id, storage_path=recv_db)
    service_recv.llm = object()

    poked_init = []
    poked_recv = []

    async def mock_init_loop(msg):
        poked_init.append(msg)

    async def mock_recv_loop(msg):
        poked_recv.append(msg)

    service_init._run_ralph_wiggum_loop = mock_init_loop
    service_recv._run_ralph_wiggum_loop = mock_recv_loop

    return {
        'initiator_id': initiator_id,
        'receiver_id': receiver_id,
        'service_init': service_init,
        'service_recv': service_recv,
        'poked_init': poked_init,
        'poked_recv': poked_recv,
    }


@pytest.mark.asyncio
async def test_initiator_auto_vote_and_query(governance_setup, monkeypatch):
    data = governance_setup
    service_init = data['service_init']
    initiator_id = data['initiator_id']

    from backend.app.services.p2p_service import p2p_service
    monkeypatch.setattr(p2p_service, 'broadcast_governance_event', AsyncMock(return_value=True))

    import backend.app.services.crypto_service as cs_mod
    monkeypatch.setattr(cs_mod.crypto_service, 'get_node_id', lambda: initiator_id)

    # 1. Initiator creates proposal
    res = await service_init.create_proposal(
        group_id='group_genesis',
        content='Upgrade network consensus rules',
        duration_minutes=60,
    )
    election_id = res['election']['election_id']
    election = service_init.governance_manager.active_elections[election_id]

    # Check initiator auto-vote recorded
    assert initiator_id in election.votes
    assert election.votes[initiator_id][0].approval is True
    assert 'Auto-voted APPROVE' in election.votes[initiator_id][0].reason

    # 2. Initiator self-vote query
    info = await service_init.get_election_info(election_id, include_content=True)
    assert info['voted_count'] == 1
    assert initiator_id in info['voted_nodes']
    assert info['approvals'] == 1
    assert len(info['ballots']) == 1
    assert info['ballots'][0]['voter_id'] == initiator_id
    assert info['ballots'][0]['approval'] is True

    # 3. Initiator monitor should NOT wake initiator
    data['poked_init'].clear()
    await service_init.check_governance_proposals()
    assert len(data['poked_init']) == 0


@pytest.mark.asyncio
async def test_p2p_realtime_trigger_and_instruction(governance_setup, monkeypatch):
    data = governance_setup
    service_init = data['service_init']
    service_recv = data['service_recv']
    initiator_id = data['initiator_id']
    receiver_id = data['receiver_id']

    from backend.app.services.p2p_service import p2p_service
    monkeypatch.setattr(p2p_service, 'broadcast_governance_event', AsyncMock(return_value=True))

    import backend.app.services.crypto_service as cs_mod
    monkeypatch.setattr(cs_mod.crypto_service, 'get_node_id', lambda: receiver_id)

    res = await service_init.create_proposal(
        group_id='group_genesis',
        content='Upgrade consensus',
        duration_minutes=60,
    )
    election_id = res['election']['election_id']

    # Ingest P2P event at receiver
    p2p_payload = {
        'proposal': res['proposal'],
        'election': res['election'],
    }
    success = service_recv.governance_manager.receive_p2p_event('proposal', p2p_payload)
    assert success is True

    recv_election = service_recv.governance_manager.active_elections[election_id]
    assert initiator_id in recv_election.votes

    # Trigger real-time check
    data['poked_recv'].clear()
    await service_recv.check_governance_proposals()
    await asyncio.sleep(0.05)
    assert len(data['poked_recv']) == 1

    poke_text = data['poked_recv'][0].content
    assert 'cast_vote' in poke_text
    assert election_id in poke_text


@pytest.mark.asyncio
async def test_cooldown_and_retry_on_failure(governance_setup, monkeypatch):
    data = governance_setup
    service_init = data['service_init']
    service_recv = data['service_recv']
    receiver_id = data['receiver_id']

    from backend.app.services.p2p_service import p2p_service
    monkeypatch.setattr(p2p_service, 'broadcast_governance_event', AsyncMock(return_value=True))

    import backend.app.services.crypto_service as cs_mod
    monkeypatch.setattr(cs_mod.crypto_service, 'get_node_id', lambda: receiver_id)

    res = await service_init.create_proposal(
        group_id='group_genesis',
        content='Upgrade consensus',
        duration_minutes=60,
    )
    election_id = res['election']['election_id']

    service_recv.governance_manager.receive_p2p_event('proposal', {
        'proposal': res['proposal'],
        'election': res['election'],
    })

    # First trigger wakes agent
    data['poked_recv'].clear()
    await service_recv.check_governance_proposals()
    await asyncio.sleep(0.05)
    assert len(data['poked_recv']) == 1

    # Second immediate check during cooldown -> no duplicate spam
    data['poked_recv'].clear()
    await service_recv.check_governance_proposals()
    await asyncio.sleep(0.05)
    assert len(data['poked_recv']) == 0

    # Cooldown expires (>300s) -> re-awakens agent to retry
    service_recv.governance_notify_attempts[election_id] -= 305.0
    data['poked_recv'].clear()
    await service_recv.check_governance_proposals()
    await asyncio.sleep(0.05)
    assert len(data['poked_recv']) == 1


@pytest.mark.asyncio
async def test_cast_vote_tool_execution(governance_setup, monkeypatch):
    data = governance_setup
    service_init = data['service_init']
    service_recv = data['service_recv']
    receiver_id = data['receiver_id']

    from backend.app.services.p2p_service import p2p_service
    monkeypatch.setattr(p2p_service, 'broadcast_governance_event', AsyncMock(return_value=True))

    class MockNode:
        node_id = receiver_id
        network_manager = None
    monkeypatch.setattr(p2p_service, 'local_node', MockNode())

    try:
        import app.services.agent_service as app_as_mod
        monkeypatch.setattr(app_as_mod, 'agent_service', service_recv)
    except Exception:
        pass
    import backend.app.services.agent_service as be_as_mod
    monkeypatch.setattr(be_as_mod, 'agent_service', service_recv)

    res = await service_init.create_proposal(
        group_id='group_genesis',
        content='Upgrade consensus',
        duration_minutes=60,
    )
    election_id = res['election']['election_id']

    service_recv.governance_manager.receive_p2p_event('proposal', {
        'proposal': res['proposal'],
        'election': res['election'],
    })

    # Call cast_vote tool
    tool_res = await cast_vote.ainvoke({
        'election_id': election_id,
        'approval': True,
        'reason': 'Audit passed: Approved'
    })
    assert 'success' in tool_res

    # Check tally
    recv_election = service_recv.governance_manager.active_elections[election_id]
    tally = recv_election.tally()
    assert tally['approvals'] == 2
    assert tally['total_votes'] == 2
    assert receiver_id in recv_election.votes

    # Subsequent check should NEVER wake again
    data['poked_recv'].clear()
    service_recv.governance_notify_attempts[election_id] = 0.0
    await service_recv.check_governance_proposals()
    await asyncio.sleep(0.05)
    assert len(data['poked_recv']) == 0
