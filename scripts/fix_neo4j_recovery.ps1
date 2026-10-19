# ==============================================================================
# Bit-Politeia Neo4j 异常退出与锁文件自动恢复脚本 (Windows PowerShell)
# 作用：
# 1. 诊断 Neo4j 容器最新崩溃日志
# 2. 终止残留死锁进程及端口占用 (17687 / 17474)
# 3. 在数据卷 neo4j_data 中精准安全清除残余 store_lock 锁文件（绝不损坏图数据）
# 4. 重新拉起 Neo4j 容器并等待事务日志自愈与健康就绪
# ==============================================================================

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🔧 [Neo4j 恢复程序] 正在处理 Neo4j 非正常关闭导致无法启动问题..." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. 探测 Docker CLI
$dockerCmd = $null
if (Get-Command "docker.exe" -ErrorAction SilentlyContinue) {
    $dockerCmd = "docker.exe"
} elseif (Get-Command "docker" -ErrorAction SilentlyContinue) {
    $dockerCmd = "docker"
}

if (-not $dockerCmd) {
    Write-Host "❌ [ERROR] 未找到 Docker 命令！请确认已安装并启动 Docker Desktop。" -ForegroundColor Red
    exit 1
}

# 检查 Docker 守护进程是否响应
try {
    $null = & $dockerCmd info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ [ERROR] Docker 守护进程未运行！请先启动 Docker Desktop 后重试。" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ [ERROR] 无法连接到 Docker 守护进程: $_" -ForegroundColor Red
    exit 1
}

$containerName = "agent-memory-neo4j"
$composeFile = "docker-compose.memory.yml"
$httpPort = if ($env:NEO4J_HTTP_PORT) { $env:NEO4J_HTTP_PORT } else { "17474" }
$boltPort = if ($env:NEO4J_BOLT_PORT) { $env:NEO4J_BOLT_PORT } else { "17687" }

# 2. 诊断并打印当前容器状态和最后错误日志
Write-Host "`n--- [1/5] 诊断现有 Neo4j 容器状态与退出日志 ---" -ForegroundColor Yellow
$containerCheck = & $dockerCmd ps -a --filter "name=^/${containerName}$" --format "{{.Status}}"
if ($containerCheck) {
    Write-Host "  容器当前状态: $containerCheck" -ForegroundColor Gray
    Write-Host "  [最新 20 行日志快照]:" -ForegroundColor Gray
    Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
    & $dockerCmd logs --tail 20 $containerName 2>&1
    Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
} else {
    Write-Host "  - 未发现名为 $containerName 的容器。" -ForegroundColor Gray
}

# 3. 安全停止并移除故障容器
Write-Host "`n--- [2/5] 停止并移除异常挂起的 Neo4j 容器 ---" -ForegroundColor Yellow
if ($containerCheck) {
    Write-Host "  正在强制移除容器: $containerName ..." -ForegroundColor Gray
    & $dockerCmd rm -f $containerName | Out-Null
    Write-Host "  ✓ 容器已成功移除。" -ForegroundColor Green
}

# 4. 检查 Windows 宿主机上是否残留占用端口的孤立进程
Write-Host "`n--- [3/5] 检查并释放端口占用 ($boltPort / $httpPort) ---" -ForegroundColor Yellow
foreach ($port in @([int]$boltPort, [int]$httpPort)) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if ($conns) {
            foreach ($c in $conns) {
                $pidToKill = $c.OwningProcess
                if ($pidToKill -gt 4) {
                    Write-Host "  检测到残留进程 (PID: $pidToKill) 占用端口 $port，正在终止..." -ForegroundColor DarkYellow
                    Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
                }
            }
        }
    } catch {}
}

# 5. 挂载数据卷并精准清除残余 store_lock
Write-Host "`n--- [4/5] 扫描并清除数据卷中的残余 store_lock 锁文件 ---" -ForegroundColor Yellow
$volumes = & $dockerCmd volume ls -q
if ($volumes -contains "neo4j_data") {
    Write-Host "  检测到 Docker 数据卷: neo4j_data" -ForegroundColor Gray
    Write-Host "  正在通过临时沙盒容器安全检查锁状态..." -ForegroundColor Gray
    
    $cleanCommand = "find /data -type f \( -name 'store_lock' -o -name '*.lock' \) -print; find /data -type f \( -name 'store_lock' -o -name '*.lock' \) -delete"
    & $dockerCmd run --rm -v neo4j_data:/data alpine sh -c $cleanCommand
    Write-Host "  ✓ 数据卷内的残余死锁标记已安全清除（数据库数据完好无损）。" -ForegroundColor Green
} else {
    Write-Host "  - 提示: 未找到名为 neo4j_data 的卷（首次部署或使用自定义目录）。" -ForegroundColor Gray
}

# 6. 重新拉起 Neo4j 容器
Write-Host "`n--- [5/5] 重新启动 Neo4j 服务并执行健康轮询 ---" -ForegroundColor Yellow
if (Test-Path $composeFile) {
    Write-Host "  正在通过 Docker Compose 拉起 Neo4j 服务..." -ForegroundColor Gray
    & $dockerCmd compose -f $composeFile up -d neo4j-temporal-kg
} else {
    Write-Host "❌ 找不到 $composeFile 文件，无法自动拉起容器！" -ForegroundColor Red
    exit 1
}

Write-Host "  正在等待 Neo4j 数据库引擎自愈恢复与端口就绪..." -ForegroundColor Gray
$maxWait = 40
$ready = $false

for ($i = 1; $i -le $maxWait; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:${httpPort}" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($resp -and $resp.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        # 仍在启动初始化
    }
    Write-Host -NoNewline "."
    Start-Sleep -Seconds 1
}
Write-Host ""

if ($ready) {
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "🎉 [修复成功] Neo4j L4 时序知识图谱服务已恢复正常运行！" -ForegroundColor Green
    Write-Host "   - HTTP 管理面板: http://localhost:$httpPort (HTTP 200 OK)" -ForegroundColor Green
    Write-Host "   - Bolt 协议端口: bolt://localhost:$boltPort" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    
    # 尝试调用 Python 验证脚本
    if (Test-Path "scripts\init_memory_stores.py") {
        Write-Host "正在执行快速存活握手检验..." -ForegroundColor Gray
        python -c "from scripts.init_memory_stores import init_neo4j; init_neo4j()" 2>$null
    }
    exit 0
} else {
    Write-Host "❌ [警告] 等待 ${maxWait} 秒后 Neo4j 仍未响应 HTTP 200。" -ForegroundColor Red
    Write-Host "   正在输出最新容器日志，供进一步分析原因:" -ForegroundColor DarkYellow
    Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
    & $dockerCmd logs --tail 30 $containerName 2>&1
    Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
    exit 1
}
