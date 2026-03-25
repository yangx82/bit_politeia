import os
import json
import subprocess
import time
from datetime import datetime

# Paths are relative to the project root where the supervisor is expected to be run
WATCH_FILE = "backend/data/code_updates/pending.json"
LOG_FILE = "backend/data/logs/supervisor.log"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    print(msg)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"Failed to write to log file: {e}")

def run_command(cmd, timeout=60):
    try:
        # Run from project root
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)

def process_update(request):
    file_path = request.get("file_path")
    new_content = request.get("new_content")
    explanation = request.get("explanation", "No explanation provided")
    
    log(f"--- STARTING SELF-REPAIR PROCESS ---")
    log(f"Target: {file_path}")
    log(f"Reason: {explanation}")
    
    # 0. Ensure we are in a clean git state or at least backup
    # Check if file exists relative to root
    if not os.path.exists(file_path):
        log(f"ERROR: File {file_path} not found.")
        return False

    # 1. Create a restore point
    log("Creating restore point (git add)...")
    run_command(["git", "add", file_path])
    
    # 2. Apply the change
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        log("Code change applied to disk.")
    except Exception as e:
        log(f"ERROR: Failed to write change to {file_path}: {e}")
        return False

    # 3. Validation Phase
    log("Phase 1: Syntax & Compile Check...")
    code, out, err = run_command(["python3", "-m", "py_compile", file_path])
    if code != 0:
        log(f"CRITICAL: Syntax error in new code. Rolling back immediately.")
        log(f"Compiler output: {err}")
        run_command(["git", "checkout", file_path])
        return False

    log("Phase 2: Automated Smoke Tests...")
    # We run a specific fast test to ensure basic functionality
    code, out, err = run_command(["pytest", "backend/tests/test_status_default.py"])
    if code != 0:
        log(f"FAILED: Smoke tests failed. Rolling back.")
        log(f"Test output:\n{out}\n{err}")
        run_command(["git", "checkout", file_path])
        return False

    log("Phase 3: Deep Reliability Verification...")
    # Run a more comprehensive but isolated test
    code, out, err = run_command(["pytest", "backend/tests/test_reliability_unit_isolated.py"])
    if code != 0:
        log(f"FAILED: Reliability tests failed. Rolling back.")
        log(f"Test output:\n{out}\n{err}")
        run_command(["git", "checkout", file_path])
        return False

    # 4. Finalize
    log("SUCCESS: All validations passed. Committing change.")
    run_command(["git", "add", file_path])
    run_command(["git", "commit", "-m", f"Self-Repair: {explanation}\n\nTarget: {file_path}"])
    
    log(f"--- SELF-REPAIR COMPLETED SUCCESSFULLY ---")
    return True

def main():
    log("Code Supervisor v1.0 started. Waiting for instructions...")
    
    while True:
        if os.path.exists(WATCH_FILE):
            log(f"Detected pending update request at {WATCH_FILE}")
            try:
                with open(WATCH_FILE, "r", encoding="utf-8") as f:
                    request = json.load(f)
                
                # Immediate rename to prevent double-processing
                processing_file = WATCH_FILE + ".processing"
                os.rename(WATCH_FILE, processing_file)
                
                success = process_update(request)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                if success:
                    os.rename(processing_file, f"backend/data/code_updates/success_{timestamp}.json")
                else:
                    os.rename(processing_file, f"backend/data/code_updates/failed_{timestamp}.json")
                    
            except Exception as e:
                log(f"CRITICAL ERROR in supervisor loop: {e}")
                if os.path.exists(WATCH_FILE):
                    os.remove(WATCH_FILE)
        
        time.sleep(5)

if __name__ == "__main__":
    main()
