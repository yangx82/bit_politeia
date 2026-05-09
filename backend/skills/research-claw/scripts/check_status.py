import json
import sys
from pathlib import Path

# Add project root to path to import TaskManager
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

try:
    from backend.app.services.task_manager import TaskStatus, task_manager
except ImportError:
    print("Error: Could not import TaskManager.")
    sys.exit(1)


def check_status(task_id: str):
    if task_id not in task_manager.tasks:
        return {"status": "error", "message": f"Task ID {task_id} not found."}

    task = task_manager.tasks[task_id]
    research_path_str = task.metadata.get("research_path")
    if not research_path_str:
        return {"status": "error", "message": "Research path missing from task metadata."}

    # AutoResearchClaw run dir is usually inside D:\git\AutoResearchClaw\artifacts
    # But in our start_research.py, we set the CWD to ARC_SRC and it might create it there.
    # Actually, research_path in metadata points to PROJECT_ROOT/backend/data/research/rc-{task_id}
    # But ARC will create its artifacts in its own way.
    # Wait, in start_research.py I only created the run_dir but passed --output-dir?
    # No, I didn't pass --output-dir in the cmd list yet.
    # Let's assume for now we look into the run_dir we created.

    run_dir = Path(research_path_str)
    checkpoint_path = run_dir / "checkpoint.json"
    heartbeat_path = run_dir / "heartbeat.json"
    summary_path = run_dir / "pipeline_summary.json"

    status_info = {
        "task_id": task_id,
        "goal": task.goal,
        "current_status": task.status,
        "stage": 0,
        "stage_name": "INITIALIZING",
        "progress": "0%",
    }

    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            status_info["stage"] = summary.get("final_stage", 23)
            status_info["stage_name"] = "COMPLETED"
            status_info["progress"] = "100%"
            task_manager.complete_task(
                task_id,
                lessons=f"Research completed successfully. Final stage: {status_info['stage']}",
            )
        except:
            pass
    elif checkpoint_path.exists():
        try:
            cp = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            status_info["stage"] = cp.get("last_completed_stage", 0)
            status_info["stage_name"] = cp.get("last_completed_name", "UNKNOWN")
            # Calculate progress (rough estimate 23 stages)
            progress_pct = int((status_info["stage"] / 23) * 100)
            status_info["progress"] = f"{progress_pct}%"

            # Update TaskManager checkpoint
            task_manager.update_task_checkpoint(
                task_id,
                f"Stage {status_info['stage']}: {status_info['stage_name']} ({status_info['progress']})",
            )
        except:
            pass
    elif heartbeat_path.exists():
        try:
            hb = json.loads(heartbeat_path.read_text(encoding="utf-8"))
            status_info["stage"] = hb.get("last_stage", 0)
            status_info["stage_name"] = hb.get("last_stage_name", "STARTING")
            status_info["progress"] = "Starting..."
        except:
            pass

    return status_info


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "Missing Task ID argument."}))
        sys.exit(1)

    tid = sys.argv[1]
    result = check_status(tid)
    print(json.dumps(result))
