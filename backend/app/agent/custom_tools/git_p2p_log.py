description = "显示提交历史，遍历commit链并格式化输出日志"


import json


def execute(input_str):
    """
    显示提交历史
    Usage: git_p2p_log --commits=<json_array> [--oneline]

    commits参数应为commit对象数组，每个对象包含hash和data字段
    """
    args = input_str.strip().split()
    commits_json = None
    oneline = False

    for arg in args:
        if arg.startswith("--commits="):
            commits_json = arg.split("=", 1)[1]
        elif arg == "--oneline":
            oneline = True

    if not commits_json:
        return "Error: --commits required (JSON array of commit objects)"

    try:
        # 解析commits数组
        commits = json.loads(commits_json)

        if not isinstance(commits, list) or len(commits) == 0:
            return "Error: commits must be a non-empty JSON array"

        # 构建parent映射以排序
        commit_map = {c.get("hash", ""): c for c in commits}

        # 找到HEAD（没有作为parent的commit）
        all_parents = set()
        for c in commits:
            parent = c.get("data", {}).get("parent")
            if parent:
                all_parents.add(parent)

        heads = [c for c in commits if c.get("hash") not in all_parents]
        if not heads:
            return "Error: No HEAD found (cycle detected or invalid structure)"

        current = heads[0]
        ordered_commits = []
        visited = set()

        # 遍历链
        while current and current.get("hash") not in visited:
            ordered_commits.append(current)
            visited.add(current.get("hash"))
            parent_hash = current.get("data", {}).get("parent")
            current = commit_map.get(parent_hash) if parent_hash else None

        # 格式化输出
        if oneline:
            lines = []
            for c in ordered_commits:
                h = c.get("hash", "unknown")[:7]
                msg = c.get("data", {}).get("message", "")[:50]
                lines.append(f"{h} {msg}")
            return "\n".join(lines)
        else:
            lines = []
            for c in ordered_commits:
                h = c.get("hash", "unknown")
                data = c.get("data", {})
                lines.append(f"commit {h}")
                lines.append(f"Tree:   {data.get('tree', 'N/A')}")
                lines.append(f"Date:   {data.get('timestamp', 'N/A')}")
                if data.get("parent"):
                    lines.append(f"Parent: {data['parent'][:7]}")
                lines.append("")
                lines.append(f"    {data.get('message', 'No message')}")
                lines.append("")
            return "\n".join(lines)

    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON - {e!s}"
    except Exception as e:
        return f"Error: {e!s}"
