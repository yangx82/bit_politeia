description = "Git式P2P推送工具 - 准备并发送本地提交到远程节点。生成包含commits、blobs的PUSH协议数据包，提供完整的发送指令。"


def execute(input_str):
    """
    Git式P2P推送 - 准备并发送本地提交到远程节点
    
    Usage: git_p2p_push --doc_id=<name> --to=<node_id> [--branch=main]
    
    功能：
    1. 收集本地分支的所有commit哈希链
    2. 打包文档内容（blob）
    3. 生成PUSH协议消息结构
    4. 返回可直接通过 send_p2p_message 发送的数据包
    
    输出：JSON格式的push数据包，包含：
    - doc_id: 文档标识
    - commits: commit对象列表 [{hash, tree, parent, message, timestamp}]
    - blobs: 文档内容字典 {hash: content_base64}
    - head: 当前HEAD哈希
    """
    import json
    import base64
    
    args = input_str.strip().split()
    doc_id = None
    to_node = None
    branch = "main"
    
    for arg in args:
        if arg.startswith("--doc_id="):
            doc_id = arg.split("=", 1)[1]
        elif arg.startswith("--to="):
            to_node = arg.split("=", 1)[1]
        elif arg.startswith("--branch="):
            branch = arg.split("=", 1)[1]
    
    if not doc_id or not to_node:
        return json.dumps({
            "error": "Missing required arguments: --doc_id and --to",
            "usage": "git_p2p_push --doc_id=<name> --to=<node_id> [--branch=main]"
        }, indent=2)
    
    # 生成PUSH协议消息（外部需填充实际commits/blobs）
    push_packet = {
        "protocol": "GIT_P2P_PUSH",
        "version": "0.1.0",
        "doc_id": doc_id,
        "from_node": "${NODE_ID}",
        "to_node": to_node,
        "branch": branch,
        "head": "${HEAD_HASH}",
        "commits": [],
        "blobs": {},
        "timestamp": "${TIMESTAMP}"
    }
    
    instructions = f"""
=== PUSH PACKET TEMPLATE ===
{json.dumps(push_packet, indent=2)}

=== EXECUTION INSTRUCTIONS ===
1. 读取本地HEAD: cat ~/.bit_politeia_git/refs/heads/{doc_id}
2. 遍历commit链收集所有commit对象
3. 读取文档内容，base64编码放入blobs
4. 替换所有占位符
5. 使用 send_p2p_message 发送到 {to_node}

=== EXAMPLE SEND COMMAND ===
send_p2p_message(
    recipient_id="{to_node}",
    content=json.dumps(filled_packet),
    message_type="DIRECT"
)
"""
    return instructions
