# Self-Improvement Learnings Log

## LRN-20260409-002: 技能日志目录设计原则

**时间**: 2026-04-09  
**类型**: Best Practice  
**优先级**: Medium  

### 场景
安装 self-improving-agent 技能时，关于日志目录位置的决策。

### 发现
日志目录放置在技能目录内部（`.learnings/` 在 `self-improving-agent/` 内）具有明显优势：

1. **自包含性** - 技能的所有组件（代码、文档、日志）集中在一个位置
2. **独立性** - 多个技能的日志不会相互干扰或混淆
3. **可移植性** - 移动或备份技能时，学习记录一并携带
4. **权限管理** - 更容易对单个技能进行访问控制

### 应用范围
- 适用于所有需要本地状态管理的技能
- 为未来技能设计提供参考模式

### 关联错误
ERR-20260409-001 (虚假报告安装成功)

---
*自动记录：Aristocles Self-Improvement System*

---
[LRN-20260409-002] P2P 选举同步故障模式确认
TYPE: knowledge_gap
DATE: 2026-04-09
PRIORITY: HIGH (recurring pattern)

### 问题描述
P2P 网络中选举/提案数据广播机制失效，导致部分节点无法查询到已创建的选举记录。

### 症状特征
- 创建选举后，发起节点可见，其他节点返回 "Election not found"
- 投票提交失败（invalid/closed/validation failed）
- 计票结果不一致或部分节点无法参与

### 历史案例汇总
1. **2026-03-24**: Aarron 事件 - 投票 ID 同步失败
2. **2026-04-07**: Aristocles vs Bit Plato - 选举数据不同步
3. **2026-04-08**: 选举 ad33c26b - Aristocles 节点不可见

### 技术根因
`submit_proposal` Gossip 广播机制存在同步延迟或丢失，未实现确认/重试逻辑。

### 影响范围
- 治理流程阻塞（需人工干预）
- 选举结果可能无效（quorum 不足）
- 节点间信任度下降

### 建议解决方案
1. **短期**: 居民手动触发同步或代码修复
2. **中期**: 选举创建后增加确认机制（所有节点 ACK）
3. **长期**: 改进 P2P 广播协议，增加重试队列和超时重传

### 验证方法
```bash
# 所有节点执行以下命令应返回相同结果
get_election_status <election_id>
```

---
