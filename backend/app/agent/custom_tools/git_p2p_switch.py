description = "Git式P2P简化切换工具 - 现代Git风格的branch切换，专注于分支操作，比checkout更直观安全"


def execute(args_str=""):
    """
    Git-style switch command for P2P document collaboration (modern alternative to checkout).
    
    Usage:
        git_p2p_switch --repo=<path> <branch-name>         # Switch to existing branch
        git_p2p_switch --repo=<path> -c <new-branch>       # Create and switch
        git_p2p_switch --repo=<path> -                     # Switch to previous branch
        git_p2p_switch --repo=<path> --detach <commit>     # Detached HEAD at commit
        git_p2p_switch --repo=<path> --orphan <new-branch> # Create orphan branch
        
    Returns:
        JSON with switch result and branch status
    """
    import json
    from pathlib import Path
    
    args = args_str.strip().split() if args_str else []
    
    # Parse arguments
    repo_path = None
    create_mode = False
    detach_mode = False
    orphan_mode = False
    target = None
    
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith('--repo='):
            repo_path = arg.split('=', 1)[1]
        elif arg == '--repo' and i + 1 < len(args):
            repo_path = args[i + 1]
            i += 1
        elif arg in ('-c', '--create'):
            create_mode = True
        elif arg == '--detach':
            detach_mode = True
        elif arg == '--orphan':
            orphan_mode = True
        elif arg == '-':
            target = '-'
        elif not arg.startswith('-') and not target:
            target = arg
        i += 1
    
    if not repo_path:
        repo_path = '.'
    
    repo = Path(repo_path)
    git_dir = repo / '.git-p2p'
    refs_dir = git_dir / 'refs' / 'heads'
    head_file = git_dir / 'HEAD'
    objects_dir = git_dir / 'objects'
    
    result = {
        "success": False,
        "operation": "switch",
        "repo": str(repo.absolute()),
        "previous_branch": None,
        "current_branch": None,
        "message": ""
    }
    
    # Validate repository
    if not git_dir.exists():
        result["message"] = f"Error: Not a git-p2p repository: {repo}"
        return json.dumps(result, indent=2)
    
    # Get current and previous branch info
    prev_branch = None
    current_commit = None
    
    if head_file.exists():
        head_content = head_file.read_text().strip()
        if head_content.startswith('ref: refs/heads/'):
            prev_branch = head_content[16:]
            branch_ref = refs_dir / prev_branch
            if branch_ref.exists():
                current_commit = branch_ref.read_text().strip()
        else:
            current_commit = head_content
    
    result["previous_branch"] = prev_branch
    
    # Handle switch to previous branch (-)
    if target == '-':
        # Read .git-p2p/PREV_BRANCH if exists
        prev_branch_file = git_dir / 'PREV_BRANCH'
        if prev_branch_file.exists():
            target = prev_branch_file.read_text().strip()
            create_mode = False  # Previous branch must exist
        else:
            result["message"] = "Error: No previous branch to switch to"
            return json.dumps(result, indent=2)
    
    if not target:
        result["message"] = "Error: No target specified"
        return json.dumps(result, indent=2)
    
    # Save current branch as previous before switching
    if prev_branch:
        prev_branch_file = git_dir / 'PREV_BRANCH'
        prev_branch_file.write_text(prev_branch)
    
    # Orphan branch mode
    if orphan_mode:
        orphan_ref = refs_dir / target
        if orphan_ref.exists():
            result["message"] = f"Error: Branch '{target}' already exists"
            return json.dumps(result, indent=2)
        # Orphan has no parent commit
        orphan_ref.write_text("0000000000000000000000000000000000000000")
        head_file.write_text(f"ref: refs/heads/{target}")
        result["success"] = True
        result["current_branch"] = target
        result["message"] = f"Created orphan branch '{target}'"
        result["operation"] = "switch-orphan"
        return json.dumps(result, indent=2)
    
    # Check if target is existing branch
    branch_ref = refs_dir / target
    branch_exists = branch_ref.exists()
    
    # Create mode
    if create_mode:
        if branch_exists:
            result["message"] = f"Error: Branch '{target}' already exists. Use without -c to switch."
            return json.dumps(result, indent=2)
        if not current_commit:
            result["message"] = "Error: Cannot create branch without a current commit"
            return json.dumps(result, indent=2)
        branch_ref.write_text(current_commit)
        head_file.write_text(f"ref: refs/heads/{target}")
        result["success"] = True
        result["current_branch"] = target
        result["message"] = f"Created and switched to branch '{target}'"
        result["operation"] = "switch-create"
        return json.dumps(result, indent=2)
    
    # Detach mode
    if detach_mode:
        # Target should be a commit hash
        commit_hash = None
        if len(target) >= 4:
            prefix = target[:2]
            suffix = target[2:]
            commit_file = objects_dir / prefix / suffix
            if commit_file.exists():
                commit_hash = target
            else:
                # Search
                for obj_dir in objects_dir.iterdir():
                    if obj_dir.is_dir():
                        for obj_file in obj_dir.iterdir():
                            full_hash = obj_dir.name + obj_file.name
                            if full_hash.startswith(target):
                                commit_hash = full_hash
                                break
        if not commit_hash:
            result["message"] = f"Error: Commit '{target}' not found"
            return json.dumps(result, indent=2)
        head_file.write_text(commit_hash)
        result["success"] = True
        result["current_branch"] = None
        result["detached_at"] = commit_hash[:12]
        result["message"] = f"Detached HEAD at {commit_hash[:12]}"
        result["operation"] = "switch-detach"
        return json.dumps(result, indent=2)
    
    # Normal switch to existing branch
    if not branch_exists:
        result["message"] = f"Error: Branch '{target}' not found. Use -c to create."
        return json.dumps(result, indent=2)
    
    # Perform switch
    head_file.write_text(f"ref: refs/heads/{target}")
    target_commit = branch_ref.read_text().strip()
    
    result["success"] = True
    result["current_branch"] = target
    result["commit"] = target_commit[:12] if target_commit != "0" * 40 else None
    result["message"] = f"Switched to branch '{target}'"
    
    return json.dumps(result, indent=2)
