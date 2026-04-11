import os
import sys
import json
from pathlib import Path

# Add project root to path to import TaskManager
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

try:
    from backend.app.services.task_manager import task_manager
except ImportError:
    print("Error: Could not import TaskManager.")
    sys.exit(1)

def get_paper(task_id: str):
    if task_id not in task_manager.tasks:
        return {"status": "error", "message": f"Task ID {task_id} not found."}

    task = task_manager.tasks[task_id]
    research_path_str = task.metadata.get("research_path")
    if not research_path_str:
        return {"status": "error", "message": "Research path missing."}

    run_dir = Path(research_path_str)
    
    # AutoResearchClaw produces deliverables in its output directory
    # If using absolute paths, they'll be in run_dir/deliverables/
    # Let's search recursively for any PDF or Markdown in a deliverables folder
    
    deliverables_path = run_dir / "deliverables"
    if not deliverables_path.exists():
        # Maybe it's in a subfolder or we need to find it differently
        # For now, let's assume it's in the run_dir
        deliverables_path = run_dir
    
    pdfs = list(deliverables_path.glob("**/*.pdf"))
    markdowns = list(deliverables_path.glob("**/*.md"))
    
    results = {
        "status": "success",
        "task_id": task_id,
        "files": []
    }
    
    for f in pdfs + markdowns:
        results["files"].append({
            "name": f.name,
            "path": str(f),
            "type": "pdf" if f.suffix == ".pdf" else "markdown"
        })
    
    if not results["files"]:
        return {"status": "error", "message": "No paper artifacts found yet. Task may still be running."}
        
    return results

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "Missing Task ID argument."}))
        sys.exit(1)
    
    tid = sys.argv[1]
    result = get_paper(tid)
    print(json.dumps(result))
