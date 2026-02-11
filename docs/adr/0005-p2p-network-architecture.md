# ADR-0005: P2P Network Architecture

## Status

Proposed

## Context

根据 `Bit_Politeia_architecture_supplement.md` 的描述，社区网络需要实现以下P2P设计：

1. **金字塔层级结构**：小组按层级组织，每个上级小组最多对应n个下级小组
2. **节点归属规则**：节点至少归属1个小组，最多2个直接相连的上下级小组
3. **节点标识**：节点ID为节点公钥，用于签名和通信
4. **新节点加入**：默认加入最底层小组
5. **节点调动**：上级小组可在必要时跨组调动节点
6. **信息查阅**：节点可随时查阅社区层级架构
7. **消息签名**：所有消息需节点私钥签名

关键问题：是否需要云端服务器辅助节点发现，还是完全分布式？

## Decision

采用**混合架构**：轻量级云端引导服务器 + P2P分布式网络

### Bootstrap Server (云端)

```
┌─────────────────────────────┐
│    Bootstrap Server         │
│  - 可加入小组列表           │
│  - 节点IP地址索引           │
│  - 仅用于初次发现           │
└─────────────────────────────┘
           │
           ▼
┌─────────────────────────────┐
│    P2P Network (分布式)     │
│  - 节点间直接通信           │
│  - 消息签名验证             │
│  - 层级架构分布式存储       │
└─────────────────────────────┘
```

### 技术选型

| 组件 | 技术 | 原因 |
|:---|:---|:---|
| P2P协议 | python-libp2p | 与现有技术栈一致 |
| 签名算法 | RSA-PSS (SHA256) | 已在 `crypto_service.py` 实现 |
| 引导服务 | FastAPI (独立部署) | 轻量级RESTful服务 |
| 架构存储 | 分布式 (DHT) | 去中心化，各节点维护本地视图 |

### 节点组归属约束

```python
# 节点可加入的小组规则
# 1. 必须归属至少1个小组
# 2. 最多2个直接相连的上下级小组
# 3. 新节点默认等级1，加入最底层小组

def can_join_group(node, target_group, existing_groups):
    if len(existing_groups) >= 2:
        return False
    if len(existing_groups) == 1:
        # 第二个小组必须与第一个直接相连(上或下级)
        existing = existing_groups[0]
        is_adjacent = (
            target_group.parent_id == existing.group_id or
            existing.parent_id == target_group.group_id
        )
        return is_adjacent
    return True
```

## Alternatives Considered

### 1. 纯云端架构
- **否决原因**：违背去中心化设计原则，单点故障风险

### 2. 纯DHT分布式发现
- **否决原因**：新节点冷启动困难，需要至少一个已知节点

### 3. 硬编码引导节点
- **否决原因**：不够灵活，运维成本高

## Consequences

*   **Positive**:
    - 新节点可快速发现并加入网络
    - 主体通信仍保持去中心化
    - 架构信息冗余存储，高可用
    
*   **Negative**:
    - 引导服务器需要维护和部署
    - 引导服务器可能成为攻击目标
    
*   **Risks**:
    - **引导服务器宕机**：已加入节点不受影响，新节点暂时无法加入
      - *缓解*：部署多个引导节点，或使用已知节点列表作为备份
    - **Sybil攻击**：恶意节点大量注册
      - *缓解*：可选身份验证，或基于声望的准入机制
