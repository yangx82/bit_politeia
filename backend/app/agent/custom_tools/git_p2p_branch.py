description = "Git式P2P分支管理工具 - 创建、列出、删除分支引用，支持分支重命名和查看分支状态"


def execute(args_str=""):
    """
    Git-style branch management for P2P document collaboration.

    Usage:
        git_p2p_branch --repo=<path>                    # List all branches
        git_p2p_branch --repo=<path> <branch-name>      # Create new branch at HEAD
        git_p2p_branch --repo=<path> <branch-name> <commit>  # Create at specific commit
        git_p2p_branch --delete <branch-name>           # Delete branch
        git_p2p_branch --rename <old-name> <new-name>   # Rename branch

    Returns:
        JSON with operation result and branch status
    """
    import json
    from pathlib import Path

    args = args_str.strip().split() if args_str else []

    # Parse arguments
    repo_path = None
    delete_mode = False
    rename_mode = False
    branch_name = None
    target_commit = None
    old_name = None
    new_name = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--repo="):
            repo_path = arg.split("=", 1)[1]
        elif arg == "--repo" and i + 1 < len(args):
            repo_path = args[i + 1]
            i += 1
        elif arg in ("-d", "--delete"):
            delete_mode = True
        elif arg in ("-m", "--rename"):
            rename_mode = True
        elif not arg.startswith("-"):
            if delete_mode and not branch_name:
                branch_name = arg
            elif rename_mode:
                if not old_name:
                    old_name = arg
                elif not new_name:
                    new_name = arg
            elif not branch_name:
                branch_name = arg
            elif not target_commit:
                target_commit = arg
        i += 1

    # Default to current directory if no repo specified
    if not repo_path:
        repo_path = "."

    repo = Path(repo_path)
    git_dir = repo / ".git-p2p"
    refs_dir = git_dir / "refs" / "heads"
    head_file = git_dir / "HEAD"

    result = {
        "success": False,
        "operation": None,
        "repo": str(repo.absolute()),
        "branches": [],
        "current_branch": None,
        "message": "",
    }

    # Validate repository
    if not git_dir.exists():
        result["message"] = f"Error: Not a git-p2p repository: {repo}"
        return json.dumps(result, indent=2)

    # Ensure refs directory exists
    refs_dir.mkdir(parents=True, exist_ok=True)

    # Get current branch
    current_branch = None
    if head_file.exists():
        head_content = head_file.read_text().strip()
        if head_content.startswith("ref: refs/heads/"):
            current_branch = head_content[16:]
    result["current_branch"] = current_branch

    # List mode (no branch name provided, not delete/rename)
    if not branch_name and not old_name:
        result["operation"] = "list"
        if refs_dir.exists():
            for ref_file in sorted(refs_dir.iterdir()):
                if ref_file.is_file():
                    commit_hash = ref_file.read_text().strip()
                    branch_info = {
                        "name": ref_file.name,
                        "commit": commit_hash[:12] if len(commit_hash) > 12 else commit_hash,
                        "current": (ref_file.name == current_branch),
                    }
                    result["branches"].append(branch_info)
        result["success"] = True
        result["message"] = f"Found {len(result['branches'])} branch(es)"
        return json.dumps(result, indent=2)

    # Delete mode
    if delete_mode:
        result["operation"] = "delete"
        ref_file = refs_dir / branch_name
        if not ref_file.exists():
            result["message"] = f"Error: Branch '{branch_name}' not found"
            return json.dumps(result, indent=2)
        if branch_name == current_branch:
            result["message"] = f"Error: Cannot delete current branch '{branch_name}'"
            return json.dumps(result, indent=2)
        ref_file.unlink()
        result["success"] = True
        result["message"] = f"Deleted branch '{branch_name}'"
        return json.dumps(result, indent=2)

    # Rename mode
    if rename_mode:
        result["operation"] = "rename"
        old_ref = refs_dir / old_name
        new_ref = refs_dir / new_name
        if not old_ref.exists():
            result["message"] = f"Error: Branch '{old_name}' not found"
            return json.dumps(result, indent=2)
        if new_ref.exists():
            result["message"] = f"Error: Branch '{new_name}' already exists"
            return json.dumps(result, indent=2)
        commit_hash = old_ref.read_text().strip()
        new_ref.write_text(commit_hash)
        old_ref.unlink()
        # Update HEAD if renaming current branch
        if old_name == current_branch and head_file.exists():
            head_file.write_text(f"ref: refs/heads/{new_name}")
            result["current_branch"] = new_name
        result["success"] = True
        result["message"] = f"Renamed '{old_name}' -> '{new_name}'"
        return json.dumps(result, indent=2)

    # Create mode
    result["operation"] = "create"
    ref_file = refs_dir / branch_name
    if ref_file.exists():
        result["message"] = f"Error: Branch '{branch_name}' already exists"
        return json.dumps(result, indent=2)

    # Determine target commit
    if not target_commit:
        # Use HEAD commit
        if not current_branch:
            result["message"] = "Error: No HEAD to create branch from. Specify a commit."
            return json.dumps(result, indent=2)
        head_ref = refs_dir / current_branch
        if head_ref.exists():
            target_commit = head_ref.read_text().strip()
        else:
            result["message"] = "Error: Cannot determine HEAD commit"
            return json.dumps(result, indent=2)

    # Validate target commit exists
    objects_dir = git_dir / "objects"
    commit_prefix = target_commit[:2]
    commit_suffix = target_commit[2:]
    commit_file = objects_dir / commit_prefix / commit_suffix

    if not commit_file.exists():
        # Try full hash lookup
        found = False
        for obj_dir in objects_dir.iterdir():
            if obj_dir.is_dir():
                for obj_file in obj_dir.iterdir():
                    full_hash = obj_dir.name + obj_file.name
                    if full_hash.startswith(target_commit):
                        target_commit = full_hash
                        found = True
                        break
            if found:
                break
        if not found:
            result["message"] = f"Error: Commit '{target_commit}' not found"
            return json.dumps(result, indent=2)

    # Create branch reference
    ref_file.write_text(target_commit)
    result["success"] = True
    result["message"] = f"Created branch '{branch_name}' at {target_commit[:12]}"
    result["created_branch"] = {"name": branch_name, "commit": target_commit[:12]}
    return json.dumps(result, indent=2)
