description = "初始化Bit-Politeia Git式文档协作仓库，创建目录结构和配置文件"


import json
from datetime import datetime

def execute(input_str):
    """
    初始化Bit-Politeia Git式文档协作仓库
    Usage: git_p2p_init --doc_id=<name>
    
    返回仓库配置信息，供后续手动创建或外部脚本执行
    """
    args = input_str.strip().split()
    doc_id = None
    
    for arg in args:
        if arg.startswith("--doc_id="):
            doc_id = arg.split("=", 1)[1]
    
    if not doc_id:
        return "Error: --doc_id required"
    
    # 生成配置JSON
    config = {
        "doc_id": doc_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "version": "0.1.0",
        "directories": [
            "objects/",
            "refs/heads/",
            "refs/remotes/",
            "docs/"
        ],
        "files_to_create": {
            f"refs/heads/{doc_id}": "",
            "config.json": {
                "doc_id": doc_id,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "version": "0.1.0"
            }
        }
    }
    
    base_path = "~/.bit_politeia_git"
    
    result = f"""✅ Repository configuration generated for '{doc_id}'

Base Path: {base_path}

Directory Structure:
  {base_path}/
  ├── objects/          # Commit object storage
  ├── refs/heads/       # Local branches
  ├── refs/remotes/     # Remote tracking branches
  └── docs/             # Working directory documents

Files to Create:
  1. {base_path}/refs/heads/{doc_id}  (empty file)
  2. {base_path}/config.json  (content below)

Config JSON Content:
{json.dumps(config["files_to_create"]["config.json"], indent=2)}

Next Steps:
  1. Run: mkdir -p ~/.bit_politeia_git/{{objects,refs/{{heads,remotes}},docs}}
  2. Place your document at: ~/.bit_politeia_git/docs/{doc_id}.md
  3. Use: git_p2p_commit --doc_id={doc_id} --message="Initial commit"

Configuration Object (for programmatic use):
{json.dumps(config, indent=2)}
"""
    return result
