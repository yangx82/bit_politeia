# Bit-Politeia 测试套件

## 概述

本测试套件旨在**防止历史 Bug 复发**，特别是 Pipeline 阶段顺序 Bug (P2P_MSG_STATUS_2026_03_11)。

## 快速开始

```bash
# 安装依赖
pip install -r requirements-dev.txt

# 运行所有测试
pytest

# 运行回归测试
pytest -m regression

# 运行关键测试（失败阻止部署）
pytest -m critical

# 运行特定 Bug 测试
pytest -k "RT-P2P-001"
```

## 测试结构

```
tests/
├── regression/          # 回归测试 - 防止 Bug 复发
│   └── test_p2p_message_status_bug.py
├── unit/               # 单元测试
│   └── agent/
│       └── test_pipeline_ordering.py
└── integration/        # 集成测试
    └── agent/
        └── test_pipeline_execution.py
```

## CI/CD 集成

- **GitHub Actions**: `.github/workflows/regression-tests.yml`
- **Pre-commit**: `.pre-commit-config.yaml`
- **配置**: `pyproject.toml`

## 测试标记

| 标记 | 说明 |
|:---|:---|
| `regression` | 回归测试 |
| `critical` | 关键测试（失败阻止部署）|
| `pipeline` | Pipeline 相关测试 |
| `p2p` | P2P 网络测试 |

## 关键测试用例

- **RT-P2P-001**: P2P 工具确认准确性
- **RT-P2P-002**: Pipeline 阶段顺序不可变性
- **TC-PIPELINE-001**: ExecuteStage 先于 NotifyStage
