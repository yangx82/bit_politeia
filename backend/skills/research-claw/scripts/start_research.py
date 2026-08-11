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


# Stage number to name mapping
STAGE_MAP = {
    1: "TOPIC_INIT", 2: "PROBLEM_DECOMPOSE", 3: "SEARCH_STRATEGY",
    4: "LITERATURE_COLLECT", 5: "LITERATURE_SCREEN", 6: "KNOWLEDGE_EXTRACT",
    7: "SYNTHESIS", 8: "HYPOTHESIS_GEN", 9: "EXPERIMENT_DESIGN",
    10: "CODE_GENERATION", 11: "RESOURCE_PLANNING", 12: "EXPERIMENT_RUN",
    13: "ITERATIVE_REFINE", 14: "RESULT_ANALYSIS", 15: "RESEARCH_DECISION",
    16: "PAPER_OUTLINE", 17: "PAPER_DRAFT", 18: "PEER_REVIEW",
    19: "PAPER_REVISION", 20: "QUALITY_GATE", 21: "KNOWLEDGE_ARCHIVE",
    22: "EXPORT_PUBLISH", 23: "CITATION_VERIFY"
}


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
    
    # Resolve stage name if numeric
    stage_name = None
    if from_stage:
        if from_stage.isdigit():
            stage_name = STAGE_MAP.get(int(from_stage))
        else:
            stage_name = from_stage

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
    if stage_name:
        cmd.extend(["--from-stage", stage_name])

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ARC_SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUNBUFFERED"] = "1"

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
        
        # UI Workaround: Sometimes the frontend passes the CLI flags inside the topic field
        clean_topic = str(topic).strip().strip("'").strip('"')
        if clean_topic.startswith("--resume") or clean_topic.startswith("resume="):
            resume = True
            topic = "Unknown Topic"  # Reset topic so it doesn't fail the pipeline
            parts = clean_topic.split()
            for i, part in enumerate(parts):
                if part == "--resume" and i + 1 < len(parts) and not parts[i+1].startswith("-"):
                    if not task_id: task_id = parts[i+1]
                elif part in ["--stage", "--from-stage"] and i + 1 < len(parts):
                    from_stage = parts[i+1]
                    
        result = start_research(topic, task_id=task_id, resume=resume, from_stage=from_stage)
    except json.JSONDecodeError:
        # Fallback: Check if it looks like a CLI resume command (e.g. "--resume rc-xxxx --stage 11")
        clean_args = raw_args.strip().strip("'").strip('"')
        if clean_args.startswith("--resume") or clean_args.startswith("resume="):
            # If it starts with resume=, it might be weirdly formatted by an agent
            if clean_args.startswith("resume="):
                clean_args = "--" + clean_args
            parts = clean_args.split()
            resume_id = None
            stage_val = None
            
            # Simple manual parser for common flags
            for i, part in enumerate(parts):
                if part == "--resume" and i + 1 < len(parts) and not parts[i+1].startswith("-"):
                    resume_id = parts[i+1]
                elif part in ["--stage", "--from-stage"] and i + 1 < len(parts):
                    stage_val = parts[i+1]
            
            # If resume_id wasn't immediately after --resume, it might be the first non-flag
            if not resume_id:
                for part in parts[1:]:
                    if not part.startswith("-"):
                        resume_id = part
                        break

            result = start_research("Unknown Topic", task_id=resume_id, resume=True, from_stage=stage_val)
        else:
            # Fallback to simple topic string
            result = start_research(raw_args)
        
    print(json.dumps(result))
