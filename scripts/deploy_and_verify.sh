#!/usr/bin/env bash
set -e

echo "=== [Step 1] 检查 Docker 运行环境 ==="
docker info > /dev/null 2>&1 || { echo "⚠️ Notice: Docker 未在当前环境运行。如需拉起 Docker 集群，请先启动 Docker 服务。项目将维持本地轻量级记忆模式运行。"; exit 0; }

echo "=== [Step 2] 启动中间件基础设施 (Docker Compose) ==="
docker compose -f docker-compose.memory.yml up -d

echo "=== [Step 3] 等待数据库服务健康就绪 (Healthcheck Loop) ==="
MAX_RETRIES=30
RETRY=0

until docker compose -f docker-compose.memory.yml ps | grep -q "healthy" || [ $RETRY -eq $MAX_RETRIES ]; do
    echo "等待服务启动中... ($((RETRY+1))/$MAX_RETRIES)"
    sleep 3
    RETRY=$((RETRY+1))
done

echo "=== [Step 4] 运行数据库 Schema 初始化脚本 ==="
if [ -n "$CONDA_PREFIX" ] && [ -x "$CONDA_PREFIX/bin/python" ]; then
    PYTHON_CMD="$CONDA_PREFIX/bin/python"
elif [ -x "/home/xing/miniconda3/envs/bit_politeia/bin/python" ]; then
    PYTHON_CMD="/home/xing/miniconda3/envs/bit_politeia/bin/python"
else
    PYTHON_CMD="python3"
fi

$PYTHON_CMD scripts/init_memory_stores.py

echo "=== [Step 5] 部署健康检查冒烟测试 (Health Check Verification) ==="

# 1. 验证 Redis
REDIS_PASS="${REDIS_PASSWORD:-MemoryRedis2026}"
REDIS_PING=$(docker exec agent-memory-redis redis-cli -a "$REDIS_PASS" ping 2>/dev/null || echo "FAIL")
if [ "$REDIS_PING" == "PONG" ]; then
    echo "  [PASS] Redis L2 记忆服务连接成功"
else
    echo "  [WARN] Redis 未响应"
fi

# 2. 验证 Qdrant
QDRANT_STATUS=$(curl -s http://localhost:6333/healthz || echo "FAIL")
if [[ "$QDRANT_STATUS" == *"ok"* ]]; then
    echo "  [PASS] Qdrant L4 向量记忆服务正常"
else
    echo "  [WARN] Qdrant 响应异常"
fi

# 3. 验证 Neo4j
NEO4J_HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:7474 || echo "000")
if [ "$NEO4J_HTTP" == "200" ]; then
    echo "  [PASS] Neo4j L4 时序图谱服务正常"
else
    echo "  [WARN] Neo4j 响应异常"
fi

echo -e "\n========================================================"
echo "🚀 下下一代企业级 Agent 全栈记忆系统自动化部署与检测完毕！"
echo "========================================================"
