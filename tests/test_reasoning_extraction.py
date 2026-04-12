import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from langchain_core.messages import AIMessage

from app.agent.pipeline import PipelineContext, PlanStage
from app.bus.events import InboundMessage


async def test_reasoning_extraction():
    print("Running Test: Reasoning Extraction from AIMessage")

    # Mock Objects
    agent = MagicMock()
    agent.message_bus = AsyncMock()

    # Simulate an AIMessage with reasoning_content in additional_kwargs (Kimi format)
    mock_response = AIMessage(
        content="This is the final answer.",
        additional_kwargs={"reasoning_content": "This is the thinking process."},
    )

    agent.llm.ainvoke = AsyncMock(return_value=mock_response)

    # Mock session and input message
    session = MagicMock()
    session.session_id = "test_session"
    session.message_count = 0

    input_msg = InboundMessage(
        channel="resident", sender_id="user123", session_id="resident", content="Dummy query"
    )

    context = PipelineContext(session=session, input_message=input_msg, metadata={"messages": []})

    # Run Stage
    stage = PlanStage()
    await stage.run(context, agent)

    # Verification
    # 1. Check thoughts logic
    print(f"Thoughts captured: {context.thoughts}")
    assert "This is the thinking process." in context.thoughts

    # 2. Check message bus publishing
    published_msgs = agent.message_bus.publish_outbound.call_args_list
    print(f"Messages published count: {len(published_msgs)}")

    thought_msg = next((m.args[0] for m in published_msgs if m.args[0].type == "thought"), None)
    assert thought_msg is not None
    print(f"Published Thought Type: {thought_msg.type}")
    print(f"Published Thought Content: {thought_msg.content}")
    assert thought_msg.content == "This is the thinking process."

    print("[OK] Test Passed: Kimi format reasoning extracted.")

    # Test Case 2: DeepSeek-like (hasattr reasoning_content)
    print("\nRunning Test: Reasoning Extraction from attribute (DeepSeek style)")
    mock_response_attr = AIMessage(content="Final answer 2")
    mock_response_attr.reasoning_content = "Thinking 2"
    agent.llm.ainvoke = AsyncMock(return_value=mock_response_attr)

    context_2 = PipelineContext(session=session, input_message=input_msg, metadata={"messages": []})
    await stage.run(context_2, agent)

    assert "Thinking 2" in context_2.thoughts
    print("[OK] Test Passed: Attribute reasoning extracted.")


if __name__ == "__main__":
    asyncio.run(test_reasoning_extraction())
