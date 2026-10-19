#!/usr/bin/env bash
# ==============================================================================
# Bit-Politeia Neo4j 异常退出与锁文件自动恢复脚本 (Linux / WSL)
# 作用：
# 1. 诊断 Neo4j 容器最新崩溃日志
# 2. 终止残留死锁进程及端口占用 (17687 / 17474)
# 3. 在数据卷 neo4j_data 中精准安全清除残余 store_lock 锁文件（绝不损坏图数据）
# 4. 重新拉起 Neo4j 容器并等待事务日志自愈与健康就绪
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "=========================================================="
echo "🔧 [Neo4j 恢复程序] 正在处理 Neo4j 非正常关闭导致无法启动问题..."
echo "=========================================================="

# 1. 探测 Docker CLI
DOCKER_CMD="docker"
DOCKER_COMPOSE_CMD="docker compose"

if command -v docker.exe >/dev/null 2>&1 && docker.exe info >/dev/null 2>&1; then
    DOCKER_CMD="docker.exe"
    DOCKER_COMPOSE_CMD="docker.exe compose"
    echo "  [INFO] 检测到宿主机 Docker Desktop (docker.exe)，使用宿主机运行时。"
elif docker info >/dev/null 2>&1; then
    DOCKER_CMD="docker"
    DOCKER_COMPOSE_CMD="docker compose"
    echo "  [INFO] 使用 Linux 原生 Docker 引擎。"
else
    echo "❌ [ERROR] 未检测到正在运行的 Docker 服务！"
    echo "   请先启动 Docker Desktop 或运行 'sudo systemctl start docker' 后再重试。"
    exit 1
fi

CONTAINER_NAME="agent-memory-neo4j"
COMPOSE_FILE="docker-compose.memory.yml"
NEO4J_HTTP_PORT="${NEO4J_HTTP_PORT:-17474}"
NEO4J_BOLT_PORT="${NEO4J_BOLT_PORT:-17687}"

# 2. 诊断并打印当前容器状态和最后错误日志
echo ""
echo "--- [1/5] 诊断现有 Neo4j 容器状态与退出日志 ---"
if $DOCKER_CMD ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    STATUS=$($DOCKER_CMD inspect --format '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
    echo "  容器当前状态: $STATUS"
    echo "  [最新 20 行日志快照]:"
    echo "----------------------------------------------------------"
    $DOCKER_CMD logs --tail 20 "$CONTAINER_NAME" 2>&1 || true
    echo "----------------------------------------------------------"
else
    echo "  - 未发现名为 $CONTAINER_NAME 的容器。"
fi

# 3. 安全停止并移除故障容器
echo ""
echo "--- [2/5] 停止并移除异常挂起的 Neo4j 容器 ---"
if $DOCKER_CMD ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "  正在停止并清理容器: $CONTAINER_NAME ..."
    $DOCKER_CMD rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    echo "  ✓ 容器已成功移除。"
fi

# 4. 清理宿主机/WSL可能残留占用的端口
echo ""
echo "--- [3/5] 检查并释放端口占用 ($NEO4J_BOLT_PORT / $NEO4J_HTTP_PORT) ---"
if command -v fuser >/dev/null 2>&1; then
    fuser -k "${NEO4J_BOLT_PORT}/tcp" 2>/dev/null || true
    fuser -k "${NEO4J_HTTP_PORT}/tcp" 2>/dev/null || true
fi

# 5. 挂载数据卷并精准清除残余 store_lock
echo ""
echo "--- [4/5] 扫描并清除数据卷中的残余 store_lock 锁文件 ---"
# 检查 neo4j_data 数据卷是否存在
VOLUME_EXISTS=$($DOCKER_CMD volume ls -q | grep -w "neo4j_data" || true)

if [ -n "$VOLUME_EXISTS" ]; then
    echo "  检测到 Docker 数据卷: neo4j_data"
    echo "  正在通过临时沙盒容器安全检查锁状态..."
    
    $DOCKER_CMD run --rm -v neo4j_data:/data alpine sh -c '
        echo "  [Volume Inspection]"
        LOCKS=$(find /data -type f \( -name "store_lock" -o -name "*.lock" \) 2>/dev/null)
        if [ -n "$LOCKS" ]; then
            echo "  发现残余锁文件:"
            echo "$LOCKS" | sed "s/^/    - /"
            echo "  正在安全删除残余锁文件..."
            find /data -type f \( -name "store_lock" -o -name "*.lock" \) -delete
            echo "  ✓ 残余锁文件已清除完毕。"
        else
            echo "  ✓ 数据卷内未发现未释放的锁文件（或已被释放）。"
        fi
    '
else
    echo "  - 提示: 未找到名为 neo4j_data 的独立数据卷（首次部署或使用本地挂载）。"
fi

# 6. 重新拉起 Neo4j 容器
echo ""
echo "--- [5/5] 重新启动 Neo4j 服务并执行健康轮询 ---"
if [ -f "$COMPOSE_FILE" ]; then
    echo "  正在通过 Docker Compose 拉起 Neo4j 服务..."
    $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" up -d neo4j-temporal-kg
else
    echo "❌ 找不到 $COMPOSE_FILE 文件，无法自动拉起容器！"
    exit 1
fi

echo "  正在等待 Neo4j 数据库引擎自愈恢复与端口就绪..."
MAX_WAIT=40
READY=0

for i in $(seq 1 $MAX_WAIT); do
    # 优先检测 HTTP 端口是否返回 200
    HTTP_CODE=$(curl -s --noproxy '*' --connect-timeout 1 -m 2 -o /dev/null -w "%{http_code}" "http://127.0.0.1:${NEO4J_HTTP_PORT}" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        READY=1
        break
    fi
    printf "."
    sleep 1
done
echo ""

if [ $READY -eq 1 ]; then
    echo "=========================================================="
    echo "🎉 [修复成功] Neo4j L4 时序知识图谱服务已恢复正常运行！"
    echo "   - HTTP 管理端口: http://localhost:${NEO4J_HTTP_PORT} (HTTP 200 OK)"
    echo "   - Bolt 协议端口: bolt://localhost:${NEO4J_BOLT_PORT}"
    echo "=========================================================="
    
    # 运行数据库验证初始化
    if [ -f "scripts/init_memory_stores.py" ]; then
        echo "正在执行快速存活握手检验..."
        if [ -n "$CONDA_PREFIX" ] && [ -x "$CONDA_PREFIX/bin/python" ]; then
            "$CONDA_PREFIX/bin/python" -c "
from scripts.init_memory_stores import init_neo4j
init_neo4j()
" 2>/dev/null || true
        elif [ -x "/home/xing/miniconda3/envs/bit_politeia/bin/python" ]; then
            /home/xing/miniconda3/envs/bit_politeia/bin/python -c "
from scripts.init_memory_stores import init_neo4j
init_neo4j()
" 2>/dev/null || true
        fi
    fi
    exit 0
else
    echo "❌ [警告] 等待 ${MAX_WAIT} 秒后 Neo4j 仍未响应 (HTTP $HTTP_CODE)。"
    echo "   正在输出最新容器日志，供进一步分析原因:"
    echo "----------------------------------------------------------"
    $DOCKER_CMD logs --tail 30 "$CONTAINER_NAME" 2>&1 || true
    echo "----------------------------------------------------------"
    exit 1
fi
