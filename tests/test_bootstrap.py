from unittest.mock import MagicMock, patch

import pytest

from app.p2p_community.bootstrap_client import NodeRegistration
from app.services.bootstrap_service import BootstrapService


@pytest.fixture
def bootstrap_service():
    return BootstrapService()


def test_initialization(bootstrap_service):
    # Should have root group (level 0) and one level 1 group
    topo = bootstrap_service.get_topology_info()
    assert topo["stats"]["total_groups"] >= 2
    assert topo["stats"]["total_nodes"] == 0


def test_node_registration(bootstrap_service):
    reg = NodeRegistration(node_id="node1", public_key="key1", ip_address="127.0.0.1", port=8000)
    result = bootstrap_service.register_node(reg)
    assert result == True

    topo = bootstrap_service.get_topology_info()
    assert topo["stats"]["total_nodes"] == 1
    assert "node1" in topo["nodes"]


def test_auto_scaling(bootstrap_service):
    # Fill up the first group
    joinable = bootstrap_service.get_joinable_groups(1)
    if not joinable:
        pytest.skip("No joinable groups found")

    group = joinable[0]
    # Artificially fill it
    bootstrap_service._groups[group.group_id].member_count = group.max_capacity

    # Requesting joinable groups should now trigger creation of a new group
    new_joinable = bootstrap_service.get_joinable_groups(1)

    assert len(new_joinable) > 0
    assert new_joinable[0].group_id != group.group_id
    assert new_joinable[0].level == 1


@pytest.mark.asyncio
async def test_client_interaction():
    # Mock httpx.AsyncClient to avoid running real server
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Mock Response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "groups": {"g1": {"group_id": "g1", "level": 1, "member_count": 0, "max_capacity": 10}}
        }

        # Create an async mock for the .get method
        async def async_get_response(*args, **kwargs):
            return mock_resp

        mock_client.get.side_effect = async_get_response

        # Test Client
        from app.p2p_community.bootstrap_client import BootstrapClient

        client = BootstrapClient()
        groups = await client.get_joinable_groups()

        assert len(groups) == 1
        assert groups[0].group_id == "g1"
