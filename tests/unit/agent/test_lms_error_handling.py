"""
LM Studio 错误处理单元测试
=========================

验证当 LM Studio 未加载模型时，PlanStage 正确拦截错误，
提供友好的中文提示，并将 continuation_req 设置为 False，避免触发 Ralph Wiggum 循环。

作者:      Bit Plato (Agent)
创建日期:  2026-05-18
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock

# Ensure we can import from backend
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.app.agent.pipeline import PlanStage, PipelineContext
from backend.app.models.session import Session
from backend.app.bus.events import InboundMessage

@pytest.mark.anyio
async def test_lms_no_models_loaded_handling():
    """
    验证 LM Studio 未加载模型时的错误处理逻辑
    """
    # 构造模拟 session 和消息
    session = Session(session_id="test_session", entity_id="user1", channel="resident")
    msg = InboundMessage(channel="resident", sender_id="user1", session_id="test_session", content="你好")
    
    # 初始化 PipelineContext
    context = PipelineContext(session=session, input_message=msg)
    context.metadata["messages"] = []
    
    # 构造模拟 Agent，其 LLM 抛出 LM Studio 的 No models loaded 异常
    agent = MagicMock()
    agent.llm.ainvoke = AsyncMock(side_effect=Exception(
        "Error code: 400 - {'error': {'message': \"No models loaded. Please load a model in the developer page or use the 'lms load' command.\", 'type': 'invalid_request_error', 'param': 'model', 'code': None}}"
    ))
    
    # 运行 PlanStage
    stage = PlanStage()
    await stage.run(context, agent)
    
    # 验证期望的结果
    assert context.stop_execution is True
    assert context.continuation_req is False
    assert context.continuation_reason == "FATAL_NO_MODEL_LOADED"
    assert "LM Studio 未加载任何模型" in context.final_answer


@pytest.mark.anyio
async def test_sglang_failed_to_parse_fc_handling():
    """
    验证 SGLang 解析工具调用失败时的错误处理逻辑
    """
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
    """
    验证 SGLang/兼容服务不支持并行工具调用时的错误处理逻辑
    """
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
    """
    验证 SGLang/兼容服务请求参数验证失败（400 Bad Request）时的错误处理逻辑
    """
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
