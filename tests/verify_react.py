
"""
Verification script for Agent ReAct Loop.
This script mocks the LLM to simulate a multi-turn conversation and verifies that the agent:
1. Receives the correct context from ContextBuilder.
2. Executes tools in a loop.
3. Continues to the next iteration after tool execution.
4. Stops when no tool calls are made.
"""

import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_react_loop():
    logger.info(">>> Starting ReAct Loop Verification")
    
    # 1. Setup Mock LLM
    mock_llm = AsyncMock()
    
    # Mock Responses for a 2-turn scenario:
    # Turn 1: Agent decides to use a tool (MockTool)
    # Turn 2: Agent receives tool output and gives final answer
    
    response_turn_1 = AIMessage(
        content="",
        tool_calls=[{
            "name": "mock_tool",
            "args": {"input": "test_data"},
            "id": "call_123"
        }]
    )
    
    response_turn_2 = AIMessage(
        content="Task completed successfully based on tool output."
    )
    
    # Configure side_effect to return these in sequence
    mock_llm.ainvoke.side_effect = [response_turn_1, response_turn_2]
    
    # 2. Initialize AgentService
    import sys
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(os.path.join(project_root, 'backend'))
    
    from app.services.agent_service import AgentService
    
    # Mock knowledge_base to avoid web search
    from unittest.mock import patch
    with patch('app.services.agent_service.knowledge_base') as mock_kb:
        mock_kb.search_web_and_context.return_value = "Mock RAG Context"
        
        agent = AgentService()
        agent.llm = mock_llm # Inject mock
    
        # Register a mock tool
        mock_tool_func = AsyncMock()
        mock_tool_func.ainvoke.return_value = "Mock Tool Output Result"
        agent.tools_map["mock_tool"] = mock_tool_func
        
        # 3. Execute _think_and_act
        logger.info("Invoking _think_and_act...")
        user_input = "Please perform a multi-step task."
        final_response = await agent._think_and_act(user_input, "User")
        
        logger.info(f"Final Response: {final_response}")
        
        # 4. Assertions
        # Verify LLM was called twice
        assert mock_llm.ainvoke.call_count == 2, f"Expected 2 LLM calls, got {mock_llm.ainvoke.call_count}"
        
        # Verify ContextBuilder Usage (Inspect first call args)
        call_args = mock_llm.ainvoke.call_args_list[0]
        messages = call_args[0][0]
        
        # Check System Prompt (ContextBuilder)
        assert isinstance(messages[0], SystemMessage)
        assert "You are the specialized Intelligent Agent" in messages[0].content
        logger.info("✔ ContextBuilder correctly injected System Prompt")
        
        # Check User Input
        logger.info(f"Messages List: {messages}")
        human_msg = next((m for m in messages if isinstance(m, HumanMessage)), None)
        assert human_msg is not None
        assert user_input in human_msg.content
        logger.info("✔ User input present in messages")
        
        # Verify Tool Execution
        assert mock_tool_func.ainvoke.called
        logger.info("✔ Mock Tool was executed")
        
        # Verify Tool Output Injection (Inspect second call args)
        call_args_2 = mock_llm.ainvoke.call_args_list[1]
        messages_2 = call_args_2[0][0]
        
        # Should contain: System, ..., User, AI(ToolCall), Tool(Result)
        # We expect the tool result to be in the history passed to the second call
        tool_msg = next((m for m in messages_2 if isinstance(m, ToolMessage)), None)
        assert tool_msg is not None
        assert tool_msg.content == "Mock Tool Output Result"
        logger.info("✔ Tool Output correctly fed back to LLM")
        
        logger.info(">>> ReAct Loop Verification PASSED")

if __name__ == "__main__":
    asyncio.run(verify_react_loop())
