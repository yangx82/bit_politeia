import json
import os
import subprocess
import sys
from datetime import datetime, UTC
import uuid
from pathlib import Path

# 0. Add project root to path BEFORE any backend imports
# This allows 'import backend...' to work reliably
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


def _load_env_file():
    """Load .env file from current directory, parent directories, or package directory.

    Returns True if a .env file was found and loaded, False otherwise.
    Note: This does NOT override existing environment variables.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False  # python-dotenv not installed

    # Try current working directory first
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
        return True

    # Try parent directories (up to 5 levels)
    cwd = Path.cwd()
    for _ in range(5):
        env_path = cwd / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
            return True
        cwd = cwd.parent
        if cwd == cwd.parent:  # Reached root
            break

    # Try the package's parent directory
    script_dir = Path(__file__).resolve().parent
    for _ in range(5):
        env_path = script_dir / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
            return True
        script_dir = script_dir.parent
        if script_dir == script_dir.parent:
            break

    return False

# 1. Backend Imports
try:
    from backend.app.services.task_manager import TaskStatus, task_manager
except ImportError as e:
    print(f"Error: Could not import TaskManager ({e}). Current sys.path: {sys.path}")
    sys.exit(1)


def get_arc_src():
    """Dynamically discover AutoResearchClaw installation path."""
    # 1. Check environment variable (set by setup_research_node.py)
    env_path = os.environ.get("RESEARCHCLAW_HOME")
    if env_path and os.path.exists(env_path):
        return Path(env_path)

    # 2. Check sibling directory in bit_politeia root
    sibling_path = PROJECT_ROOT.parent / "AutoResearchClaw"
    if sibling_path.exists():
        return sibling_path

    # 3. Last resort - check common git paths
    common_path = Path("D:/git/AutoResearchClaw")
    if common_path.exists():
        return common_path

    return None


def start_research(topic: str, task_id: str = None, resume: bool = False, from_stage: str = None):
    # 1. Setup paths
    research_root = PROJECT_ROOT / "backend" / "data" / "research"
    research_root.mkdir(parents=True, exist_ok=True)

    ARC_SRC = get_arc_src()
    if not ARC_SRC:
        return {
            "status": "error",
            "message": "AutoResearchClaw not found. Please run 'python scripts/setup_research_node.py' first.",
        }

    # 2. Resolve Task & Run Dir
    if task_id and resume:
        if task_id not in task_manager.tasks:
            # Try to see if it's a directory name like rc-xxxx
            found_id = None
            for tid, t in task_manager.tasks.items():
                if t.metadata.get("research_path") and Path(t.metadata["research_path"]).name == task_id:
                    found_id = tid
                    break
            if found_id:
                task_id = found_id
            else:
                return {"status": "error", "message": f"Task ID or run directory '{task_id}' not found for resumption."}
        
        task = task_manager.tasks[task_id]
        if not topic or topic == "Unknown Topic":
            # Recover topic from task goal
            topic = task.goal.replace("Autonomous Research: ", "")

        run_dir_str = task.metadata.get("research_path")
        if not run_dir_str or not os.path.exists(run_dir_str):
             return {"status": "error", "message": f"Research path for Task {task_id} does not exist on disk."}
        run_dir = Path(run_dir_str)
        print(f"Resuming research task {task_id} in {run_dir}")
    else:
        # Create NEW Task
        task = task_manager.create_task(
            goal=f"Autonomous Research: {topic}",
            priority=7,
            subtasks=[
                "Scoping & Literature Search",
                "Experiment Design & Execution",
                "Drafting & Peer Review",
                "Final Paper Generation",
            ],
        )
        task_id = task.id
        run_dir = research_root / f"rc-{task_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

    # 3. Prepare command
    # Try to use the venv python if it exists, otherwise system python
    venv_python = (
        ARC_SRC / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    )
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable

    config_path = ARC_SRC / "config.arc.yaml"
    cmd = [
        python_cmd,
        "-m",
        "researchclaw",
        "run",
        "--topic",
        topic,
        "--auto-approve",
        "--config",
        str(config_path),
        "--output",
        str(run_dir),
    ]

    if resume:
        cmd.append("--resume")
    if from_stage:
        cmd.extend(["--from-stage", from_stage])

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ARC_SRC) + os.pathsep + env.get("PYTHONPATH", "")

    log_file = run_dir / "run.log"

    try:
        # Launch as background process
        # We append to log if resuming
        log_mode = "a" if resume else "w"
        
        if sys.platform == "win32":
            process = subprocess.Popen(
                cmd,
                cwd=str(ARC_SRC),
                env=env,
                stdout=open(log_file, log_mode),
                stderr=subprocess.STDOUT,
                creationflags=0x00000008,
            )
        else:
            process = subprocess.Popen(
                cmd,
                cwd=str(ARC_SRC),
                env=env,
                stdout=open(log_file, log_mode),
                stderr=subprocess.STDOUT,
                preexec_fn=os.setpgrp,
            )

        # Update Task Metadata
        task.metadata["research_path"] = str(run_dir)
        task.metadata["pid"] = process.pid
        if resume:
            task.status = TaskStatus.RUNNING
        task_manager.save_tasks()

        mode_str = "Resumed" if resume else "Started"
        return {
            "status": "success",
            "task_id": task_id,
            "message": f"Research task {mode_str.lower()} for topic: '{topic}'. Check status with Task ID: {task_id}",
            "log_path": str(log_file),
            "resume": resume,
            "from_stage": from_stage
        }
    except Exception as e:
        if not resume:
            task_manager.fail_task(task_id, str(e))
        return {"status": "error", "message": f"Failed to { 'resume' if resume else 'start' } research: {e!s}"}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "Missing arguments."}))
        sys.exit(1)

    # Load .env file
    _load_env_file()

    raw_args = sys.argv[1]
    
    # Try to parse as JSON for advanced control
    try:
        args_obj = json.loads(raw_args)
        topic = args_obj.get("topic", "Unknown Topic")
        task_id = args_obj.get("task_id")
        resume = args_obj.get("resume", False)
        from_stage = args_obj.get("from_stage")
        
        result = start_research(topic, task_id=task_id, resume=resume, from_stage=from_stage)
    except json.JSONDecodeError:
        # Fallback: Check if it looks like a CLI resume command (e.g. "--resume rc-2026...")
        if raw_args.strip().startswith("--resume"):
            parts = raw_args.strip().split()
            resume_val = parts[1] if len(parts) > 1 else None
            # If resume_val is provided, treat it as task_id
            result = start_research("Unknown Topic", task_id=resume_val, resume=True)
        else:
            # Fallback to simple topic string
            result = start_research(raw_args)
        
    print(json.dumps(result))
