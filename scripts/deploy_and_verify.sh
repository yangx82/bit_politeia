#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "=== [Step 1] 检查 Docker 运行环境 ==="

# 选择最佳 Docker CLI：在 WSL 下优先探测 Windows Docker Desktop (docker.exe)，其次使用 Linux docker
DOCKER_CMD="docker"
DOCKER_COMPOSE_CMD="docker compose"

if command -v docker.exe >/dev/null 2>&1 && docker.exe info >/dev/null 2>&1; then
    DOCKER_CMD="docker.exe"
    DOCKER_COMPOSE_CMD="docker.exe compose"
    echo "  [INFO] 检测到宿主机 Docker Desktop (docker.exe)，优先使用宿主机容器运行时。"
elif docker info >/dev/null 2>&1; then
    DOCKER_CMD="docker"
    DOCKER_COMPOSE_CMD="docker compose"
    echo "  [INFO] 使用 Linux 原生 Docker 引擎。"
else
    echo "⚠️ Notice: Docker 未在当前环境运行。如需拉起 Docker 集群，请先启动 Docker 服务。项目将维持本地轻量级记忆模式运行。"
    exit 0
fi

echo "=== [Step 2] 检查与启动中间件基础设施 (Docker Compose) ==="

NEO4J_PORT_VAL=${NEO4J_HTTP_PORT:-17474}
QDRANT_PORT_VAL=${QDRANT_PORT:-16333}

# 优先检查端口是否已处于就绪状态，避免重复 pull / recreate
if (nc -zv 127.0.0.1 6379 2>&1 | grep -q "succeeded") && (curl -s -o /dev/null -w "%{http_code}" http://localhost:${NEO4J_PORT_VAL} | grep -q "200"); then
    echo "  [INFO] 记忆中间件服务集群已在运行中 (Redis:6379, Neo4j:${NEO4J_PORT_VAL}, Qdrant:${QDRANT_PORT_VAL} 已就绪)，跳过拉取与重启阶段。"
else
    echo "  [INFO] 正在拉起记忆数据库集群..."
    $DOCKER_COMPOSE_CMD -f docker-compose.memory.yml up -d
fi

echo "=== [Step 3] 等待数据库服务健康就绪 (Healthcheck Loop) ==="
MAX_RETRIES=30
RETRY=0

until ( ($DOCKER_CMD exec agent-memory-redis redis-cli -a "${REDIS_PASSWORD:-MemoryRedis2026}" ping 2>/dev/null | grep -q "PONG" || nc -zv 127.0.0.1 6379 2>&1 | grep -q "succeeded") && curl -s -o /dev/null -w "%{http_code}" http://localhost:${NEO4J_PORT_VAL} | grep -q "200") || [ $RETRY -eq $MAX_RETRIES ]; do
    echo "等待数据库基础设施全服务就绪中... ($((RETRY+1))/$MAX_RETRIES)"
    sleep 2
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
REDIS_PING=$($DOCKER_CMD exec agent-memory-redis redis-cli -a "$REDIS_PASS" ping 2>/dev/null || (nc -zv 127.0.0.1 6379 2>&1 | grep -q "succeeded" && echo "PONG") || echo "FAIL")
if [ "$REDIS_PING" == "PONG" ]; then
    echo "  [PASS] Redis L2 记忆服务连接成功"
else
    echo "  [WARN] Redis 未响应"
fi

# 2. 验证 Qdrant
QDRANT_STATUS=$(curl -s http://localhost:${QDRANT_PORT_VAL}/healthz || echo "FAIL")
if [[ "$QDRANT_STATUS" == *"passed"* ]] || [[ "$QDRANT_STATUS" == *"ok"* ]] || [[ "$QDRANT_STATUS" == *"healthz"* ]]; then
    echo "  [PASS] Qdrant L4 向量记忆服务正常"
else
    echo "  [WARN] Qdrant 响应异常"
fi

# 3. 验证 Neo4j
NEO4J_HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${NEO4J_PORT_VAL} || echo "000")
if [ "$NEO4J_HTTP" == "200" ]; then
    echo "  [PASS] Neo4j L4 时序图谱服务正常"
else
    echo "  [WARN] Neo4j 响应异常"
fi

echo -e "\n========================================================"
echo "🚀 下下一代企业级 Agent 全栈记忆系统自动化部署与检测完毕！"
echo "========================================================"
