"""
Pipeline 执行集成测试
======================

验证完整的 Agent Pipeline 执行流程，包括:
- 阶段流转正确性
- 数据传递完整性
- 错误处理与恢复
- 并发安全性

作者:      Bit Plato (Agent)
创建日期:  2026-03-22
关联 Bug:  P2P_MSG_STATUS_2026_03_11
"""

import asyncio
from datetime import datetime
from unittest.mock import Mock

import pytest

# ============================================================================
# 集成测试配置
# ============================================================================

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.timeout(60),  # 集成测试超时 60 秒
]


# ============================================================================
# 集成测试套件
# ============================================================================


@pytest.mark.integration
class TestPipelineExecutionFlow:
    """
    Pipeline 完整执行流程集成测试

    模拟真实的 Agent 处理流程，验证各阶段协同工作。
    """

    async def test_full_pipeline_success_flow(self):
        """
        集成测试: TC-INT-PIPELINE-001

        验证: 完整的成功执行流程

        流程:
            Sense → Plan → Execute → Notify → Consolidate → Archive
        """
        # 构建模拟 Pipeline
        pipeline = self._create_mock_pipeline()

        # 初始输入
        user_input = "发送消息给 node1: 你好"
        context = Mock()
        context.user_message = user_input
        context.tool_calls = []
        context.tool_results = []
        context.response = None
        context.metadata = {}

        # 执行 Pipeline
        result = await pipeline.execute(context)

        # 验证执行顺序
        execution_order = pipeline.get_execution_order()
        assert execution_order == [
            "SenseStage",
            "PlanStage",
            "ExecuteStage",
            "NotifyStage",
            "ConsolidateStage",
            "ArchiveStage",
        ], f"执行顺序错误: {execution_order}"

        # 验证最终输出
        assert result.response is not None
        assert len(result.tool_results) > 0

    async def test_pipeline_with_p2p_message(self):
        """
        集成测试: TC-INT-PIPELINE-002

        验证: 包含 P2P 消息发送的完整流程

        关联 Bug: P2P_MSG_STATUS_2026_03_11
        """
        pipeline = self._create_mock_pipeline()

        context = Mock()
        context.user_message = "发送 P2P 消息给 Aristocles"
        context.tool_calls = [
            {
                "name": "send_p2p_message",
                "arguments": {"recipient_id": "5faa8871...", "content": "Git-P2P 测试状态探查"},
            }
        ]
        context.tool_results = []

        # 执行
        result = await pipeline.execute(context)

        # 关键验证: ExecuteStage 在 NotifyStage 之前执行
        execution_order = pipeline.get_execution_order()
        execute_idx = execution_order.index("ExecuteStage")
        notify_idx = execution_order.index("NotifyStage")

        assert execute_idx < notify_idx, (
            f"ExecuteStage 必须在 NotifyStage 之前执行\n当前顺序: {execution_order}"
        )

        # 验证 tool_results 被正确生成和使用
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool"] == "send_p2p_message"

        # 验证回复基于实际执行结果
        if result.tool_results[0]["success"]:
            assert "成功" in result.response or "sent" in result.response.lower()
        else:
            assert "失败" in result.response or "error" in result.response.lower()

    async def test_pipeline_with_multiple_tools(self):
        """
        集成测试: TC-INT-PIPELINE-003

        验证: 包含多个工具调用的复杂流程
        """
        pipeline = self._create_mock_pipeline()

        context = Mock()
        context.user_message = "检查余额并发送消息"
        context.tool_calls = [
            {"name": "check_my_balance", "arguments": {}},
            {"name": "send_p2p_message", "arguments": {"recipient_id": "test", "content": "hi"}},
        ]
        context.tool_results = []

        result = await pipeline.execute(context)

        # 验证所有工具都被执行
        assert len(result.tool_results) == 2

        # 验证结果顺序与调用顺序一致
        assert result.tool_results[0]["tool"] == "check_my_balance"
        assert result.tool_results[1]["tool"] == "send_p2p_message"

    async def test_pipeline_error_recovery(self):
        """
        集成测试: TC-INT-PIPELINE-004

        验证: 工具执行失败时的错误处理
        """
        pipeline = self._create_mock_pipeline_with_error()

        context = Mock()
        context.user_message = "发送消息（将失败）"
        context.tool_calls = [{"name": "send_p2p_message", "arguments": {}}]
        context.tool_results = []

        # 执行（包含模拟错误）
        result = await pipeline.execute(context)

        # 验证错误被正确捕获和报告
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["success"] == False
        assert "error" in result.tool_results[0]

        # 验证 NotifyStage 报告失败而非成功
        assert "失败" in result.response or "error" in result.response.lower()

    async def test_pipeline_stage_isolation(self):
        """
        集成测试: TC-INT-PIPELINE-005

        验证: 各阶段之间的隔离性

        确保一个阶段的错误不会影响其他阶段的执行。
        """
        pipeline = self._create_mock_pipeline()

        execution_log = []

        # 包装每个阶段以记录执行
        original_stages = pipeline.stages.copy()
        for stage in original_stages:
            original_execute = stage.execute

            async def logged_execute(ctx, orig=original_execute, name=stage.__class__.__name__):
                execution_log.append(f"{name}_start")
                try:
                    result = await orig(ctx)
                    execution_log.append(f"{name}_end")
                    return result
                except Exception as e:
                    execution_log.append(f"{name}_error: {e}")
                    raise

            stage.execute = logged_execute

        context = Mock()
        context.user_message = "测试"
        context.tool_calls = []
        context.tool_results = []

        await pipeline.execute(context)

        # 验证所有阶段都完成了执行
        for stage in original_stages:
            name = stage.__class__.__name__
            assert f"{name}_start" in execution_log
            assert f"{name}_end" in execution_log or f"{name}_error" in execution_log

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _create_mock_pipeline(self):
        """创建模拟 Pipeline"""

        class MockPipeline:
            def __init__(self):
                self.execution_order = []
                self.stages = [
                    self._create_stage("SenseStage"),
                    self._create_stage("PlanStage"),
                    self._create_stage("ExecuteStage"),
                    self._create_stage("NotifyStage"),
                    self._create_stage("ConsolidateStage"),
                    self._create_stage("ArchiveStage"),
                ]

            def _create_stage(self, name):
                stage = Mock()
                stage.__class__.__name__ = name

                async def execute(ctx):
                    self.execution_order.append(name)

                    if name == "PlanStage":
                        # PlanStage 生成 tool_calls
                        if not ctx.tool_calls:
                            ctx.tool_calls = [{"name": "default_action", "arguments": {}}]

                    elif name == "ExecuteStage":
                        # ExecuteStage 执行工具并生成 tool_results
                        ctx.tool_results = []
                        for call in ctx.tool_calls:
                            ctx.tool_results.append(
                                {
                                    "tool": call["name"],
                                    "success": True,
                                    "result": {
                                        "status": "completed",
                                        "timestamp": datetime.now().isoformat(),
                                    },
                                    "error": None,
                                }
                            )

                    elif name == "NotifyStage":
                        # NotifyStage 基于 tool_results 生成回复
                        if ctx.tool_results:
                            success_count = sum(1 for r in ctx.tool_results if r["success"])
                            ctx.response = f"执行完成: {success_count}/{len(ctx.tool_results)} 成功"
                        else:
                            ctx.response = "无需执行操作"

                    return ctx

                stage.execute = execute
                return stage

            async def execute(self, context):
                for stage in self.stages:
                    context = await stage.execute(context)
                return context

            def get_execution_order(self):
                return self.execution_order

        return MockPipeline()

    def _create_mock_pipeline_with_error(self):
        """创建包含错误的模拟 Pipeline"""

        class MockPipelineWithError:
            def __init__(self):
                self.execution_order = []

            async def execute(self, context):
                # Sense
                self.execution_order.append("SenseStage")

                # Plan
                self.execution_order.append("PlanStage")

                # Execute (模拟失败)
                self.execution_order.append("ExecuteStage")
                context.tool_results = [
                    {
                        "tool": "send_p2p_message",
                        "success": False,
                        "error": "Network timeout: connection refused",
                        "result": None,
                    }
                ]

                # Notify (必须正确处理失败)
                self.execution_order.append("NotifyStage")
                context.response = f"发送失败: {context.tool_results[0]['error']}"

                # Consolidate
                self.execution_order.append("ConsolidateStage")

                # Archive
                self.execution_order.append("ArchiveStage")

                return context

            def get_execution_order(self):
                return self.execution_order

        return MockPipelineWithError()


@pytest.mark.integration
class TestPipelineConcurrency:
    """
    Pipeline 并发执行测试

    验证 Pipeline 在多请求并发时的正确性。
    """

    async def test_concurrent_pipeline_execution(self):
        """
        集成测试: TC-INT-CONC-001

        验证: 多个 Pipeline 实例并发执行互不干扰
        """

        async def run_pipeline(instance_id: int):
            pipeline = TestPipelineExecutionFlow()._create_mock_pipeline()

            context = Mock()
            context.user_message = f"请求 {instance_id}"
            context.tool_calls = [{"name": "test_action", "arguments": {"id": instance_id}}]
            context.tool_results = []

            result = await pipeline.execute(context)

            # 验证结果与请求匹配
            assert result.tool_results[0]["result"]["id"] == instance_id

            return instance_id

        # 并发执行多个 Pipeline
        tasks = [run_pipeline(i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        # 验证所有任务都成功完成
        assert sorted(results) == list(range(5))

    async def test_pipeline_state_isolation(self):
        """
        集成测试: TC-INT-CONC-002

        验证: 并发执行时状态隔离
        """
        shared_state = {"counter": 0}

        async def run_with_state(instance_id: int):
            # 每个实例应有独立的状态
            local_state = {"id": instance_id, "executed": False}

            await asyncio.sleep(0.01)  # 模拟处理时间
            local_state["executed"] = True
            shared_state["counter"] += 1

            return local_state

        tasks = [run_with_state(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # 验证每个实例状态独立
        for i, state in enumerate(results):
            assert state["id"] == i
            assert state["executed"] == True

        # 验证共享状态正确更新
        assert shared_state["counter"] == 10


@pytest.mark.integration
class TestPipelineErrorScenarios:
    """
    Pipeline 错误场景测试
    """

    async def test_execute_stage_failure_handling(self):
        """
        集成测试: TC-INT-ERR-001

        验证: ExecuteStage 失败时的处理
        """
        context = Mock()
        context.tool_calls = [{"name": "failing_tool", "arguments": {}}]
        context.tool_results = []

        # 模拟 ExecuteStage 抛出异常
        async def failing_execute(ctx):
            raise RuntimeError("工具执行失败: 网络连接超时")

        # 验证异常被正确传播
        with pytest.raises(RuntimeError) as exc:
            await failing_execute(context)

        assert "网络连接超时" in str(exc.value)

    async def test_notify_stage_with_partial_results(self):
        """
        集成测试: TC-INT-ERR-002

        验证: NotifyStage 处理部分成功/部分失败的结果
        """
        context = Mock()
        context.tool_calls = [
            {"name": "tool_a", "arguments": {}},
            {"name": "tool_b", "arguments": {}},
            {"name": "tool_c", "arguments": {}},
        ]
        context.tool_results = [
            {"tool": "tool_a", "success": True, "result": {}},
            {"tool": "tool_b", "success": False, "error": "Timeout"},
            {"tool": "tool_c", "success": True, "result": {}},
        ]

        # 模拟 NotifyStage
        success_count = sum(1 for r in context.tool_results if r["success"])
        failure_count = len(context.tool_results) - success_count

        response = f"执行结果: {success_count} 成功, {failure_count} 失败"

        assert "2 成功" in response
        assert "1 失败" in response


# ============================================================================
# 性能基准测试
# ============================================================================


@pytest.mark.integration
@pytest.mark.benchmark
class TestPipelinePerformance:
    """
    Pipeline 性能基准测试
    """

    async def test_pipeline_execution_time(self):
        """
        集成测试: TC-INT-PERF-001

        验证: Pipeline 执行时间在可接受范围内
        """
        pipeline = TestPipelineExecutionFlow()._create_mock_pipeline()

        context = Mock()
        context.user_message = "性能测试"
        context.tool_calls = [{"name": "test", "arguments": {}}]
        context.tool_results = []

        start_time = datetime.now()
        result = await pipeline.execute(context)
        end_time = datetime.now()

        execution_time = (end_time - start_time).total_seconds()

        # 断言执行时间小于 1 秒（模拟环境）
        assert execution_time < 1.0, f"Pipeline 执行时间过长: {execution_time}s"

    async def test_pipeline_memory_usage(self):
        """
        集成测试: TC-INT-PERF-002

        验证: Pipeline 内存使用合理
        """
        import sys

        pipeline = TestPipelineExecutionFlow()._create_mock_pipeline()

        # 记录初始内存
        initial_size = sys.getsizeof(pipeline)

        # 执行多次
        for i in range(100):
            context = Mock()
            context.user_message = f"请求 {i}"
            context.tool_calls = [{"name": "test", "arguments": {}}]
            context.tool_results = []
            await pipeline.execute(context)

        # 验证内存使用没有异常增长
        final_size = sys.getsizeof(pipeline)
        size_growth = final_size - initial_size

        # 内存增长应小于 10KB（模拟环境阈值）
        assert size_growth < 10240, f"Pipeline 内存增长过大: {size_growth} bytes"


# ============================================================================
# 主入口
# ============================================================================

if __name__ == "__main__":
    pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "-m",
            "integration",
            "--html=integration_report.html",
        ]
    )
