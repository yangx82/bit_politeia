from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_service import AgentService


@pytest.mark.asyncio
async def test_agent_initialization():
    service = AgentService()

    # Mock P2P Service
    with patch("app.services.agent_service.p2p_service") as mock_p2p:
        mock_p2p.initialize = AsyncMock()

        # Mock ChatOpenAI to avoid real network call
        with patch("app.services.agent_service.ChatOpenAI") as MockChat:
            MockChat.return_value = MagicMock()

            await service.configure_agent("http://mock-url", "mock-key")

            # Verify Agent LLM Initialized
            assert service.llm is not None


@pytest.mark.asyncio
async def test_agent_think_logic():
    service = AgentService()

    # Mock LLM
    mock_llm = AsyncMock()
    # First response: No tools
    mock_llm.ainvoke.return_value = MagicMock(content="Thinking...", tool_calls=[])
    service.llm = mock_llm

    response = await service._think_and_act("Hello", "User")
    assert response == "Thinking..."
    mock_llm.ainvoke.assert_called_once()
