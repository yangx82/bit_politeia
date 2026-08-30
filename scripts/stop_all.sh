#!/usr/bin/env bash
# ==============================================================================
# Bit-Politeia Graceful Shutdown Script
# Safely stops Agent Backend and Docker Memory Infrastructure
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "=========================================="
echo "🛑 正在优雅关停 Bit-Politeia 全栈服务..."
echo "=========================================="

# 1. 关停智能体后端服务 (Backend API & P2P Node)
echo "[1/2] 正在停止智能体后端进程..."
if pgrep -f "uvicorn main:app" > /dev/null 2>&1; then
    pkill -TERM -f "uvicorn main:app" 2>/dev/null || true
    sleep 2
    pkill -9 -f "uvicorn main:app" 2>/dev/null || true
    echo "  ✓ 后端服务已安全停止。"
else
    echo "  - 未检测到运行中的后端进程。"
fi

if pgrep -f "supervisord" > /dev/null 2>&1; then
    pkill -TERM -f "supervisord" 2>/dev/null || true
    echo "  ✓ 进程管理器 (Supervisor) 已停止。"
fi

# 2. 优雅停止 Docker 记忆数据库集群 (Redis, MongoDB, Neo4j, Qdrant, MinIO)
echo "[2/2] 正在优雅停止数据库中间件集群 (保留数据)..."
DOCKER_CMD="docker"
if ! command -v docker &> /dev/null && command -v docker.exe &> /dev/null; then
    DOCKER_CMD="docker.exe"
fi

if $DOCKER_CMD info >/dev/null 2>&1; then
    if $DOCKER_CMD compose version >/dev/null 2>&1; then
        $DOCKER_CMD compose -f docker-compose.memory.yml stop
    else
        docker-compose -f docker-compose.memory.yml stop
    fi
    echo "  ✓ 数据库集群已安全关停 (数据卷已完整落盘保存)。"
else
    echo "  - Docker 未运行，跳过容器停止。"
fi

echo "=========================================="
echo "🎉 全栈服务已安全优雅退出！"
echo "=========================================="
