description = "Git式P2P拉取工具 - 请求并处理远程节点的提交。生成PULL请求消息并提供响应处理逻辑。"


def execute(input_str):
    """
    Git式P2P拉取 - 请求并处理远程节点的提交

    Usage: git_p2p_pull --doc_id=<name> --from=<node_id> [--branch=main]

    功能：
    1. 生成本地HEAD状态报告
    2. 创建PULL请求消息
    3. 提供处理远程响应的解析逻辑

    输出：包含请求模板和响应处理器代码
    """
    import json

    args = input_str.strip().split()
    doc_id = None
    from_node = None
    branch = "main"

    for arg in args:
        if arg.startswith("--doc_id="):
            doc_id = arg.split("=", 1)[1]
        elif arg.startswith("--from="):
            from_node = arg.split("=", 1)[1]
        elif arg.startswith("--branch="):
            branch = arg.split("=", 1)[1]

    if not doc_id or not from_node:
        return json.dumps(
            {
                "error": "Missing required arguments: --doc_id and --from",
                "usage": "git_p2p_pull --doc_id=<name> --from=<node_id> [--branch=main]",
            },
            indent=2,
        )

    # PULL请求模板
    pull_request = {
        "protocol": "GIT_P2P_PULL",
        "version": "0.1.0",
        "doc_id": doc_id,
        "from_node": "${NODE_ID}",
        "have": "${LOCAL_HEAD_OR_EMPTY}",
        "want": "${REMOTE_HEAD}",
        "branch": branch,
        "timestamp": "${TIMESTAMP}",
    }

    # 响应处理器（伪代码，供外部实现参考）
    response_handler = """
# 收到PUSH/PULL响应后的处理流程：
def handle_pull_response(response_json):
    data = json.loads(response_json)
    
    # 1. 验证协议版本
    if data.get("protocol") != "GIT_P2P_PUSH_RESPONSE":
        raise ValueError("Invalid protocol")
    
    # 2. 存储commits到 objects/
    for commit in data["commits"]:
        hash_prefix = commit["hash"][:2]
        hash_suffix = commit["hash"][2:]
        # mkdir -p ~/.bit_politeia_git/objects/{hash_prefix}
        # write commit JSON to ~/.bit_politeia_git/objects/{hash_prefix}/{hash_suffix}
    
    # 3. 存储blobs
    for blob_hash, content_b64 in data["blobs"].items():
        content = base64.b64decode(content_b64)
        # write to ~/.bit_politeia_git/objects/{blob_hash[:2]}/{blob_hash[2:]}
    
    # 4. 更新HEAD（快进合并）
    # echo {data["head"]} > ~/.bit_politeia_git/refs/heads/{data["doc_id"]}
    
    # 5. 更新工作区文档
    # decode latest blob to ~/.bit_politeia_git/docs/{data["doc_id"]}.md
    
    return f"Pulled {len(data['commits'])} commits, HEAD now at {data['head']}"
"""

    instructions = f"""
=== PULL REQUEST TEMPLATE ===
{json.dumps(pull_request, indent=2)}

=== RESPONSE HANDLER (Python Pseudocode) ===
{response_handler}

=== EXECUTION WORKFLOW ===
1. 读取本地HEAD（如有）: cat ~/.bit_politeia_git/refs/heads/{doc_id}
2. 填充PULL请求模板
3. 使用 send_p2p_message 发送到 {from_node}
4. 等待响应（异步）
5. 调用handle_pull_response处理响应数据

=== EXAMPLE SEND COMMAND ===
send_p2p_message(
    recipient_id="{from_node}",
    content=json.dumps(pull_request_filled),
    message_type="DIRECT"
)
"""
    return instructions
