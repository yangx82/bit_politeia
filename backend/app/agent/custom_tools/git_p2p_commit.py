description = "创建新的commit对象，计算文档哈希，生成commit元数据，返回可存储的commit结构"


import hashlib
import json
from datetime import datetime


def execute(input_str):
    """
    创建新的commit对象
    Usage: git_p2p_commit --doc_id=<name> --content=<text> --message=<msg> [--parent=<hash>]

    计算内容哈希，生成commit对象，返回完整数据结构供存储
    """
    args = input_str.strip().split()
    doc_id = None
    content = None
    message = None
    parent = None

    for arg in args:
        if arg.startswith("--doc_id="):
            doc_id = arg.split("=", 1)[1]
        elif arg.startswith("--content="):
            content = arg.split("=", 1)[1]
        elif arg.startswith("--message="):
            message = arg.split("=", 1)[1].strip("\"'")
        elif arg.startswith("--parent="):
            parent = arg.split("=", 1)[1]

    if not doc_id or not message or content is None:
        return "Error: --doc_id, --content, and --message required"

    try:
        # 计算内容哈希（tree-like）
        content_bytes = content.encode("utf-8")
        content_hash = hashlib.sha256(content_bytes).hexdigest()[:12]

        # 构建commit对象
        commit_data = {
            "tree": content_hash,
            "parent": parent,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "doc_id": doc_id,
            "content_preview": content[:100] + "..." if len(content) > 100 else content,
        }

        # 序列化并计算commit哈希
        commit_json = json.dumps(commit_data, sort_keys=True)
        commit_hash = hashlib.sha256(commit_json.encode()).hexdigest()[:8]

        # 构建完整commit对象（包含实际内容）
        full_commit = {
            "hash": commit_hash,
            "data": commit_data,
            "content": content,  # 完整内容存储
        }

        parent_info = f", parent: {parent[:8]}..." if parent else " (initial commit)"

        result = f"""✅ Commit created successfully

Commit Hash: {commit_hash}
Message: {message}
Tree (Content Hash): {content_hash}{parent_info}
Timestamp: {commit_data["timestamp"]}

Storage Instructions:
  Path: ~/.bit_politeia_git/objects/{commit_hash[:2]}/{commit_hash[2:]}
  
Full Commit Object (JSON):
{json.dumps(full_commit, indent=2)}

Next Steps:
  1. Store this JSON to the path above
  2. Update HEAD: echo '{commit_hash}' > ~/.bit_politeia_git/refs/heads/{doc_id}
  3. To share: Send this commit object to remote nodes via P2P

Use: git_p2p_log --doc_id={doc_id} to view history
"""
        return result

    except Exception as e:
        return f"Error: {e!s}"
