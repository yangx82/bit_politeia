description = "Git式P2P检出工具 - 切换工作区到指定分支或commit，更新HEAD指针和工作区文档"


def execute(args_str=""):
    """
    Git-style checkout for P2P document collaboration.

    Usage:
        git_p2p_checkout --repo=<path> <branch-name>     # Switch to branch
        git_p2p_checkout --repo=<path> <commit-hash>     # Detached HEAD state
        git_p2p_checkout --repo=<path> -b <new-branch>   # Create and switch
        git_p2p_checkout --repo=<path> --detach          # Force detached mode

    Returns:
        JSON with checkout result, previous and new HEAD state
    """
    import json
    from pathlib import Path

    args = args_str.strip().split() if args_str else []

    # Parse arguments
    repo_path = None
    create_branch = False
    force_detach = False
    target = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--repo="):
            repo_path = arg.split("=", 1)[1]
        elif arg == "--repo" and i + 1 < len(args):
            repo_path = args[i + 1]
            i += 1
        elif arg in ("-b", "--create-branch"):
            create_branch = True
        elif arg == "--detach":
            force_detach = True
        elif not arg.startswith("-") and not target:
            target = arg
        i += 1

    if not repo_path:
        repo_path = "."

    repo = Path(repo_path)
    git_dir = repo / ".git-p2p"
    refs_dir = git_dir / "refs" / "heads"
    head_file = git_dir / "HEAD"
    objects_dir = git_dir / "objects"

    result = {
        "success": False,
        "operation": "checkout",
        "repo": str(repo.absolute()),
        "previous_state": {},
        "new_state": {},
        "message": "",
    }

    # Validate repository
    if not git_dir.exists():
        result["message"] = f"Error: Not a git-p2p repository: {repo}"
        return json.dumps(result, indent=2)

    # Get current state
    prev_branch = None
    prev_commit = None
    if head_file.exists():
        head_content = head_file.read_text().strip()
        if head_content.startswith("ref: refs/heads/"):
            prev_branch = head_content[16:]
            branch_ref = refs_dir / prev_branch
            if branch_ref.exists():
                prev_commit = branch_ref.read_text().strip()
        else:
            prev_commit = head_content  # Detached HEAD

    result["previous_state"] = {
        "branch": prev_branch,
        "commit": prev_commit[:12] if prev_commit else None,
    }

    if not target:
        result["message"] = "Error: No target specified (branch name or commit hash)"
        return json.dumps(result, indent=2)

    # Determine if target is a branch or commit
    branch_ref = refs_dir / target
    is_branch = branch_ref.exists()

    # Handle -b flag (create and checkout)
    if create_branch:
        if is_branch:
            result["message"] = f"Error: Branch '{target}' already exists"
            return json.dumps(result, indent=2)
        # Use current HEAD as base
        base_commit = prev_commit
        if not base_commit:
            result["message"] = "Error: No HEAD to create branch from"
            return json.dumps(result, indent=2)
        branch_ref.write_text(base_commit)
        is_branch = True
        result["operation"] = "checkout-create"

    # Resolve target to commit hash
    target_commit = None
    target_branch = None

    if is_branch and not force_detach:
        # Checkout branch
        target_branch = target
        target_commit = branch_ref.read_text().strip()
        head_file.write_text(f"ref: refs/heads/{target_branch}")
    else:
        # Checkout commit (detached HEAD)
        # Try to resolve as full/partial commit hash
        if len(target) >= 4:
            # Direct lookup
            prefix = target[:2]
            suffix = target[2:]
            commit_file = objects_dir / prefix / suffix

            if commit_file.exists():
                target_commit = target
            else:
                # Search for matching prefix
                found = False
                for obj_dir in objects_dir.iterdir():
                    if obj_dir.is_dir():
                        for obj_file in obj_dir.iterdir():
                            full_hash = obj_dir.name + obj_file.name
                            if full_hash.startswith(target):
                                target_commit = full_hash
                                found = True
                                break
                    if found:
                        break

        if not target_commit:
            result["message"] = f"Error: Unknown revision '{target}'"
            return json.dumps(result, indent=2)

        head_file.write_text(target_commit)

    # Update new state
    result["new_state"] = {
        "branch": target_branch,
        "commit": target_commit[:12],
        "detached": (target_branch is None),
    }

    # Load commit info for display
    commit_prefix = target_commit[:2]
    commit_suffix = target_commit[2:]
    commit_file = objects_dir / commit_prefix / commit_suffix

    commit_info = {}
    if commit_file.exists():
        try:
            commit_data = json.loads(commit_file.read_text())
            commit_info = {
                "author": commit_data.get("author", "Unknown"),
                "timestamp": commit_data.get("timestamp"),
                "message": commit_data.get("message", "")[:50],
            }
        except:
            pass

    result["commit_info"] = commit_info
    result["success"] = True

    if target_branch:
        action_msg = f"Switched to branch '{target_branch}'"
    else:
        action_msg = f"Detached HEAD at {target_commit[:12]}"

    result["message"] = action_msg
    return json.dumps(result, indent=2)
