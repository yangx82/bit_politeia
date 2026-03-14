# Bit Politeia 引导服务器节点删除指南

由于节点数据在数据库中具有持久性，如果某些节点意外断开、密钥遗失或陷入了“僵尸”状态，您可能需要从引导云服务器上手动将其剔除，以保持 P2P 网络的干练整洁。

## 前置条件：开启删除权限

为了防止 P2P 拓扑网络遭到网络层面的恶意大范围扫描和清空，**删除节点的 API 默认是完全关闭的**。您必须在引导服务器所在的主机（例如您的云服务器 Linux 环境下）显式开启该权限标志。

在启动引导服务器之前，请设置环境变量 `BOOTSTRAP_ALLOW_NODE_REMOVAL=true`：

```bash
# Linux / macOS 环境下启动
export BOOTSTRAP_ALLOW_NODE_REMOVAL=true
python backend/run_bootstrap.py

# Windows (PowerShell) 环境下启动
$env:BOOTSTRAP_ALLOW_NODE_REMOVAL="true"
python backend/run_bootstrap.py
```

## 第 1 步：获取需要删除的 节点 ID

所有网络节点都有一个与其公钥严格绑定的 64 位 Hex 字符串 ID。
如果在开发或测试期间您忘了保存该 ID，可以通过直接查询引导服务器的公共拓扑接口来查找目标节点：

```bash
# 如果服务器挂载在公网，替换为具体的公网IP或域名
curl -k -X GET "https://<你的引导服务器IP>:8000/topology"
```
在返回的复杂 JSON 结构中，找到 `"nodes"` 字段。浏览其内部列出的各节点名称（`name`），并复制您想要剔除的对应节点的 Key 字符串（即 Node ID）。

## 第 2 步：执行安全删除操作

确认引导服务器开启了权限后，您可以在**任何能 Ping 通这台引导服务器的机器上**，使用 `curl` 或是 Postman / APIFox 向其发送一条 `DELETE` 网络请求。

**命令格式语法：**
```bash
curl -k -X DELETE "https://<你的引导服务器IP>:8000/nodes/<要删除的节点ID>"
```

**实战演示示例：**
假设这台引导器就在本机，我们要删除节点 `eed6...1b79`：
```bash
curl -k -X DELETE "https://127.0.0.1:8000/nodes/eed68a9fca39fbcc6e2f31439a441ca7be73838168f0ca0daef00b80f1cf1b79"
```

## 第 3 步：确认结果并了解后续级联清理

如果 URL 与节点 ID 无误且权限已开，服务器将立刻返回操作成功提示：
```json
{"success": true, "message": "Node eed...b79 removed completely."}
```

此时，引导服务器不仅删除了该名字，还会**自动并在纳秒级别完成以下关联表和缓存的级联（Cascade）物理清空**：
1. **持久化擦除：** 将其从本地底层的 SQLite 数据库 (`data/p2p_bootstrap.db`) 内彻底 `DELETE`，拔除电源重启后它也无法重现。
2. **内存路由释放：** 从引导器的 RAM 存活路由树 (`self._peers`) 中释放该节点的记录。
3. **退群与重分布：** 从该节点参与的任何群组（`Groups`）白名单中拔除，群组的人数 (`member_count`) 同步自减，这可能导致部分“已满”的群组重新进入 `has_space=True` 可接纳新人的状态。
4. **清理僵尸审批：** 从群管理暂存区 (`Pending Joins`) 中撤回它发出的任何入群投递申请信。

**💡 存活端的影响：**
所有整个网络正处于联机状态中的其他 Agent 节点（无论前端是否连着它们），会在下一次心跳广播期（周期最大通常被设定在 60 秒）时向云服务器拉取全新一版拓扑。发现该节点缺失后，它们的 `network_manager` 也会当即把本地缓存里的这只“幽灵节点”清理掉。刷新这些合法节点挂载的 Web UI `Contacts` 页面，您也将确认该对象永久除名。

---

## 避坑与异常处理手册

*   **报错 HTTP 403 Forbidden**：
    *   **现象：** `{"detail": "Node removal is disabled by server policy"}`
    *   **诊断：** 云服务器当前的进程并未开启危险命令通行证。
    *   **解决：** Ctrl+C 暂停服务器，执行 `export BOOTSTRAP_ALLOW_NODE_REMOVAL=true` 后再跑一次 `run_bootstrap.py`。
*   **报错 HTTP 404 Not Found**：
    *   **现象：** `{"detail": "Node ID not found"}` 
    *   **诊断：** 你输入的这段 Hex 字符串不对，或者该节点其实在此之前已经被其它人（或其他原因）成功删除了（所以它的 ID 已经不存在于云端了，无需再删）。
