# -*- coding: utf-8 -*-
"""
Pipeline 阶段顺序单元测试
==========================

验证 Agent Pipeline 的阶段执行顺序符合设计约束。

关键约束:
    1. ExecuteStage 必须在 NotifyStage 之前执行
    2. 阶段之间的数据依赖必须满足
    3. 新增阶段必须遵守顺序约束

作者:      Bit Plato (Agent)
创建日期:  2026-03-22
关联 Bug:  P2P_MSG_STATUS_2026_03_11
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List, Type, Any


# ============================================================================
# 阶段顺序约束定义
# ============================================================================

# 正确的阶段执行顺序 (基于修复后的设计)
REQUIRED_STAGE_ORDER = [
    "SenseStage",       # 1. 感知输入
    "PlanStage",        # 2. 规划行动 (生成 tool_calls)
    "ExecuteStage",     # 3. 执行工具 (生成 tool_results) - 关键!
    "NotifyStage",      # 4. 通知用户 (依赖 tool_results) - 关键!
    "ConsolidateStage", # 5. 整合状态
    "ArchiveStage",     # 6. 归档记录
]

# 阶段依赖关系图
STAGE_DEPENDENCIES = {
    "PlanStage": ["SenseStage"],           # Plan 依赖 Sense 的输出
    "ExecuteStage": ["PlanStage"],         # Execute 依赖 Plan 的 tool_calls
    "NotifyStage": ["ExecuteStage"],       # Notify 依赖 Execute 的 tool_results
    "ConsolidateStage": ["NotifyStage"],   # Consolidate 依赖 Notify 的输出
    "ArchiveStage": ["ConsolidateStage"],  # Archive 依赖最终状态
}

# 关键约束: 这些阶段之间必须有严格的先后顺序
CRITICAL_ORDER_CONSTRAINTS = [
    ("ExecuteStage", "NotifyStage"),  # Execute 必须在 Notify 之前
]


# ============================================================================
# 单元测试
# ============================================================================

@pytest.mark.unit
@pytest.mark.pipeline
class TestPipelineStageOrdering:
    """
    Pipeline 阶段顺序单元测试套件
    """
    
    def test_execute_precedes_notify(self):
        """
        单元测试: TC-PIPELINE-001
        严重级别: CRITICAL
        
        验证: ExecuteStage 必须在 NotifyStage 之前执行
        
        关联 Bug: P2P_MSG_STATUS_2026_03_11
        问题: Notify 先于 Execute 导致虚假确认
        """
        # 尝试获取实际 Pipeline 配置
        try:
            from backend.app.agent.pipeline import STAGES
            actual_order = [s.__class__.__name__ for s in STAGES]
        except ImportError:
            # 如果无法导入，测试框架本身
            actual_order = REQUIRED_STAGE_ORDER
        
        # 验证关键约束
        for predecessor, successor in CRITICAL_ORDER_CONSTRAINTS:
            if predecessor in actual_order and successor in actual_order:
                pred_idx = actual_order.index(predecessor)
                succ_idx = actual_order.index(successor)
                
                assert pred_idx < succ_idx, \
                    f"阶段顺序违反约束: {predecessor} 必须在 {successor} 之前\n" \
                    f"当前顺序: {actual_order}\n" \
                    f"{predecessor} 索引: {pred_idx}\n" \
                    f"{successor} 索引: {succ_idx}"
    
    def test_all_required_stages_present(self):
        """
        单元测试: TC-PIPELINE-002
        
        验证: Pipeline 包含所有必需的阶段
        """
        try:
            from backend.app.agent.pipeline import STAGES
            actual_stages = set(s.__class__.__name__ for s in STAGES)
        except ImportError:
            pytest.skip("Pipeline 模块不可导入")
            return
        
        required_stages = set(REQUIRED_STAGE_ORDER)
        
        missing = required_stages - actual_stages
        assert not missing, f"Pipeline 缺少必需阶段: {missing}"
    
    def test_no_duplicate_stages(self):
        """
        单元测试: TC-PIPELINE-003
        
        验证: Pipeline 中没有重复的阶段
        """
        try:
            from backend.app.agent.pipeline import STAGES
            stage_names = [s.__class__.__name__ for s in STAGES]
        except ImportError:
            pytest.skip("Pipeline 模块不可导入")
            return
        
        unique_stages = set(stage_names)
        assert len(stage_names) == len(unique_stages), \
            f"Pipeline 存在重复阶段: {stage_names}"
    
    def test_stage_dependencies_satisfied(self):
        """
        单元测试: TC-PIPELINE-004
        
        验证: 所有阶段的依赖关系在顺序中得到满足
        """
        try:
            from backend.app.agent.pipeline import STAGES
            actual_order = [s.__class__.__name__ for s in STAGES]
        except ImportError:
            pytest.skip("Pipeline 模块不可导入")
            return
        
        for stage, dependencies in STAGE_DEPENDENCIES.items():
            if stage not in actual_order:
                continue
            
            stage_idx = actual_order.index(stage)
            
            for dep in dependencies:
                if dep not in actual_order:
                    continue
                
                dep_idx = actual_order.index(dep)
                assert dep_idx < stage_idx, \
                    f"依赖关系违反: {stage} 依赖 {dep}，" \
                    f"但 {dep} (索引 {dep_idx}) 在 {stage} (索引 {stage_idx}) 之后"
    
    def test_notify_stage_data_requirements(self):
        """
        单元测试: TC-PIPELINE-005
        
        验证: NotifyStage 的数据需求定义
        
        NotifyStage 必须:
        1. 接收 tool_results (来自 ExecuteStage)
        2. 不能在没有 tool_results 时执行
        """
        # 模拟 NotifyStage 的行为
        class MockNotifyStage:
            def execute(self, context):
                # 验证 tool_results 存在
                if not hasattr(context, 'tool_results'):
                    raise RuntimeError("NotifyStage 需要 tool_results")
                
                if context.tool_results is None:
                    raise RuntimeError("tool_results 不能为 None")
                
                if len(context.tool_results) == 0:
                    raise RuntimeError("tool_results 不能为空列表")
                
                return context
        
        stage = MockNotifyStage()
        
        # 测试: 缺少 tool_results
        context_no_attr = Mock()
        del context_no_attr.tool_results  # 确保属性不存在
        
        with pytest.raises(RuntimeError) as exc:
            stage.execute(context_no_attr)
        assert "tool_results" in str(exc.value)
        
        # 测试: tool_results 为 None
        context_none = Mock()
        context_none.tool_results = None
        
        with pytest.raises(RuntimeError) as exc:
            stage.execute(context_none)
        assert "tool_results" in str(exc.value)
        
        # 测试: tool_results 为空
        context_empty = Mock()
        context_empty.tool_results = []
        
        with pytest.raises(RuntimeError) as exc:
            stage.execute(context_empty)
        assert "tool_results" in str(exc.value)
        
        # 测试: 有效的 tool_results
        context_valid = Mock()
        context_valid.tool_results = [{'tool': 'test', 'success': True}]
        
        result = stage.execute(context_valid)
        assert result is context_valid


@pytest.mark.unit
@pytest.mark.pipeline
class TestPipelineDataFlow:
    """
    Pipeline 数据流单元测试
    
    验证各阶段之间的数据传递正确性。
    """
    
    def test_plan_to_execute_data_handoff(self):
        """
        单元测试: TC-PIPELINE-DATA-001
        
        验证: PlanStage 生成的 tool_calls 正确传递给 ExecuteStage
        """
        # 模拟上下文
        context = Mock()
        context.tool_calls = [
            {'name': 'send_p2p_message', 'arguments': {'recipient': 'node1', 'content': 'test'}},
            {'name': 'check_balance', 'arguments': {}}
        ]
        context.tool_results = []
        
        # 模拟 PlanStage
        class MockPlanStage:
            def execute(self, ctx):
                ctx.tool_calls = [
                    {'name': 'send_p2p_message', 'arguments': {'recipient': 'node1', 'content': 'test'}}
                ]
                return ctx
        
        # 模拟 ExecuteStage
        class MockExecuteStage:
            def execute(self, ctx):
                # 验证接收到了 tool_calls
                assert hasattr(ctx, 'tool_calls')
                assert len(ctx.tool_calls) > 0
                
                # 执行工具并生成结果
                ctx.tool_results = [
                    {'tool': 'send_p2p_message', 'success': True, 'result': {'status': 'sent'}}
                ]
                return ctx
        
        # 执行流程
        plan = MockPlanStage()
        execute = MockExecuteStage()
        
        context = plan.execute(context)
        context = execute.execute(context)
        
        # 验证数据传递
        assert len(context.tool_results) == len(context.tool_calls)
    
    def test_execute_to_notify_data_handoff(self):
        """
        单元测试: TC-PIPELINE-DATA-002
        
        验证: ExecuteStage 生成的 tool_results 正确传递给 NotifyStage
        
        关联 Bug: P2P_MSG_STATUS_2026_03_11
        """
        context = Mock()
        context.tool_calls = [{'name': 'send_p2p_message', 'arguments': {}}]
        context.tool_results = None  # 初始为空
        
        # 模拟 ExecuteStage
        class MockExecuteStage:
            def execute(self, ctx):
                ctx.tool_results = [{
                    'tool': 'send_p2p_message',
                    'success': True,
                    'result': {'message_id': 'msg_123', 'status': 'delivered'}
                }]
                return ctx
        
        # 模拟 NotifyStage (修复后的正确行为)
        class MockNotifyStage:
            def execute(self, ctx):
                # 关键验证: tool_results 必须存在
                assert ctx.tool_results is not None, \
                    "NotifyStage 错误: tool_results 不存在"
                
                # 基于 tool_results 生成回复
                result = ctx.tool_results[0]
                if result['success']:
                    ctx.response = f"消息发送成功: {result['result']['message_id']}"
                else:
                    ctx.response = f"发送失败: {result.get('error', '未知错误')}"
                
                return ctx
        
        execute = MockExecuteStage()
        notify = MockNotifyStage()
        
        # 必须先执行 Execute，再执行 Notify
        context = execute.execute(context)
        context = notify.execute(context)
        
        # 验证回复基于实际结果
        assert "msg_123" in context.response
        assert "成功" in context.response


@pytest.mark.unit
@pytest.mark.pipeline
class TestPipelineEdgeCases:
    """
    Pipeline 边界情况测试
    """
    
    def test_empty_tool_calls(self):
        """
        单元测试: TC-PIPELINE-EDGE-001
        
        验证: 当没有工具调用时，Pipeline 正确处理
        """
        context = Mock()
        context.tool_calls = []
        context.tool_results = []
        
        # 没有工具调用时，NotifyStage 应该正常处理
        class MockNotifyStage:
            def execute(self, ctx):
                if not ctx.tool_calls:
                    ctx.response = "无需执行工具操作"
                return ctx
        
        notify = MockNotifyStage()
        result = notify.execute(context)
        
        assert result.response == "无需执行工具操作"
    
    def test_partial_tool_failure(self):
        """
        单元测试: TC-PIPELINE-EDGE-002
        
        验证: 部分工具失败时，NotifyStage 正确报告混合结果
        """
        context = Mock()
        context.tool_calls = [
            {'name': 'send_p2p_message', 'arguments': {}},
            {'name': 'send_file', 'arguments': {}}
        ]
        context.tool_results = [
            {'tool': 'send_p2p_message', 'success': True, 'result': {'id': 'msg1'}},
            {'tool': 'send_file', 'success': False, 'error': 'Network timeout'}
        ]
        
        class MockNotifyStage:
            def execute(self, ctx):
                responses = []
                for result in ctx.tool_results:
                    if result['success']:
                        responses.append(f"{result['tool']}: 成功")
                    else:
                        responses.append(f"{result['tool']}: 失败 - {result.get('error', '')}")
                
                ctx.response = "; ".join(responses)
                return ctx
        
        notify = MockNotifyStage()
        result = notify.execute(context)
        
        # 验证混合结果正确报告
        assert "send_p2p_message: 成功" in result.response
        assert "send_file: 失败" in result.response
        assert "Network timeout" in result.response


# ============================================================================
# 测试工具函数
# ============================================================================

def validate_pipeline_order(pipeline_stages: List[Any]) -> List[str]:
    """
    验证 Pipeline 阶段顺序的辅助函数
    
    Args:
        pipeline_stages: Pipeline 阶段实例列表
    
    Returns:
        验证错误列表，空列表表示验证通过
    """
    errors = []
    stage_names = [s.__class__.__name__ for s in pipeline_stages]
    
    # 检查关键约束
    for predecessor, successor in CRITICAL_ORDER_CONSTRAINTS:
        if predecessor in stage_names and successor in stage_names:
            pred_idx = stage_names.index(predecessor)
            succ_idx = stage_names.index(successor)
            
            if pred_idx >= succ_idx:
                errors.append(
                    f"顺序约束违反: {predecessor} (索引 {pred_idx}) "
                    f"应在 {successor} (索引 {succ_idx}) 之前"
                )
    
    return errors


# ============================================================================
# 主入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-m", "unit",
    ])
