import json

import pytest

from app.agent.tools import read_community_rules, update_system_parameter
from app.services.community_config import RULES_FILE_PATH, community_config


@pytest.fixture
def clean_config():
    """Reset config before and after tests."""
    original_rules = community_config.rules.copy()
    yield
    community_config.rules = original_rules
    community_config.save_rules()


@pytest.mark.asyncio
async def test_config_update(clean_config):
    # Test reading
    rules_json = await read_community_rules.ainvoke({})
    assert "organization" in rules_json

    # Test updating group capacity
    original_capacity = community_config.get_group_capacity()
    new_capacity = original_capacity + 5

    result = await update_system_parameter.ainvoke(
        {"parameter_path": "organization.group_size.max", "value": str(new_capacity)}
    )
    assert "Successfully updated" in result

    # Verify in memory
    assert community_config.get_group_capacity() == new_capacity

    # Verify in file
    with open(RULES_FILE_PATH) as f:
        data = json.load(f)
        assert data["organization"]["group_size"]["max"] == new_capacity


@pytest.mark.asyncio
async def test_bootstrap_respects_config(clean_config):
    # Set a distinct capacity in config
    test_capacity = 42
    await update_system_parameter.ainvoke(
        {"parameter_path": "organization.group_size.max", "value": str(test_capacity)}
    )

    # Initialize service directly (logic matches server)
    from app.services.bootstrap_service import BootstrapService

    # Force re-init to pick up new config
    sim = BootstrapService()

    # It should use the config value
    assert sim.group_capacity == test_capacity

    # Verify simulation logic uses it
    found = False
    for g in sim._groups.values():
        if g.max_capacity == test_capacity:
            found = True
            break
    assert found
