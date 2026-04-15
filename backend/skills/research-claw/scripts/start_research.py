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


def start_research(topic: str):
    # 1. Setup paths
    research_root = PROJECT_ROOT / "backend" / "data" / "research"
    research_root.mkdir(parents=True, exist_ok=True)

    ARC_SRC = get_arc_src()
    if not ARC_SRC:
        return {
            "status": "error",
            "message": "AutoResearchClaw not found. Please run 'python scripts/setup_research_node.py' first.",
        }

    # 2. Create Task in bit_politeia
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
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ARC_SRC) + os.pathsep + env.get("PYTHONPATH", "")

    log_file = run_dir / "run.log"

    try:
        # Launch as background process
        if sys.platform == "win32":
            # DETACHED_PROCESS = 0x00000008
            process = subprocess.Popen(
                cmd,
                cwd=str(ARC_SRC),
                env=env,
                stdout=open(log_file, "w"),
                stderr=subprocess.STDOUT,
                creationflags=0x00000008,
            )
        else:
            process = subprocess.Popen(
                cmd,
                cwd=str(ARC_SRC),
                env=env,
                stdout=open(log_file, "w"),
                stderr=subprocess.STDOUT,
                preexec_fn=os.setpgrp,
            )

        # Update Task Metadata
        task.metadata["research_path"] = str(run_dir)
        task.metadata["pid"] = process.pid
        task_manager.save_tasks()

        return {
            "status": "success",
            "task_id": task_id,
            "message": f"Research task started for topic: '{topic}'. Check status with Task ID: {task_id}",
            "log_path": str(log_file),
        }
    except Exception as e:
        task_manager.fail_task(task_id, str(e))
        return {"status": "error", "message": f"Failed to start research: {e!s}"}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "Missing topic argument."}))
        sys.exit(1)

    topic_arg = sys.argv[1]
    result = start_research(topic_arg)
    print(json.dumps(result))
