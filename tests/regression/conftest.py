"""
回归测试配置
=============

为回归测试套件提供共享配置和 Fixture。

作者:      Bit Plato (Agent)
创建日期:  2026-03-22
"""

from datetime import datetime

import pytest

# ============================================================================
# 测试配置
# ============================================================================


def pytest_configure(config):
    """
    配置 pytest 标记
    """
    config.addinivalue_line("markers", "regression: 标记为回归测试，用于防止历史 Bug 复发")
    config.addinivalue_line("markers", "critical: 标记为关键测试，失败时阻止部署")
    config.addinivalue_line("markers", "property_test: 属性测试，使用随机输入验证")
    config.addinivalue_line("markers", "performance: 性能测试")


# ============================================================================
# 共享 Fixture
# ============================================================================


@pytest.fixture
def bug_metadata():
    """
    提供 Bug 元数据 Fixture

    用于测试报告中追溯 Bug 信息。
    """
    return {
        "P2P_MSG_STATUS_2026_03_11": {
            "id": "P2P_MSG_STATUS_2026_03_11",
            "date": datetime(2026, 3, 11),
            "severity": "CRITICAL",
            "description": "Pipeline Notify先于Execute导致虚假消息状态报告",
            "affected_tools": [
                "send_p2p_message",
                "send_file",
                "pay_resident",
                "cast_ballot",
            ],
            "prohibited_phrases": [
                "已发送",
                "已完成",
                "已提交",
                "已处理",
                "已成功",
                "Message sent",
                "File sent",
                "Payment completed",
                "Vote cast",
            ],
        }
    }


@pytest.fixture
def mock_agent_context():
    """
    提供模拟 Agent 上下文 Fixture
    """

    class MockContext:
        def __init__(self):
            self.user_message = ""
            self.tool_calls = []
            self.tool_results = []
            self.response = None
            self.stage_outputs = {}
            self.metadata = {}

    return MockContext


@pytest.fixture
def sample_tool_calls():
    """
    提供示例工具调用 Fixture
    """
    return {
        "send_p2p_message": {
            "name": "send_p2p_message",
            "arguments": {
                "recipient_id": "test_node_123",
                "content": "测试消息",
                "message_type": "DIRECT",
            },
        },
        "send_file": {
            "name": "send_file",
            "arguments": {
                "recipient_id": "test_node_123",
                "file_path": "/test/file.txt",
                "description": "测试文件",
            },
        },
        "pay_resident": {
            "name": "pay_resident",
            "arguments": {"payee_id": "test_node_123", "amount": 100.0, "details": "测试支付"},
        },
        "cast_ballot": {
            "name": "cast_ballot",
            "arguments": {"election_id": "test_election_123", "ballot_json": '[{"approve": true}]'},
        },
    }


@pytest.fixture
def sample_tool_results():
    """
    提供示例工具执行结果 Fixture
    """
    return {
        "success": {
            "tool": "send_p2p_message",
            "success": True,
            "result": {
                "message_id": "msg_abc123",
                "status": "delivered",
                "timestamp": "2026-03-22T21:30:00Z",
            },
            "error": None,
        },
        "failure": {
            "tool": "send_p2p_message",
            "success": False,
            "result": None,
            "error": "Network timeout: connection refused",
        },
        "partial": {
            "tool": "send_file",
            "success": True,
            "result": {"status": "partial", "bytes_sent": 1024, "bytes_total": 2048},
            "error": None,
        },
    }


# ============================================================================
# 钩子函数
# ============================================================================


def pytest_collection_modifyitems(config, items):
    """
    修改测试项集合

    自动为回归测试添加标记和排序。
    """
    for item in items:
        # 为回归测试添加标记
        if "regression" in item.nodeid:
            item.add_marker(pytest.mark.regression)

            # 关键回归测试
            if "critical" in item.name.lower() or "RT-P2P-001" in item.name:
                item.add_marker(pytest.mark.critical)


def pytest_runtest_setup(item):
    """
    每个测试运行前的设置
    """
    # 可以在这里添加测试前的环境检查
    pass


def pytest_runtest_teardown(item):
    """
    每个测试运行后的清理
    """
    # 可以在这里添加测试后的清理
    pass
