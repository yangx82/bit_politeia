"""
LM Studio & LLM Error Handling Unit Tests
=========================================
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock

# Ensure we can import from backend
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
backend_path = os.path.join(project_root, "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.agent.pipeline import PlanStage, PipelineContext
from app.models.session import Session
from app.bus.events import InboundMessage
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


@pytest.mark.anyio
async def test_lm_studio_no_models_loaded_handling():
    session = Session(session_id="test_session", entity_id="user1", channel="resident")
    msg = InboundMessage(channel="resident", sender_id="user1", session_id="test_session", content="测试")

    context = PipelineContext(session=session, input_message=msg)
    context.metadata["messages"] = []

    agent = MagicMock()
    agent.llm.ainvoke = AsyncMock(side_effect=Exception(
        "Error code: 400 - {'error': 'no models loaded'}"
    ))

    stage = PlanStage()
    await stage.run(context, agent)

    assert context.stop_execution is True
    assert context.continuation_req is False
    assert context.continuation_reason == "FATAL_NO_MODEL_LOADED"
    assert "LM Studio 未加载任何模型" in context.final_answer


@pytest.mark.anyio
async def test_sglang_failed_to_parse_fc_handling():
    session = Session(session_id="test_session", entity_id="user1", channel="resident")
    msg = InboundMessage(channel="resident", sender_id="user1", session_id="test_session", content="测试")

    context = PipelineContext(session=session, input_message=msg)
    context.metadata["messages"] = []

    agent = MagicMock()
    agent.llm.ainvoke = AsyncMock(side_effect=Exception(
        "Error code: 400 - Failed to parse fc related info to json format!"
    ))

    stage = PlanStage()
    await stage.run(context, agent)

    assert context.stop_execution is True
    assert context.continuation_req is False
    assert context.continuation_reason == "FATAL_SGLANG_FC_PARSER_ERROR"
    assert "SGLang 部署的模型解析工具调用失败" in context.final_answer


@pytest.mark.anyio
async def test_sglang_parallel_tool_calls_handling():
    session = Session(session_id="test_session", entity_id="user1", channel="resident")
    msg = InboundMessage(channel="resident", sender_id="user1", session_id="test_session", content="测试")

    context = PipelineContext(session=session, input_message=msg)
    context.metadata["messages"] = []

    agent = MagicMock()
    agent.llm.ainvoke = AsyncMock(side_effect=Exception(
        "Error code: 400 - model does not support parallel_tool_calls"
    ))

    stage = PlanStage()
    await stage.run(context, agent)

    assert context.stop_execution is True
    assert context.continuation_req is False
    assert context.continuation_reason == "FATAL_PARALLEL_TOOL_CALLS_UNSUPPORTED"
    assert "不支持并行工具调用" in context.final_answer


@pytest.mark.anyio
async def test_sglang_validation_400_handling():
    session = Session(session_id="test_session", entity_id="user1", channel="resident")
    msg = InboundMessage(channel="resident", sender_id="user1", session_id="test_session", content="测试")

    context = PipelineContext(session=session, input_message=msg)
    context.metadata["messages"] = []

    agent = MagicMock()
    agent.llm.ainvoke = AsyncMock(side_effect=Exception(
        "Error code: 400 - {'detail': 'validation error: extra fields not permitted'}"
    ))

    stage = PlanStage()
    await stage.run(context, agent)

    assert context.stop_execution is True
    assert context.continuation_req is False
    assert context.continuation_reason == "FATAL_LLM_REQUEST_VALIDATION_ERROR"
    assert "请求参数验证失败（400 Bad Request）" in context.final_answer


@pytest.mark.anyio
async def test_dashscope_in_flight_recovery():
    session = Session(session_id="test_session", entity_id="user1", channel="resident")
    msg = InboundMessage(channel="resident", sender_id="user1", session_id="test_session", content="编写代码")

    context = PipelineContext(session=session, input_message=msg)
    context.metadata["messages"] = [
        SystemMessage(content="System prompt"),
        ToolMessage(tool_call_id="1", content="X" * 5000),
        HumanMessage(content="Next step")
    ]

    mock_ok_response = MagicMock()
    mock_ok_response.additional_kwargs = {}

    agent = MagicMock()
    agent.message_bus = MagicMock()
    agent.message_bus.publish_outbound = AsyncMock()
    agent.llm.ainvoke = AsyncMock(side_effect=[
        Exception("<400> InternalError.Algo.InvalidParameter: Range of input length should be [1, 260096]"),
        mock_ok_response
    ])

    stage = PlanStage()
    await stage.run(context, agent)

    assert context.stop_execution is False
    assert agent.llm.ainvoke.call_count == 2
    compacted_messages = context.metadata["messages"]
    assert "Payload truncated" in compacted_messages[1].content


@pytest.mark.anyio
async def test_dashscope_260096_exhausted_retries():
    session = Session(session_id="test_session", entity_id="user1", channel="resident")
    msg = InboundMessage(channel="resident", sender_id="user1", session_id="test_session", content="编写代码")

    context = PipelineContext(session=session, input_message=msg)
    context.metadata["messages"] = [SystemMessage(content="System prompt")]

    agent = MagicMock()
    agent.message_bus = MagicMock()
    agent.message_bus.publish_outbound = AsyncMock()
    agent.llm.ainvoke = AsyncMock(side_effect=Exception(
        "<400> InternalError.Algo.InvalidParameter: Range of input length should be [1, 260096]"
    ))

    stage = PlanStage()
    await stage.run(context, agent)

    assert context.stop_execution is True
    assert context.continuation_req is False
    assert "TOKEN_LENGTH_EXCEEDED" in context.continuation_reason
    assert "超出模型 token 上限" in context.final_answer


@pytest.mark.anyio
async def test_feishu_channel_promised_action_reprompt():
    """
    验证当消息渠道为 feishu 时，如果模型输出口头承诺文本（如“现在我来为您编写分析脚本：”），
    PlanStage 正确拦截并自动重新激发 tool_call 驱动。
    """
    session = Session(session_id="test_feishu_session", entity_id="feishu_user_1", channel="feishu")
    msg = InboundMessage(channel="feishu", sender_id="feishu_user_1", session_id="test_feishu_session", content="分析代谢笼数据")

    context = PipelineContext(session=session, input_message=msg)
    context.metadata["messages"] = [SystemMessage(content="System prompt")]

    mock_promised_resp = MagicMock(spec=AIMessage)
    mock_promised_resp.content = "好的，现在我来为您编写分析脚本："
    mock_promised_resp.tool_calls = []
    mock_promised_resp.additional_kwargs = {}

    mock_tool_resp = MagicMock(spec=AIMessage)
    mock_tool_resp.content = ""
    mock_tool_resp.tool_calls = [{"name": "delegate_coding_task", "args": {"task_description": "分析代谢笼数据"}, "id": "call_1"}]
    mock_tool_resp.additional_kwargs = {}

    agent = MagicMock()
    agent.message_bus = MagicMock()
    agent.message_bus.publish_outbound = AsyncMock()
    agent.llm.ainvoke = AsyncMock(side_effect=[mock_promised_resp, mock_tool_resp])

    stage = PlanStage()
    await stage.run(context, agent)

    # Must NOT stop execution because missing tool reprompting succeeded and produced tool_calls
    assert context.stop_execution is False
    assert len(context.tool_calls) == 1
    assert context.tool_calls[0]["name"] == "delegate_coding_task"
    assert agent.llm.ainvoke.call_count == 2


@pytest.mark.anyio
async def test_verify_on_stop_code_task_reprompt():
    """
    验证当用户要求编写代码/程序，而模型未提供语法/存在性验证即尝试结束时，
    PlanStage 正确拦截并触发 Verify-on-Stop 校验导引。
    """
    session = Session(session_id="test_code_session", entity_id="user1", channel="resident")
    msg = InboundMessage(channel="resident", sender_id="user1", session_id="test_code_session", content="请编写一个代谢笼分析程序")

    context = PipelineContext(session=session, input_message=msg)
    context.metadata["messages"] = [SystemMessage(content="System prompt")]

    mock_unverified_resp = MagicMock(spec=AIMessage)
    mock_unverified_resp.content = "程序已经写好了。"
    mock_unverified_resp.tool_calls = []
    mock_unverified_resp.additional_kwargs = {}

    mock_verify_tool_resp = MagicMock(spec=AIMessage)
    mock_verify_tool_resp.content = ""
    mock_verify_tool_resp.tool_calls = [{"name": "check_python_syntax", "args": {"file_path": "data/resident/metabolic_cage.py"}, "id": "call_v1"}]
    mock_verify_tool_resp.additional_kwargs = {}

    agent = MagicMock()
    agent.message_bus = MagicMock()
    agent.message_bus.publish_outbound = AsyncMock()
    agent.llm.ainvoke = AsyncMock(side_effect=[mock_unverified_resp, mock_verify_tool_resp])

    stage = PlanStage()
    await stage.run(context, agent)

    assert context.stop_execution is False
    assert len(context.tool_calls) == 1
    assert context.tool_calls[0]["name"] == "check_python_syntax"
    assert agent.llm.ainvoke.call_count == 2

